"""Runtime security helpers for the local-only deployment model."""
from __future__ import annotations

import os
from typing import Any, Mapping

from starlette.middleware.sessions import SessionMiddleware


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def env_flag(name: str, default: bool = False, environ: Mapping[str, str] | None = None) -> bool:
    """Read a strict boolean environment flag."""

    source = os.environ if environ is None else environ
    raw = str(source.get(name, "")).strip().lower()
    if not raw:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of: true, false, 1, 0, yes, no, on, off")


def configure_session_middleware(app: Any, environ: Mapping[str, str] | None = None) -> None:
    """Keep the legacy session object available without exposing login controls."""

    del environ  # Kept in the signature for compatibility with older callers/tests.
    for middleware in getattr(app, "user_middleware", []):
        if getattr(middleware, "cls", None) is SessionMiddleware:
            middleware.kwargs["https_only"] = False
            middleware.kwargs.setdefault("same_site", "lax")
            app.middleware_stack = None
            return


def enforce_local_mode(app: Any, core: Any) -> bool:
    """Persist the application in passwordless local mode.

    The legacy core still reads ``loginMode`` in several places. Keeping that
    compatibility key forced to ``False`` makes those paths behave as local
    access while the surrounding application removes the login/account UI.
    """

    config = getattr(getattr(app, "state", None), "config", None)
    if not isinstance(config, dict) or config.get("loginMode") is False:
        return False

    config["loginMode"] = False
    save_config = getattr(core, "saveConfig", None)
    if callable(save_config):
        save_config(config)
    return True


def secret_backups_allowed(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether backups containing cookies and platform secrets are enabled."""

    return env_flag("ALLOW_SECRET_BACKUPS", False, environ)
