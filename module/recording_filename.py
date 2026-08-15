"""Filename-only fallbacks for incomplete recording metadata."""
from __future__ import annotations

import contextvars
import re
from functools import wraps
from typing import Any

_FILENAME_QUALITY: contextvars.ContextVar[str] = contextvars.ContextVar(
    "lar_recording_filename_quality",
    default="best",
)

_UNKNOWN_QUALITY = (
    "알 수 없는 품질",
    "Unknown Quality",
)
_UNKNOWN_FRAME_RATE = (
    "알 수 없는 프레임 레이트",
    "Unknown Frame Rate",
)


def begin_filename_context(channel: dict[str, Any] | None) -> contextvars.Token:
    """Remember the configured quality for filename fallback during one session."""
    quality = str((channel or {}).get("quality") or "best").strip() or "best"
    return _FILENAME_QUALITY.set(quality)


def end_filename_context(token: contextvars.Token) -> None:
    try:
        _FILENAME_QUALITY.reset(token)
    except (LookupError, ValueError):
        pass


def sanitize_recording_filename(filename: str, *, quality: str = "") -> str:
    """Replace metadata sentinel text without changing recorder quality selection."""
    text = str(filename or "")
    fallback_quality = str(quality or _FILENAME_QUALITY.get() or "best").strip() or "best"

    for marker in _UNKNOWN_QUALITY:
        text = re.sub(re.escape(marker), lambda _match: fallback_quality, text, flags=re.IGNORECASE)

    for marker in _UNKNOWN_FRAME_RATE:
        escaped = re.escape(marker)
        text = re.sub(
            rf"\s*[\[\(\{{]\s*{escaped}\s*[\]\)\}}]\s*",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(rf"\s*{escaped}\s*", " ", text, flags=re.IGNORECASE)

    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    text = re.sub(r"\s+(\.[^./\\\s]+)$", r"\1", text)
    return text


def install_live_recorder_filename_sanitizer() -> None:
    """Wrap live_recorder.uniqueFilename once so only filename text is normalized."""
    from module import live_recorder

    original = getattr(live_recorder, "uniqueFilename", None)
    if not original or getattr(original, "_lar_filename_sanitizer_wrapped", False):
        return

    @wraps(original)
    def sanitized_unique_filename(output_dir, filename, *args, **kwargs):
        return original(
            output_dir,
            sanitize_recording_filename(str(filename or "")),
            *args,
            **kwargs,
        )

    sanitized_unique_filename._lar_filename_sanitizer_wrapped = True
    live_recorder.uniqueFilename = sanitized_unique_filename
