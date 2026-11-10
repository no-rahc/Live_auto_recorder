"""Read-only V2 readiness and mounted-storage failure regression coverage."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.check_v2_readiness import evaluate


class ReadinessPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / "data"
        self.media = self.root / "media"
        self.data.mkdir()
        self.media.mkdir()

    def test_missing_mount_marker_fails_without_creating_files(self):
        before = set(self.root.rglob("*"))
        report = evaluate(self.data, self.media)
        self.assertFalse(report["ready"])
        self.assertTrue(report["read_only"])
        self.assertEqual(before, set(self.root.rglob("*")))
        self.assertFalse((self.media / ".lar-storage-id").exists())

    def test_wrong_mount_identity_is_blocked(self):
        (self.media / ".lar-storage-id").write_text("NAS-A")
        report = evaluate(self.data, self.media, expected_marker="NAS-B")
        self.assertFalse(report["ready"])

    def test_valid_local_database_and_recordings_marker_pass_read_only(self):
        (self.media / ".lar-storage-id").write_text("NAS-A")
        before = set(self.root.rglob("*"))
        report = evaluate(self.data, self.media, expected_marker="NAS-A")
        self.assertTrue(report["ready"], report)
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_mounted_database_metadata_is_rejected(self):
        (self.media / ".lar-storage-id").write_text("NAS-A")
        remote = {"filesystem": "nfs4", "mount_point": str(self.data), "mount_id": "1"}
        with mock.patch("module.v2_storage.filesystem_info", return_value=remote):
            report = evaluate(self.data, self.media, expected_marker="NAS-A")
        self.assertFalse(report["ready"])
        self.assertIn("local persistent", str(report["data"]["errors"]))
