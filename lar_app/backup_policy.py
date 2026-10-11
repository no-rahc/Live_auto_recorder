"""Shared secret filtering for backup/export and sanitized restore paths.

Secret fields are omitted, never replaced with masked strings that might later
be saved as credentials. Match keys recursively, including extension settings.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from lar_app.security import secret_backups_allowed


def is_secret_key(key: str) -> bool:
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key)).lower().replace("-", "_")
    return (
        key in {"authorization", "auth", "authentication", "webhooks", "credentials", "credential", "cookie", "cookies", "telegram_chat_id", "chat_id", "nid_aut", "nid_ses"}
        or any(word in key for word in ("password", "passwd", "secret", "token", "api_key", "apikey", "private_key", "webhook_url"))
        or key.endswith("_cookie")
    )


def sanitize_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_secrets(item) for key, item in value.items() if not is_secret_key(key)}
    if isinstance(value, list):
        return [sanitize_secrets(item) for item in value]
    return deepcopy(value)


def preserve_existing_secrets(incoming: Any, current: Any) -> Any:
    """Restore omitted secret fields without overriding explicit new values.

    List credentials are copied only for matching identities, never blindly
    transferred to a different webhook/channel at the same list position.
    """
    result = deepcopy(incoming)
    if isinstance(result, dict) and isinstance(current, dict):
        for key, old in current.items():
            if key not in result:
                if is_secret_key(key):
                    result[key] = deepcopy(old)
            else:
                result[key] = preserve_existing_secrets(result[key], old)
    elif isinstance(result, list) and isinstance(current, list):
        for index, item in enumerate(result):
            if not isinstance(item, dict):
                continue
            identity = next((key for key in ("id", "url", "name") if item.get(key)), None)
            old = next((entry for entry in current if isinstance(entry, dict) and entry.get(identity) == item[identity]), {}) if identity else {}
            result[index] = preserve_existing_secrets(item, old)
    return result
