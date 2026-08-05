from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from module.operations_v2 import OperationsRuntime


class FakeManager:
    def __init__(self):
        self.recording = {}
        self.reserved = {}
        self.processes = {}
        self.filenames = {}

    def get_status_recording(self, channel_id):
        return bool(self.recording.get(channel_id))

    def get_status_reserved(self, channel_id):
        return bool(self.reserved.get(channel_id))

    def get_tasks_process(self, channel_id):
        return self.processes.get(channel_id)

    def get_recording_filename(self, channel_id):
        return self.filenames.get(channel_id)


class FakeRecorderClass:
    recording_filename = {}
    recording_start_time = {}

    @classmethod
    def setChannels(cls, channels):
        cls.channels = list(channels)


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
        self.stopped.append(channel_id)

    async def stopAll(self):
        self.stopped.append("all")


class FakeLar:
    def __init__(self, root: Path):
        self.CONFIG_PATH = str(root / "json" / "config.json")
        self.recorder_manager = FakeManager()
        self.RecorderManager = FakeRecorderClass
        self.queueBatchPattern = self._queue_pattern
        self.queueBatchLast = self._queue_last
        self.sent = []
        self._channels = []

    async def _queue_pattern(self, channel_id, source):
        return {"channel": channel_id, "source": source}

    async def _queue_last(self, channel_id):
        return {"channel": channel_id}

    def busyFilePaths(self, manager, channels):
        return [str(path) for path in getattr(self, "busy", [])]

    def sendTelegram(self, message):
        self.sent.append(message)

    def loadConfig(self):
        path = Path(self.CONFIG_PATH)
        return json.loads(path.read_text()) if path.exists() else {}

    def loadChannels(self):
        return list(self._channels)


class OperationsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lar = FakeLar(self.root)
        self.channels = [{"id": "a", "name": "Alpha", "platform": "chzzk", "live_title": "Game Night", "category": "Game"}]
        self.lar._channels = self.channels
        self.app = SimpleNamespace(state=SimpleNamespace(channels=self.channels, config={}, fsm=FakeFsm()))
        self.runtime = OperationsRuntime(self.app, self.lar)
        self.runtime.recording_root = self.root / "recordings"
        self.runtime.recording_root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_rule_matching_and_exclusion(self):
        self.runtime.set_rule("a", {"enabled": True, "title_include": ["game"], "title_exclude": ["rerun"], "categories": ["game"]})
        self.assertEqual(self.runtime.evaluate_rule(self.channels[0]), (True, "허용"))
        self.channels[0]["live_title"] = "Game rerun"
        allowed, reason = self.runtime.evaluate_rule(self.channels[0])
        self.assertFalse(allowed)
        self.assertIn("제외", reason)

    def test_cleanup_never_selects_busy_or_recent_files(self):
        old = self.runtime.recording_root / "old.ts"
        busy = self.runtime.recording_root / "busy.ts"
        recent = self.runtime.recording_root / "recent.ts"
        for path in (old, busy, recent):
            path.write_bytes(b"x" * 10)
        old_time = 1_600_000_000
        busy_time = 1_600_000_000
        old.touch()
        busy.touch()
        import os
        os.utime(old, (old_time, old_time))
        os.utime(busy, (busy_time, busy_time))
        self.lar.busy = [busy]
        result = self.runtime.cleanup_candidates({"mode": "age", "retention_days": 1, "minimum_file_age_minutes": 10})
        names = {item["name"] for item in result["candidates"]}
        self.assertIn("old.ts", names)
        self.assertNotIn("busy.ts", names)
        self.assertNotIn("recent.ts", names)

    def test_storage_threshold_blocks_new_recordings(self):
        usage = SimpleNamespace(total=1000, used=960, free=40)
        with patch("module.operations_common.shutil.disk_usage", return_value=usage):
            info = self.runtime.storage_info()
            self.assertEqual(info["status"], "critical")
            allowed, reason, delay = self.runtime.can_start("a")
            self.assertFalse(allowed)
            self.assertIn("여유 공간", reason)
            self.assertEqual(delay, 0)

    def test_backup_excludes_secrets_by_default(self):
        data = Path(self.lar.CONFIG_PATH).parent
        data.mkdir(parents=True)
        (data / "config.json").write_text("{}")
        (data / "channels.json").write_text("[]")
        (data / "cookie.json").write_text('{"secret": true}')
        result = self.runtime.create_backup(include_secrets=False)
        import zipfile
        with zipfile.ZipFile(self.runtime.backup_dir / result["name"]) as archive:
            names = set(archive.namelist())
        self.assertIn("config.json", names)
        self.assertIn("channels.json", names)
        self.assertNotIn("cookie.json", names)

    def test_fsm_guard_applies_rule_and_quality_override(self):
        self.runtime.set_rule("a", {"enabled": True, "title_include": ["game"], "quality_override": "1080p", "start_delay_seconds": 0})
        self.runtime._install_start_guard()
        asyncio.run(self.app.state.fsm.userStart("a", is_user_request=True))
        self.assertEqual(self.channels[0]["quality"], "1080p")
        self.assertEqual(self.app.state.fsm.started, [("a", True)])


if __name__ == "__main__":
    unittest.main()
