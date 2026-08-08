import asyncio
import json
import sqlite3
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

    def _runtime(self, config=None):
        fake_app = SimpleNamespace(state=SimpleNamespace(config=config or {}))
        fake_lar = SimpleNamespace(
            CONFIG_PATH=str(Path(self.temp.name) / "config.json"),
            sendTelegram=mock.Mock(),
        )
        return PlatformRuntime(fake_app, fake_lar, operations=SimpleNamespace())

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
        runtime = self._runtime()
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

    def test_schema_migrates_v1_to_v3_and_keeps_pre_migration_backup(self):
        legacy = Path(self.temp.name) / "legacy.sqlite3"
        catalog.DB_PATH = legacy
        with sqlite3.connect(legacy) as conn:
            catalog._migrate_v1(conn)
            conn.execute("PRAGMA user_version=1")
            conn.commit()

        catalog.init_catalog()

        with catalog._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            recording_columns = {row[1] for row in conn.execute("PRAGMA table_info(recordings)")}
            notification_columns = {row[1] for row in conn.execute("PRAGMA table_info(notification_queue)")}
            archive_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='archive_jobs'"
            ).fetchone()
        self.assertEqual(version, 3)
        self.assertIn("stop_reason", recording_columns)
        self.assertIn("delivery_json", notification_columns)
        self.assertIsNotNone(archive_table)
        self.assertTrue(list(legacy.parent.glob("legacy.sqlite3.pre-migrate-*.bak")))

    def test_stop_reason_is_persisted_on_active_recording(self):
        catalog.record_event({
            "ts": "2026-08-07 09:00:00", "epoch": 1.0, "channel_id": "abc", "channel_name": "테스트",
            "platform": "chzzk", "event": "recording_started", "filename": "sample.mp4",
            "duration": "", "error": "", "file_path": "/tmp/sample.mp4",
        })
        self.assertTrue(catalog.set_active_stop_reason("abc", "health_restart"))
        item = catalog.list_recordings()["items"][0]
        self.assertEqual(item["stop_reason"], "health_restart")

    def test_notification_retry_does_not_resend_successful_destination(self):
        runtime = self._runtime({
            "telegram_enabled": True,
            "discord_enabled": True,
            "discord_webhook_url": "https://discord.example/hook",
        })
        runtime.enqueue_notification("storage.warning", {"detail": "disk low"})
        ok_response = SimpleNamespace(raise_for_status=lambda: None)

        with mock.patch("module.operations_platform_v3.requests.post", side_effect=[RuntimeError("discord down"), ok_response]) as post:
            asyncio.run(runtime._process_notification_once())
            with catalog._connect() as conn:
                row = conn.execute("SELECT * FROM notification_queue ORDER BY id DESC LIMIT 1").fetchone()
                first = dict(row)
                conn.execute("UPDATE notification_queue SET next_attempt=0 WHERE id=?", (first["id"],))
            self.assertEqual(first["status"], "retry")
            delivery = json.loads(first["delivery_json"])
            self.assertEqual(delivery["telegram"]["status"], "sent")
            self.assertEqual(delivery["discord"]["status"], "failed")

            asyncio.run(runtime._process_notification_once())

        self.assertEqual(runtime.lar.sendTelegram.call_count, 1)
        self.assertEqual(post.call_count, 2)
        with catalog._connect() as conn:
            final = dict(conn.execute("SELECT * FROM notification_queue ORDER BY id DESC LIMIT 1").fetchone())
        self.assertEqual(final["status"], "sent")
        self.assertEqual(json.loads(final["delivery_json"])["discord"]["status"], "sent")

    def test_archive_job_recovers_after_restart_and_completes(self):
        path = Path(self.temp.name) / "sample.mp4"
        path.write_bytes(b"video")
        catalog.record_event({
            "ts": "2026-08-07 09:00:00", "epoch": 1.0, "channel_id": "abc", "channel_name": "테스트",
            "platform": "chzzk", "event": "recording_started", "filename": path.name,
            "duration": "", "error": "", "file_path": str(path),
        })
        item = catalog.list_recordings()["items"][0]
        runtime = self._runtime()
        runtime.settings["archive"].update({"enabled": True, "remote": "test:archive", "verify_size": True})
        job_id = runtime.enqueue_archive(item["id"])
        with catalog._connect() as conn:
            conn.execute("UPDATE archive_jobs SET status='uploading' WHERE id=?", (job_id,))

        self.assertEqual(runtime._recover_archive_jobs(), 1)
        with catalog._connect() as conn:
            recovered = dict(conn.execute("SELECT * FROM archive_jobs WHERE id=?", (job_id,)).fetchone())
            conn.execute("UPDATE archive_jobs SET next_attempt=0 WHERE id=?", (job_id,))
        self.assertEqual(recovered["status"], "retry")

        copy_result = SimpleNamespace(returncode=0, stdout="", stderr="")
        size_result = SimpleNamespace(returncode=0, stdout='{"bytes":5}', stderr="")
        with mock.patch("module.operations_platform_v3.subprocess.run", side_effect=[copy_result, size_result]):
            asyncio.run(runtime._process_archive_once())

        with catalog._connect() as conn:
            finished = dict(conn.execute("SELECT * FROM archive_jobs WHERE id=?", (job_id,)).fetchone())
        self.assertEqual(finished["status"], "completed")
        saved = catalog.get_recording(item["id"])
        self.assertEqual(saved["archive_status"], "completed")
        self.assertEqual(saved["archive_target"], "test:archive/sample.mp4")


if __name__ == "__main__":
    unittest.main()
