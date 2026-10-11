"""Concurrent merge admission and no-clobber media publication regressions."""
from __future__ import annotations

import errno
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from module import recording_merge


class RecordingMergeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = [self.root / "first.ts", self.root / "second.ts"]
        for path in self.paths:
            path.write_bytes(b"source recording")
        self.group = {"segments": [{"file_path": str(path)} for path in self.paths]}
        self.catalog = self.patch("get_broadcast", return_value=self.group)
        self.status = self.patch("set_broadcast_merge")
        self.patch("_ffmpeg_path", return_value="test-ffmpeg")
        self.verify = self.patch("_verify_merged")
        self.run = self.patch("subprocess.run", side_effect=self.fake_ffmpeg)

    def patch(self, name, **kwargs):
        patcher = mock.patch(f"module.recording_merge.{name}", **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def fake_ffmpeg(self, args, **kwargs):
        self.assertIn("-n", args)
        self.assertNotIn("-y", args)
        Path(args[-1]).write_bytes(b"merged recording")
        return subprocess.CompletedProcess(args, 0, "", "")

    def assert_no_temps(self):
        self.assertEqual(list(self.root.glob("lar-merge-*")), [])

    def test_same_broadcast_rejected_before_catalog_or_file_changes(self):
        entered, release = threading.Event(), threading.Event()

        def blocked_ffmpeg(args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5), "concurrent test did not release FFmpeg")
            return self.fake_ffmpeg(args, **kwargs)

        self.run.side_effect = blocked_ffmpeg
        with ThreadPoolExecutor(max_workers=2) as pool:
            active = pool.submit(recording_merge.merge_broadcast, "same")
            try:
                self.assertTrue(entered.wait(5))
                before = list(self.status.call_args_list)
                rejected = pool.submit(recording_merge.merge_broadcast, "same", delete_segments=True)
                with self.assertRaises(recording_merge.MergeInProgressError):
                    rejected.result(timeout=5)
                self.assertEqual(self.status.call_args_list, before)
                self.assertEqual(self.catalog.call_count, 1)
                self.assertEqual(self.run.call_count, 1)
                self.assertTrue(all(path.exists() for path in self.paths))
            finally:
                release.set()
            result = active.result(timeout=5)
        self.assertEqual(Path(result["output_path"]).read_bytes(), b"merged recording")
        self.assertEqual([call.kwargs["status"] for call in self.status.call_args_list], ["merging", "completed"])
        self.assert_no_temps()

    def test_distinct_broadcasts_with_same_output_stem_publish_independently(self):
        rendezvous = threading.Barrier(2)
        temp_paths = []

        def concurrent_ffmpeg(args, **kwargs):
            temp_paths.append(Path(args[-1]))
            rendezvous.wait(timeout=5)
            return self.fake_ffmpeg(args, **kwargs)

        self.run.side_effect = concurrent_ffmpeg
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(recording_merge.merge_broadcast, bid) for bid in ("one", "two")]
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual(len(set(temp_paths)), 2)
        outputs = {Path(result["output_path"]) for result in results}
        self.assertEqual(outputs, {self.root / "first.merged.ts", self.root / "first.merged-2.ts"})
        self.assertTrue(all(path.read_bytes() == b"merged recording" for path in outputs))
        self.assert_no_temps()

    def test_failed_concurrent_attempt_cannot_remove_successful_output(self):
        rendezvous = threading.Barrier(2)
        published = threading.Event()
        original_publish = recording_merge._publish_merged
        local = threading.local()

        def ffmpeg(args, **kwargs):
            rendezvous.wait(timeout=5)
            return self.fake_ffmpeg(args, **kwargs)

        def verify(path):
            if local.fail:
                self.assertTrue(published.wait(5))
                raise RuntimeError("invalid media")

        def publish(*args):
            output = original_publish(*args)
            published.set()
            return output

        def merge(bid, fail):
            local.fail = fail
            return recording_merge.merge_broadcast(bid, delete_segments=fail)

        self.run.side_effect = ffmpeg
        self.verify.side_effect = verify
        with mock.patch.object(recording_merge, "_publish_merged", side_effect=publish):
            with ThreadPoolExecutor(max_workers=2) as pool:
                success = pool.submit(merge, "success", False)
                failure = pool.submit(merge, "failure", True)
                with self.assertRaisesRegex(RuntimeError, "invalid media"):
                    failure.result(timeout=5)
                result = success.result(timeout=5)
        self.assertEqual(Path(result["output_path"]).read_bytes(), b"merged recording")
        self.assertTrue(all(path.exists() for path in self.paths))
        self.assert_no_temps()

    def test_publish_collision_created_at_link_time_is_preserved(self):
        original_link = recording_merge.os.link
        collision = self.root / "first.merged.ts"

        def racing_link(src, dst):
            if dst == collision:
                collision.write_bytes(b"another writer's output")
            return original_link(src, dst)

        with mock.patch.object(recording_merge.os, "link", side_effect=racing_link):
            result = recording_merge.merge_broadcast("race")
        self.assertEqual(collision.read_bytes(), b"another writer's output")
        self.assertEqual(Path(result["output_path"]), self.root / "first.merged-2.ts")
        self.assert_no_temps()

    def test_validation_failure_preserves_sources_existing_output_and_legacy_partial(self):
        existing = self.root / "first.merged.ts"
        legacy_partial = self.root / "first.merged-2.partial.ts"
        existing.write_bytes(b"existing output")
        legacy_partial.write_bytes(b"other active attempt")
        self.verify.side_effect = RuntimeError("invalid duration")
        with self.assertRaisesRegex(RuntimeError, "invalid duration"):
            recording_merge.merge_broadcast("invalid", delete_segments=True)
        self.assertEqual(existing.read_bytes(), b"existing output")
        self.assertEqual(legacy_partial.read_bytes(), b"other active attempt")
        self.assertTrue(all(path.exists() for path in self.paths))
        self.assert_no_temps()
        # Failure must also release admission so a retry can proceed.
        self.verify.side_effect = None
        self.assertEqual(recording_merge.merge_broadcast("invalid")["status"], "completed")

    def test_ffmpeg_failures_cleanup_only_private_files_and_allow_retry(self):
        for mode in ("error", "timeout", "empty", "missing"):
            with self.subTest(mode=mode):
                def fail(args, **kwargs):
                    if mode != "missing":
                        Path(args[-1]).write_bytes(b"" if mode == "empty" else b"partial")
                    if mode == "timeout":
                        raise subprocess.TimeoutExpired(args, 1)
                    return subprocess.CompletedProcess(args, 1 if mode == "error" else 0, "", "concat failed")

                self.run.side_effect = fail
                with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                    recording_merge.merge_broadcast("ffmpeg-failure", delete_segments=True)
                self.assertTrue(all(path.exists() for path in self.paths))
                self.assert_no_temps()
        self.run.side_effect = self.fake_ffmpeg
        self.assertEqual(recording_merge.merge_broadcast("ffmpeg-failure")["status"], "completed")

    def test_catalog_failure_after_publication_keeps_verified_output_and_sources(self):
        def update(bid, **kwargs):
            if kwargs["status"] == "completed":
                raise RuntimeError("catalog unavailable")

        self.status.side_effect = update
        with self.assertRaisesRegex(RuntimeError, "catalog unavailable"):
            recording_merge.merge_broadcast("catalog-failure", delete_segments=True)
        self.assertEqual((self.root / "first.merged.ts").read_bytes(), b"merged recording")
        self.assertTrue(all(path.exists() for path in self.paths))
        self.assert_no_temps()

    def test_unsupported_hardlinks_fail_without_replacing_or_deleting_files(self):
        with mock.patch.object(recording_merge.os, "link", side_effect=OSError(errno.EPERM, "no hardlinks")):
            with self.assertRaises(OSError):
                recording_merge.merge_broadcast("unsupported", delete_segments=True)
        self.assertEqual(set(self.root.iterdir()), set(self.paths))
        self.assert_no_temps()

    def test_dangling_symlink_is_a_collision_not_an_available_output(self):
        existing = self.root / "first.merged.ts"
        try:
            existing.symlink_to(self.root / "missing.ts")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(str(exc))
        result = recording_merge.merge_broadcast("symlink")
        self.assertTrue(existing.is_symlink())
        self.assertEqual(Path(result["output_path"]), self.root / "first.merged-2.ts")
        self.assertFalse((self.root / "missing.ts").exists())
        self.assert_no_temps()

    def test_success_verifies_privately_and_deletes_sources_only_after_completion(self):
        def verify(path):
            self.assertIn("lar-merge-", str(path))
            self.assertFalse((self.root / "first.merged.ts").exists())

        def status(bid, **kwargs):
            if kwargs["status"] == "completed":
                self.assertTrue(all(path.exists() for path in self.paths))
                self.assertTrue(Path(kwargs["output_path"]).is_file())

        self.verify.side_effect = verify
        self.status.side_effect = status
        result = recording_merge.merge_broadcast("delete", delete_segments=True)
        self.assertFalse(any(path.exists() for path in self.paths))
        self.assertEqual(result["size"], len(b"merged recording"))
        self.assertEqual(Path(result["output_path"]).read_bytes(), b"merged recording")
        self.assert_no_temps()

    def test_admission_released_when_input_validation_fails(self):
        self.catalog.return_value = None
        with self.assertRaises(ValueError):
            recording_merge.merge_broadcast("missing")
        self.catalog.return_value = self.group
        self.assertEqual(recording_merge.merge_broadcast("missing")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
