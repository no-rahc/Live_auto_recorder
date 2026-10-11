"""Durable channel intent and broadcast-scoped controls over the legacy engines.

The engine remains responsible for capture. This layer commits user intent first
and makes its admission decision from the *same metadata* the engine consumes.
No policy is installed for a legacy (feature-flag off) session.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import re
import signal
import time
import uuid
from contextlib import contextmanager
from typing import Any
from pathlib import Path

from module.data_manager import RecorderManager
from module.v2_repository import NotFound
from module.v2_worker import _group_members, boot_identity

_ACTIVE_POLICY: contextvars.ContextVar[Any] = contextvars.ContextVar("lar_v2_channel_policy", default=None)


class ChannelControlError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409, details: Any = None):
        super().__init__(message)
        self.code, self.status_code, self.details = code, status_code, details or {}


def provider_broadcast_identity(channel: dict, metadata: dict | None) -> tuple[str | None, str | None]:
    """Use a provider identifier, never a mutable title or date-only fallback."""
    meta = metadata or {}
    platform = str(channel.get("platform") or "").lower()
    value = (meta.get("liveId") or meta.get("live_id")) if platform == "chzzk" else (
        meta.get("video_id") or meta.get("videoId") if platform == "youtube" else meta.get("provider_live_id")
    )
    if value is None or str(value).strip() == "":
        return None, None
    provider_id = str(value)
    payload = json.dumps([platform, str(channel["id"]), provider_id], separators=(",", ":"))
    return "live-" + hashlib.sha256(payload.encode()).hexdigest()[:32], provider_id


def allow_capture(channel: dict, metadata: dict | None, *, is_live: bool) -> bool:
    """Legacy-safe engine hook. A rejected admission must never spawn a process."""
    policy = _ACTIVE_POLICY.get()
    return True if policy is None else policy.admit_metadata(channel, metadata, is_live=is_live)


def capture_policy_active() -> bool:
    return _ACTIVE_POLICY.get() is not None


def capture_started(channel_id: str, path: str, process: Any) -> None:
    policy = _ACTIVE_POLICY.get()
    if policy is not None:
        policy.capture_started(channel_id, path, process)


def capture_process_launched(channel_id: str, process: Any) -> None:
    policy = _ACTIVE_POLICY.get()
    if policy is not None:
        policy.retain_capture_process(channel_id, process)


def capture_finished(channel_id: str) -> None:
    policy = _ACTIVE_POLICY.get()
    if policy is not None:
        policy.capture_finished(channel_id)


def capture_moved(source: str, destination: str) -> None:
    policy = _ACTIVE_POLICY.get()
    if policy is not None:
        for capture in policy._captures.values():
            if os.path.abspath(capture["path"]) == os.path.abspath(source):
                capture["path"] = destination


def event_identity(channel_id: str) -> dict:
    policy = _ACTIVE_POLICY.get()
    if policy is None:
        return {}
    identity = policy._identities.get(channel_id, {})
    return {key: identity[key] for key in ("broadcast_id", "provider_live_id", "identity_basis", "title") if key in identity}


class ChannelControlService:
    def __init__(self, repository: Any, fsm: Any):
        self.repository = repository
        self.fsm = fsm
        self.manager = getattr(fsm, "rm", RecorderManager())
        self._locks: dict[str, asyncio.Lock] = {}
        self._once: dict[str, dict] = {}
        self._continuing: dict[str, str] = {}
        self._current: dict[str, str] = {}
        self._reasons: dict[str, str] = {}
        self._stopping: set[str] = set()
        self._identities: dict[str, dict] = {}
        self._captures: dict[str, dict] = {}
        self._owned_processes: dict[str, list[dict]] = {}
        self._blocked_processes: set[str] = set()

    def _channel(self, cid: str) -> dict:
        channel = next((c for c in (self.manager.getChannels() or []) if str(c.get("id")) == str(cid)), None)
        if channel is None:
            raise ChannelControlError("CHANNEL_NOT_FOUND", "Unknown channel", 404)
        return channel

    def _lock(self, cid: str) -> asyncio.Lock:
        return self._locks.setdefault(cid, asyncio.Lock())

    def _ensure(self, cid: str) -> dict:
        channel = self._channel(cid)
        try:
            state = self.repository.get_channel(cid)
        except NotFound:
            state = self.repository.upsert_channel(
                cid, platform=str(channel.get("platform") or ""), name=str(channel.get("name") or cid),
                desired_mode="auto" if channel.get("record_enabled", True) else "paused",
            )
        # Compatibility projection only. The repository is the source of intent.
        channel["record_enabled"] = state["desired_mode"] == "auto"
        return state

    async def initialize(self, channels: list[dict], *, auto_start: bool = True) -> None:
        # A previously accepted start is uncertain after a crash: do not replay it.
        cursor = None
        while True:
            page = self.repository.list_commands(states=["accepted", "running"], limit=100, cursor=cursor)
            for command in page["items"]:
                self.repository.update_command(command["id"], "interrupted", error_code="RESTART_INTERRUPTED")
            cursor = page.get("next_cursor")
            if not cursor:
                break
        for channel in channels:
            cid = str(channel["id"])
            state = self.repository.upsert_channel(
                cid, platform=str(channel.get("platform") or ""), name=str(channel.get("name") or cid),
                desired_mode="auto" if auto_start and channel.get("record_enabled", True) else "paused",
            )
            channel["record_enabled"] = state["desired_mode"] == "auto"
            # Never mistake persisted observation for a surviving process.
            self.repository.observe_channel(cid, "idle", reason_code="RECONCILED_AFTER_RESTART")
        self.fsm.v2_policy = self

    async def start_watching(self) -> None:
        """Called by assembly after storage guards and the dispatcher are ready."""
        await self.fsm.startAllWatching()
        for channel in self.manager.getChannels() or []:
            cid = str(channel["id"])
            if self._ensure(cid)["desired_mode"] == "auto":
                self._note_start_admission(cid)

    def _note_start_admission(self, cid: str) -> bool:
        admitted = self.fsm._procAlive(cid) or self.fsm.getState(cid) in {"WATCHING", "RECORDING"}
        if not admitted:
            self._observe(cid, "blocked", "ADMISSION_BLOCKED")
            self._finish_once(cid, state="blocked", reason="ADMISSION_BLOCKED")
        return bool(admitted)

    def should_watch(self, cid: str) -> bool:
        try:
            state = self._ensure(cid)
        except ChannelControlError:
            return False
        return cid not in self._stopping and cid not in self._blocked_processes and (
            state["desired_mode"] == "auto" or cid in self._once or cid in self._continuing
        )

    def session_is_manual(self, cid: str) -> bool:
        return cid in self._once or cid in self._continuing

    @contextmanager
    def session_context(self, cid: str):
        token = _ACTIVE_POLICY.set(self)
        try:
            yield
        finally:
            _ACTIVE_POLICY.reset(token)

    def _observe(self, cid: str, state: str, reason: str = "", broadcast_id: str | None = None):
        self._reasons[cid] = reason
        self.repository.observe_channel(cid, state, reason_code=reason, current_broadcast_id=broadcast_id)

    def _finish_once(self, cid: str, *, state: str = "succeeded", reason: str = ""):
        scope = self._once.pop(cid, None)
        if scope:
            self.repository.update_command(scope["command_id"], state, error_code=reason,
                                           result={"broadcast_id": scope.get("broadcast_id")})

    def admit_metadata(self, channel: dict, metadata: dict | None, *, is_live: bool) -> bool:
        cid = str(channel["id"])
        state = self._ensure(cid)
        if cid in self._stopping:
            return False
        if cid in self._blocked_processes or self.capture_is_active(cid):
            self._observe(cid, "blocked", "CAPTURE_RECONCILIATION_REQUIRED", self._current.get(cid))
            self._finish_once(cid, state="blocked", reason="CAPTURE_RECONCILIATION_REQUIRED")
            return False
        meta = metadata or {}
        if not is_live:
            # Missing metadata is a network uncertainty, not evidence of an end.
            confirmed_offline = meta.get("metadata_available", True) and (str(meta.get("status") or "").upper() in {"CLOSE", "CLOSED", "ENDED"} or (
                "is_live" in meta and meta["is_live"] is False
            ))
            if confirmed_offline:
                self._current.pop(cid, None)
                self._continuing.pop(cid, None)
                self._finish_once(cid, state="succeeded" if self._once.get(cid, {}).get("broadcast_id") else "failed",
                                  reason="" if self._once.get(cid, {}).get("broadcast_id") else "NOT_LIVE")
            self._observe(cid, "watching" if state["desired_mode"] == "auto" else "idle",
                          "NOT_LIVE" if confirmed_offline else "METADATA_UNAVAILABLE")
            return False

        broadcast_id, provider_id = provider_broadcast_identity(channel, meta)
        if broadcast_id is None:
            # Reuse only within this running scope; never infer identity by title.
            broadcast_id = self._current.get(cid) or "heuristic-" + uuid.uuid4().hex
        broadcast = self.repository.upsert_broadcast(
            broadcast_id, cid, platform=str(channel.get("platform") or ""), provider_live_id=provider_id,
            title=str(meta.get("live_title") or meta.get("liveTitle") or meta.get("title") or ""),
            identity_basis="provider" if provider_id else "heuristic", status="live",
        )
        broadcast_id = broadcast["id"]
        once = self._once.get(cid)
        continuing = self._continuing.get(cid)
        if once and once.get("broadcast_id") is None:
            once["broadcast_id"] = broadcast_id
        once_allowed = bool(once and once.get("broadcast_id") == broadcast_id)
        continuing_allowed = continuing == broadcast_id
        if once and not once_allowed:
            self._finish_once(cid)
        if continuing and not continuing_allowed:
            self._continuing.pop(cid, None)

        # An explicit once command may override a prior stop, but never clears
        # durable suppression and never changes the user's automatic mode.
        if not once_allowed and self.repository.is_suppressed(cid, broadcast_id):
            self._observe(cid, "idle", "BROADCAST_SUPPRESSED", broadcast_id)
            return False
        if not once_allowed and not continuing_allowed and state["desired_mode"] != "auto":
            self._current.pop(cid, None)
            self._observe(cid, "idle", "PAUSED")
            return False
        from module.v2_runtime import capture_storage_report
        storage = capture_storage_report(channel)
        if not storage.get("ok", False):
            reason = storage.get("reason_code") or "STORAGE_UNAVAILABLE"
            self._observe(cid, "blocked", reason, broadcast_id)
            self._finish_once(cid, state="blocked", reason=reason)
            return False
        self._current[cid] = broadcast_id
        self._identities[cid] = {"broadcast_id": broadcast_id, "provider_live_id": provider_id,
                                 "identity_basis": "provider" if provider_id else "heuristic",
                                 "title": broadcast["title"]}
        self._observe(cid, "starting", "", broadcast_id)
        return True

    def capture_started(self, cid: str, path: str, process: Any) -> None:
        if cid not in self._current:
            raise ChannelControlError("CAPTURE_NOT_ADMITTED", "Capture has no admitted broadcast", 409)
        # Numeric segment patterns are materialized only after the encoder closes
        # them; no imaginary '%03d.ts' artifact is added to the library.
        pattern = re.search(r"%0?\d*d", Path(path).name)
        self._captures[cid] = {"path": str(path), "initial_path": str(path), "process": process,
                               "pattern": bool(pattern), "started": False, "identity": dict(self._identities[cid])}
        self.retain_capture_process(cid, process)
        if not pattern:
            self._capture_event(cid, "recording_started", str(path), self._captures[cid])
            self._captures[cid]["started"] = True
        self._observe(cid, "recording", "", self._current[cid])

    def capture_process(self, cid: str) -> Any:
        process = self._captures.get(cid, {}).get("process")
        if process is not None:
            return process
        records = self._owned_processes.get(cid, [])
        return records[0]["process"] if records else None

    def retain_capture_process(self, cid: str, process: Any) -> None:
        """Retain the original process group before a leader can exit/reap."""
        import psutil
        records = self._owned_processes.setdefault(cid, [])
        if any(item["process"] is process for item in records):
            return
        record = {"process": process, "pid": int(process.pid), "pgid": int(process.pid),
                  "started_at": None, "boot_id": boot_identity()}
        records.append(record)
        try:
            record["started_at"] = psutil.Process(process.pid).create_time()
            if os.name == "posix":
                record["pgid"] = os.getpgid(process.pid)
                if record["pgid"] != process.pid or record["pgid"] == os.getpgrp():
                    raise RuntimeError("Capture was not launched in its own process group")
        except (ProcessLookupError, psutil.NoSuchProcess):
            # Fast-exiting leaders are safe only if their entire expected group
            # has already disappeared. Otherwise ownership is uncertain.
            if os.name == "posix" and _group_members(record["pgid"]) != []:
                self._blocked_processes.add(cid)
        except Exception:
            self._blocked_processes.add(cid)
            raise
        from module.v2_runtime import record_capture_process
        record_capture_process(process)

    def _capture_group_members(self, record: dict) -> list[int] | None:
        import psutil
        if record["boot_id"] != boot_identity():
            return []
        if os.name != "posix":
            return [] if record["process"].returncode is not None else [record["pid"]]
        if record["pgid"] <= 1 or record["pgid"] != record["pid"] or record["pgid"] == os.getpgrp():
            return None  # Never signal an inherited or the application's group.
        try:
            process = psutil.Process(record["pid"])
            if record["started_at"] is None or abs(process.create_time() - record["started_at"]) > 0.01:
                return None
        except psutil.NoSuchProcess:
            pass
        except psutil.Error:
            return None
        members = _group_members(record["pgid"])
        if members and record["started_at"] is None:
            return None
        return members

    def capture_is_active(self, cid: str) -> bool:
        records = self._owned_processes.get(cid, [])
        if records:
            return any(self._capture_group_members(record) != [] for record in records)
        process = self._captures.get(cid, {}).get("process")
        return bool(process is not None and process.returncode is None)

    async def terminate_capture_groups(self, cid: str, *, process: Any = None, timeout: float = 3.0) -> None:
        """Return only after every owned POSIX group has no live descendants."""
        if not self._owned_processes.get(cid) and process is not None:
            self.retain_capture_process(cid, process)
        records = list(self._owned_processes.get(cid, []))
        if not records:
            return

        def signal_groups(sig: int) -> None:
            for record in records:
                members = self._capture_group_members(record)
                if members is None:
                    raise RuntimeError("Capture group ownership could not be verified")
                if members:
                    try:
                        os.killpg(record["pgid"], sig)
                    except ProcessLookupError:
                        pass

        async def wait_groups() -> bool:
            deadline = time.monotonic() + max(0.05, timeout)
            while True:
                members = [self._capture_group_members(record) for record in records]
                if all(value == [] for value in members):
                    return True
                if any(value is None for value in members):
                    raise RuntimeError("Capture group absence could not be verified")
                if time.monotonic() >= deadline:
                    return False
                await asyncio.sleep(min(0.05, max(0.001, deadline - time.monotonic())))

        try:
            signal_groups(signal.SIGTERM)
            if not await wait_groups():
                signal_groups(signal.SIGKILL)
                if not await wait_groups():
                    raise RuntimeError("Capture descendants survived forced termination")
            for record in records:
                if record["process"].returncode is None:
                    await asyncio.wait_for(record["process"].wait(), timeout=max(0.1, timeout))
        except BaseException as exc:
            self._blocked_processes.add(cid)
            self._observe(cid, "blocked", "CAPTURE_RECONCILIATION_REQUIRED", self._current.get(cid))
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise ChannelControlError("CAPTURE_RECONCILIATION_REQUIRED", "Capture process group termination could not be confirmed", 503) from exc
        # Keep records until capture_finished has indexed stable output. Their
        # original PGIDs remain available if another finalizer runs meanwhile.
        self._blocked_processes.discard(cid)

    def _capture_event(self, cid: str, event: str, path: str, capture: dict, **extra) -> None:
        from module.recording_history import log_event
        channel = self.repository.get_channel(cid)
        log_event(cid, str(channel.get("name") or cid), str(channel.get("platform") or ""), event,
                  filename=path, extra={**capture["identity"], **extra})

    def capture_finished(self, cid: str) -> None:
        capture = self._captures.get(cid)
        if not capture:
            if self.capture_is_active(cid):
                self._blocked_processes.add(cid)
                self._observe(cid, "blocked", "CAPTURE_RECONCILIATION_REQUIRED", self._current.get(cid))
            else:
                self._owned_processes.pop(cid, None)
            return
        process = capture["process"]
        # A cancelled watch may have handed finalization to a shielded segment
        # pipeline. Its outputs are still being written until the process exits.
        if self.capture_is_active(cid):
            if process is not None and process.returncode is not None:
                self._blocked_processes.add(cid)
                self._observe(cid, "blocked", "CAPTURE_RECONCILIATION_REQUIRED", self._current.get(cid))
            return
        self._owned_processes.pop(cid, None)
        self._blocked_processes.discard(cid)
        self._captures.pop(cid, None)
        path = Path(capture["path"])
        if capture["pattern"]:
            pattern = re.search(r"%0?\d*d", path.name)
            regex = re.compile(re.escape(path.name[:pattern.start()]) + r"(\d+)" + re.escape(path.name[pattern.end():]))
            paths = sorted((item for item in path.parent.iterdir() if regex.fullmatch(item.name)
                            and item.is_file() and not item.is_symlink()), key=lambda item: int(regex.fullmatch(item.name).group(1))) if path.parent.is_dir() else []
        else:
            paths = [path]
        for final_path in paths:
            if capture["pattern"] or not capture["started"]:
                self._capture_event(cid, "recording_started", str(final_path), capture, timing_estimated=True)
            exists = final_path.is_file() and not final_path.is_symlink()
            nonempty = exists and final_path.stat().st_size > 0
            event = "recording_stopped" if nonempty else "recording_failed"
            initial = str(final_path) if capture["pattern"] else capture["initial_path"]
            self._capture_event(cid, event, initial, capture,
                                process_exit_code=getattr(process, "returncode", None),
                                final_file_path=str(final_path), final_filename=final_path.name,
                                stop_reason="stop_current" if cid in self._stopping else "",
                                capture_outcome="ended" if nonempty else "output_missing")

    def session_finished(self, cid: str, outcome: Any) -> bool:
        self.capture_finished(cid)
        if cid in self._blocked_processes:
            self._finish_once(cid, state="blocked", reason="CAPTURE_RECONCILIATION_REQUIRED")
            return False
        value = str(getattr(outcome, "value", outcome) or "")
        if cid in self._stopping:
            self._finish_once(cid, reason="STOP_CURRENT")
            self._continuing.pop(cid, None)
            return False
        if value in {"fatal_error", "unsupported", "user_stopped"}:
            self._finish_once(cid, state="failed", reason=value.upper())
            self._continuing.pop(cid, None)
            self._observe(cid, "error" if value != "user_stopped" else "idle", value.upper())
            return False
        if value == "retryable_error":
            self._observe(cid, "reconnecting", "RECORDER_RETRY", self._current.get(cid))
        # A once request with no positively identified live must not wait forever.
        if cid in self._once and not self._once[cid].get("broadcast_id"):
            self._finish_once(cid, state="failed", reason="NOT_LIVE")
        return self.should_watch(cid)

    def get_channel(self, cid: str) -> dict:
        state = dict(self._ensure(cid))
        process = self.manager.get_tasks_process(cid) or self.capture_process(cid)
        alive = bool(process and process.returncode is None) or self.capture_is_active(cid)
        recording = bool(self.manager.get_status_recording(cid))
        current = self._current.get(cid)
        reason = self._reasons.get(cid, state.get("reason_code") or "")
        if cid in self._stopping:
            actual = "stopping"
        elif cid in self._blocked_processes:
            actual = "blocked"
        elif alive or recording:
            actual = "recording"
            reason = ""
        elif reason == "BROADCAST_SUPPRESSED":
            actual = "idle"
        elif state.get("actual_state") in {"blocked", "error", "reconnecting"}:
            actual = state["actual_state"]
        elif self.fsm.getState(cid) == "WATCHING":
            actual = "starting" if cid in self._once else "watching"
        else:
            actual = "idle"
        state.update(actual_state=actual, observed_at=time.time(), reason_code=reason,
                     broadcast_id=current, current_broadcast_id=current)
        # Only a curated metadata projection is part of the public contract.
        state.pop("metadata", None)
        return state

    def list_channels(self) -> list[dict]:
        return [self.get_channel(str(channel["id"])) for channel in (self.manager.getChannels() or [])]

    async def patch_mode(self, cid: str, desired_mode: str, expected_revision: int) -> dict:
        if desired_mode not in {"auto", "paused"}:
            raise ChannelControlError("INVALID_DESIRED_MODE", "Expected auto or paused", 422)
        async with self._lock(cid):
            self._ensure(cid)
            self.repository.set_desired_mode(cid, desired_mode, expected_revision)
            self._channel(cid)["record_enabled"] = desired_mode == "auto"
            if desired_mode == "paused":
                # Keep the already-admitted broadcast, including reconnects.
                if self._current.get(cid):
                    self._continuing[cid] = self._current[cid]
                if not self._continuing.get(cid) and cid not in self._once:
                    await self.fsm.onRecordEnabledChanged(cid, enabled=False)
            else:
                self._continuing.pop(cid, None)
                await self.fsm.userStart(cid)
                self._note_start_admission(cid)
            return self.get_channel(cid)

    async def command(self, cid: str, kind: str, idempotency_key: str, *, broadcast_id: str | None = None) -> dict:
        if kind not in {"start_once", "stop_current"}:
            raise ChannelControlError("INVALID_COMMAND", "Unknown channel command", 422)
        if not idempotency_key or len(idempotency_key) > 200:
            raise ChannelControlError("IDEMPOTENCY_KEY_REQUIRED", "Provide an Idempotency-Key up to 200 characters", 422)
        async with self._lock(cid):
            self._ensure(cid)
            if kind == "stop_current" and not broadcast_id:
                raise ChannelControlError("BROADCAST_REQUIRED", "stop_current requires the current broadcast_id", 422)
            # Repository validates replays first, so an old completed request
            # remains retrievable even after the broadcast changes.
            command = self.repository.create_command(cid, kind, idempotency_key=idempotency_key,
                                                     broadcast_id=broadcast_id)
            if not command.pop("created", False):
                return command
            command_id = command["id"]
            if kind == "stop_current" and broadcast_id != self._current.get(cid):
                self.repository.update_command(command_id, "failed", error_code="BROADCAST_CHANGED")
                raise ChannelControlError("BROADCAST_CHANGED", "The current broadcast changed; refresh before stopping", 409,
                                          self.get_channel(cid))
            self.repository.update_command(command_id, "running")
            try:
                if kind == "start_once":
                    if cid in self._once:
                        self.repository.update_command(command_id, "succeeded", result={"already_active": True})
                    elif self.manager.get_status_recording(cid) or self.fsm._procAlive(cid):
                        self.repository.update_command(command_id, "succeeded", result={"already_active": True})
                    else:
                        self._once[cid] = {"command_id": command_id, "broadcast_id": broadcast_id}
                        self._reasons[cid] = ""
                        await self.fsm.userStart(cid, is_user_request=True)
                        self._note_start_admission(cid)
                else:
                    self._stopping.add(cid)
                    self._observe(cid, "stopping", "STOP_CURRENT", broadcast_id)
                    await self.fsm.stop(cid, reason="stop_current")
                    self.capture_finished(cid)
                    self._finish_once(cid, reason="STOP_CURRENT")
                    self._continuing.pop(cid, None)
                    self._current.pop(cid, None)
                    self._observe(cid, "idle", "BROADCAST_SUPPRESSED", broadcast_id)
                    self.repository.update_command(command_id, "succeeded", result={"broadcast_id": broadcast_id})
            except BaseException as exc:
                if kind == "start_once" and self._once.get(cid, {}).get("command_id") == command_id:
                    self._once.pop(cid, None)
                if isinstance(exc, asyncio.CancelledError):
                    self.repository.update_command(command_id, "interrupted", error_code="COMMAND_INTERRUPTED")
                else:
                    self.repository.update_command(command_id, "failed", error_code="RECORDER_CONTROL_FAILED")
                raise
            finally:
                self._stopping.discard(cid)
            if kind == "stop_current" and self._ensure(cid)["desired_mode"] == "auto":
                # Poll for the next broadcast; the durable admission guard
                # prevents another capture of the stopped one.
                await self.fsm.userStart(cid)
            return self.repository.get_command(command_id)

    def get_command(self, command_id: str) -> dict | None:
        return self.repository.get_command(command_id)

    async def legacy_stop(self, cid: str) -> None:
        """Compatibility stop: never invent a broadcast for an untracked process."""
        snapshot = self.get_channel(cid)
        if snapshot.get("broadcast_id"):
            await self.command(cid, "stop_current", "legacy-stop:" + uuid.uuid4().hex,
                               broadcast_id=snapshot["broadcast_id"])
            return
        async with self._lock(cid):
            if snapshot["actual_state"] == "recording":
                # The process predates our metadata observation. Persist a
                # fail-closed guard before stopping, rather than guessing its ID.
                self.repository.set_channel_suppression(cid, "*")
            self._stopping.add(cid)
            try:
                await self.fsm.stop(cid, reason="stop_current")
                self.capture_finished(cid)
                self._finish_once(cid, reason="STOP_CURRENT")
                self._continuing.pop(cid, None)
                self._current.pop(cid, None)
                self._observe(cid, "idle", "USER_STOPPED")
            finally:
                self._stopping.discard(cid)
