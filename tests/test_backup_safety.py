"""Backup policy, staging/validation and rollback regression coverage."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from lar_app.backup_policy import preserve_existing_secrets, sanitize_secrets
from module.operations_backup import BackupStatsMixin
from module.operations_common import DEFAULT_SETTINGS


class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = BackupStatsMixin()
        self.runtime.data_dir = self.root / "json"
        self.runtime.data_dir.mkdir()
        self.runtime.backup_dir = self.root / "backups"
        self.runtime.backup_dir.mkdir()
        self.runtime.settings_path = self.runtime.data_dir / "operations_v2.json"
        self.runtime.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.runtime.settings["backup"]["keep"] = 1
        self.runtime.app = SimpleNamespace(state=SimpleNamespace(config={"discord_webhook_url": "live-secret"}, channels=[]))
        self.runtime.audit = mock.Mock()
        self.runtime.lar = SimpleNamespace(loadChannels=lambda: json.loads((self.runtime.data_dir / "channels.json").read_text()), RecorderManager=SimpleNamespace(setChannels=mock.Mock()))
        self.write("config.json", {"discord_webhook_url": "live-secret", "recheckInterval": 60})
        self.env = mock.patch.dict(os.environ, {"ALLOW_SECRET_BACKUPS": "false"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, name, value):
        (self.runtime.data_dir / name).write_text(json.dumps(value), encoding="utf-8")

    def archive(self, entries):
        path = self.runtime.backup_dir / "backup_selected.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in entries:
                archive.writestr(name, value if isinstance(value, bytes) else json.dumps(value))
        return path

    def snapshots(self):
        return {path.name: path.read_bytes() for path in self.runtime.data_dir.iterdir() if path.is_file()}

    def test_default_backup_recursively_redacts_secrets(self):
        self.write("config.json", {"discord_webhook_url": "discord-secret", "nested": [{"apiKey": "api-secret", "password": "pw", "name": "safe"}]})
        self.write("telegram.json", {"telegram_bot_token": "telegram-secret"})
        result = self.runtime.create_backup()
        with zipfile.ZipFile(self.runtime.backup_path(result["name"])) as archive:
            self.assertNotIn("telegram.json", archive.namelist())
            value = json.loads(archive.read("config.json"))
            self.assertEqual(value, {"nested": [{"name": "safe"}]})

    def test_policy_applies_inside_runtime_for_all_creation_paths(self):
        with self.assertRaises(HTTPException) as error:
            self.runtime.create_backup(True)
        self.assertEqual(error.exception.status_code, 403)
        self.runtime.settings["backup"]["include_secrets"] = True
        for reason in ("scheduled", "pre_restore"):
            result = self.runtime.create_backup(reason=reason)
            with zipfile.ZipFile(self.runtime.backup_path(result["name"])) as archive:
                self.assertFalse(json.loads(archive.read("manifest.json"))["include_secrets"])
                self.assertNotIn(b"live-secret", archive.read("config.json"))

    def test_explicit_opt_in_allows_secret_archive(self):
        with mock.patch.dict(os.environ, {"ALLOW_SECRET_BACKUPS": "true"}):
            result = self.runtime.create_backup(True)
        with zipfile.ZipFile(self.runtime.backup_path(result["name"])) as archive:
            self.assertIn(b"live-secret", archive.read("config.json"))

    def test_restore_selected_oldest_with_keep_one(self):
        path = self.archive([("config.json", {"recheckInterval": 90})])
        os.utime(path, (1, 1))
        result = self.runtime.restore_backup(path.name)
        value = json.loads((self.runtime.data_dir / "config.json").read_text())
        self.assertEqual(value["recheckInterval"], 90)
        self.assertEqual(value["discord_webhook_url"], "live-secret")
        self.assertEqual(len(self.runtime.list_backups()), 1)
        with zipfile.ZipFile(self.runtime.backup_path(result["pre_restore_backup"]["name"])) as archive:
            self.assertNotIn(b"live-secret", archive.read("config.json"))

    def test_all_members_validated_before_live_writes_or_pre_backup(self):
        cases = [
            [("config.json", {"recheckInterval": 90}), ("channels.json", b"{broken")],
            [("config.json", {"recheckInterval": 90}), ("../channels.json", [])],
            [("channels.json", {"not": "list"})],
            [("operations_v2.json", {"backup": []})],
            [("operations_v2.json", {"backup": {"keep": "bad"}})],
            [("operations_v2.json", {"backup": {"scheduled": "true"}})],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                path = self.archive(entries)
                before = self.snapshots()
                with self.assertRaises(HTTPException) as error:
                    self.runtime.restore_backup(path.name)
                self.assertEqual(error.exception.status_code, 400)
                self.assertEqual(self.snapshots(), before)
                self.assertEqual(len(self.runtime.list_backups()), 1)

    def test_corrupt_zip_does_not_change_live_files(self):
        path = self.runtime.backup_dir / "backup_broken.zip"
        path.write_bytes(b"not-a-zip")
        before = self.snapshots()
        with self.assertRaises(HTTPException):
            self.runtime.restore_backup(path.name)
        self.assertEqual(self.snapshots(), before)

    def test_late_commit_failure_rolls_back_earlier_file(self):
        self.write("channels.json", [{"id": "old"}])
        path = self.archive([("config.json", {"recheckInterval": 90}), ("channels.json", [{"id": "new"}])])
        before = self.snapshots()
        replace = os.replace
        failed = False
        def fail_once(source, target):
            nonlocal failed
            if Path(target).name == "channels.json" and not failed:
                failed = True
                raise OSError("injected disk failure")
            return replace(source, target)
        with mock.patch("module.operations_backup.os.replace", side_effect=fail_once):
            with self.assertRaises(HTTPException) as error:
                self.runtime.restore_backup(path.name)
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(self.snapshots(), before)
        self.assertEqual(self.runtime.app.state.config, {"discord_webhook_url": "live-secret"})

    def test_selected_archive_pinned_during_commit(self):
        path = self.archive([("config.json", {"recheckInterval": 90})])
        os.utime(path, (1, 1))
        replace = os.replace
        def verify_pin(source, target):
            if Path(target).name == "config.json":
                self.assertTrue(path.exists())
            return replace(source, target)
        with mock.patch("module.operations_backup.os.replace", side_effect=verify_pin):
            self.runtime.restore_backup(path.name)

    def test_failed_creation_leaves_no_partial_or_corrupt_zip(self):
        self.write("config.json", {"nested": {"token": "secret"}})
        (self.runtime.data_dir / "channels.json").write_text("{broken")
        with self.assertRaises(ValueError):
            self.runtime.create_backup()
        self.assertEqual(list(self.runtime.backup_dir.iterdir()), [])

    def test_identityless_list_does_not_transfer_credentials(self):
        result = preserve_existing_secrets([{"enabled": True}], [{"enabled": False, "token": "old"}])
        self.assertNotIn("token", result[0])

    def test_bad_crc_late_member_leaves_files_unchanged(self):
        path = self.archive([("config.json", {"recheckInterval": 90}), ("channels.json", [{"id": "CRC_MARKER"}])])
        path.write_bytes(path.read_bytes().replace(b"CRC_MARKER", b"CRC_BROKEN"))
        before = self.snapshots()
        with self.assertRaises(HTTPException) as error:
            self.runtime.restore_backup(path.name)
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.snapshots(), before)

    def test_duplicate_member_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            path = self.archive([("config.json", {}), ("config.json", {"recheckInterval": 90})])
        before = self.snapshots()
        with self.assertRaises(HTTPException):
            self.runtime.restore_backup(path.name)
        self.assertEqual(self.snapshots(), before)

    def test_runtime_reload_failure_restores_files_and_state(self):
        path = self.archive([("config.json", {"recheckInterval": 90}), ("channels.json", [{"id": "new"}])])
        before = self.snapshots()
        self.runtime.lar.loadChannels = mock.Mock(side_effect=RuntimeError("reload failure"))
        with self.assertRaises(HTTPException) as error:
            self.runtime.restore_backup(path.name)
        self.assertEqual(error.exception.status_code, 500)
        self.assertEqual(self.snapshots(), before)
        self.assertEqual(self.runtime.app.state.channels, [])

    def test_name_collisions_preserve_unowned_partial_and_archive(self):
        import datetime
        timestamp = datetime.datetime(2026, 1, 2, 3, 4, 5)
        filename = "backup_20260102_030405_manual_deadbeef"
        partial = self.runtime.backup_dir / (filename + ".partial")
        archive = self.runtime.backup_dir / (filename + ".zip")
        partial.write_bytes(b"other process partial")
        archive.write_bytes(b"existing archive")
        with mock.patch("module.operations_backup.datetime") as dates, mock.patch("module.operations_backup.uuid.uuid4", return_value=SimpleNamespace(hex="deadbeef")):
            dates.now.return_value = timestamp
            with self.assertRaises(FileExistsError):
                self.runtime.create_backup()
            self.assertEqual(partial.read_bytes(), b"other process partial")
            self.assertEqual(archive.read_bytes(), b"existing archive")
            partial.unlink()
            with self.assertRaises(FileExistsError):
                self.runtime.create_backup()
            self.assertEqual(archive.read_bytes(), b"existing archive")
            self.assertFalse(partial.exists())

    def test_restore_recovers_malformed_live_json_without_leaking_it(self):
        path = self.archive([("config.json", {"recheckInterval": 90})])
        (self.runtime.data_dir / "config.json").write_bytes(b'{"token":"broken-secret",')
        result = self.runtime.restore_backup(path.name)
        value = json.loads((self.runtime.data_dir / "config.json").read_text())
        self.assertEqual(value["recheckInterval"], 90)
        self.assertEqual(value["discord_webhook_url"], "live-secret")
        pre = result["pre_restore_backup"]
        self.assertEqual(pre["omitted_files"], ["config.json"])
        self.assertEqual(pre["omission_reason"], "invalid JSON")
        with zipfile.ZipFile(self.runtime.backup_path(pre["name"])) as archive:
            self.assertNotIn("config.json", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["omitted_files"], ["config.json"])
            self.assertNotIn(b"broken-secret", archive.read("manifest.json"))

    def test_failed_recovery_keeps_exact_malformed_original_bytes(self):
        path = self.archive([("config.json", {"recheckInterval": 90}), ("channels.json", [{"id": "new"}])])
        (self.runtime.data_dir / "config.json").write_bytes(b'{"token":"broken-secret",')
        before = self.snapshots()
        self.runtime.lar.loadChannels = mock.Mock(side_effect=RuntimeError("reload failure"))
        with self.assertRaises(HTTPException):
            self.runtime.restore_backup(path.name)
        self.assertEqual(self.snapshots(), before)

    def test_secret_merge_matches_nested_identity(self):
        old = {"hooks": [{"id": "a", "token": "a-secret"}, {"id": "b", "token": "b-secret"}]}
        incoming = {"hooks": [{"id": "b"}, {"id": "new"}]}
        result = preserve_existing_secrets(incoming, old)
        self.assertEqual(result["hooks"][0]["token"], "b-secret")
        self.assertNotIn("token", result["hooks"][1])
        self.assertEqual(sanitize_secrets({"telegram_bot_token": "a", "telegram_chat_id": "b", "enabled": True}), {"enabled": True})


if __name__ == "__main__":
    unittest.main()
