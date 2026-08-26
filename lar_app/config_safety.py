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
    """Require explicit acknowledgement when enabling or changing risky file access."""

    def risky(values: dict[str, Any]) -> bool:
        return bool(
            truthy(values.get("fileManagerEnabled"))
            and (
                str(values.get("fileManagerMode") or "whitelist") == "blacklist"
                or not truthy(values.get("fileManagerReadOnly"))
                or not truthy(values.get("trashEnabled"))
            )
        )

    next_values = {
        "fileManagerEnabled": enabled,
        "fileManagerMode": mode,
        "fileManagerReadOnly": read_only,
        "trashEnabled": trash_enabled,
    }
    changed = any(
        str(next_values[name]).lower() != str(current.get(name, default)).lower()
        for name, default in (
            ("fileManagerEnabled", False),
            ("fileManagerMode", "whitelist"),
            ("fileManagerReadOnly", True),
            ("trashEnabled", True),
        )
    )
    if risky(next_values) and (not risky(current) or changed):
        if acknowledgement.strip() != "위험 설정 적용":
            return "위험한 파일 관리자 설정을 적용하려면 확인 문구 ‘위험 설정 적용’을 입력하세요."
    return None
