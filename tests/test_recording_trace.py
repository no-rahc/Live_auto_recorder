import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from module import recording_history
from module.recording_trace import append_stderr, begin_session, end_session, trace_fields


class RecordingTraceTests(unittest.TestCase):
    def test_session_trace_is_bounded_redacted_and_survives_session_end(self):
        session_id, token = begin_session("trace-a", "chzzk")
        try:
            append_stderr(
                "trace-a",
                "network failure NID_SES=top-secret; Authorization: Bearer hidden-token",
                source="pid:123",
            )
            active = trace_fields("trace-a", include_tail=True)
            self.assertEqual(active["session_id"], session_id)
            self.assertTrue(active["session_active"])
            self.assertIn("network failure", active["process_stderr_tail"])
            self.assertNotIn("top-secret", active["process_stderr_tail"])
            self.assertNotIn("hidden-token", active["process_stderr_tail"])
            self.assertIn("NID_SES=***", active["process_stderr_tail"])
        finally:
            end_session("trace-a", session_id, token)

        ended = trace_fields("trace-a", include_tail=True)
        self.assertFalse(ended["session_active"])
        self.assertGreater(ended["session_ended_epoch"], 0)
        self.assertIn("network failure", ended["process_stderr_tail"])

    def test_stop_history_contains_session_id_and_stderr_tail(self):
        session_id, token = begin_session("trace-b", "chzzk")
        append_stderr("trace-b", "streamlink exited with code 7", source="pid:456")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                history_path = Path(tmp) / "recording_history.jsonl"
                with patch.object(recording_history, "HISTORY_PATH", str(history_path)), patch.object(
                    recording_history, "_mirror_event"
                ):
                    recording_history.log_event(
                        "trace-b",
                        "Trace Channel",
                        "chzzk",
                        "recording_stop_requested",
                        extra={"reason": "health_restart", "process_exit_code": 7},
                    )

                entry = json.loads(history_path.read_text(encoding="utf-8").strip())
                self.assertEqual(entry["session_id"], session_id)
                self.assertEqual(entry["reason"], "health_restart")
                self.assertEqual(entry["process_exit_code"], 7)
                self.assertIn("streamlink exited with code 7", entry["process_stderr_tail"])
        finally:
            end_session("trace-b", session_id, token)


if __name__ == "__main__":
    unittest.main()
