import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from module import recording_catalog
from module.readiness import readiness_snapshot


class FakeTask:
    def __init__(self, done=False):
        self._done = done

    def done(self):
        return self._done


class ReadinessTests(unittest.TestCase):
    def _runtime(self, root: Path, *, storage_blocked=False, dead_task=False):
        data_dir = root / "data"
        recording_root = root / "recordings"
        operations = SimpleNamespace(
            data_dir=data_dir,
            recording_root=recording_root,
            _started=True,
            background_tasks=[FakeTask(done=dead_task), FakeTask()],
            storage_info=lambda: {
                "status": "critical" if storage_blocked else "ok",
                "recording_blocked": storage_blocked,
                "free_percent": 4.0 if storage_blocked else 50.0,
            },
        )
        platform = SimpleNamespace(
            _started=True,
            tasks=[FakeTask(), FakeTask()],
        )
        return operations, platform

    def test_ready_when_paths_catalog_storage_and_workers_are_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            operations, platform = self._runtime(root)
            with patch.object(recording_catalog, "DB_PATH", root / "data" / "recordings.sqlite3"):
                snapshot = readiness_snapshot(operations, platform)

        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["status"], "ready")
        self.assertTrue(all(item["ok"] for item in snapshot["checks"].values()))

    def test_not_ready_when_background_worker_has_died(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            operations, platform = self._runtime(root, dead_task=True)
            with patch.object(recording_catalog, "DB_PATH", root / "data" / "recordings.sqlite3"):
                snapshot = readiness_snapshot(operations, platform)

        self.assertFalse(snapshot["ready"])
        self.assertFalse(snapshot["checks"]["operations_tasks"]["ok"])

    def test_not_ready_when_recording_storage_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            operations, platform = self._runtime(root, storage_blocked=True)
            with patch.object(recording_catalog, "DB_PATH", root / "data" / "recordings.sqlite3"):
                snapshot = readiness_snapshot(operations, platform)

        self.assertFalse(snapshot["ready"])
        self.assertFalse(snapshot["checks"]["storage"]["ok"])


if __name__ == "__main__":
    unittest.main()
