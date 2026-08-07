import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import module.recording_catalog as catalog
from module.operations_platform_v3 import PlatformRuntime
from module.recording_verify import verify_recording


class RecordingPlatformV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_db = catalog.DB_PATH
        catalog.DB_PATH = Path(self.temp.name) / "recordings.sqlite3"
        self.addCleanup(setattr, catalog, "DB_PATH", self.old_db)
        catalog.init_catalog()

    def test_catalog_keeps_completed_recording_and_searches_it(self):
        catalog.record_event({
            "ts": "2026-08-07 09:00:00", "epoch": 1.0, "channel_id": "abc", "channel_name": "테스트",
            "platform": "chzzk", "event": "recording_started", "filename": "sample.mp4",
            "duration": "", "error": "", "file_path": "/tmp/sample.mp4", "title": "아침 방송",
        })
        catalog.record_event({
            "ts": "2026-08-07 10:00:00", "epoch": 2.0, "channel_id": "abc", "channel_name": "테스트",
            "platform": "chzzk", "event": "recording_stopped", "filename": "sample.mp4",
            "duration": "01:00:00", "error": "",
        })

        result = catalog.list_recordings(query="아침")
        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["status"], "completed")
        self.assertEqual(item["duration"], "01:00:00")
        self.assertEqual(item["title"], "아침 방송")

    def test_api_token_is_hashed_scoped_and_revocable(self):
        fake_app = SimpleNamespace(state=SimpleNamespace(config={}))
        fake_lar = SimpleNamespace(CONFIG_PATH=str(Path(self.temp.name) / "config.json"))
        runtime = PlatformRuntime(fake_app, fake_lar, operations=SimpleNamespace())
        created = runtime.create_token("automation", ["read"], 1)

        self.assertTrue(created["token"].startswith("lar_"))
        self.assertIsNotNone(runtime.verify_token(created["token"], "read"))
        self.assertIsNone(runtime.verify_token(created["token"], "control"))
        with catalog._connect() as conn:
            row = conn.execute("SELECT token_hash FROM api_tokens WHERE id=?", (created["id"],)).fetchone()
        self.assertNotEqual(row["token_hash"], created["token"])

    def test_completed_file_validation_records_probe_result(self):
        path = Path(self.temp.name) / "sample.mp4"
        path.write_bytes(b"video")
        catalog.record_event({
            "ts": "2026-08-07 09:00:00", "epoch": 1.0, "channel_id": "abc", "channel_name": "테스트",
            "platform": "chzzk", "event": "recording_started", "filename": path.name,
            "duration": "", "error": "", "file_path": str(path),
        })
        item = catalog.list_recordings()["items"][0]
        probe = SimpleNamespace(returncode=0, stdout='{"streams":[{"codec_type":"video","codec_name":"h264"},{"codec_type":"audio","codec_name":"aac"}],"format":{"duration":"60.0"}}', stderr="")
        with mock.patch("module.recording_verify.subprocess.run", return_value=probe):
            result = verify_recording(item["id"], attempt_repair=True)

        self.assertEqual(result["status"], "ok")
        saved = catalog.get_recording(item["id"])
        self.assertEqual(saved["validation_status"], "ok")
        self.assertEqual(saved["file_size"], 5)


if __name__ == "__main__":
    unittest.main()
