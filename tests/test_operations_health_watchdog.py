from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from module.operations_v2 import OperationsRuntime


class FakeManager:
    def __init__(self):
        self.recording = {}
        self.reserved = {}
        self.processes = {}
        self.filenames = {}
        self.user_stopped = {}

    def get_status_recording(self, channel_id):
        return bool(self.recording.get(channel_id))

    def get_status_reserved(self, channel_id):
        return bool(self.reserved.get(channel_id))

    def get_tasks_process(self, channel_id):
        return self.processes.get(channel_id)

    def get_recording_filename(self, channel_id):
        return self.filenames.get(channel_id)

    def get_is_user_stopped(self, channel_id):
        return bool(self.user_stopped.get(channel_id))


class FakeRecorderClass:
    recording_filename = {}
    recording_start_time = {}


class FakeFsm:
    def __init__(self):
        self.states = {}
        self.started = []
        self.stopped = []

    def getState(self, channel_id):
        return self.states.get(channel_id, "STOPPED")

    async def userStart(self, channel_id, is_user_request=False):
        self.started.append((channel_id, is_user_request))

    async def userStop(self, channel_id):
        self.stopped.append((channel_id, "user"))

    async def stop(self, channel_id, reason="user"):
        self.stopped.append((channel_id, reason))


class FakeLar:
    def __init__(self, root: Path):
        self.CONFIG_PATH = str(root / "json" / "config.json")
        self.recorder_manager = FakeManager()
        self.RecorderManager = FakeRecorderClass
        self.queueBatchPattern = self._queue_pattern
        self.queueBatchLast = self._queue_last

    async def _queue_pattern(self, channel_id, source):
        return {"channel": channel_id, "source": source}

    async def _queue_last(self, channel_id):
        return {"channel": channel_id}

    def busyFilePaths(self, manager, channels):
        return []


class OperationsHealthWatchdogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.channel = {"id": "a", "name": "Alpha", "platform": "chzzk"}
        self.fsm = FakeFsm()
        self.fsm.states["a"] = "RECORDING"
        self.app = SimpleNamespace(state=SimpleNamespace(channels=[self.channel], config={}, fsm=self.fsm))
        self.lar = FakeLar(self.root)
        self.runtime = OperationsRuntime(self.app, self.lar)
        self.path = self.root / "recording.ts"
        self.path.write_bytes(b"x" * 1024)
        self.lar.recorder_manager.recording["a"] = True
        self.lar.recorder_manager.filenames["a"] = str(self.path)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_clean_process_exit_waits_for_recorder_cleanup(self):
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=0)
        self.runtime.samples["a"] = {
            "size": 1024,
            "mtime": 900.0,
            "sample_time": 990.0,
            "last_growth": 900.0,
            "proc_exit_seen_at": 970.0,
            "stall_checks": 0,
        }
        with patch("module.operations_health.time.time", return_value=1000.0), patch.object(
            self.runtime, "_restart_channel", new=AsyncMock()
        ) as restart:
            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)

        restart.assert_not_awaited()
        health = self.runtime.health["a"]
        self.assertEqual(health["state"], "checking")
        self.assertEqual(health["process_exit_code"], 0)
        self.assertIn("정상 종료", health["last_error"])

    async def test_failed_process_restarts_only_after_grace_and_records_reason(self):
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=7)
        self.runtime.settings["health"]["process_exit_grace_seconds"] = 20
        self.runtime.samples["a"] = {
            "size": 1024,
            "mtime": 900.0,
            "sample_time": 990.0,
            "last_growth": 900.0,
            "proc_exit_seen_at": 970.0,
            "stall_checks": 0,
        }
        with patch("module.operations_health.time.time", return_value=1000.0), patch.object(
            self.runtime, "_restart_channel", new=AsyncMock()
        ) as restart:
            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)

        restart.assert_awaited_once()
        args = restart.await_args.args
        self.assertEqual(args[:3], ("a", 1, "failed"))
        self.assertEqual(args[3]["process_exit_code"], 7)
        self.assertEqual(self.runtime.health["a"]["last_restart"]["reason"], "failed")
        audit = self.runtime.read_audit(10)
        scheduled = next(item for item in audit if item["action"] == "health_restart_scheduled")
        self.assertIn("reason=failed", scheduled["detail"])
        self.assertIn("exit=7", scheduled["detail"])

    async def test_fresh_mtime_prevents_false_stall_restart(self):
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=None)
        os.utime(self.path, (999.0, 999.0))
        self.runtime.settings["health"]["stall_seconds"] = 120
        self.runtime.settings["health"]["stall_confirmations"] = 2
        self.runtime.samples["a"] = {
            "size": 1024,
            "mtime": 800.0,
            "sample_time": 990.0,
            "last_growth": 800.0,
            "proc_exit_seen_at": 0,
            "stall_checks": 1,
        }
        with patch("module.operations_health.time.time", return_value=1000.0), patch.object(
            self.runtime, "_restart_channel", new=AsyncMock()
        ) as restart:
            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)

        restart.assert_not_awaited()
        self.assertEqual(self.runtime.health["a"]["state"], "recording")
        self.assertEqual(self.runtime.health["a"]["stall_checks"], 0)

    async def test_stall_requires_consecutive_confirmation_and_is_diagnostic(self):
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=None)
        os.utime(self.path, (800.0, 800.0))
        self.runtime.settings["health"]["stall_seconds"] = 120
        self.runtime.settings["health"]["stall_confirmations"] = 2
        self.runtime.samples["a"] = {
            "size": 1024,
            "mtime": 800.0,
            "sample_time": 990.0,
            "last_growth": 800.0,
            "proc_exit_seen_at": 0,
            "stall_checks": 1,
        }
        with patch("module.operations_health.time.time", return_value=1000.0), patch.object(
            self.runtime, "_restart_channel", new=AsyncMock()
        ) as restart:
            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)

        restart.assert_awaited_once()
        args = restart.await_args.args
        self.assertEqual(args[:3], ("a", 1, "stalled"))
        self.assertEqual(args[3]["stall_checks"], 2)
        self.assertEqual(self.runtime.health["a"]["last_restart"]["reason"], "stalled")

    async def test_pending_restart_is_not_scheduled_twice_or_counted_twice(self):
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=7)
        self.runtime.settings["health"]["process_exit_grace_seconds"] = 0
        self.runtime.settings["health"]["restart_cooldown_seconds"] = 0
        self.runtime.samples["a"] = {
            "size": 1024,
            "mtime": 900.0,
            "sample_time": 990.0,
            "last_growth": 900.0,
            "proc_exit_seen_at": 970.0,
            "stall_checks": 0,
        }
        release_restart = asyncio.Event()

        async def blocked_restart(*args, **kwargs):
            await release_restart.wait()

        with patch("module.operations_health.time.time", return_value=1000.0), patch.object(
            self.runtime, "_restart_channel", side_effect=blocked_restart
        ) as restart:
            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)
            self.assertEqual(restart.await_count, 1)
            self.assertEqual(self.runtime.health["a"]["restart_attempts"], 1)

            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)

            self.assertEqual(restart.await_count, 1)
            self.assertEqual(self.runtime.health["a"]["restart_attempts"], 1)
            release_restart.set()
            await asyncio.sleep(0)

    async def test_runtime_stop_cancels_pending_health_restart(self):
        started = asyncio.Event()

        async def pending_restart():
            started.set()
            await asyncio.sleep(60)

        task = asyncio.create_task(pending_restart())
        self.runtime._restart_tasks["a"] = task
        await started.wait()

        await self.runtime.stop()

        self.assertTrue(task.cancelled())
        self.assertEqual(self.runtime._restart_tasks, {})

    async def test_restart_revalidation_cancels_when_file_growth_resumes(self):
        proc = SimpleNamespace(returncode=None)
        self.lar.recorder_manager.processes["a"] = proc
        before = self.path.stat()
        diagnostic = {
            "file_size": before.st_size,
            "file_mtime": before.st_mtime,
        }
        self.path.write_bytes(b"x" * 2048)

        needed, reason = self.runtime._restart_still_needed("a", "stalled", diagnostic)

        self.assertFalse(needed)
        self.assertEqual(reason, "file size resumed")

    async def test_watching_too_long_can_trigger_missed_recording_recovery(self):
        self.lar.recorder_manager.recording["a"] = False
        self.lar.recorder_manager.reserved["a"] = True
        self.fsm.states["a"] = "WATCHING"
        self.runtime.settings["health"]["missed_recording_seconds"] = 60
        self.runtime.samples["a"] = {
            "size": 0,
            "mtime": 0.0,
            "sample_time": 990.0,
            "last_growth": 990.0,
            "proc_exit_seen_at": 0,
            "stall_checks": 0,
            "watching_since": 900.0,
        }
        with patch("module.operations_health.time.time", return_value=1000.0), patch.object(
            self.runtime, "_restart_channel", new=AsyncMock()
        ) as restart, patch.object(self.runtime, "_notify", new=AsyncMock()) as notify:
            await self.runtime._sample_channel(self.channel)
            await asyncio.sleep(0)

        restart.assert_awaited_once()
        self.assertEqual(restart.await_args.args[:3], ("a", 1, "missed"))
        notify.assert_awaited_once()
        self.assertEqual(notify.await_args.args[0], "recording.missed")

    async def test_restart_revalidation_respects_user_stop(self):
        self.lar.recorder_manager.user_stopped["a"] = True
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=7)

        needed, reason = self.runtime._restart_still_needed("a", "failed", {"file_size": 1024})

        self.assertFalse(needed)
        self.assertEqual(reason, "user stop requested")

    async def test_restart_revalidation_respects_recording_disabled(self):
        self.channel["record_enabled"] = False
        self.lar.recorder_manager.processes["a"] = SimpleNamespace(returncode=7)

        needed, reason = self.runtime._restart_still_needed("a", "failed", {"file_size": 1024})

        self.assertFalse(needed)
        self.assertEqual(reason, "recording disabled")


if __name__ == "__main__":
    unittest.main()
