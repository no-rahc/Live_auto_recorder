import queue
import unittest
from unittest.mock import patch

from module import recording_verify


class RecordingVerifyQueueTests(unittest.TestCase):
    def test_duplicate_file_is_coalesced_and_full_queue_is_rejected(self):
        pending = set()
        work_queue = queue.Queue(maxsize=1)
        with patch.object(recording_verify, "_VALIDATION_QUEUE", work_queue), patch.object(
            recording_verify, "_VALIDATION_PENDING", pending
        ), patch.object(recording_verify, "_ensure_validation_workers"):
            self.assertTrue(recording_verify.queue_validation("a", "one.ts"))
            self.assertFalse(recording_verify.queue_validation("a", "one.ts"))
            self.assertFalse(recording_verify.queue_validation("b", "two.ts"))

        self.assertEqual(work_queue.get_nowait(), ("a", "one.ts"))
        self.assertEqual(pending, {("a", "one.ts")})

    def test_worker_releases_pending_key_after_validation(self):
        item = ("a", "one.ts")
        pending = {item}
        with patch.object(recording_verify, "_VALIDATION_PENDING", pending), patch.object(
            recording_verify, "_run_validation"
        ) as run:
            recording_verify._process_validation_item(item)

        run.assert_called_once_with("a", "one.ts")
        self.assertNotIn(item, pending)

    def test_empty_filename_is_preserved_and_not_deduplicated(self):
        work_queue = queue.Queue(maxsize=4)
        pending = set()
        with patch.object(recording_verify, "_VALIDATION_QUEUE", work_queue), patch.object(
            recording_verify, "_VALIDATION_PENDING", pending
        ), patch.object(recording_verify, "_ensure_validation_workers"):
            self.assertTrue(recording_verify.queue_validation("a", ""))
            self.assertTrue(recording_verify.queue_validation("a", ""))

        self.assertEqual(work_queue.get_nowait(), ("a", ""))
        self.assertEqual(work_queue.get_nowait(), ("a", ""))
        self.assertEqual(pending, set())


if __name__ == "__main__":
    unittest.main()
