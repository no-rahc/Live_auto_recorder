"""Channel intent, command replay and restart admission regressions."""
from __future__ import annotations

import asyncio
from pathlib import Path
import os
import contextlib
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from module.channel_fsm import ChannelFsm
from module.data_manager import RecorderManager
from module.recording_attempt import RecorderAttemptOutcome
from module.recording_session import SessionOutcome
from module.v2_channels import ChannelControlService, ChannelControlError, allow_capture, provider_broadcast_identity
from module.v2_repository import V2Repository, Conflict


class ChannelControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "v2.sqlite3"
        self.root = Path(temp.name)
        self.repo = V2Repository(self.db)
        self.repo.initialize()
        self.enterContext(patch.multiple(
            RecorderManager, status_recording={}, status_reserved={}, tasks_process={},
            recording_start_time={}, recording_filename={}, is_user_stopped=set(),
            guard_starting=set(), _channels_cache=[], _channels_ref=None,
        ))
        self.channels = [{"id": "channel", "name": "Test", "platform": "chzzk", "record_enabled": True}]
        RecorderManager.setChannels(self.channels)
        self.fsm = ChannelFsm()
        self.fsm._spawnWatch = Mock()
        self.fsm._recordStopReason = Mock()
        self.service = ChannelControlService(self.repo, self.fsm)
        self.enterContext(patch("module.v2_runtime.capture_storage_report", return_value={"ok": True}))
        self.process_registration = self.enterContext(patch("module.v2_runtime.record_capture_process", Mock()))
        await self.service.initialize(self.channels)

    def live(self, live_id="first", title="Title"):
        return {"status": "OPEN", "liveId": live_id, "liveTitle": title}

    def admit(self, metadata=None, *, live=True, service=None):
        controller = service or self.service
        with controller.session_context("channel"):
            return allow_capture(self.channels[0], metadata or self.live(), is_live=live)

    async def test_pause_persists_without_stopping_current_broadcast(self):
        self.assertTrue(self.admit())
        self.fsm._stopAllWorkers = AsyncMock()
        latest = self.service.get_channel("channel")
        result = await self.service.patch_mode("channel", "paused", latest["revision"])
        self.assertEqual(result["desired_mode"], "paused")
        self.fsm._stopAllWorkers.assert_not_awaited()
        self.assertTrue(self.service.session_finished("channel", SessionOutcome.RETRYABLE_ERROR))
        self.assertTrue(self.admit())
        self.assertFalse(self.admit(self.live("next")))
        self.assertFalse(self.service.should_watch("channel"))
        self.assertEqual(self.repo.get_channel("channel")["desired_mode"], "paused")

    async def test_revision_conflict_preserves_intent(self):
        revision = self.service.get_channel("channel")["revision"]
        await self.service.patch_mode("channel", "paused", revision)
        with self.assertRaises(Conflict):
            await self.service.patch_mode("channel", "auto", revision)
        self.assertEqual(self.repo.get_channel("channel")["desired_mode"], "paused")

    async def test_start_once_preserves_paused_and_stops_at_broadcast_boundary(self):
        await self.service.patch_mode("channel", "paused", self.service.get_channel("channel")["revision"])
        command = await self.service.command("channel", "start_once", "once-key")
        self.assertEqual(command["state"], "running")
        self.assertEqual(self.repo.get_channel("channel")["desired_mode"], "paused")
        self.assertTrue(self.admit())
        self.assertTrue(self.service.session_finished("channel", SessionOutcome.COMPLETED))
        self.assertTrue(self.admit(self.live(title="Changed title")))
        self.assertFalse(self.admit(self.live("next")))
        self.assertEqual(self.service.get_command(command["id"])["state"], "succeeded")
        self.assertFalse(self.service.should_watch("channel"))

    async def test_command_replay_never_double_starts_and_changed_body_conflicts(self):
        self.fsm.userStart = AsyncMock()
        first = await self.service.command("channel", "start_once", "replay-key")
        second = await self.service.command("channel", "start_once", "replay-key")
        self.assertEqual(first["id"], second["id"])
        self.fsm.userStart.assert_awaited_once()
        with self.assertRaises(Conflict):
            await self.service.command("channel", "start_once", "replay-key", broadcast_id="different")

    async def test_stop_commits_suppression_before_touching_process(self):
        self.assertTrue(self.admit())
        broadcast_id = self.service.get_channel("channel")["broadcast_id"]
        original_stop = self.fsm.stop
        async def stop(cid, **kwargs):
            self.assertTrue(self.repo.is_suppressed(cid, broadcast_id))
            await original_stop(cid, **kwargs)
        self.fsm.stop = AsyncMock(side_effect=stop)
        command = await self.service.command("channel", "stop_current", "stop-key", broadcast_id=broadcast_id)
        self.assertEqual(command["state"], "succeeded")
        self.assertEqual(self.service.get_channel("channel")["actual_state"], "idle")
        self.assertFalse(self.admit())
        replay = await self.service.command("channel", "stop_current", "stop-key", broadcast_id=broadcast_id)
        self.assertEqual(replay["id"], command["id"])
        self.fsm.stop.assert_awaited_once()
        self.assertTrue(self.admit(self.live("next")))

    async def test_restart_reads_suppression_before_any_automatic_capture(self):
        self.admit()
        broadcast_id = self.service.get_channel("channel")["broadcast_id"]
        await self.service.command("channel", "stop_current", "stop-before-restart", broadcast_id=broadcast_id)
        restarted_repo = V2Repository(self.db)
        restarted_repo.initialize()
        restarted_fsm = ChannelFsm()
        restarted_fsm._spawnWatch = Mock()
        restarted = ChannelControlService(restarted_repo, restarted_fsm)
        await restarted.initialize(self.channels, auto_start=False)
        self.assertEqual(restarted.get_channel("channel")["desired_mode"], "auto")
        self.assertFalse(self.admit(service=restarted))
        self.assertTrue(self.admit(self.live("new-provider-id"), service=restarted))

    async def test_unknown_broadcast_stop_fails_closed_after_restart(self):
        self.admit({"status": "OPEN"})
        broadcast_id = self.service.get_channel("channel")["broadcast_id"]
        self.assertTrue(broadcast_id.startswith("heuristic-"))
        await self.service.command("channel", "stop_current", "unknown-stop", broadcast_id=broadcast_id)
        self.assertTrue(self.repo.is_suppressed("channel", "any-broadcast"))
        restarted_fsm = ChannelFsm()
        restarted_fsm._spawnWatch = Mock()
        restarted = ChannelControlService(V2Repository(self.db), restarted_fsm)
        await restarted.initialize(self.channels)
        self.assertFalse(self.admit({"status": "OPEN"}, service=restarted))
        self.assertFalse(self.admit(self.live("known-after-unknown"), service=restarted))
        await restarted.command("channel", "start_once", "explicit-restart")
        self.assertTrue(self.admit(self.live("known-after-unknown"), service=restarted))

    async def test_pending_once_is_interrupted_not_replayed_after_restart(self):
        await self.service.patch_mode("channel", "paused", self.service.get_channel("channel")["revision"])
        command = await self.service.command("channel", "start_once", "pending-restart")
        new_fsm = ChannelFsm()
        new_fsm._spawnWatch = Mock()
        restarted = ChannelControlService(V2Repository(self.db), new_fsm)
        await restarted.initialize(self.channels)
        self.assertEqual(restarted.get_command(command["id"])["state"], "interrupted")
        new_fsm._spawnWatch.assert_not_called()
        await restarted.command("channel", "start_once", "pending-restart")
        new_fsm._spawnWatch.assert_not_called()

    async def test_stale_stop_rejected_without_stopping_or_suppressing(self):
        self.admit()
        old = self.service.get_channel("channel")["broadcast_id"]
        self.admit(self.live("next"))
        self.fsm.stop = AsyncMock()
        with self.assertRaises((Conflict, ChannelControlError)):
            await self.service.command("channel", "stop_current", "stale-stop", broadcast_id=old)
        self.fsm.stop.assert_not_awaited()
        self.assertFalse(self.repo.is_suppressed("channel", old))

    async def test_stop_requires_explicit_current_broadcast(self):
        with self.assertRaises(ChannelControlError) as failure:
            await self.service.command("channel", "stop_current", "missing-target")
        self.assertEqual(failure.exception.status_code, 422)

    async def test_missing_metadata_is_not_a_confirmed_broadcast_end(self):
        self.admit()
        await self.service.patch_mode("channel", "paused", self.service.get_channel("channel")["revision"])
        self.assertFalse(self.admit({"name": "network fallback"}, live=False))
        self.assertTrue(self.service.should_watch("channel"))
        self.assertTrue(self.admit())
        self.assertFalse(self.admit({"status": "CLOSE"}, live=False))
        self.assertFalse(self.service.should_watch("channel"))

    async def test_legacy_hook_is_noop_outside_v2_context(self):
        self.repo.set_channel_suppression("channel", "*")
        self.assertTrue(allow_capture(self.channels[0], self.live(), is_live=True))

    async def test_provider_identity_stable_across_title_change(self):
        first = provider_broadcast_identity(self.channels[0], self.live())
        second = provider_broadcast_identity(self.channels[0], self.live(title="New title"))
        self.assertEqual(first, second)
        self.assertNotEqual(first, provider_broadcast_identity(self.channels[0], self.live("new")))
        youtube = {"id": "channel", "platform": "youtube"}
        self.assertEqual(provider_broadcast_identity(youtube, {"video_id": "video"})[1], "video")
        self.assertIsNone(provider_broadcast_identity(youtube, {"title": "title only"})[0])

    async def test_both_engines_reject_suppression_before_subprocess_spawn(self):
        from module import live_recorder, youtube_recorder
        self.repo.set_channel_suppression("channel", "*")
        self.fsm.rm.set_is_user_stopped("channel", False)
        with self.service.session_context("channel"), \
             patch.object(live_recorder, "getLiveMetadata", AsyncMock(return_value=self.live())), \
             patch.object(live_recorder.asyncio, "create_subprocess_exec", AsyncMock()) as spawn:
            result = await live_recorder.chzzkStartRecording(
                self.channels[0], {}, 60, 0, False, "{recording_time}", "basic", 0, single_attempt=True,
            )
        self.assertEqual(result, RecorderAttemptOutcome.OFFLINE)
        spawn.assert_not_awaited()

        self.channels[0]["platform"] = "youtube"
        with self.service.session_context("channel"), \
             patch.object(youtube_recorder, "getYoutubeMetadata", AsyncMock(return_value={"is_live": True, "video_id": "video"})), \
             patch.object(youtube_recorder, "ysaveCookies", Mock(return_value="")), \
             patch.object(youtube_recorder, "validateCookies", Mock(return_value=(False, ""))), \
             patch.object(youtube_recorder.asyncio, "create_subprocess_exec", AsyncMock()) as spawn:
            result = await youtube_recorder.ytStartRecording(
                self.channels[0], 60, "{recording_time}", False, "", None, single_attempt=True,
            )
        self.assertEqual(result, RecorderAttemptOutcome.OFFLINE)
        spawn.assert_not_awaited()

    async def test_initialize_defers_watchers_until_application_guards_are_ready(self):
        self.fsm._spawnWatch.assert_not_called()
        await self.service.start_watching()
        self.fsm._spawnWatch.assert_called_once()

    async def test_storage_failure_blocks_before_capture(self):
        with patch("module.v2_runtime.capture_storage_report", return_value={"ok": False}):
            self.assertFalse(self.admit())
        state = self.service.get_channel("channel")
        self.assertEqual((state["actual_state"], state["reason_code"]), ("blocked", "STORAGE_UNAVAILABLE"))

    async def test_policy_rejected_once_finishes_as_blocked_instead_of_running_forever(self):
        await self.service.patch_mode("channel", "paused", self.service.get_channel("channel")["revision"])
        self.fsm.userStart = AsyncMock(return_value=None)
        command = await self.service.command("channel", "start_once", "operations-blocked")
        self.assertEqual(command["state"], "blocked")
        self.assertEqual(command["error_code"], "ADMISSION_BLOCKED")
        self.assertFalse(self.service.should_watch("channel"))

    async def test_failed_start_does_not_leave_a_paused_one_time_scope_armed(self):
        await self.service.patch_mode("channel", "paused", self.service.get_channel("channel")["revision"])
        self.fsm.userStart = AsyncMock(side_effect=RuntimeError("engine unavailable"))
        with self.assertRaises(RuntimeError):
            await self.service.command("channel", "start_once", "failed-start")
        self.assertFalse(self.service.should_watch("channel"))
        self.assertEqual(self.repo.list_commands()["items"][0]["state"], "failed")

    async def test_once_storage_rejection_is_visible_and_does_not_resume_after_pause(self):
        await self.service.patch_mode("channel", "paused", self.service.get_channel("channel")["revision"])
        command = await self.service.command("channel", "start_once", "storage-blocked")
        with patch("module.v2_runtime.capture_storage_report", return_value={"ok": False}):
            self.assertFalse(self.admit())
        self.assertEqual(self.service.get_command(command["id"])["state"], "blocked")
        self.assertFalse(self.service.should_watch("channel"))

    async def test_removed_channels_are_still_stopped_on_shutdown(self):
        self.fsm._runtime("removed-channel")
        self.fsm.stop = AsyncMock()
        await self.fsm.stopAll()
        self.assertEqual({call.args[0] for call in self.fsm.stop.await_args_list}, {"channel", "removed-channel"})

    def recording_context(self):
        from module import recording_catalog, recording_history, v2_runtime
        self.enterContext(patch.object(recording_catalog, "DB_PATH", self.root / "catalog.sqlite3"))
        self.enterContext(patch.object(recording_history, "HISTORY_PATH", str(self.root / "history.jsonl")))
        self.enterContext(patch.object(v2_runtime, "_repository", self.repo))
        self.enterContext(patch.dict(os.environ, {"LAR_V2_ENABLED": "1", "RECORDINGS_ROOT": str(self.root)}))
        self.enterContext(patch("module.operations_platform_v3.emit_runtime_event", Mock()))
        self.enterContext(patch.object(self.service, "retain_capture_process", Mock()))
        return recording_catalog

    async def test_actual_capture_events_share_provider_identity_and_queue_durable_verification(self):
        catalog = self.recording_context()
        self.admit()
        expected = self.service.get_channel("channel")["broadcast_id"]
        path = self.root / "capture.ts"
        process = SimpleNamespace(returncode=None)
        with self.service.session_context("channel"):
            self.service.capture_started("channel", str(path), process)
            self.assertEqual(catalog.find_latest_recording("channel")["broadcast_id"], expected)
            path.write_bytes(b"recorded media")
            process.returncode = 0
            self.service.capture_finished("channel")
            self.service.capture_finished("channel")
        row = catalog.find_latest_recording("channel")
        self.assertEqual(row["status"], "completed")
        jobs = self.repo.list_jobs()["items"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "verify")
        self.assertEqual(self.repo.get_artifact(jobs[0]["target_id"])["broadcast_id"], expected)

    async def test_split_finalization_tracks_only_exact_owned_numeric_files(self):
        catalog = self.recording_context()
        self.admit()
        process = SimpleNamespace(returncode=None)
        for name in ("session_000.ts", "session_001.ts", "session_backup.ts", "someone_002.ts"):
            (self.root / name).write_bytes(b"media")
        with self.service.session_context("channel"):
            self.service.capture_started("channel", str(self.root / "session_%03d.ts"), process)
            self.service.capture_finished("channel")
            self.assertEqual(self.repo.list_jobs()["items"], [])
            process.returncode = 0
            self.service.capture_finished("channel")
        jobs = self.repo.list_jobs()["items"]
        self.assertEqual(len(jobs), 2)
        artifacts = [self.repo.get_artifact(job["target_id"]) for job in jobs]
        self.assertEqual({Path(item["legacy_path"]).name for item in artifacts}, {"session_000.ts", "session_001.ts"})
        self.assertEqual(len({item["broadcast_id"] for item in artifacts}), 1)

    async def test_legacy_output_move_keeps_catalog_and_verification_at_actual_final_path(self):
        from module.data_manager import moveDirectory
        catalog = self.recording_context()
        self.admit()
        source = self.root / "recorded.mp4"
        destination = self.root / "moved"
        process = SimpleNamespace(returncode=None)
        with self.service.session_context("channel"):
            self.service.capture_started("channel", str(source), process)
            source.write_bytes(b"media")
            await moveDirectory(str(source), str(destination))
            process.returncode = 0
            self.service.capture_finished("channel")
        expected = destination / source.name
        row = catalog.find_latest_recording("channel")
        self.assertEqual(row["file_path"], str(expected))
        self.assertEqual(self.repo.list_jobs()["items"][0]["state"], "queued")



