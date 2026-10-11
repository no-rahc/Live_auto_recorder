"""Exercise destination validation through the helpers and installed HTTP routes."""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lar_app.routers.files import install_file_routes
from module import file_manager


class FileDestinationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "allowed"
        self.root.mkdir()
        self.outside = self.base / "outside"
        self.outside.mkdir()
        self.src = self.root / "original.ts"
        self.src.write_text("original recording", encoding="utf-8")
        self.busy = []

        async def require_login():
            return True

        core = SimpleNamespace(
            **{name: getattr(file_manager, name) for name in (
                "buildAllowedRoots", "ensureInRoots", "isLocked", "renamePath", "mkdirPath"
            )},
            requireLogin=require_login,
            busyFilePaths=lambda manager, channels: self.busy,
            recorder_manager=None,
        )
        self.app = FastAPI()
        self.app.state.config = {
            "fileManagerEnabled": True,
            "fileManagerReadOnly": False,
            "fileManagerMode": "whitelist",
            "fileManagerRoots": [str(self.root)],
        }
        self.app.state.channels = []
        self.app.state.channels_lock = asyncio.Lock()
        install_file_routes(self.app, core)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def post(self, operation, name, path=None):
        if path is None:
            path = self.src if operation == "rename" else self.root
        return self.client.post(
            f"/api/files/{operation}",
            json={"path": str(path), "new_name": name},
        )

    def symlink(self, target, path, *, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")

    def test_helpers_reject_paths_and_nonstring_names(self):
        invalid_names = [
            None, "", " ", ".", "..", "/absolute", "\\absolute",
            "../escape", "..\\escape", "nested/name", "nested\\name",
            "C:relative", "C:\\absolute", "//server/share", "\\\\server\\share",
            "recording.ts:stream", "bad\x00name", "bad\nname", [], {}, 1, True,
        ]
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    file_manager.renamePath(str(self.src), name)
                with self.assertRaises(ValueError):
                    file_manager.mkdirPath(str(self.root), name)
        self.assertEqual(self.src.read_text(encoding="utf-8"), "original recording")
        self.assertEqual(list(self.root.iterdir()), [self.src])

    def test_routes_reject_invalid_names_without_mutation(self):
        target = self.outside / "preserved.ts"
        target.write_text("keep me", encoding="utf-8")
        invalid_names = [
            None, "", " ", ".", "..", str(target), "../outside/preserved.ts",
            "..\\outside\\preserved.ts", "nested/name", "nested\\name",
            "C:relative", "C:\\absolute", "//server/share", "\\\\server\\share",
            "recording.ts:stream", "bad\x00name", "bad\nname", ["name"], {"name": 1}, 1, True,
        ]
        for operation in ("rename", "mkdir"):
            for name in invalid_names:
                with self.subTest(operation=operation, name=name):
                    self.assertEqual(self.post(operation, name).status_code, 400)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(self.src.read_text(encoding="utf-8"), "original recording")
        self.assertEqual(list(self.root.iterdir()), [self.src])

    def test_routes_reject_nonstring_paths(self):
        for operation in ("rename", "mkdir"):
            for path in (None, [], ["path"], {"path": 1}, 1, True):
                with self.subTest(operation=operation, path=path):
                    response = self.client.post(
                        f"/api/files/{operation}", json={"path": path, "new_name": "safe"}
                    )
                    self.assertEqual(response.status_code, 400)

    def test_normal_unicode_and_hidden_names_are_preserved(self):
        name = "녹화 영상 01.ts"
        response = self.post("rename", name)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], str(self.root / name))
        self.assertEqual((self.root / name).read_text(encoding="utf-8"), "original recording")
        self.assertFalse(self.src.exists())
        response = self.post("mkdir", ".archive")
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.root / ".archive").is_dir())

    def test_windows_device_and_normalized_names_are_rejected(self):
        with mock.patch.object(file_manager.os, "name", "nt"):
            for name in ("CON", "con.txt", "NUL", "LPT1", "COM².log", "CON .txt", "dir.", "dir ", "a?b"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    file_manager.validateBasename(name)
            self.assertEqual(file_manager.validateBasename("normal.ts"), "normal.ts")

    def test_rename_same_name_is_a_noop(self):
        response = self.post("rename", self.src.name)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.src.read_text(encoding="utf-8"), "original recording")

    def test_rename_rejects_existing_file_without_overwrite(self):
        target = self.root / "existing.ts"
        target.write_text("existing recording", encoding="utf-8")
        response = self.post("rename", target.name)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(target.read_text(encoding="utf-8"), "existing recording")
        self.assertEqual(self.src.read_text(encoding="utf-8"), "original recording")

    def test_rename_rejects_existing_directory(self):
        source = self.root / "source-directory"
        source.mkdir()
        target = self.root / "destination-directory"
        target.mkdir()
        self.assertEqual(self.post("rename", target.name, source).status_code, 409)
        self.assertTrue(source.is_dir())
        self.assertTrue(target.is_dir())

    def test_rename_rejects_dangling_symlink_without_removing_it(self):
        target = self.root / "dangling.ts"
        self.symlink(self.root / "missing.ts", target)
        self.assertEqual(self.post("rename", target.name).status_code, 409)
        self.assertTrue(target.is_symlink())
        self.assertTrue(self.src.is_file())

    def test_rename_rejects_symlink_to_existing_allowed_file(self):
        existing = self.root / "existing.ts"
        existing.write_text("keep me", encoding="utf-8")
        target = self.root / "link.ts"
        self.symlink(existing, target)
        self.assertEqual(self.post("rename", target.name).status_code, 409)
        self.assertTrue(target.is_symlink())
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep me")

    def test_rename_revalidates_destination_outside_allowed_root(self):
        target = self.outside / "keep.ts"
        target.write_text("keep me", encoding="utf-8")
        link = self.root / "link.ts"
        self.symlink(target, link)
        self.assertEqual(self.post("rename", link.name).status_code, 403)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")
        self.assertTrue(self.src.is_file())

    def test_mkdir_revalidates_destination_outside_allowed_root(self):
        link = self.root / "link-directory"
        self.symlink(self.outside, link, directory=True)
        self.assertEqual(self.post("mkdir", link.name).status_code, 403)
        self.assertTrue(link.is_symlink())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_routes_revalidate_blacklisted_destination(self):
        self.app.state.config["fileManagerMode"] = "blacklist"
        target = Path(r"C:\Windows") if os.name == "nt" else Path("/etc")
        link = self.root / "system-directory"
        self.symlink(target, link, directory=True)
        for operation in ("mkdir", "rename"):
            with self.subTest(operation=operation):
                self.assertEqual(self.post(operation, link.name).status_code, 403)
        self.assertTrue(link.is_symlink())
        self.assertTrue(self.src.is_file())

    def test_rename_cannot_move_an_allowed_root_to_an_unapproved_sibling(self):
        self.assertEqual(self.post("rename", "unapproved-root", self.root).status_code, 403)
        self.assertTrue(self.root.is_dir())
        self.assertFalse((self.base / "unapproved-root").exists())

    def test_source_and_parent_outside_allowed_roots_are_rejected(self):
        outside_file = self.outside / "outside.ts"
        outside_file.write_text("outside recording", encoding="utf-8")
        self.assertEqual(self.post("rename", "renamed.ts", outside_file).status_code, 403)
        self.assertEqual(self.post("mkdir", "new-directory", self.outside).status_code, 403)
        self.assertTrue(outside_file.is_file())
        self.assertFalse((self.outside / "new-directory").exists())

    def test_mkdir_preserves_existing_directory_success(self):
        for _ in range(2):
            self.assertEqual(self.post("mkdir", "directory").status_code, 200)
        self.assertTrue((self.root / "directory").is_dir())

    def test_mkdir_rejects_existing_file(self):
        self.assertEqual(self.post("mkdir", self.src.name).status_code, 409)
        self.assertEqual(self.src.read_text(encoding="utf-8"), "original recording")

    def test_rename_rejects_busy_source(self):
        self.busy.append(str(self.src))
        self.assertEqual(self.post("rename", "renamed.ts").status_code, 423)
        self.assertTrue(self.src.is_file())

    def test_rename_rejects_directory_containing_busy_file(self):
        source = self.root / "recordings"
        source.mkdir()
        busy = source / "live.ts"
        busy.write_text("recording", encoding="utf-8")
        self.busy.append(str(busy))
        self.assertEqual(self.post("rename", "renamed-directory", source).status_code, 423)
        self.assertTrue(busy.is_file())

    def test_rename_rejects_busy_destination(self):
        target = self.root / "live.ts"
        target.write_text("recording", encoding="utf-8")
        self.busy.append(str(target))
        self.assertEqual(self.post("rename", target.name).status_code, 423)
        self.assertEqual(target.read_text(encoding="utf-8"), "recording")
        self.assertTrue(self.src.is_file())

    def test_busy_destination_is_locked_even_before_it_exists(self):
        target = self.root / "starting.ts"
        self.busy.append(str(target))
        for operation in ("mkdir", "rename"):
            with self.subTest(operation=operation):
                self.assertEqual(self.post(operation, target.name).status_code, 423)
        self.assertFalse(target.exists())
        self.assertTrue(self.src.is_file())

    def test_routes_reject_destination_directory_containing_busy_file(self):
        target = self.root / "recordings"
        target.mkdir()
        busy = target / "live.ts"
        busy.write_text("recording", encoding="utf-8")
        self.busy.append(str(busy))
        for operation in ("mkdir", "rename"):
            with self.subTest(operation=operation):
                self.assertEqual(self.post(operation, target.name).status_code, 423)
        self.assertTrue(busy.is_file())

    def test_unrelated_siblings_of_recording_remain_writable(self):
        self.busy.append(str(self.root / "live.ts"))
        self.assertEqual(self.post("rename", "renamed.ts").status_code, 200)
        self.assertEqual(self.post("mkdir", "new-directory").status_code, 200)

    def test_lock_uses_path_components_not_prefixes(self):
        busy = str(self.root / "recordings" / "live.ts")
        self.assertTrue(file_manager.isLocked(busy, [busy]))
        self.assertTrue(file_manager.isLocked(str(self.root / "recordings"), [busy]))
        self.assertTrue(file_manager.isLocked(str(self.root), [busy]))
        self.assertFalse(file_manager.isLocked(str(self.root / "recordings-old"), [busy]))
        self.assertFalse(file_manager.isLocked(str(self.root / "recordings" / "other.ts"), [busy]))

    def test_read_only_mode_still_blocks_both_routes(self):
        self.app.state.config["fileManagerReadOnly"] = True
        for operation in ("mkdir", "rename"):
            with self.subTest(operation=operation):
                self.assertEqual(self.post(operation, "safe").status_code, 403)
        self.assertTrue(self.src.is_file())
        self.assertFalse((self.root / "safe").exists())

    def test_missing_rename_source_returns_404(self):
        self.assertEqual(self.post("rename", "new.ts", self.root / "missing.ts").status_code, 404)


if __name__ == "__main__":
    unittest.main()
