"""Per-recording session diagnostics with bounded process stderr capture."""
from __future__ import annotations

import contextvars
import os
import re
import threading
import time
import uuid
from collections import deque
from typing import Any

_CURRENT: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "lar_recording_trace", default=None
)
_LOCK = threading.RLock()
_SESSIONS: dict[str, dict[str, Any]] = {}
_MAX_LINES = max(20, min(int(os.getenv("RECORDING_STDERR_TAIL_LINES", "120")), 500))
_MAX_LINE_CHARS = max(120, min(int(os.getenv("RECORDING_STDERR_LINE_CHARS", "600")), 2000))
_MAX_TAIL_CHARS = max(2000, min(int(os.getenv("RECORDING_STDERR_TAIL_CHARS", "12000")), 50000))

_REDACTIONS = (
    re.compile(r"(NID_(?:SES|AUT)=)[^;\s]+", re.I),
    re.compile(r"((?:Cookie|Authorization)\s*:\s*)[^\r\n]+", re.I),
)


def _redact(value: str) -> str:
    text = str(value or "")
    for pattern in _REDACTIONS:
        text = pattern.sub(r"\1***", text)
    return text


def begin_session(channel_id: str, platform: str = "") -> tuple[str, contextvars.Token]:
    """Start a trace context for one recorder attempt and return its session id/token."""
    cid = str(channel_id or "unknown")
    session_id = uuid.uuid4().hex
    now = time.time()
    with _LOCK:
        _SESSIONS[cid] = {
            "channel_id": cid,
            "platform": str(platform or "").lower(),
            "session_id": session_id,
            "started_epoch": now,
            "ended_epoch": 0.0,
            "last_stderr_epoch": 0.0,
            "active": True,
            "stderr_tail": deque(maxlen=_MAX_LINES),
        }
    token = _CURRENT.set((cid, session_id))
    return session_id, token


def end_session(channel_id: str, session_id: str, token: contextvars.Token) -> None:
    cid = str(channel_id or "unknown")
    with _LOCK:
        state = _SESSIONS.get(cid)
        if state and state.get("session_id") == session_id:
            state["active"] = False
            state["ended_epoch"] = time.time()
    try:
        _CURRENT.reset(token)
    except (LookupError, ValueError):
        pass


def append_stderr(channel_id: str, value: str, *, source: str = "process") -> None:
    """Append redacted process stderr lines to the latest channel session."""
    cid = str(channel_id or "unknown")
    with _LOCK:
        state = _SESSIONS.get(cid)
        if not state:
            return
        tail = state.get("stderr_tail")
        if tail is None:
            return
        for raw in str(value or "").splitlines():
            line = _redact(raw.strip())
            if not line:
                continue
            tail.append(f"[{source}] {line}"[:_MAX_LINE_CHARS])
        state["last_stderr_epoch"] = time.time()


def trace_fields(channel_id: str, *, include_tail: bool = False) -> dict[str, Any]:
    """Return the latest session diagnostics for history/audit correlation."""
    cid = str(channel_id or "unknown")
    with _LOCK:
        state = _SESSIONS.get(cid)
        if not state:
            return {}
        result: dict[str, Any] = {
            "session_id": str(state.get("session_id") or ""),
            "session_platform": str(state.get("platform") or ""),
            "session_started_epoch": float(state.get("started_epoch") or 0.0),
            "session_active": bool(state.get("active")),
        }
        ended = float(state.get("ended_epoch") or 0.0)
        last_stderr = float(state.get("last_stderr_epoch") or 0.0)
        if ended:
            result["session_ended_epoch"] = ended
        if last_stderr:
            result["last_stderr_epoch"] = last_stderr
        if include_tail:
            joined = "\n".join(list(state.get("stderr_tail") or ()))
            if joined:
                result["process_stderr_tail"] = joined[-_MAX_TAIL_CHARS:]
        return result


def current_session_id(channel_id: str = "") -> str:
    current = _CURRENT.get()
    if current and (not channel_id or current[0] == str(channel_id)):
        return current[1]
    return str(trace_fields(channel_id).get("session_id") or "") if channel_id else ""


def install_live_recorder_stderr_capture() -> None:
    """Wrap the Chzzk stderr reader without changing recorder process semantics."""
    from module import live_recorder

    original = getattr(live_recorder, "read_stderr", None)
    if not original or getattr(original, "_lar_trace_wrapped", False):
        return

    async def traced_read_stderr(proc, channel_id):
        try:
            while True:
                stderr_chunk = await proc.stderr.read(1024)
                if not stderr_chunk:
                    break
                try:
                    decoded = stderr_chunk.decode(live_recorder.default_encoding, errors="replace")
                except UnicodeDecodeError:
                    decoded = stderr_chunk.decode("utf-8", errors="replace")
                append_stderr(
                    str(channel_id),
                    decoded,
                    source=f"pid:{getattr(proc, 'pid', '?')}",
                )
                live_recorder.logger.debug(decoded.rstrip())
        except Exception as exc:
            live_recorder.logger.error(f"read_stderr 중 오류 발생: {exc}")

    traced_read_stderr._lar_trace_wrapped = True
    live_recorder.read_stderr = traced_read_stderr
