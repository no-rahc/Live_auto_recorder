import unittest
from unittest.mock import AsyncMock, patch

from module import recording_adapter, recording_session
from module.recording_attempt import RecorderAttemptOutcome
from module.recording_session import SessionOutcome


class RecordingSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_keeps_legacy_start_session_api_as_thin_wrapper(self):
        channel = {"id": "a", "platform": "chzzk"}
        cfg = {"recheckInterval": 60}
        runner = AsyncMock()
        with patch.object(recording_adapter, "start_session", new=runner):
            await recording_adapter.startSession(channel, "chzzk", cfg, is_user_request=True)

        runner.assert_awaited_once_with(channel, "chzzk", cfg, is_user_request=True)

    async def test_chzzk_orchestrator_preserves_existing_recorder_options(self):
        channel = {"id": "a", "platform": "chzzk", "plugin_type": "invalid"}
        cfg = {
            "recheckInterval": 45,
            "autoStopInterval": 3,
            "autoPostProcessing": True,
            "filenamePattern": "{recording_time}{file_extension}",
            "timemachine_time_shift": 99,
            "splitRecordingMode": True,
            "video_codec": "libx264",
        }
        recorder = AsyncMock()
        token = object()
        with patch.object(recording_session, "loadCookies", return_value={"NID_SES": "cookie"}), patch.object(
            recording_session, "begin_session", return_value=("session-id", token)
        ), patch.object(recording_session, "end_session") as end, patch.object(
            recording_session, "chzzkStartRecording", new=recorder
        ):
            outcome = await recording_session.start_session(channel, "chzzk", cfg, is_user_request=True)

        self.assertEqual(outcome, SessionOutcome.COMPLETED)
        kwargs = recorder.await_args.kwargs
        self.assertEqual(kwargs["plugin_type"], "basic")
        self.assertEqual(kwargs["timemachine_time_shift"], 10)
        self.assertEqual(kwargs["recheckInterval"], 45)
        self.assertTrue(kwargs["autoPostProcessing"])
        self.assertTrue(kwargs["splitRecordingMode"])
        self.assertTrue(kwargs["single_attempt"])
        self.assertEqual(kwargs["post_cfg"]["video_codec"], "libx264")
        end.assert_called_once_with("a", "session-id", token)

    async def test_explicit_attempt_outcome_is_mapped_for_fsm(self):
        channel = {"id": "y", "name": "YouTube", "platform": "youtube", "record_enabled": True}
        recorder = AsyncMock(return_value=RecorderAttemptOutcome.OFFLINE)
        with patch.object(recording_session, "yloadCookies", return_value=None), patch.object(
            recording_session, "ytStartRecording", new=recorder
        ):
            outcome = await recording_session.record_once(channel, "youtube", {"recheckInterval": 30})

        self.assertEqual(outcome, SessionOutcome.OFFLINE)
        self.assertTrue(recorder.await_args.kwargs["single_attempt"])

    async def test_unsupported_platform_returns_explicit_outcome(self):
        token = object()
        with patch.object(
            recording_session, "begin_session", return_value=("session-id", token)
        ), patch.object(recording_session, "end_session") as end:
            outcome = await recording_session.start_session({"id": "x"}, "unknown", {})

        self.assertEqual(outcome, SessionOutcome.UNSUPPORTED)
        end.assert_called_once_with("x", "session-id", token)

    async def test_start_session_wraps_record_once_and_preserves_outcome(self):
        token = object()
        runner = AsyncMock(return_value=SessionOutcome.RECHECK)
        with patch.object(
            recording_session, "begin_session", return_value=("session-id", token)
        ), patch.object(recording_session, "end_session") as end, patch.object(
            recording_session, "record_once", new=runner
        ):
            outcome = await recording_session.start_session({"id": "x"}, "youtube", {"recheckInterval": 30})

        self.assertEqual(outcome, SessionOutcome.RECHECK)
        runner.assert_awaited_once_with(
            {"id": "x"}, "youtube", {"recheckInterval": 30}, is_user_request=False
        )
        end.assert_called_once_with("x", "session-id", token)


if __name__ == "__main__":
    unittest.main()
