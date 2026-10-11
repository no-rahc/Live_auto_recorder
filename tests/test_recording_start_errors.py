"""Regression coverage for recording-start errors from core through the UI."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
import httpx

import live_auto_recorder as core
from lar_app.routers.recording import install_recording_routes
from module.channel_fsm import ChannelFsm
from module.data_manager import RecorderManager


ROOT = Path(__file__).resolve().parents[1]
CHANNEL = "test-channel"


class RecordingStartErrorsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state_patch = patch.multiple(
            RecorderManager,
            status_recording={}, status_reserved={}, tasks_process={},
            recording_start_time={}, recording_filename={}, is_user_stopped=set(),
            guard_starting=set(), _channels_cache=[], _channels_ref=None,
        )
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.sleep = self.enterContext(patch.object(core.asyncio, "sleep", new=AsyncMock()))
        self.log = self.enterContext(patch.object(core.logger, "exception"))
        self.app = FastAPI()
        self.app.state.channels = [{"id": CHANNEL, "record_enabled": True}]
        self.app.state.channels_lock = asyncio.Lock()
        self.app.state.fsm = SimpleNamespace(
            userStart=AsyncMock(), getState=Mock(return_value="STOPPED"),
        )
        RecorderManager.setChannels(self.app.state.channels)
        self.manager = RecorderManager()
        install_recording_routes(self.app, core)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_unknown_channel_is_404_without_polling_or_fsm_start(self):
        response = await self.client.post("/api/start_recording/missing", json={})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {
            "status": "error", "code": "channel_not_found", "message": "unknown channel",
        })
        self.app.state.fsm.userStart.assert_not_awaited()
        self.app.state.fsm.getState.assert_not_called()
        self.sleep.assert_not_awaited()
        self.assertEqual(RecorderManager.status_reserved, {})

    async def test_fsm_failure_is_500_with_message_and_no_false_reservation(self):
        self.app.state.fsm.userStart.side_effect = RuntimeError("start rejected")
        response = await self.client.post(
            f"/api/start_recording/{CHANNEL}", json={"is_user_request": True},
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {
            "status": "error", "code": "start_failed", "message": "start rejected",
        })
        self.app.state.fsm.userStart.assert_awaited_once_with(CHANNEL, is_user_request=True)
        self.app.state.fsm.getState.assert_not_called()
        self.sleep.assert_not_awaited()
        self.assertFalse(self.manager.get_status_reserved(CHANNEL))

    async def test_core_returns_typed_failure_and_http_status(self):
        self.app.state.fsm.userStart.side_effect = RuntimeError("start rejected")
        result = await core.startRecordingForChannel(self.app, CHANNEL)
        self.assertEqual(result, {
            "status": "error", "code": "start_failed", "message": "start rejected",
            "status_code": 500,
        })

    async def test_blank_failure_message_has_a_useful_fallback(self):
        self.app.state.fsm.userStart.side_effect = RuntimeError()
        result = await core.startRecordingForChannel(self.app, CHANNEL)
        self.assertEqual(result["status_code"], 500)
        self.assertTrue(result["message"])

    async def test_cancellation_is_not_converted_to_start_failure(self):
        self.app.state.fsm.userStart.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await core.startRecordingForChannel(self.app, CHANNEL)
        self.log.assert_not_called()

    async def test_accepted_watching_request_preserves_success_contract(self):
        async def start(channel_id, **kwargs):
            self.manager.set_status_reserved(channel_id, True)

        self.app.state.fsm.userStart.side_effect = start
        self.app.state.fsm.getState.return_value = "WATCHING"
        response = await self.client.post(f"/api/start_recording/{CHANNEL}", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "success", "message": "시작 요청을 접수했습니다.", "state": "예약녹화 중",
        })

    async def test_repeated_start_preserves_live_process_and_metadata(self):
        # Use the real FSM to cover its idempotency guard, including a process
        # whose recording flag has not yet caught up.
        for recording in (False, True):
            with self.subTest(recording=recording):
                self.app.state.fsm = ChannelFsm()
                self.app.state.fsm._spawnWatch = Mock()
                process = SimpleNamespace(returncode=None)
                self.manager.set_tasks_process(CHANNEL, process)
                self.manager.set_status_recording(CHANNEL, recording)
                self.manager.recording_set_filename(CHANNEL, "live.ts")
                self.manager.recording_set_start_time(CHANNEL, 123.0)
                response = await self.client.post(
                    f"/api/start_recording/{CHANNEL}", json={"is_user_request": True},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["state"], "녹화 중")
                self.assertIs(self.manager.get_tasks_process(CHANNEL), process)
                self.assertEqual(self.manager.get_recording_filename(CHANNEL), "live.ts")
                self.assertEqual(RecorderManager.recording_start_time[CHANNEL], 123.0)
                self.app.state.fsm._spawnWatch.assert_not_called()

    async def test_inactive_start_still_clears_stale_metadata(self):
        self.manager.set_tasks_process(CHANNEL, SimpleNamespace(returncode=0))
        self.manager.recording_set_filename(CHANNEL, "old.ts")
        self.manager.recording_set_start_time(CHANNEL, 123.0)
        result = await core.startRecordingForChannel(self.app, CHANNEL)
        self.assertEqual(result, {"status": "success", "state": "대기 중", "filename": ""})
        self.assertIsNone(self.manager.get_tasks_process(CHANNEL))
        self.assertNotIn(CHANNEL, RecorderManager.recording_start_time)

    async def test_legacy_core_error_is_not_returned_as_success(self):
        with patch.object(core, "startRecordingForChannel", new=AsyncMock(return_value={
            "status": "error", "message": "legacy failure",
        })):
            response = await self.client.post(f"/api/start_recording/{CHANNEL}", json={})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["message"], "legacy failure")
        self.sleep.assert_not_awaited()


@unittest.skipUnless(shutil.which("node"), "Node.js is required for UI regression coverage")
class RecordingStartUiTest(unittest.TestCase):
    def test_error_success_network_and_repeat_click_feedback(self):
        # Execute the existing UI functions with a small DOM/fetch harness.
        # Loading the entire legacy dashboard would also start unrelated timers.
        app_source = (ROOT / "templates/static/js/app.js").read_text(encoding="utf-8")
        start_source = app_source.split("async function startRecording(channelId) {", 1)[1]
        start_source = "async function startRecording(channelId) {" + start_source.split(
            "// 개별 채널 녹화 중지", 1,
        )[0]
        console_source = (ROOT / "templates/static/js/console.js").read_text(encoding="utf-8")
        feedback_source = console_source.split("  function installFetchFeedback() {", 1)[1]
        feedback_source = "function installFetchFeedback() {" + feedback_source.split(
            "  function confirmDialog()", 1,
        )[0]
        script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const toasts = [], alerts = [], updates = [];
let fetchCount = 0;
let pendingResponse;
const context = {
  console: {error() {}},
  window: {LiveAutoRecorderUI: {toast: (message, tone) => toasts.push({message, tone})}},
  document: {querySelector: () => null},
  alert: message => alerts.push(message),
  updateChannelStatusWithPriority: (...args) => updates.push(args),
  checkStatus: async () => {}, cssEsc: value => value,
  Request,
  nativeFetch: async () => { fetchCount++; return await pendingResponse; },
  toast: (message, tone) => toasts.push({message, tone}),
  feedbackMessage: () => 'generic success',
};
vm.createContext(context);
vm.runInContext('let isStartingRecordings = false;\n' + START_SOURCE + '\n' + FEEDBACK_SOURCE, context);
context.installFetchFeedback();
context.fetch = context.window.fetch;
function response(ok, data) {
  return {ok, status: ok ? 200 : 500, json: async () => data};
}
function reset() { toasts.length = 0; alerts.length = 0; updates.length = 0; }
(async () => {
  for (const ok of [false, true]) {
    reset();
    pendingResponse = response(ok, {status: 'error', code: 'start_failed', message: 'start rejected'});
    await context.startRecording('test-channel');
    assert.deepEqual(toasts, [{message: 'start rejected', tone: 'error'}]);
    assert.equal(updates.length, 0);
  }
  reset();
  pendingResponse = response(true, {status: 'success', state: '예약녹화 중', message: 'accepted'});
  await context.startRecording('test-channel');
  assert.deepEqual(toasts, [{message: 'accepted', tone: 'success'}]);
  assert.equal(updates.length, 1);
  assert.equal(updates[0][1], '예약녹화 중');

  reset();
  pendingResponse = Promise.reject(new Error('connection lost'));
  await context.startRecording('test-channel');
  assert.deepEqual(toasts, [{message: 'connection lost', tone: 'error'}]);

  reset();
  pendingResponse = {ok: false, status: 500, json: async () => {throw new Error('invalid JSON');}};
  await context.startRecording('test-channel');
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].tone, 'error');
  assert.ok(toasts[0].message);

  reset();
  let resolve;
  pendingResponse = new Promise(done => { resolve = done; });
  const before = fetchCount;
  const first = context.startRecording('test-channel');
  await context.startRecording('test-channel');
  assert.equal(fetchCount - before, 1);
  resolve(response(true, {status: 'success', state: '녹화 중'}));
  await first;
  assert.equal(toasts.length, 1);

  reset();
  context.window.LiveAutoRecorderUI = undefined;
  pendingResponse = response(false, {status: 'error', message: 'fallback error'});
  await context.startRecording('test-channel');
  assert.deepEqual(alerts, ['fallback error']);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
        script = "const START_SOURCE = " + json.dumps(start_source) + ";\n" + (
            "const FEEDBACK_SOURCE = " + json.dumps(feedback_source) + ";\n"
        ) + script
        result = subprocess.run(
            [shutil.which("node"), "-e", script], text=True, capture_output=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
