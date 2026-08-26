from __future__ import annotations

import os
import subprocess
import unittest

from module.recording_process import grouped_subprocess_kwargs


class RecordingProcessPolicyTests(unittest.TestCase):
    def test_grouped_process_policy_matches_platform(self):
        kwargs = grouped_subprocess_kwargs()
        if os.name == "nt":
            self.assertEqual(kwargs, {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP})
        elif hasattr(os, "setsid"):
            self.assertIs(kwargs.get("preexec_fn"), os.setsid)
            self.assertNotIn("creationflags", kwargs)
        else:
            self.assertEqual(kwargs, {})

    def test_each_call_returns_independent_kwargs(self):
        first = grouped_subprocess_kwargs()
        second = grouped_subprocess_kwargs()
        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
