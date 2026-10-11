"""Recording cleanup must never consume an unverified or unrelated recording."""
import asyncio
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from module import live_recorder, youtube_recorder


class SegmentOutputSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.session = self.root / "session"
        self.session.mkdir()
        self.destination = self.root / "processed"
        for name, value in (
            ("getFFmpeg", Mock(return_value="ffmpeg")),
            ("resolveFFprobe", Mock(return_value="ffprobe")),
            ("get_media_duration", Mock(return_value=3.0)),
            ("logger", Mock()),
        ):
            patcher = patch.object(live_recorder, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def segment(self, index=0, *, extension=".ts", tiny=False):
        path = self.session / f"recording_{index:03d}{extension}"
        path.write_bytes(b"raw" if tiny else b"raw recording" * 4096)
        return path

    async def run_batch(self, encoder, *, extension=".ts", **options):
        config = {"deleteAfterPostProcessing": True, **options}
        with patch.object(live_recorder, "ffAsync", AsyncMock(side_effect=encoder)) as ff:
            await live_recorder.batchEncodeSegments(
                str(self.session), "recording", 0, config, input_ext=extension
            )
        return ff

    @staticmethod
    async def encode_successfully(command, **kwargs):
        Path(command[-1]).write_bytes(b"encoded output")

    async def test_only_successful_sources_are_deleted_and_published(self):
        successful = self.segment(0)
        failed = self.segment(1)
        skipped = self.segment(2, tiny=True)

        async def mixed_results(command, **kwargs):
            source = Path(command[command.index("-i") + 1])
            Path(command[-1]).write_bytes(b"partial" if source == failed else b"encoded")
            if source == failed:
                raise subprocess.CalledProcessError(1, command)

        await self.run_batch(
            mixed_results,
            removeFixedPrefix=True,
            moveAfterProcessingEnabled=True,
            moveAfterProcessing=str(self.destination),
        )

        self.assertFalse(successful.exists())
        self.assertTrue(failed.exists())
        self.assertTrue(skipped.exists())
        self.assertEqual(
            [p.name for p in self.destination.iterdir()], ["recording_000.mp4"]
        )
        self.assertEqual(
            (self.session / "fixed_recording_001.mp4").read_bytes(), b"partial"
        )

    async def test_all_three_failed_attempts_preserve_source(self):
        source = self.segment()

        async def fail(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, command)

        ff = await self.run_batch(fail, removeFixedPrefix=True)
        self.assertEqual(ff.await_count, 3)
        self.assertTrue(source.exists())
        self.assertFalse((self.session / "recording_000.mp4").exists())

    async def test_success_on_second_attempt_allows_source_cleanup(self):
        source = self.segment()
        attempts = 0

        async def retry(command, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise subprocess.CalledProcessError(1, command)
            Path(command[-1]).write_bytes(b"encoded output")

        await self.run_batch(retry)
        self.assertEqual(attempts, 2)
        self.assertFalse(source.exists())

    async def test_zero_exit_without_output_preserves_source(self):
        source = self.segment()
        await self.run_batch(AsyncMock())
        self.assertTrue(source.exists())

    async def test_empty_output_preserves_source(self):
        source = self.segment()

        async def empty_output(command, **kwargs):
            Path(command[-1]).touch()

        await self.run_batch(empty_output)
        self.assertTrue(source.exists())

    async def test_output_aliasing_source_is_not_success(self):
        source = self.segment()

        async def alias_output(command, **kwargs):
            os.link(source, command[-1])

        await self.run_batch(alias_output, removeFixedPrefix=True)
        self.assertTrue(source.exists())
        self.assertFalse((self.session / "recording_000.mp4").exists())

    async def test_stale_output_is_not_overwritten_or_used_as_success(self):
        source = self.segment()
        stale = self.session / "fixed_recording_000.mp4"
        stale.write_bytes(b"previous recording")
        ff = await self.run_batch(AsyncMock(), removeFixedPrefix=True)
        self.assertNotEqual(ff.await_args.args[0][-1], str(stale))
        self.assertEqual(stale.read_bytes(), b"previous recording")
        self.assertTrue(source.exists())

    async def test_existing_source_alias_is_not_overwritten(self):
        source = self.segment()
        original = source.read_bytes()
        alias = self.session / "fixed_recording_000.mp4"
        os.link(source, alias)
        ff = await self.run_batch(self.encode_successfully, deleteAfterPostProcessing=False)
        self.assertNotEqual(ff.await_args.args[0][-1], str(alias))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)

    async def test_retained_mp4_is_neither_overwritten_nor_moved(self):
        source = self.segment(extension=".mp4")
        original = source.read_bytes()
        await self.run_batch(
            self.encode_successfully,
            extension=".mp4",
            deleteAfterPostProcessing=False,
            removeFixedPrefix=True,
            moveAfterProcessingEnabled=True,
            moveAfterProcessing=str(self.destination),
        )
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(
            (self.destination / "fixed_recording_000.mp4").read_bytes(), b"encoded output"
        )

    async def test_successful_mp4_can_replace_deleted_source(self):
        source = self.segment(extension=".mp4")
        await self.run_batch(
            self.encode_successfully, extension=".mp4", removeFixedPrefix=True
        )
        self.assertEqual(source.read_bytes(), b"encoded output")

    async def test_string_false_keeps_source(self):
        source = self.segment()
        await self.run_batch(self.encode_successfully, deleteAfterPostProcessing="false")
        self.assertTrue(source.exists())

    async def test_output_is_rechecked_before_deleting_source(self):
        first = self.segment(0)
        second = self.segment(1)
        earlier_output = None

        async def disappearing_output(command, **kwargs):
            nonlocal earlier_output
            if earlier_output:
                earlier_output.unlink()
            earlier_output = Path(command[-1])
            earlier_output.write_bytes(b"encoded output")

        await self.run_batch(disappearing_output)
        self.assertTrue(first.exists())
        self.assertFalse(second.exists())

    async def test_cancellation_keeps_original_segments(self):
        source = self.segment()
        with self.assertRaises(asyncio.CancelledError):
            await self.run_batch(AsyncMock(side_effect=asyncio.CancelledError))
        self.assertTrue(source.exists())


class YoutubeOutputSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "recordings"
        self.output.mkdir()
        self.shared_tmp = self.root / "ytarchive"
        self.shared_tmp.mkdir()
        self.destination = self.root / "processed"
        self.prefix = self.output / "this session [special]"
        patcher = patch.object(youtube_recorder, "TMP_ROOT", str(self.shared_tmp))
        patcher.start()
        self.addCleanup(patcher.stop)

    def unrelated_files(self):
        paths = [
            self.output / "another channel.mp4",
            self.output / (self.prefix.name + " extra.mkv"),
            self.output / (self.prefix.name + ".f140.ts"),
            self.shared_tmp / "another channel.mkv",
            self.shared_tmp / (self.prefix.name + ".mp4"),
        ]
        for path in paths:
            path.write_bytes(b"another recording")
        return paths

    async def move(self, move_src=None):
        await youtube_recorder.moveAfterProcessingTask(
            mp_enabled=True,
            mp_dir=str(self.destination),
            prefix_path=str(self.prefix),
            move_src=move_src,
            settle_sec=0,
        )

    async def test_missing_output_never_moves_unrelated_recent_files(self):
        unrelated = self.unrelated_files()
        with (
            patch.object(youtube_recorder, "moveDirectory", AsyncMock()) as move,
            self.assertLogs(youtube_recorder.logger, level="INFO"),
        ):
            await self.move()
        move.assert_not_awaited()
        self.assertTrue(all(path.read_bytes() == b"another recording" for path in unrelated))
        self.assertIsNone(youtube_recorder.findSessionOutput(str(self.prefix)))

    async def test_exact_alternate_container_is_moved(self):
        unrelated = self.unrelated_files()
        owned = Path(str(self.prefix) + ".mkv")
        owned.write_bytes(b"this recording")
        with self.assertLogs(youtube_recorder.logger, level="INFO"):
            await self.move()
        self.assertFalse(owned.exists())
        self.assertEqual((self.destination / owned.name).read_bytes(), b"this recording")
        self.assertTrue(all(path.exists() for path in unrelated))

    async def test_explicit_process_reported_output_is_accepted(self):
        reported = self.shared_tmp / "reported merged output.mp4"
        reported.write_bytes(b"this recording")
        await self.move(str(reported))
        self.assertFalse(reported.exists())
        self.assertEqual((self.destination / reported.name).read_bytes(), b"this recording")

    async def test_late_move_after_success_leaves_other_recordings_alone(self):
        unrelated = self.unrelated_files()
        owned = Path(str(self.prefix) + ".mp4")
        owned.write_bytes(b"this recording")
        await self.move(str(owned))
        with patch.object(youtube_recorder, "moveDirectory", AsyncMock()) as move:
            await self.move(str(owned))
        move.assert_not_awaited()
        self.assertTrue(all(path.exists() for path in unrelated))

    async def test_output_directory_with_expected_name_is_not_a_recording(self):
        Path(str(self.prefix) + ".mp4").mkdir()
        self.assertIsNone(youtube_recorder.findSessionOutput(str(self.prefix)))

    async def test_main_missing_output_does_not_adopt_or_cleanup_other_recordings(self):
        unrelated = self.unrelated_files()
        channel = {
            "id": "test-channel", "name": "Test channel", "platform": "youtube",
            "record_enabled": False, "output_dir": str(self.output),
        }
        manager = Mock()
        manager.get_is_user_stopped.return_value = False
        manager.get_status_recording.return_value = False
        process = Mock(returncode=0)
        process.wait = AsyncMock(return_value=0)
        clock = Mock()
        clock.time.side_effect = [0, 9]  # The missing-output grace period has elapsed.
        replacements = {
            "logger": Mock(),
            "recorder_manager": manager,
            "ysaveCookies": Mock(return_value=None),
            "validateCookies": Mock(return_value=(False, "no cookies")),
            "getYoutubeMetadata": AsyncMock(return_value={"is_live": True, "video_id": "test-video"}),
            "buildCommand": Mock(return_value=(["ytarchive"], str(self.prefix), str(self.prefix) + ".mp4")),
            "getFFmpeg": Mock(return_value="ffmpeg"),
            "progressTouchLoop": AsyncMock(),
            "spawnHeartbeat": Mock(return_value=None),
            "readPipe": AsyncMock(),
            "checkStopRequest": AsyncMock(),
            "safeRename": AsyncMock(),
            "moveDirectory": AsyncMock(),
            "cleanupTmp": Mock(),
            "sendTelegram": Mock(),
            "loadConfig": Mock(return_value={}),
            "last_notified_state": {},
            "time": clock,
        }
        with (
            patch.multiple(youtube_recorder, **replacements),
            patch.object(youtube_recorder.RecorderManager, "getChannels", return_value=[channel]),
            patch.object(youtube_recorder.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)),
        ):
            result = await youtube_recorder.ytStartRecording(
                channel, 30, "{channel_name}{file_extension}", True,
                str(self.destination), None, single_attempt=True,
            )
        self.assertEqual(result, youtube_recorder.RecorderAttemptOutcome.DISABLED)
        replacements["logger"].error.assert_not_called()
        process.wait.assert_awaited_once()
        replacements["safeRename"].assert_not_awaited()
        replacements["moveDirectory"].assert_not_awaited()
        replacements["cleanupTmp"].assert_not_called()
        self.assertTrue(all(path.exists() for path in unrelated))
        self.assertFalse(Path(str(self.prefix) + ".mp4").exists())
        self.assertFalse(any(
            "병합 완료" in call.args[0]
            for call in replacements["sendTelegram"].call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
