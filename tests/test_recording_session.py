import unittest
from unittest.mock import AsyncMock, patch

from module import recording_adapter, recording_session


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
            await recording_session.start_session(channel, "chzzk", cfg, is_user_request=True)

        kwargs = recorder.await_args.kwargs
        self.assertEqual(kwargs["plugin_type"], "basic")
        self.assertEqual(kwargs["timemachine_time_shift"], 10)
        self.assertEqual(kwargs["recheckInterval"], 45)
        self.assertTrue(kwargs["autoPostProcessing"])
        self.assertTrue(kwargs["splitRecordingMode"])
        self.assertEqual(kwargs["post_cfg"]["video_codec"], "libx264")
        end.assert_called_once_with("a", "session-id", token)


if __name__ == "__main__":
    unittest.main()
