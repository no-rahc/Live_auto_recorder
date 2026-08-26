from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from module.channel_fsm import ChannelFsm
from module.recording_session import SessionOutcome


class FakeManager:
    def __init__(self):
        self.channels = [{"id": "a", "name": "Alpha", "platform": "chzzk", "record_enabled": True}]
        self.user_stopped = {"a": False}
        self.recording = {"a": False}
        self.reserved = {"a": False}

    def getChannels(self):
        return self.channels

    def get_is_user_stopped(self, cid):
        return bool(self.user_stopped.get(cid))

    def set_is_user_stopped(self, cid, value):
        self.user_stopped[cid] = bool(value)

    def get_status_recording(self, cid):
        return bool(self.recording.get(cid))

    def set_status_recording(self, cid, value):
        self.recording[cid] = bool(value)

    def get_status_reserved(self, cid):
        return bool(self.reserved.get(cid))

    def set_status_reserved(self, cid, value):
        self.reserved[cid] = bool(value)

    def get_tasks_process(self, cid):
        return None

    def guard_try_acquire_start(self, cid):
        return True

    def guard_release_start(self, cid):
        return None

    async def force_terminate_worker(self, cid):
        return None


class ChannelFsmStabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fsm = ChannelFsm()
        self.fsm.rm = FakeManager()

    async def test_stop_cancels_pending_respawn_task(self):
        blocker = asyncio.Event()

        async def fake_start_session(*args, **kwargs):
            return None

        async def fake_sleep(_seconds):
            await blocker.wait()

        with patch("module.channel_fsm.startSession", new=AsyncMock(side_effect=fake_start_session)), patch.object(
            self.fsm, "_sleepWithJitter", new=AsyncMock(side_effect=fake_sleep)
        ):
            await self.fsm.userStart("a")
            await asyncio.sleep(0)
            await asyncio.sleep(0)

            task = self.fsm.respawnTask.get("a")
            self.assertIsNotNone(task)
            self.assertFalse(task.done())

            await self.fsm.userStop("a")

            self.assertNotIn("a", self.fsm.respawnTask)
            self.assertTrue(task.done())
            self.assertTrue(task.cancelled())

    async def test_only_one_pending_respawn_exists_per_channel(self):
        blocker = asyncio.Event()

        async def fake_sleep(_seconds):
            await blocker.wait()

        with patch.object(self.fsm, "_sleepWithJitter", new=AsyncMock(side_effect=fake_sleep)):
            self.fsm._scheduleRespawn("a", 60)
            first = self.fsm.respawnTask["a"]
            self.fsm._scheduleRespawn("a", 60)
            self.assertIs(self.fsm.respawnTask["a"], first)
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first

    async def test_fsm_owns_stop_intent_even_if_manager_flag_is_stale(self):
        blocker = asyncio.Event()

        async def fake_sleep(_seconds):
            await blocker.wait()

        self.fsm._setWatching("a")
        self.fsm.rm.user_stopped["a"] = True
        self.assertFalse(self.fsm.isStopRequested("a"))

        with patch.object(self.fsm, "_sleepWithJitter", new=AsyncMock(side_effect=fake_sleep)):
            self.fsm._scheduleRespawn("a", 60)
            task = self.fsm.respawnTask["a"]
            self.assertFalse(task.done())

            await self.fsm.userStop("a")
            self.assertTrue(self.fsm.isStopRequested("a"))
            self.assertTrue(task.done())

    async def test_unsupported_platform_does_not_schedule_respawn(self):
        self.fsm.rm.channels[0]["platform"] = "unknown"
        with patch(
            "module.channel_fsm.startSession",
            new=AsyncMock(return_value=SessionOutcome.UNSUPPORTED),
        ):
            await self.fsm.userStart("a")
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        self.assertEqual(self.fsm.getState("a"), "STOPPED")
        self.assertNotIn("a", self.fsm.respawnTask)


if __name__ == "__main__":
    unittest.main()