@unittest.skipUnless(os.name == "posix", "Owned POSIX process-group regression")
class CaptureProcessGroupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = V2Repository(self.root / "v2.sqlite3")
        self.repo.initialize()
        self.enterContext(patch.multiple(
            RecorderManager, status_recording={}, status_reserved={}, tasks_process={},
            recording_start_time={}, recording_filename={}, is_user_stopped=set(),
            guard_starting=set(), _channels_cache=[], _channels_ref=None,
        ))
        self.channel = {"id": "owned", "name": "Owned fixture", "platform": "chzzk", "record_enabled": True}
        RecorderManager.setChannels([self.channel])
        self.fsm = ChannelFsm()
        self.fsm._spawnWatch = Mock()
        self.fsm._recordStopReason = Mock()
        self.service = ChannelControlService(self.repo, self.fsm)
        self.service._capture_event = Mock()
        self.enterContext(patch("module.v2_runtime.capture_storage_report", return_value={"ok": True}))
        self.enterContext(patch("module.v2_runtime.record_capture_process", Mock()))
        await self.service.initialize([self.channel])
        self.assertTrue(self.service.admit_metadata(self.channel, {"status": "OPEN", "liveId": "fixture"}, is_live=True))
        self.broadcast_id = self.service.get_channel("owned")["broadcast_id"]
        original = self.fsm._killProcessTree
        async def fast_stop(cid, timeout=3):
            await original(cid, timeout=0.1)
        self.fsm._killProcessTree = fast_stop

    async def stubborn_group(self, name):
        marker = self.root / (name + ".pid")
        child = "import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path(" + repr(str(marker)) + ").write_text(str(os.getpid())); time.sleep(60)"
        leader = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(60)"
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", leader, start_new_session=True,
                                                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        async def cleanup():
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), 3)
        self.addAsyncCleanup(cleanup)
        self.service.retain_capture_process("owned", process)
        for _ in range(500):
            if marker.exists():
                break
            await asyncio.sleep(0.01)
        self.assertTrue(marker.exists(), "Owned child did not become ready")
        path = self.root / (name + ".ts")
        path.write_bytes(b"owned recording")
        return process, path

    async def test_stop_current_kills_stubborn_child_after_group_leader_exits(self):
        from module.v2_worker import _group_members
        process, path = await self.stubborn_group("stop")
        self.service.capture_started("owned", str(path), process)
        self.fsm.rm.set_tasks_process("owned", process)
        command = await self.service.command("owned", "stop_current", "stop-stubborn", broadcast_id=self.broadcast_id)
        self.assertEqual(command["state"], "succeeded")
        self.assertIsNotNone(process.returncode)
        self.assertEqual(_group_members(process.pid), [])
        self.assertIsNone(self.fsm.rm.get_tasks_process("owned"))
        self.assertNotIn("owned", self.service._captures)

    async def test_natural_leader_exit_retains_capture_and_blocks_reentry_until_group_stop(self):
        process, path = await self.stubborn_group("natural")
        self.service.capture_started("owned", str(path), process)
        process.terminate()
        await asyncio.wait_for(process.wait(), 3)
        self.service.capture_finished("owned")
        self.assertIn("owned", self.service._captures)
        self.assertTrue(self.service.capture_is_active("owned"))
        self.assertFalse(self.service.admit_metadata(self.channel, {"status": "OPEN", "liveId": "different"}, is_live=True))
        self.assertEqual(self.service.get_channel("owned")["reason_code"], "CAPTURE_RECONCILIATION_REQUIRED")
        self.assertFalse(any(call.args[1] == "recording_stopped" for call in self.service._capture_event.call_args_list))
        await self.fsm._killProcessTree("owned")
        self.service.capture_finished("owned")
        self.assertNotIn("owned", self.service._captures)
        self.assertFalse(self.service.capture_is_active("owned"))

    async def test_uncertain_group_proof_preserves_ownership_and_blocks_new_capture(self):
        process, path = await self.stubborn_group("uncertain")
        self.service.capture_started("owned", str(path), process)
        self.fsm.rm.set_tasks_process("owned", process)
        with patch.object(self.service, "_capture_group_members", return_value=None):
            with self.assertRaises(ChannelControlError):
                await self.fsm._killProcessTree("owned")
            self.service.capture_finished("owned")
            self.assertIs(self.fsm.rm.get_tasks_process("owned"), process)
            self.assertIn("owned", self.service._captures)
            self.assertFalse(self.service.should_watch("owned"))
        await self.fsm._killProcessTree("owned")
        self.service.capture_finished("owned")

    async def test_split_capture_waits_for_both_owned_process_groups(self):
        from module.v2_worker import _group_members
        streamlink, _ = await self.stubborn_group("streamlink")
        ffmpeg, path = await self.stubborn_group("ffmpeg")
        self.service.capture_started("owned", str(path), ffmpeg)
        self.fsm.rm.set_tasks_process("owned", ffmpeg)
        await self.fsm._killProcessTree("owned")
        self.assertEqual(_group_members(streamlink.pid), [])
        self.assertEqual(_group_members(ffmpeg.pid), [])
        self.service.capture_finished("owned")
        self.assertNotIn("owned", self.service._captures)

    async def test_unisolated_process_group_is_never_signalled(self):
        process = SimpleNamespace(pid=os.getpid(), returncode=None)
        with self.assertRaises(RuntimeError):
            self.service.retain_capture_process("owned", process)
        with patch("module.v2_channels.os.killpg") as killpg:
            with self.assertRaises(ChannelControlError):
                await self.service.terminate_capture_groups("owned", timeout=0.05)
        killpg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
