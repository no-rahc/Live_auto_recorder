"""Pure helpers for safe local configuration updates."""
from __future__ import annotations

from typing import Any


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "on", "yes"}


def resolve_secret(posted: str | None, action: str | None, stored: str | None) -> str:
    """Resolve a masked secret field without exposing the stored value to the browser."""
    current = str(stored or "")
    candidate = str(posted or "").strip()
    choice = str(action or "").strip().lower()
    if choice == "clear":
        return ""
    if choice == "replace":
        return candidate
    if choice == "keep" or not candidate:
        return current
    return candidate


def validate_file_manager_transition(
    current: dict[str, Any],
    *,
    enabled: bool,
    mode: str,
    read_only: bool,
    trash_enabled: bool,
    acknowledgement: str = "",
) -> str | None:
    """Compatibility wrapper around the shared transition policy."""
    from lar_app.config_validation import ConfigValidationError, validate_transition
    candidate = dict(current, fileManagerEnabled=enabled, fileManagerMode=mode,
                     fileManagerReadOnly=read_only, trashEnabled=trash_enabled)
    try:
        validate_transition(current, candidate, acknowledgement)
    except ConfigValidationError as exc:
        return str(exc)
    return None
