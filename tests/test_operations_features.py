from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from module.operations_v2 import OperationsRuntime


class FakeManager:
    def __init__(self):
        self.recording = {"a": False}
        self.reserved = {"a": False}
        self.processes = {"a": None}
        self.user_stopped = {"a": False}
        self.filenames = {}
        self.start_times = {}

    def get_status_recording(self, cid): return bool(self.recording.get(cid))
    def set_status_recording(self, cid, value): self.recording[cid] = bool(value)
    def get_status_reserved(self, cid): return bool(self.reserved.get(cid))
    def set_status_reserved(self, cid, value): self.reserved[cid] = bool(value)
    def get_tasks_process(self, cid): return self.processes.get(cid)
    def clear_tasks_process(self, cid): self.processes[cid] = None
    def get_is_user_stopped(self, cid): return bool(self.user_stopped.get(cid))
    def set_is_user_stopped(self, cid, value): self.user_stopped[cid] = bool(value)
    def get_recording_filename(self, cid): return self.filenames.get(cid)
    def recording_remove_start_time(self, cid): self.start_times.pop(cid, None)


class FakeRecorderClass:
    recording_start_time = {}


class FakeLar:
    def __init__(self, root: Path):
        self.CONFIG_PATH = str(root / "json" / "config.json")
        self.recorder_manager = FakeManager()
        self.RecorderManager = FakeRecorderClass
        self.queueBatchPattern = self._noop
        self.queueBatchLast = self._noop

    async def _noop(self, *args, **kwargs): return None
    def busyFilePaths(self, manager, channels): return []


class FakeFsm:
    def __init__(self): self.states = {"a": "STOPPED"}
    def getState(self, cid): return self.states.get(cid, "STOPPED")


class OperationsFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.channel = {"id": "a", "name": "Alpha", "platform": "chzzk", "record_enabled": True}
        self.app = SimpleNamespace(state=SimpleNamespace(channels=[self.channel], config={}, fsm=FakeFsm()))
        self.lar = FakeLar(self.root)
        self.runtime = OperationsRuntime(self.app, self.lar)
        self.runtime.recording_root = self.root / "recordings"
        self.runtime.recording_root.mkdir(parents=True)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_per_channel_health_override_merges_with_global(self):
        self.runtime.settings["health"]["stall_seconds"] = 120
        result = self.runtime.set_channel_health_settings("a", {"stall_seconds": 240, "missed_recording_seconds": 90})
        self.assertEqual(result["stall_seconds"], 240)
        self.assertEqual(result["missed_recording_seconds"], 90)
        self.assertIn("auto_restart", result)

    async def test_schedule_api_updates_only_schedule_fields(self):
        self.runtime.settings["rules"]["a"] = {"title_include": ["keep-me"]}
        result = self.runtime.set_channel_schedule("a", {"days": [0, 2], "time_start": "20:00", "time_end": "02:00", "start_delay_seconds": 12})
        self.assertEqual(result["days"], [0, 2])
        self.assertEqual(result["time_start"], "20:00")
        self.assertEqual(self.runtime.settings["rules"]["a"]["title_include"], ["keep-me"])

    async def test_file_protection_is_confined_to_recording_root(self):
        path = self.runtime.recording_root / "a.ts"
        path.write_bytes(b"abc")
        result = self.runtime.set_file_protected(str(path), True)
        self.assertTrue(result["protected"])
        self.assertIn(path.resolve(), self.runtime.protected_paths())

    async def test_startup_reconcile_clears_stale_recording_flag(self):
        self.lar.recorder_manager.recording["a"] = True
        result = await self.runtime.reconcile_startup()
        self.assertEqual(result["fixed_channels"], ["a"])
        self.assertFalse(self.lar.recorder_manager.recording["a"])

    async def test_recovery_strategy_can_open_circuit_breaker(self):
        self.runtime.settings["health"]["circuit_breaker_after"] = 2
        self.runtime.settings["health"]["circuit_breaker_seconds"] = 90
        result = self.runtime.recovery_strategy("a", "failed", 2)
        self.assertEqual(result, {"action": "circuit_breaker", "delay_seconds": 90})


if __name__ == "__main__":
    unittest.main()
