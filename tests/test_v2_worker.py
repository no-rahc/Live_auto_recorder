"""Deterministic durable-media failures: use real child processes, fake codecs."""
from __future__ import annotations

import asyncio
import errno
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import psutil

from module.v2_repository import V2Repository
from module.v2_storage import StorageRoot
from module.v2_worker import (AttemptContext, InstanceAlreadyRunning, MediaJobError,
                              SingleInstanceLock, V2Worker, boot_identity,
                              process_confirmed_absent)


class V2MediaWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "media"
        self.archive = self.root / "archive"
        self.media.mkdir()
        self.archive.mkdir()
        self.repo = V2Repository(self.root / "v2.sqlite3")
        self.repo.initialize()
        self.repo.upsert_channel("channel")
        self.repo.upsert_broadcast("broadcast", "channel")
        self.sources = []
        for index in range(2):
            path = self.media / f"source-{index}.ts"
            path.write_bytes(b"source recording " + bytes([index]))
            self.sources.append(path)
            self.repo.upsert_artifact({"id": f"source-{index}", "broadcast_id": "broadcast", "kind": "original",
                "storage_id": "recordings", "relative_path": path.name, "size": path.stat().st_size})
        self.sentinel = self.root / "processes.json"
        self.ffprobe = self.make_tool("ffprobe", '''
import json, pathlib, sys
value = pathlib.Path(sys.argv[-1]).read_bytes()
if value.startswith(b'invalid'):
    print('invalid media', file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({'format': {'duration': '2.0', 'format_name': 'mpegts'},
                  'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 32, 'height': 32}]}))
''')
        self.ffmpeg = self.make_tool("ffmpeg", f'''
import json, os, pathlib, subprocess, sys, time
source = pathlib.Path(sys.argv[sys.argv.index('-i') + 1]).read_bytes()
if source.startswith(b'hold'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    pathlib.Path({str(self.sentinel)!r}).write_text(json.dumps([os.getpid(), child.pid]))
    time.sleep(120)
if source.startswith(b'failure'):
    pathlib.Path(sys.argv[-1]).write_bytes(b'partial')
    raise SystemExit(1)
if '-n' not in sys.argv or '-y' in sys.argv:
    raise SystemExit(9)
with open(sys.argv[-1], 'xb') as handle:
    handle.write(b'verified output')
''')
        self.storages = {"recordings": StorageRoot("recordings", self.media),
                         "archive": StorageRoot("archive", self.archive)}
        self.worker = self.make_worker()

    def make_tool(self, name, content):
        path = self.root / name
        path.write_text(f"#!{sys.executable}\n" + content)
        path.chmod(0o700)
        return str(path)

    def make_worker(self):
        worker = V2Worker(self.repo, data_dir=self.root, storages=self.storages,
                          ffmpeg=self.ffmpeg, ffprobe=self.ffprobe,
                          poll_seconds=0.01, heartbeat_seconds=0.1, lease_seconds=10,
                          terminate_seconds=1)
        self.addCleanup(worker.release_instance_lock)
        return worker

    def job(self, kind, **options):
        # Snapshot completed-file metadata as the real catalog ingest does.
        for index, path in enumerate(self.sources):
            if not path.is_symlink():
                self.repo.upsert_artifact({"id": f"source-{index}", "size": path.stat().st_size})
        target = "broadcast" if kind == "merge" else "source-0"
        entity = self.repo.get_broadcast(target) if kind == "merge" else self.repo.get_artifact(target)
        return self.repo.create_job(kind, target, input_revision=entity["revision"], options=options)

    def assert_sources(self, expected=None):
        for index, path in enumerate(self.sources):
            value = expected if index == 0 and expected is not None else b"source recording " + bytes([index])
            self.assertEqual(path.read_bytes(), value)

    def assert_no_temps(self):
        self.assertEqual(list(self.media.glob(".lar-v2-*")) + list(self.archive.glob(".lar-v2-*")), [])

    def test_verify_commits_validation_and_never_repairs_original(self):
        job = self.job("verify")
        self.assertTrue(self.worker.run_once())
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(self.repo.get_artifact("source-0")["validation"], "ok")
        self.assertEqual(len(self.repo.get_attempts(job["id"])), 1)
        self.assert_sources()
        self.assert_no_temps()

    def test_invalid_verify_records_failure_without_modification(self):
        self.sources[0].write_bytes(b"invalid recording")
        job = self.job("verify")
        self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "failed", result)
        self.assertEqual(result["error_code"], "MEDIA_INVALID")
        self.assertEqual(self.repo.get_artifact("source-0")["validation"], "invalid")
        self.assert_sources(b"invalid recording")
        self.assert_no_temps()

    def test_recover_and_remux_publish_distinct_artifacts_preserving_originals(self):
        for kind in ("recover", "remux"):
            with self.subTest(kind=kind):
                job = self.job(kind)
                self.worker.run_once()
                result = self.repo.get_job(job["id"])
                self.assertEqual(result["state"], "succeeded", result)
                self.assertEqual(Path(result["result"]["output_path"]).read_bytes(), b"verified output")
                self.assertNotEqual(result["result"]["artifact_id"], "source-0")
        self.assert_sources()
        self.assert_no_temps()

    def test_merge_uses_private_paths_and_never_deletes_inputs(self):
        job = self.job("merge")
        self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(result["result"]["input_artifact_ids"], ["source-0", "source-1"])
        self.assert_sources()
        self.assert_no_temps()

    def test_local_archive_hash_matches_source_and_keeps_original(self):
        job = self.job("archive")
        self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(Path(result["result"]["output_path"]).read_bytes(), self.sources[0].read_bytes())
        self.assertEqual(self.repo.get_artifact(result["result"]["artifact_id"])["storage_id"], "archive")
        self.assert_sources()
        self.assert_no_temps()

    def test_existing_output_and_dangling_symlink_are_never_replaced(self):
        for name, symlink in (("existing.ts", False), ("dangling.ts", True)):
            with self.subTest(symlink=symlink):
                destination = self.media / name
                if symlink:
                    destination.symlink_to(self.media / "missing.ts")
                else:
                    destination.write_bytes(b"already there")
                job = self.job("recover", output_relative_path=name)
                self.worker.run_once()
                self.assertEqual(self.repo.get_job(job["id"])["state"], "blocked")
                if symlink:
                    self.assertTrue(destination.is_symlink())
                else:
                    self.assertEqual(destination.read_bytes(), b"already there")
        self.assert_sources()

    def test_failed_remux_cleans_only_attempt_files(self):
        self.sources[0].write_bytes(b"failure recording")
        foreign = self.media / "legacy.partial.ts"
        foreign.write_bytes(b"other attempt")
        job = self.job("recover")
        self.worker.run_once()
        self.assertEqual(self.repo.get_job(job["id"])["state"], "failed")
        self.assertEqual(foreign.read_bytes(), b"other attempt")
        self.assert_sources(b"failure recording")
        self.assert_no_temps()

    def test_hardlink_unsupported_blocks_without_copy_fallback(self):
        job = self.job("recover")
        real_link = os.link
        def fail_publication(source, destination, *args, **kwargs):
            if str(source).startswith("output.partial"):
                raise OSError(errno.EOPNOTSUPP, "hard links unsupported")
            return real_link(source, destination, *args, **kwargs)
        with mock.patch("module.v2_worker.os.link", side_effect=fail_publication):
            self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "blocked", result)
        self.assert_sources()
        self.assert_no_temps()
        self.assertEqual(self.repo.list_publications(states=("pending",)), [])

    def test_commit_failure_after_link_reconciles_without_second_execution(self):
        job = self.job("recover")
        original_finish = self.repo.finish_job
        def fail_success(*args, **kwargs):
            if kwargs.get("state") == "succeeded":
                raise sqlite3.OperationalError("disk full after publication")
            return original_finish(*args, **kwargs)
        with mock.patch.object(self.repo, "finish_job", side_effect=fail_success):
            self.worker.run_once()
        pending = self.repo.list_publications(states=("pending",))
        self.assertEqual(len(pending), 1)
        final = Path(pending[0]["final_path"])
        self.assertEqual(final.read_bytes(), b"verified output")
        self.worker.release_instance_lock()
        recovered = self.make_worker()
        recovered.reconcile(startup=True)
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "succeeded", result)
        self.assertTrue(result["result"]["reconciled"])
        self.assertFalse(recovered.run_once())
        self.assertEqual(len(self.repo.get_attempts(job["id"])), 1)
        self.assertEqual(final.read_bytes(), b"verified output")
        self.assert_sources()
        self.assert_no_temps()

    def test_changed_published_output_blocks_and_is_not_removed(self):
        job = self.job("recover")
        with mock.patch.object(self.repo, "finish_job", side_effect=sqlite3.OperationalError("commit failed")):
            self.worker.run_once()
        publication = self.repo.list_publications(states=("pending",))[0]
        final = Path(publication["final_path"])
        final.write_bytes(b"unrelated changed output")
        self.worker.release_instance_lock()
        recovered = self.make_worker()
        recovered.reconcile(startup=True)
        self.assertEqual(self.repo.get_job(job["id"])["state"], "blocked")
        self.assertEqual(final.read_bytes(), b"unrelated changed output")
        self.assertFalse(recovered.run_once())
        self.assert_sources()

    def test_cancellation_after_link_records_success_and_keeps_result(self):
        job = self.job("recover")
        real_link = os.link
        def cancel_after_link(source, destination, *args, **kwargs):
            result = real_link(source, destination, *args, **kwargs)
            if str(source).startswith("output.partial"):
                self.repo.request_cancel(job["id"])
            return result
        with mock.patch("module.v2_worker.os.link", side_effect=cancel_after_link):
            self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "succeeded", result)
        self.assertIn("cancellation_race", result["result"])
        self.assertTrue(Path(result["result"]["output_path"]).exists())
        self.assert_sources()
        self.assert_no_temps()

    def test_cancel_terminates_the_whole_process_group(self):
        self.sources[0].write_bytes(b"hold recording")
        job = self.job("recover")
        thread = threading.Thread(target=self.worker.run_once)
        thread.start()
        try:
            deadline = time.monotonic() + 8
            while not self.sentinel.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(self.sentinel.exists(), self.repo.get_job(job["id"]))
            pids = json.loads(self.sentinel.read_text())
            self.repo.request_cancel(job["id"])
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(self.repo.get_job(job["id"])["state"], "cancelled")
            for pid in pids:
                if psutil.pid_exists(pid):
                    self.assertEqual(psutil.Process(pid).status(), psutil.STATUS_ZOMBIE)
        finally:
            self.worker._stopping.set()
            thread.join(5)
        self.assert_sources(b"hold recording")
        self.assert_no_temps()

    def test_lease_loss_fences_publication_and_preserves_sources(self):
        job = self.job("recover")
        original_record = self.repo.record_publication
        def expire_after_intent(*args, **kwargs):
            result = original_record(*args, **kwargs)
            with self.repo._transaction() as conn:
                conn.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
            return result
        with mock.patch.object(self.repo, "record_publication", side_effect=expire_after_intent):
            self.worker.run_once()
        pending = self.repo.list_publications(states=("pending",))
        self.assertEqual(len(pending), 1)
        self.assertFalse(Path(pending[0]["final_path"]).exists())
        self.worker.release_instance_lock()
        replacement = self.make_worker()
        replacement.reconcile(startup=True)
        self.assertEqual(self.repo.get_job(job["id"])["state"], "retry_wait")
        replacement.run_once()
        self.assertEqual(self.repo.get_job(job["id"])["state"], "succeeded")
        self.assert_sources()

    def test_source_changed_during_render_is_never_published(self):
        job = self.job("recover")
        original_render = self.worker._render
        def change_input(ctx, suffix):
            result = original_render(ctx, suffix)
            self.sources[0].write_bytes(b"new source version")
            return result
        with mock.patch.object(self.worker, "_render", side_effect=change_input):
            self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["error_code"], "INPUT_CHANGED", result)
        self.assertEqual(self.sources[0].read_bytes(), b"new source version")
        self.assert_no_temps()
        self.assertEqual(self.repo.list_publications(), [])

    def test_single_instance_lock_cannot_be_replaced_by_second_owner(self):
        first = SingleInstanceLock(self.root / "exclusive.lock")
        second = SingleInstanceLock(self.root / "exclusive.lock")
        first.acquire()
        try:
            with self.assertRaises(InstanceAlreadyRunning):
                second.acquire()
        finally:
            first.release()
        self.assertTrue((self.root / "exclusive.lock").exists())
        second.acquire()
        second.release()

    def test_unrecorded_child_cannot_execute_before_process_commit(self):
        job = self.job("recover")
        sentinel = self.root / "forbidden-side-effect"
        claimed = self.repo.claim_job(self.worker.owner, kinds=("recover",))
        ctx = AttemptContext(self.worker, claimed)
        with mock.patch.object(self.repo, "set_process", side_effect=sqlite3.OperationalError("identity write failed")):
            with self.assertRaises(sqlite3.OperationalError):
                ctx.run([sys.executable, "-c", f"from pathlib import Path; Path({str(sentinel)!r}).write_text('ran')"], timeout=3)
        self.assertFalse(sentinel.exists())
        self.assert_sources()

    def test_active_artifact_is_blocked_before_any_media_process(self):
        self.repo.upsert_artifact({"id": "source-0", "metadata": {"status": "recording"}})
        job = self.job("recover")
        with mock.patch.object(self.worker, "_render") as render:
            self.worker.run_once()
        self.assertFalse(render.called)
        self.assertEqual(self.repo.get_job(job["id"])["error_code"], "INPUT_RECORDING")
        self.assert_sources()
        self.assert_no_temps()

    def test_active_merge_input_is_blocked_even_when_broadcast_looks_finished(self):
        self.repo.upsert_artifact({"id": "source-1", "metadata": {"status": "recording"}})
        job = self.job("merge")
        self.worker.run_once()
        self.assertEqual(self.repo.get_job(job["id"])["error_code"], "INPUT_RECORDING")
        self.assert_no_temps()
        self.assert_sources()

    def test_input_symlink_is_never_followed(self):
        outside = self.root / "outside.ts"
        outside.write_bytes(b"private unrelated input")
        self.sources[0].unlink()
        self.sources[0].symlink_to(outside)
        job = self.job("recover")
        self.worker.run_once()
        self.assertEqual(self.repo.get_job(job["id"])["state"], "blocked")
        self.assertTrue(self.sources[0].is_symlink())
        self.assertEqual(outside.read_bytes(), b"private unrelated input")
        self.assert_no_temps()

    def test_enospc_during_temporary_output_blocks_and_preserves_input(self):
        job = self.job("archive")
        real_open = os.open
        def disk_full(name, flags, *args, **kwargs):
            if str(name).startswith("output.partial") and flags & os.O_CREAT:
                raise OSError(errno.ENOSPC, "injected disk full")
            return real_open(name, flags, *args, **kwargs)
        with mock.patch("module.v2_worker.os.open", side_effect=disk_full):
            self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["state"], "blocked", result)
        self.assertEqual(result["error_code"], "STORAGE_FULL")
        self.assert_sources()
        self.assert_no_temps()

    def test_link_time_collision_keeps_foreign_output(self):
        job = self.job("recover", output_relative_path="collision.ts")
        real_link = os.link
        def collision(source, destination, *args, **kwargs):
            if str(source).startswith("output.partial"):
                (self.media / "collision.ts").write_bytes(b"another publisher")
            return real_link(source, destination, *args, **kwargs)
        with mock.patch("module.v2_worker.os.link", side_effect=collision):
            self.worker.run_once()
        self.assertEqual(self.repo.get_job(job["id"])["state"], "blocked")
        self.assertEqual((self.media / "collision.ts").read_bytes(), b"another publisher")
        self.assert_sources()
        self.assert_no_temps()

    def test_ambiguous_link_exception_keeps_pending_own_output_for_reconciliation(self):
        job = self.job("recover", output_relative_path="ambiguous.ts")
        real_link = os.link
        def linked_then_error(source, destination, *args, **kwargs):
            real_link(source, destination, *args, **kwargs)
            if str(source).startswith("output.partial"):
                raise OSError(errno.EIO, "injected uncertain link outcome")
        with mock.patch("module.v2_worker.os.link", side_effect=linked_then_error):
            self.worker.run_once()
        self.assertEqual(len(self.repo.list_publications()), 1)
        self.assertEqual((self.media / "ambiguous.ts").read_bytes(), b"verified output")
        self.worker.release_instance_lock()
        replacement = self.make_worker()
        replacement.reconcile(startup=True)
        self.assertEqual(self.repo.get_job(job["id"])["state"], "succeeded")
        self.assertEqual(len(self.repo.get_attempts(job["id"])), 1)
        self.assert_sources()
        self.assert_no_temps()

    def test_restart_reclaims_unpublished_private_attempt_only(self):
        job = self.job("recover")
        claimed = self.repo.claim_job(self.worker.owner)
        ctx = AttemptContext(self.worker, claimed)
        ctx.prepare_directory(self.media)
        temporary = ctx.work_dir / "output.partial.ts"
        temporary.write_bytes(b"interrupted output")
        foreign = self.media / ".lar-v2-foreign-attempt"
        foreign.mkdir()
        (foreign / "output.partial.ts").write_bytes(b"belongs to someone else")
        ctx.preserve_work = True
        ctx.cleanup()
        self.worker.release_instance_lock()
        replacement = self.make_worker()
        replacement.reconcile(startup=True)
        self.assertEqual(self.repo.get_job(job["id"])["state"], "retry_wait")
        self.assertFalse(temporary.exists())
        self.assertEqual((foreign / "output.partial.ts").read_bytes(), b"belongs to someone else")
        self.assert_sources()

    def test_required_storage_marker_failure_does_not_create_marker(self):
        marked = StorageRoot("recordings", self.media, marker=".storage-identity", expected_marker="nas-one")
        self.worker.storages["recordings"] = marked
        before = set(self.media.iterdir())
        self.assertFalse(self.worker.preflight(probe_writes=True)["ok"])
        self.assertEqual(set(self.media.iterdir()), before)
        (self.media / ".storage-identity").write_text("nas-one")
        self.assertTrue(self.worker.preflight(probe_writes=True)["ok"])
        (self.media / ".storage-identity").write_text("wrong-nas")
        self.assertFalse(self.worker.preflight(probe_writes=True)["ok"])

    def test_validation_failure_can_be_retried_as_a_new_attempt(self):
        self.sources[0].write_bytes(b"invalid recording")
        job = self.job("verify")
        self.worker.run_once()
        self.repo.retry_job(job["id"])
        self.worker.run_once()
        result = self.repo.get_job(job["id"])
        self.assertEqual(result["error_code"], "MEDIA_INVALID", result)
        self.assertEqual(len(self.repo.get_attempts(job["id"])), 2)
        self.assert_sources(b"invalid recording")

    def test_async_shutdown_waits_for_process_exit_before_unlocking(self):
        self.sources[0].write_bytes(b"hold recording")
        job = self.job("recover")
        async def exercise():
            await self.worker.start()
            deadline = time.monotonic() + 8
            while not self.sentinel.exists() and time.monotonic() < deadline:
                await asyncio.sleep(.02)
            self.assertTrue(self.sentinel.exists())
            self.assertTrue(self.worker.snapshot()["ready"])
            await self.worker.stop()
            self.assertFalse(self.worker.snapshot()["ready"])
            lock = SingleInstanceLock(self.root / "v2.instance.lock")
            lock.acquire()
            lock.release()
        asyncio.run(exercise())
        self.assertEqual(self.repo.get_job(job["id"])["state"], "retry_wait")
        for pid in json.loads(self.sentinel.read_text()):
            if psutil.pid_exists(pid):
                self.assertEqual(psutil.Process(pid).status(), psutil.STATUS_ZOMBIE)
        self.assert_sources(b"hold recording")
        self.assert_no_temps()

    def test_tool_timeout_terminates_and_clears_recorded_identity(self):
        self.job("recover")
        claimed = self.repo.claim_job(self.worker.owner)
        ctx = AttemptContext(self.worker, claimed)
        with self.assertRaises(MediaJobError) as error:
            ctx.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=.05)
        self.assertEqual(error.exception.code, "PROCESS_TIMEOUT")
        attempt = self.repo.get_attempts(claimed["id"])[0]
        self.assertIsNone(attempt["pid"])
        self.assertTrue(process_confirmed_absent(attempt))

    def test_restart_blocks_while_previous_media_process_is_alive(self):
        job = self.job("recover")
        claimed = self.repo.claim_job("previous-worker")
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        try:
            self.repo.set_process(job["id"], "previous-worker", claimed["generation"], pid=proc.pid,
                                  process_started_at=psutil.Process(proc.pid).create_time(), boot_id=boot_identity())
            self.worker.reconcile(startup=True)
            state = self.repo.get_job(job["id"])
            self.assertEqual(state["state"], "blocked")
            self.assertEqual(state["error_code"], "PROCESS_IDENTITY_UNCERTAIN")
            self.assertFalse(self.worker.run_once())
            self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            proc.wait(timeout=3)
        self.worker.reconcile()
        self.assertEqual(self.repo.get_job(job["id"])["state"], "retry_wait")
        self.worker.run_once()
        self.assertEqual(self.repo.get_job(job["id"])["state"], "succeeded")
        self.assert_sources()
        self.assert_no_temps()

    def test_unknown_pid_identity_is_not_reclaimed(self):
        self.assertIsNone(process_confirmed_absent({"pid": os.getpid(), "boot_id": boot_identity(),
                                                   "process_started_at": psutil.Process().create_time() - 20}))
        self.assertIsNone(process_confirmed_absent({"pid": os.getpid()}))
        self.assertTrue(process_confirmed_absent({"pid": os.getpid(), "boot_id": "a-previous-boot",
                                                "process_started_at": psutil.Process().create_time()}))


if __name__ == "__main__":
    unittest.main()
