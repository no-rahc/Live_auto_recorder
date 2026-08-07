"""Validated server configuration for the production entrypoint."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

import uvicorn


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_LOG_LEVEL = "info"
_ALLOWED_LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})


@dataclass(frozen=True, slots=True)
class ServerSettings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ServerSettings":
        source = env if env is not None else os.environ
        host = str(source.get("HOST", DEFAULT_HOST)).strip() or DEFAULT_HOST
        raw_port = str(source.get("PORT", DEFAULT_PORT)).strip()
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError(f"PORT must be an integer, got {raw_port!r}") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"PORT must be between 1 and 65535, got {port}")

        log_level = str(source.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)).strip().lower() or DEFAULT_LOG_LEVEL
        if log_level not in _ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(_ALLOWED_LOG_LEVELS))
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return cls(host=host, port=port, log_level=log_level)


def run_server(app: Any, settings: ServerSettings | None = None) -> None:
    """Run the assembled ASGI application with validated environment values."""

    resolved = settings or ServerSettings.from_env()
    uvicorn.run(
        app,
        host=resolved.host,
        port=resolved.port,
        log_level=resolved.log_level,
        access_log=True,
    )
