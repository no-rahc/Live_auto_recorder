import unittest
from unittest.mock import AsyncMock, patch

from module import live_recorder, recording_filename, recording_session


class RecordingFilenameTests(unittest.IsolatedAsyncioTestCase):
    def test_unknown_quality_uses_channel_setting_and_unknown_fps_is_removed(self):
        name = (
            "[2026-08-08] 카로띠 [버미육] 나랑 게이무 해줄사람 "
            "알 수 없는 품질알 수 없는 프레임 레이트.ts"
        )

        self.assertEqual(
            recording_filename.sanitize_recording_filename(name, quality="best"),
            "[2026-08-08] 카로띠 [버미육] 나랑 게이무 해줄사람 best.ts",
        )

    def test_unknown_fps_placeholder_group_is_removed_cleanly(self):
        name = "카로띠 1080p [알 수 없는 프레임 레이트].mp4"

        self.assertEqual(
            recording_filename.sanitize_recording_filename(name, quality="1080p"),
            "카로띠 1080p.mp4",
        )

    def test_known_quality_and_fps_are_preserved(self):
        name = "카로띠 1080p 60fps.ts"
        self.assertEqual(
            recording_filename.sanitize_recording_filename(name, quality="best"),
            name,
        )

    def test_live_recorder_unique_filename_hook_uses_session_quality(self):
        original = live_recorder.uniqueFilename
        captured = {}

        def fake_unique_filename(output_dir, filename, add_suffix=False):
            captured["output_dir"] = output_dir
            captured["filename"] = filename
            captured["add_suffix"] = add_suffix
            return filename

        token = None
        try:
            live_recorder.uniqueFilename = fake_unique_filename
            recording_filename.install_live_recorder_filename_sanitizer()
            token = recording_filename.begin_filename_context({"quality": "720p"})
            result = live_recorder.uniqueFilename(
                "/tmp",
                "방송 알 수 없는 품질 알 수 없는 프레임 레이트.ts",
                add_suffix=False,
            )
        finally:
            if token is not None:
                recording_filename.end_filename_context(token)
            live_recorder.uniqueFilename = original

        self.assertEqual(result, "방송 720p.ts")
        self.assertEqual(captured["filename"], "방송 720p.ts")
        self.assertFalse(captured["add_suffix"])

    async def test_chzzk_session_installs_and_cleans_filename_context(self):
        channel = {"id": "a", "platform": "chzzk", "quality": "1080p"}
        cfg = {"recheckInterval": 60}
        trace_token = object()
        filename_token = object()
        recorder = AsyncMock()

        with patch.object(
            recording_session, "begin_session", return_value=("session-id", trace_token)
        ), patch.object(recording_session, "end_session"), patch.object(
            recording_session, "install_live_recorder_filename_sanitizer"
        ) as install, patch.object(
            recording_session, "begin_filename_context", return_value=filename_token
        ) as begin_filename, patch.object(
            recording_session, "end_filename_context"
        ) as end_filename, patch.object(
            recording_session, "loadCookies", return_value={}
        ), patch.object(
            recording_session, "chzzkStartRecording", new=recorder
        ):
            await recording_session.start_session(channel, "chzzk", cfg)

        install.assert_called_once_with()
        begin_filename.assert_called_once_with(channel)
        end_filename.assert_called_once_with(filename_token)
        recorder.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
