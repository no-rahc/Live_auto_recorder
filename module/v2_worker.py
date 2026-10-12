"""Durable, fenced media jobs. Original recordings are never modified or removed.

Each FFmpeg/FFprobe process is gated until its identity is durable. Publication
uses a hard link (no replacement/copy fallback), followed by a fenced catalog
commit. An unresolved publication is reconciled before its job can run again.
The local/NAS archive handler is deliberately separate from legacy rclone jobs.
"""
from __future__ import annotations

import asyncio
import contextlib
import errno
import hashlib
import json
import math
import os
import random
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import psutil


class MediaJobError(RuntimeError):
    def __init__(self, code: str, detail: str, *, state: str = "failed"):
        super().__init__(detail)
        self.code, self.state = code, state


class JobCancelled(MediaJobError):
    def __init__(self):
        super().__init__("CANCELLED", "Cancellation confirmed; original files were preserved.", state="cancelled")


class WorkerStopping(MediaJobError):
    def __init__(self):
        super().__init__("WORKER_STOPPING", "Worker stopped after terminating its media process.", state="retry_wait")


class InstanceAlreadyRunning(RuntimeError):
    pass


class SingleInstanceLock:
    """An OS-held lock, never an unlinkable PID-file lock."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle: Any = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        handle = os.fdopen(fd, "r+b", buffering=0)
        try:
            if os.name == "nt":
                import msvcrt
                if self.path.stat().st_size == 0:
                    handle.write(b"\0")
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise InstanceAlreadyRunning("Another recorder instance holds the v2 data-directory lock.") from exc
        self._handle = handle

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        # Never unlink: another process may already be waiting on this inode.


def boot_identity() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return f"boot-time:{psutil.boot_time():.3f}"


def _group_members(pgid: int) -> list[int] | None:
    """Return non-zombie members, or None when absence cannot be established."""
    if os.name != "posix":
        return None
    members = []
    try:
        for proc in psutil.process_iter(["pid", "status"]):
            try:
                if os.getpgid(proc.pid) == pgid and proc.info["status"] != psutil.STATUS_ZOMBIE:
                    members.append(proc.pid)
            except (ProcessLookupError, psutil.NoSuchProcess):
                continue
            except (PermissionError, psutil.AccessDenied):
                return None
    except (OSError, psutil.Error):
        return None
    return members


def process_confirmed_absent(attempt: dict[str, Any]) -> bool | None:
    """Never reclaim merely because a lease expired or a PID changed owner."""
    pid = attempt.get("pid") or attempt.get("process_pid")
    if not pid:
        # All launches use a gate. An unrecorded launch cannot begin media work.
        return True
    recorded_boot = str(attempt.get("boot_id") or "")
    started = attempt.get("process_started_at")
    if not recorded_boot or started is None:
        return None
    if recorded_boot != boot_identity():
        return True  # The original boot's processes cannot have survived reboot.
    try:
        proc = psutil.Process(int(pid))
        if abs(proc.create_time() - float(started)) > 0.01:
            return None  # PID reuse is ambiguous: do not kill or retry.
        if proc.status() != psutil.STATUS_ZOMBIE:
            return False
    except psutil.NoSuchProcess:
        pass
    except (ValueError, TypeError, psutil.Error):
        return None
    if os.name == "posix":
        members = _group_members(int(pid))
        return members == [] if members is not None else None
    return True


def _sync(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as exc:
        # Some supported network filesystems cannot fsync directories. Other I/O
        # failures must prevent the catalog from claiming durable publication.
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
            raise


def _fingerprint(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _hash_fd(fd: int, check: Callable[[], Any] = lambda: None) -> str:
    digest = hashlib.sha256()
    offset = 0
    while True:
        check()
        block = os.pread(fd, 1024 * 1024, offset)
        if not block:
            return digest.hexdigest()
        digest.update(block)
        offset += len(block)


def _open_directory(path: Path) -> int:
    """Walk from / with openat(O_NOFOLLOW), refusing every symlink component."""
    path = Path(path).absolute()
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise MediaJobError("PLATFORM_UNSUPPORTED", "Durable media execution requires POSIX no-follow file descriptors.", state="blocked")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in {"", ".", ".."}:
                raise MediaJobError("PATH_UNSAFE", "Storage paths must not contain traversal components.", state="blocked")
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


@dataclass
class PinnedInput:
    artifact: dict[str, Any]
    path: Path
    fd: int
    fingerprint: tuple[int, int, int, int]

    @classmethod
    def open(cls, artifact: dict[str, Any], path: Path) -> "PinnedInput":
        parent_fd = _open_directory(path.parent)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise MediaJobError("INPUT_INVALID", "The input must be a regular media file.")
        if info.st_size <= 0:
            os.close(fd)
            raise MediaJobError("INPUT_EMPTY", "The input media file is empty.")
        return cls(artifact, path, fd, _fingerprint(info))

    def check(self) -> None:
        try:
            parent_fd = _open_directory(self.path.parent)
            try:
                current = os.stat(self.path.name, dir_fd=parent_fd, follow_symlinks=False)
            finally:
                os.close(parent_fd)
        except OSError as exc:
            raise MediaJobError("INPUT_CHANGED", "An input path disappeared or changed during this attempt.") from exc
        if _fingerprint(os.fstat(self.fd)) != self.fingerprint or _fingerprint(current) != self.fingerprint:
            raise MediaJobError("INPUT_CHANGED", "An input file changed during this attempt.")

    def close(self) -> None:
        os.close(self.fd)


class AttemptContext:
    def __init__(self, worker: "V2Worker", job: dict[str, Any]):
        self.worker, self.repo, self.job = worker, worker.repo, job
        self.owner, self.generation = str(job["owner"]), int(job["generation"])
        self.last_heartbeat = 0.0
        self.process: subprocess.Popen | None = None
        self.process_started_at: float | None = None
        self.inputs: list[PinnedInput] = []
        self.work_dir: Path | None = None
        self.work_fd: int | None = None
        self.parent_fd: int | None = None
        self.parent: Path | None = None
        self.parent_identity: tuple[int, int] | None = None
        self.publication: dict[str, Any] | None = None
        self.published = False
        self.preserve_work = False
        self.finished = False
        self.nonce = uuid.uuid4().hex
        self.owned_names = {"owner.json"}

    def check(self, *, allow_cancel: bool = False) -> dict[str, Any]:
        if self.worker._stopping.is_set() and not allow_cancel:
            raise WorkerStopping()
        now = time.monotonic()
        if now - self.last_heartbeat >= self.worker.heartbeat_seconds:
            job = self.repo.heartbeat(self.job["id"], self.owner, self.generation, lease_seconds=self.worker.lease_seconds)
            self.last_heartbeat = now
        else:
            job = self.repo.assert_lease(self.job["id"], self.owner, self.generation)
        if (job.get("state") == "cancel_requested" or job.get("cancel_requested")) and not allow_cancel:
            raise JobCancelled()
        return job

    def progress(self, stage: str) -> None:
        self.check()
        self.repo.heartbeat(self.job["id"], self.owner, self.generation, lease_seconds=self.worker.lease_seconds,
                            progress={"stage": stage, "attempt_id": self.job["attempt_id"]})
        self.last_heartbeat = time.monotonic()

    def check_inputs(self) -> None:
        self.check()
        for item in self.inputs:
            item.check()

    def prepare_directory(self, parent: Path) -> None:
        self.check()
        self.parent = parent
        self.parent_fd = _open_directory(parent)
        info = os.fstat(self.parent_fd)
        self.parent_identity = (info.st_dev, info.st_ino)
        name = f".lar-v2-{self.job['id']}-{self.job['attempt_id']}-{self.nonce}"
        os.mkdir(name, mode=0o700, dir_fd=self.parent_fd)
        self.work_dir = parent / name
        self.work_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent_fd)
        marker = {"job_id": self.job["id"], "attempt_id": self.job["attempt_id"], "nonce": self.nonce}
        fd = os.open("owner.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=self.work_fd)
        with os.fdopen(fd, "w") as stream:
            json.dump(marker, stream)
            stream.flush()
            _sync(stream.fileno())
        _sync(self.work_fd)
        self.repo.set_attempt_context(self.job["id"], self.owner, self.generation, work_dir=str(self.work_dir))

    def check_parent(self) -> None:
        assert self.parent is not None and self.parent_fd is not None
        fd = _open_directory(self.parent)
        try:
            current = os.fstat(fd)
            if (current.st_dev, current.st_ino) != self.parent_identity:
                raise MediaJobError("STORAGE_CHANGED", "The publication directory changed during this attempt.", state="blocked")
        finally:
            os.close(fd)

    def run(self, argv: list[str], *, timeout: float, pass_fds: tuple[int, ...] = ()) -> subprocess.CompletedProcess:
        """Record the process identity before allowing the child to execute tools."""
        self.check()
        if os.name != "posix" or not Path("/proc/self/fd").is_dir():
            raise MediaJobError("PLATFORM_UNSUPPORTED", "Fenced media subprocesses require Linux /proc file descriptors.", state="blocked")
        read_fd, write_fd = os.pipe()
        stdout = tempfile.TemporaryFile()
        stderr = tempfile.TemporaryFile()
        proc = None
        recorded = False
        try:
            command = [sys.executable, str(Path(__file__).resolve()), "--exec-gated", str(read_fd), *argv]
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                    start_new_session=True, pass_fds=tuple(set((read_fd, *pass_fds))))
            self.process = proc
            os.close(read_fd)
            read_fd = -1
            started = psutil.Process(proc.pid).create_time()
            self.process_started_at = started
            self.repo.set_process(self.job["id"], self.owner, self.generation, pid=proc.pid,
                                  process_started_at=started, boot_id=boot_identity())
            recorded = True
            self.check()
            os.write(write_fd, b"1")
            os.close(write_fd)
            write_fd = -1
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                self.check()
                if time.monotonic() >= deadline:
                    raise MediaJobError("PROCESS_TIMEOUT", "The media tool exceeded its time limit.", state="retry_wait")
                self.worker._stopping.wait(self.worker.poll_seconds)
            # A tool must not leave a child running after its leader exits.
            members = _group_members(proc.pid)
            if members is None or members:
                raise MediaJobError("PROCESS_UNCERTAIN", "Media subprocess termination could not be confirmed.", state="blocked")
            self.check()
            stdout.seek(0)
            stderr.seek(0, os.SEEK_END)
            stderr.seek(max(0, stderr.tell() - 4000))
            return subprocess.CompletedProcess(argv, proc.returncode, stdout.read(2 * 1024 * 1024).decode("utf-8", "replace"),
                                               stderr.read().decode("utf-8", "replace"))
        finally:
            if read_fd >= 0:
                os.close(read_fd)
            if write_fd >= 0:
                os.close(write_fd)  # Unreleased children see EOF and exit without executing.
            try:
                if proc is not None:
                    self._terminate(proc)
                    if recorded:
                        self.repo.set_process(self.job["id"], self.owner, self.generation, pid=None,
                                              process_started_at=None, boot_id="")
            except BaseException:
                # Keep process identity and private files for restart inspection.
                self.preserve_work = True
                raise
            finally:
                self.process = None
                stdout.close()
                stderr.close()

    def _terminate(self, proc: subprocess.Popen) -> None:
        members = _group_members(proc.pid)
        if proc.poll() is not None and members == []:
            return
        if members is None:
            raise MediaJobError("PROCESS_UNCERTAIN", "Could not inspect the owned process group.", state="blocked")
        try:
            leader = psutil.Process(proc.pid)
            if self.process_started_at is not None and abs(leader.create_time() - self.process_started_at) > .01:
                raise MediaJobError("PROCESS_UNCERTAIN", "The process group leader identity changed.", state="blocked")
        except psutil.NoSuchProcess:
            pass  # A remaining group is still ours until its original members exit.
        except psutil.Error as exc:
            raise MediaJobError("PROCESS_UNCERTAIN", "Cannot verify the process group leader.", state="blocked") from exc
        # The process group was created by this attempt; the live Popen owns its
        # identity. Never use this helper on an arbitrary PID read from the DB.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=self.worker.terminate_seconds)
        except subprocess.TimeoutExpired:
            pass
        members = _group_members(proc.pid)
        if members:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        try:
            proc.wait(timeout=self.worker.terminate_seconds)
        except subprocess.TimeoutExpired as exc:
            raise MediaJobError("PROCESS_UNCERTAIN", "The media process could not be terminated.", state="blocked") from exc
        deadline = time.monotonic() + self.worker.terminate_seconds
        while True:
            members = _group_members(proc.pid)
            if members == []:
                return
            if members is None or time.monotonic() >= deadline:
                raise MediaJobError("PROCESS_UNCERTAIN", "A child media process may still be running.", state="blocked")
            time.sleep(0.02)

    def cleanup(self) -> None:
        for item in self.inputs:
            item.close()
        if self.work_fd is not None:
            if not self.preserve_work:
                # Only this private directory's regular files are owned. A
                # surprising subdirectory or substituted entry is left alone.
                for name in self.owned_names:
                    try:
                        info = os.stat(name, dir_fd=self.work_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if stat.S_ISREG(info.st_mode):
                        os.unlink(name, dir_fd=self.work_fd)
                if self.parent_fd is not None and self.work_dir is not None:
                    with contextlib.suppress(OSError):
                        os.rmdir(self.work_dir.name, dir_fd=self.parent_fd)
            os.close(self.work_fd)
        if self.parent_fd is not None:
            os.close(self.parent_fd)


def _exec_gated() -> None:
    fd, argv = int(sys.argv[2]), sys.argv[3:]
    try:
        token = os.read(fd, 1)
    finally:
        os.close(fd)
    if token != b"1" or not argv:
        raise SystemExit(125)
    os.execvp(argv[0], argv)


class V2Worker:
    """One lightweight verification lane and one shared heavy-media lane."""

    KINDS = ("verify", "recover", "remux", "merge", "archive")
    MEDIA_SUFFIXES = {".ts", ".mkv", ".mp4", ".webm", ".mov", ".m4v"}

    def __init__(self, repo: Any, *, data_dir: Path | None = None, storages: dict[str, Any] | None = None,
                 ffmpeg: str | None = None, ffprobe: str | None = None,
                 heartbeat_seconds: float = 15, lease_seconds: float = 90,
                 poll_seconds: float = 0.25, terminate_seconds: float = 3):
        from module.v2_storage import StorageRoot

        self.repo = repo
        db_path = getattr(repo, "db_path", Path("json") / "recordings-v2.sqlite3")
        self.data_dir = Path(data_dir or Path(db_path).parent)
        if storages is None:
            from module.recording_verify import _recording_root
            storages = {"recordings": StorageRoot("recordings", _recording_root(),
                marker=os.getenv("LAR_V2_RECORDINGS_MARKER", ".lar-storage-id") or ".lar-storage-id",
                expected_marker=os.getenv("LAR_V2_RECORDINGS_MARKER_VALUE") or None, min_free_bytes=64 * 1024 * 1024)}
            archive = os.getenv("LAR_V2_ARCHIVE_ROOT", "").strip()
            if archive:
                storages["archive"] = StorageRoot("archive", Path(archive).expanduser().absolute(),
                    marker=os.getenv("LAR_V2_ARCHIVE_MARKER") or None,
                    expected_marker=os.getenv("LAR_V2_ARCHIVE_MARKER_VALUE") or None, min_free_bytes=64 * 1024 * 1024)
        self.storages = dict(storages)
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.heartbeat_seconds = heartbeat_seconds
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds
        self.terminate_seconds = terminate_seconds
        self.owner = f"worker-{uuid.uuid4().hex}"
        self._lock = SingleInstanceLock(self.data_dir / "v2.instance.lock")
        self._stopping = threading.Event()
        self._tasks: list[asyncio.Task] = []
        self._active: dict[str, Any] = {}
        self._ready = False
        self._last_error = ""
        self._storage_identity: dict[str, tuple[int, int]] = {}
        self._storage_reports: dict[str, dict[str, Any]] = {}
        self._reconciled = False
        self._recovery_lock = threading.Lock()
        self._last_recovery = 0.0

    def acquire_instance_lock(self) -> None:
        self._lock.acquire()

    def release_instance_lock(self) -> None:
        if self._tasks or self._active:
            raise RuntimeError("Cannot release the instance lock while media execution is active.")
        self._lock.release()

    async def start(self) -> None:
        if self._tasks:
            return
        self.acquire_instance_lock()
        self._stopping.clear()
        try:
            await asyncio.to_thread(self.reconcile, startup=True)
            await asyncio.to_thread(self.preflight, probe_writes=True)
            self._ready = True
            self._tasks = [asyncio.create_task(self._lane(("verify",)), name="v2-verify"),
                           asyncio.create_task(self._lane(("recover", "remux", "merge", "archive")), name="v2-media")]
        except BaseException:
            self._ready = False
            self.release_instance_lock()
            raise

    async def stop(self) -> None:
        self._ready = False
        self._stopping.set()
        tasks, self._tasks = self._tasks, []
        try:
            if tasks:
                # Do not cancel to_thread's await: its subprocess-owning thread
                # must finish and confirm process termination before unlock.
                waiter = asyncio.gather(*tasks, return_exceptions=True)
                try:
                    await asyncio.shield(waiter)
                except asyncio.CancelledError:
                    await waiter
                    raise
        finally:
            if not self._active:
                self._lock.release()

    def snapshot(self) -> dict[str, Any]:
        storage_ready = self._storage_reports.get("recordings", {}).get("ok", False)
        return {"ready": self._ready and storage_ready, "running": len(self._active), "owner": self.owner,
                "reconciled": self._reconciled, "error": self._last_error, "storages": dict(self._storage_reports)}

    def preflight(self, *, probe_writes: bool = False) -> dict[str, Any]:
        from module.v2_storage import preflight_storage
        self._storage_reports = {key: preflight_storage(storage, probe_writes=probe_writes)
                                 for key, storage in self.storages.items()}
        return {"ok": bool(self._storage_reports.get("recordings", {}).get("ok")),
                "storages": dict(self._storage_reports)}

    async def _lane(self, kinds: tuple[str, ...]) -> None:
        while not self._stopping.is_set():
            try:
                if kinds == ("verify",) and time.monotonic() - self._last_recovery > 15:
                    await asyncio.to_thread(self.reconcile)
                worked = await asyncio.to_thread(self.run_once, kinds=kinds)
                if not worked:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                self._stopping.set()
                raise
            except Exception as exc:
                self._last_error = str(exc)[:500]
                self._ready = False
                await asyncio.sleep(1)

    def _storage(self, storage_id: str, *, write: bool = False) -> Any:
        from module.v2_storage import preflight_storage
        storage = self.storages.get(storage_id)
        if storage is None:
            raise MediaJobError("STORAGE_UNAVAILABLE", f"Storage '{storage_id}' is not configured.", state="blocked")
        report = preflight_storage(storage, probe_writes=write)
        self._storage_reports[storage_id] = report
        if not report.get("ok"):
            raise MediaJobError("STORAGE_UNAVAILABLE", "Storage preflight failed: " + str(report.get("errors") or "unavailable")[:700], state="blocked")
        fd = _open_directory(Path(storage.root))
        try:
            info = os.fstat(fd)
            identity = (info.st_dev, info.st_ino)
        finally:
            os.close(fd)
        prior = self._storage_identity.setdefault(storage_id, identity)
        if prior != identity:
            raise MediaJobError("STORAGE_CHANGED", "The storage root or mount changed; inspect it before restarting the worker.", state="blocked")
        return storage

    def _path(self, artifact: dict[str, Any]) -> Path:
        from module.v2_storage import resolve_storage_path
        storage = self._storage(str(artifact["storage_id"]))
        return resolve_storage_path(storage, str(artifact["relative_path"]), must_exist=True)

    def _inputs(self, ctx: AttemptContext) -> list[PinnedInput]:
        job, options = ctx.job, ctx.job.get("options") or {}
        if job["kind"] == "merge":
            broadcast = self.repo.get_broadcast(job["target_id"])
            if not broadcast:
                raise MediaJobError("TARGET_MISSING", "The broadcast no longer exists.")
            if int(broadcast.get("revision", 1)) != int(job["input_revision"]):
                raise MediaJobError("INPUT_CHANGED", "The broadcast revision has changed.")
            if str(broadcast.get("status") or "").lower() in {"recording", "starting", "reconnecting", "stopping"}:
                raise MediaJobError("INPUT_RECORDING", "The broadcast is still recording.", state="blocked")
            artifacts = broadcast.get("artifacts") or self.repo.list_artifacts(broadcast_id=job["target_id"])
            selected = options.get("input_artifact_ids")
            if selected:
                if not isinstance(selected, list) or len(set(map(str, selected))) != len(selected):
                    raise MediaJobError("INPUT_INVALID", "Merge input artifact IDs must be a distinct ordered list.")
                lookup = {str(item["id"]): item for item in artifacts}
                try:
                    artifacts = [lookup[str(key)] for key in selected]
                except KeyError as exc:
                    raise MediaJobError("INPUT_INVALID", "A selected input does not belong to this broadcast.") from exc
            else:
                artifacts = [item for item in artifacts if item.get("kind") in {"original", "recording", "source"}]
            if len(artifacts) < 2:
                raise MediaJobError("INPUT_INVALID", "Merging requires at least two source artifacts.")
        else:
            artifact = self.repo.get_artifact(job["target_id"])
            if not artifact:
                raise MediaJobError("TARGET_MISSING", "The target artifact no longer exists.")
            if int(artifact.get("revision", 1)) != int(job["input_revision"]):
                raise MediaJobError("INPUT_CHANGED", "The artifact revision has changed.")
            artifacts = [artifact]
        for artifact in artifacts:
            if str((artifact.get("metadata") or {}).get("status") or "").lower() in {"recording", "starting", "reconnecting", "stopping"}:
                raise MediaJobError("INPUT_RECORDING", "A source artifact is still recording.", state="blocked")
            pinned = PinnedInput.open(artifact, self._path(artifact))
            ctx.inputs.append(pinned)
            expected_size = int(artifact.get("size") or 0)
            if expected_size > 0 and pinned.fingerprint[2] != expected_size:
                raise MediaJobError("INPUT_CHANGED", "The input size no longer matches its catalog revision.")
        identities = [(item.fingerprint[0], item.fingerprint[1]) for item in ctx.inputs]
        if len(set(identities)) != len(identities):
            raise MediaJobError("INPUT_INVALID", "The same input file was selected more than once.")
        return ctx.inputs

    def _check_revision(self, ctx: AttemptContext) -> None:
        entity = (self.repo.get_broadcast(ctx.job["target_id"]) if ctx.job["kind"] == "merge"
                  else self.repo.get_artifact(ctx.job["target_id"]))
        if not entity or int(entity.get("revision", 1)) != int(ctx.job["input_revision"]):
            raise MediaJobError("INPUT_CHANGED", "The target revision changed before completion.")
        for item in ctx.inputs:
            current = self.repo.get_artifact(item.artifact["id"])
            if current and str((current.get("metadata") or {}).get("status") or "").lower() in {"recording", "starting", "reconnecting", "stopping"}:
                raise MediaJobError("INPUT_RECORDING", "A source artifact resumed recording.", state="blocked")
            if not current or int(current.get("revision", 1)) != int(item.artifact.get("revision", 1)):
                raise MediaJobError("INPUT_CHANGED", "An input artifact revision changed before completion.")

    def _tool(self, name: str) -> str:
        from module.recording_merge import _ffmpeg_path, _ffprobe_path
        configured = getattr(self, name)
        command = configured or (_ffmpeg_path() if name == "ffmpeg" else _ffprobe_path())
        resolved = shutil.which(command)
        if not resolved:
            raise MediaJobError("TOOL_UNAVAILABLE", f"{name} is not installed or executable.", state="blocked")
        return resolved

    def _probe(self, ctx: AttemptContext, fd: int) -> dict[str, Any]:
        proc = ctx.run([self._tool("ffprobe"), "-v", "error", "-show_entries",
                        "format=duration,format_name:stream=codec_type,codec_name,width,height,sample_rate,channels",
                        "-of", "json", f"/proc/self/fd/{fd}"], timeout=60, pass_fds=(fd,))
        if proc.returncode:
            raise MediaJobError("MEDIA_INVALID", (proc.stderr or "FFprobe could not read the media file.")[-1000:])
        try:
            data = json.loads(proc.stdout)
            duration = float((data.get("format") or {}).get("duration") or 0)
            streams = data.get("streams") or []
            if not math.isfinite(duration) or duration <= 0 or not any(item.get("codec_type") == "video" for item in streams):
                raise ValueError("missing video or duration")
        except (ValueError, TypeError, AttributeError) as exc:
            raise MediaJobError("MEDIA_INVALID", "The media must contain a video stream and a finite positive duration.") from exc
        return {"duration": duration, "streams": streams, "format": data.get("format") or {}}

    def _output(self, ctx: AttemptContext) -> tuple[Any, str, str]:
        from module.v2_storage import resolve_storage_path
        first, options, kind = ctx.inputs[0], ctx.job.get("options") or {}, ctx.job["kind"]
        storage_id = str(options.get("output_storage_id") or ("archive" if kind == "archive" else first.artifact["storage_id"]))
        storage = self._storage(storage_id, write=True)
        suffix = str(options.get("suffix") or first.path.suffix).lower()
        if suffix not in self.MEDIA_SUFFIXES:
            raise MediaJobError("FORMAT_UNSUPPORTED", "The output container extension is not supported.")
        if kind == "archive" and suffix != first.path.suffix.lower():
            raise MediaJobError("INPUT_INVALID", "An archive copy must keep the original media extension.")
        default_dir = str(Path(first.artifact["relative_path"]).parent) if storage_id == first.artifact["storage_id"] else "."
        label = {"recover": "recovered", "remux": "remuxed", "merge": "merged", "archive": "archive"}[kind]
        stem = first.path.stem.encode("utf-8")[:160].decode("utf-8", "ignore").rstrip(". ") or "recording"
        relative = str(options.get("output_relative_path") or str(Path(default_dir) / f"{stem}.{label}-{ctx.job['id']}{suffix}"))
        if Path(relative).suffix.lower() != suffix:
            raise MediaJobError("INPUT_INVALID", "The output extension must match the requested container.")
        path = resolve_storage_path(storage, relative, must_exist=False)
        if os.path.lexists(path):
            raise MediaJobError("OUTPUT_EXISTS", "The destination already exists and will not be overwritten.", state="blocked")
        ctx.prepare_directory(path.parent)
        expected_size = sum(item.fingerprint[2] for item in ctx.inputs)
        free = shutil.disk_usage(path.parent).free
        if free < expected_size + max(16 * 1024 * 1024, int(expected_size * 0.05)):
            raise MediaJobError("STORAGE_FULL", "There is not enough free space for a private output and safety margin.", state="blocked")
        return storage, relative, suffix

    def _render(self, ctx: AttemptContext, suffix: str) -> tuple[str, dict[str, Any]]:
        assert ctx.work_fd is not None
        kind = ctx.job["kind"]
        ctx.progress("copying" if kind == "archive" else "remuxing" if kind in {"recover", "remux"} else "merging")
        output_name = "output.partial" + suffix
        ctx.owned_names.add(output_name)
        if kind == "archive":
            source = ctx.inputs[0]
            fd = os.open(output_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=ctx.work_fd)
            digest, offset = hashlib.sha256(), 0
            with os.fdopen(fd, "wb") as out:
                while True:
                    ctx.check_inputs()
                    block = os.pread(source.fd, 1024 * 1024, offset)
                    if not block:
                        break
                    out.write(block)
                    digest.update(block)
                    offset += len(block)
                out.flush()
                _sync(out.fileno())
            out_fd = os.open(output_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=ctx.work_fd)
            try:
                if _hash_fd(out_fd, ctx.check) != digest.hexdigest():
                    raise MediaJobError("ARCHIVE_MISMATCH", "The archive copy did not match the source bytes.")
                probe = self._probe(ctx, out_fd)
            finally:
                os.close(out_fd)
            return output_name, probe
        argv = [self._tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin"]
        passed = tuple(item.fd for item in ctx.inputs) + (ctx.work_fd,)
        if kind == "merge":
            probes = [self._probe(ctx, item.fd) for item in ctx.inputs]
            signatures = [json.dumps(item["streams"], sort_keys=True) for item in probes]
            if len(set(signatures)) != 1:
                raise MediaJobError("CODEC_INCOMPATIBLE", "Merge inputs have different stream layouts or codecs.")
            ctx.owned_names.add("concat.txt")
            list_fd = os.open("concat.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=ctx.work_fd)
            with os.fdopen(list_fd, "w") as out:
                for item in ctx.inputs:
                    # FD paths avoid quoting original filenames and pin each input.
                    out.write(f"file '/proc/self/fd/{item.fd}'\n")
            argv += ["-f", "concat", "-safe", "0", "-i", f"/proc/self/fd/{ctx.work_fd}/concat.txt"]
        else:
            argv += ["-i", f"/proc/self/fd/{ctx.inputs[0].fd}"]
        argv += ["-map", "0", "-c", "copy", "-n", f"/proc/self/fd/{ctx.work_fd}/{output_name}"]
        proc = ctx.run(argv, timeout=6 * 3600, pass_fds=passed)
        if proc.returncode:
            raise MediaJobError("MEDIA_PROCESS_FAILED", (proc.stderr or "FFmpeg did not produce an output.")[-1200:])
        fd = os.open(output_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=ctx.work_fd)
        try:
            if os.fstat(fd).st_size <= 0:
                raise MediaJobError("OUTPUT_EMPTY", "The media tool produced an empty result.")
            _sync(fd)
            probe = self._probe(ctx, fd)
        finally:
            os.close(fd)
        return output_name, probe

    def _publish(self, ctx: AttemptContext, storage: Any, relative: str, output_name: str, probe: dict[str, Any]) -> dict[str, Any]:
        from module.v2_storage import resolve_storage_path
        assert ctx.work_fd is not None and ctx.parent_fd is not None and ctx.work_dir is not None
        ctx.check_inputs()
        self._check_revision(ctx)
        self._storage(str(storage.storage_id))
        ctx.check_parent()
        final_path = resolve_storage_path(storage, relative, must_exist=False)
        fd = os.open(output_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=ctx.work_fd)
        try:
            info = os.fstat(fd)
            digest = _hash_fd(fd, ctx.check)
            _sync(fd)
        finally:
            os.close(fd)
        artifact = {"broadcast_id": ctx.inputs[0].artifact["broadcast_id"], "segment_id": None,
                    "kind": {"recover": "recovered", "remux": "remuxed", "merge": "merged", "archive": "archive"}[ctx.job["kind"]],
                    "storage_id": storage.storage_id, "relative_path": relative, "size": info.st_size,
                    "validation": "ok", "metadata": {"sha256": digest, "probe": probe,
                    "input_artifact_ids": [item.artifact["id"] for item in ctx.inputs],
                    "input_revisions": {item.artifact["id"]: item.artifact.get("revision", 1) for item in ctx.inputs}}}
        result = {"status": "completed", "output_path": str(final_path), "size": info.st_size,
                  "sha256": digest, "input_artifact_ids": [item.artifact["id"] for item in ctx.inputs],
                  "originals_preserved": True, "probe": probe}
        metadata = {"artifact": artifact, "result": result, "device": info.st_dev, "inode": info.st_ino,
                    "size": info.st_size, "sha256": digest, "work_nonce": ctx.nonce}
        ctx.progress("publishing")
        ctx.publication = self.repo.record_publication(ctx.job["id"], ctx.owner, ctx.generation,
                              temporary_path=str(ctx.work_dir / output_name), final_path=str(final_path), metadata=metadata)
        # Persisted intent must survive every ambiguous outcome from this point.
        ctx.preserve_work = True
        try:
            ctx.check_inputs()
            ctx.check_parent()
            os.link(output_name, final_path.name, src_dir_fd=ctx.work_fd, dst_dir_fd=ctx.parent_fd, follow_symlinks=False)
            ctx.published = True
            current_output = os.stat(final_path.name, dir_fd=ctx.parent_fd, follow_symlinks=False)
            if _fingerprint(current_output) != _fingerprint(info):
                raise MediaJobError("PUBLICATION_CHANGED", "The output changed during publication.", state="blocked")
            _sync(ctx.parent_fd)
            ctx.check_parent()
            current = ctx.check(allow_cancel=True)
            if current.get("state") == "cancel_requested" or current.get("cancel_requested"):
                result["cancellation_race"] = "Publication completed before cancellation could take effect."
            self.repo.finish_job(ctx.job["id"], ctx.owner, ctx.generation, state="succeeded", result=result, artifact=artifact)
            ctx.finished = True
            ctx.preserve_work = False
            return result
        except BaseException:
            if not ctx.published:
                # No final entry belonging to this attempt exists. An existing
                # collision is never ours, even if it has identical bytes.
                try:
                    existing = os.stat(final_path.name, dir_fd=ctx.parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    existing = None
                if existing and (existing.st_dev, existing.st_ino) == (info.st_dev, info.st_ino):
                    ctx.published = True
                    raise
                self.repo.abandon_publication(ctx.publication["id"], ctx.owner, ctx.generation, final_confirmed_absent=True)
                ctx.preserve_work = False
            raise

    def _verify(self, ctx: AttemptContext) -> dict[str, Any]:
        source = ctx.inputs[0]
        ctx.progress("verifying")
        try:
            probe = self._probe(ctx, source.fd)
        except MediaJobError as exc:
            if exc.code != "MEDIA_INVALID":
                raise
            ctx.check_inputs()
            self._check_revision(ctx)
            result = {"status": "invalid", "detail": str(exc), "originals_preserved": True,
                      "input_revisions": {source.artifact["id"]: source.artifact.get("revision", 1)}}
            self.repo.finish_job(ctx.job["id"], ctx.owner, ctx.generation, state="failed", result=result,
                                 error_code=exc.code, error_detail=str(exc),
                                 artifact={"id": source.artifact["id"], "validation": "invalid", "size": source.fingerprint[2]})
            ctx.finished = True
            return result
        ctx.check_inputs()
        self._check_revision(ctx)
        result = {"status": "ok", "artifact_id": source.artifact["id"], "size": source.fingerprint[2],
                  "probe": probe, "originals_preserved": True,
                  "input_revisions": {source.artifact["id"]: source.artifact.get("revision", 1)}}
        self.repo.finish_job(ctx.job["id"], ctx.owner, ctx.generation, state="succeeded", result=result,
                             artifact={"id": source.artifact["id"], "validation": "ok", "size": source.fingerprint[2]})
        ctx.finished = True
        return result

    def _notify(self, ctx: AttemptContext, result: dict[str, Any]) -> None:
        if ctx.job["kind"] != "verify" or not ctx.finished:
            return
        # The generic legacy emitter also schedules possibly destructive remote
        # archives. Use its durable notification queue, with no such side effect.
        try:
            from module import operations_platform_v3
            runtime = operations_platform_v3._RUNTIME
            if runtime is not None:
                runtime.enqueue_notification("recording.validated", {"event_id": f"v2-job:{ctx.job['id']}",
                    "job_id": ctx.job["id"], "artifact_id": ctx.inputs[0].artifact["id"], **result})
        except Exception:
            # Media success remains durable. Notification delivery remains the
            # legacy queue's responsibility, and isn't an exactly-once promise.
            pass

    def run_once(self, *, kinds: tuple[str, ...] | None = None) -> bool:
        if self._stopping.is_set():
            return False
        self.acquire_instance_lock()
        job = self.repo.claim_job(self.owner, kinds=kinds or self.KINDS, lease_seconds=self.lease_seconds)
        if not job:
            return False
        ctx = AttemptContext(self, job)
        self._active[str(job["id"])] = ctx
        try:
            options = job.get("options") or {}
            allowed = {"output_storage_id", "output_relative_path", "suffix", "input_artifact_ids", "attempt_repair"}
            if set(options) - allowed or options.get("attempt_repair"):
                raise MediaJobError("OPTIONS_UNSUPPORTED", "Unsupported media options. Recovery must be requested as a separate preserving job.")
            ctx.progress("checking_inputs")
            self._inputs(ctx)
            if job["kind"] == "verify":
                result = self._verify(ctx)
            else:
                storage, relative, suffix = self._output(ctx)
                output_name, probe = self._render(ctx, suffix)
                result = self._publish(ctx, storage, relative, output_name, probe)
            self._notify(ctx, result)
        except Exception as exc:
            self._last_error = str(exc)[:500]
            if not ctx.published and not ctx.preserve_work and not ctx.finished:
                error = self._classify(exc)
                try:
                    current = ctx.check(allow_cancel=True)
                    state = "cancelled" if current.get("state") == "cancel_requested" else error.state
                    delay = min(900, 30 * (2 ** max(0, int(job.get("attempt_count", 1)) - 1)))
                    self.repo.finish_job(job["id"], ctx.owner, ctx.generation, state=state,
                                         error_code=error.code, error_detail=str(error)[:1200],
                                         retry_delay=random.uniform(delay * 0.8, delay * 1.2) if state == "retry_wait" else None)
                    ctx.finished = True
                except Exception:
                    # A lost lease or unavailable DB cannot authorize an update.
                    pass
        finally:
            try:
                ctx.cleanup()
            finally:
                self._active.pop(str(job["id"]), None)
        return True

    @staticmethod
    def _classify(exc: Exception) -> MediaJobError:
        if isinstance(exc, MediaJobError):
            return exc
        if getattr(exc, "code", "") == "STORAGE_UNAVAILABLE":
            return MediaJobError("STORAGE_UNAVAILABLE", str(exc), state="blocked")
        if (getattr(exc, "details", None) or {}).get("code") == "INPUT_CHANGED":
            return MediaJobError("INPUT_CHANGED", str(exc))
        if isinstance(exc, FileExistsError):
            return MediaJobError("OUTPUT_EXISTS", "An existing destination was preserved.", state="blocked")
        if isinstance(exc, FileNotFoundError):
            return MediaJobError("INPUT_OR_TOOL_MISSING", "A required media file, storage path, or tool is missing.", state="blocked")
        if isinstance(exc, OSError):
            code = "STORAGE_FULL" if exc.errno in {errno.ENOSPC, errno.EDQUOT} else "STORAGE_UNAVAILABLE"
            return MediaJobError(code, str(exc), state="blocked")
        return MediaJobError("MEDIA_JOB_FAILED", str(exc))

    def reconcile(self, *, startup: bool = False) -> None:
        """Resolve pending links before reclaiming interrupted process leases."""
        self.acquire_instance_lock()
        with self._recovery_lock:
            self._reconcile_publications()
            confirmed: dict[str, dict[str, Any]] = {}
            def inspect(attempt: dict[str, Any]) -> bool | None:
                if str(attempt.get("job_id")) in self._active:
                    return False
                absent = process_confirmed_absent(attempt)
                if absent is True:
                    confirmed[str(attempt.get("job_id"))] = attempt
                return absent
            recovered = self.repo.recover_expired(inspect, include_unexpired=startup)
            for job in recovered:
                if job["state"] in {"retry_wait", "cancelled", "failed"} and str(job["id"]) in confirmed:
                    self._cleanup_interrupted(confirmed[str(job["id"])])
            self._reconciled = True
            self._last_recovery = time.monotonic()

    def _reconcile_publications(self) -> None:
        for publication in self.repo.list_publications(states=("pending",)):
            self._reconcile_publication(publication)

    def _reconcile_publication(self, publication: dict[str, Any]) -> None:
        attempt = publication.get("attempt") or publication
        if str(publication.get("job_id")) in self._active:
            return
        absent = process_confirmed_absent(attempt)
        if absent is not True:
            self.repo.reject_publication(publication["id"], error_code="PROCESS_UNCERTAIN",
                                         error_detail="The previous process identity is still live or uncertain.")
            return
        metadata = publication.get("metadata") or {}
        artifact, result = metadata.get("artifact") or {}, metadata.get("result") or {}
        generation = int(publication.get("generation") or publication.get("lease_generation") or attempt.get("generation") or 0)
        try:
            from module.v2_storage import resolve_storage_path
            storage = self._storage(str(artifact["storage_id"]))
            final = resolve_storage_path(storage, artifact["relative_path"], must_exist=False)
            if str(final) != str(publication["final_path"]):
                raise MediaJobError("PUBLICATION_UNCERTAIN", "The registered output path no longer matches its publication intent.", state="blocked")
            if not os.path.lexists(final):
                self.repo.reconcile_publication(publication["id"], published=False,
                                                expected_generation=generation, process_confirmed_absent=True)
                self._cleanup_reconciled(publication)
                return
            item = PinnedInput.open(artifact, final)
            try:
                if item.fingerprint[:3] != (metadata.get("device"), metadata.get("inode"), metadata.get("size")):
                    raise MediaJobError("PUBLICATION_CONFLICT", "An existing output does not belong to this publication attempt.", state="blocked")
                if _hash_fd(item.fd) != metadata.get("sha256"):
                    raise MediaJobError("PUBLICATION_CHANGED", "The published output content changed before recovery.", state="blocked")
                item.check()
            finally:
                item.close()
            result = {**result, "reconciled": True}
            self.repo.reconcile_publication(publication["id"], artifact=artifact, result=result,
                                            expected_generation=generation, process_confirmed_absent=True)
            self._cleanup_reconciled(publication)
        except Exception as exc:
            error = self._classify(exc)
            self.repo.reject_publication(publication["id"], error_code=error.code, error_detail=str(error)[:1200])

    @staticmethod
    def _cleanup_interrupted(attempt: dict[str, Any]) -> None:
        directory = Path(attempt.get("work_dir") or ".")
        prefix = f".lar-v2-{attempt.get('job_id')}-{attempt.get('id')}-"
        if not directory.name.startswith(prefix):
            return
        try:
            parent_fd = _open_directory(directory.parent)
            try:
                fd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
                try:
                    marker_fd = os.open("owner.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                    with os.fdopen(marker_fd) as stream:
                        marker = json.load(stream)
                    if (str(marker.get("job_id")) != str(attempt.get("job_id")) or
                        str(marker.get("attempt_id")) != str(attempt.get("id")) or
                        directory.name != prefix + str(marker.get("nonce"))):
                        return
                    for name in ["owner.json", "concat.txt", *("output.partial" + suffix for suffix in V2Worker.MEDIA_SUFFIXES)]:
                        try:
                            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        except FileNotFoundError:
                            continue
                        if stat.S_ISREG(info.st_mode):
                            os.unlink(name, dir_fd=fd)
                    with contextlib.suppress(OSError):
                        os.rmdir(directory.name, dir_fd=parent_fd)
                finally:
                    os.close(fd)
            finally:
                os.close(parent_fd)
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _cleanup_reconciled(publication: dict[str, Any]) -> None:
        # Only the validated output and marker from this exact attempt may be
        # removed. Unknown leftovers, links, and directories are never adopted.
        temporary = Path(publication["temporary_path"])
        metadata = publication.get("metadata") or {}
        try:
            fd = _open_directory(temporary.parent)
            try:
                marker_fd = os.open("owner.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                with os.fdopen(marker_fd) as stream:
                    marker = json.load(stream)
                if marker.get("nonce") != metadata.get("work_nonce"):
                    return
                info = os.stat(temporary.name, dir_fd=fd, follow_symlinks=False)
                if (info.st_dev, info.st_ino) != (metadata.get("device"), metadata.get("inode")):
                    return
                os.unlink(temporary.name, dir_fd=fd)
                # concat.txt is also private, but leave arbitrary unknown files.
                for name in ("concat.txt", "owner.json"):
                    with contextlib.suppress(FileNotFoundError):
                        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISREG(info.st_mode):
                            os.unlink(name, dir_fd=fd)
            finally:
                os.close(fd)
            with contextlib.suppress(OSError):
                temporary.parent.rmdir()
        except (OSError, ValueError, TypeError):
            pass


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "--exec-gated":
    _exec_gated()
