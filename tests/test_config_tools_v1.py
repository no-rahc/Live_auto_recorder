from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from module.config_tools_v1 import _check_path, _probe_encoders


class ConfigToolsTests(unittest.TestCase):
    def test_existing_directory_reports_capacity_and_writable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _check_path(directory)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["exists"])
        self.assertTrue(result["writable"])
        self.assertGreater(result["total_gb"], 0)

    def test_missing_child_uses_existing_parent_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / "new" / "recordings"
            result = _check_path(str(child))
            self.assertFalse(child.exists())
        self.assertFalse(result["exists"])
        self.assertTrue(result["writable"])

    def test_relative_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "절대 경로"):
            _check_path("relative/path")

    @unittest.skipIf(os.name == "nt", "shell fixture is POSIX-only")
    def test_encoder_probe_marks_reported_encoders(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "ffmpeg"
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' ' V..... libx264 H.264' ' V..... h264_nvenc NVIDIA NVENC'\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            result = _probe_encoders(str(executable))
        available = {item["id"]: item["available"] for item in result["encoders"]}
        self.assertTrue(available["libx264"])
        self.assertTrue(available["h264_nvenc"])
        self.assertFalse(available["hevc_nvenc"])
        self.assertTrue(result["hardware_available"])


if __name__ == "__main__":
    unittest.main()
