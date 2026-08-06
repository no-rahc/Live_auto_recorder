"""Runtime security defaults for public and self-hosted deployments."""
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
    """Apply cookie security flags before Starlette builds its middleware stack."""

    https_only = env_flag("SESSION_HTTPS_ONLY", False, environ)
    for middleware in getattr(app, "user_middleware", []):
        if getattr(middleware, "cls", None) is SessionMiddleware:
            middleware.kwargs["https_only"] = https_only
            middleware.kwargs.setdefault("same_site", "lax")
            app.middleware_stack = None
            return


def enforce_login_default(app: Any, core: Any, environ: Mapping[str, str] | None = None) -> bool:
    """Require login unless the operator explicitly enables anonymous mode."""

    if env_flag("ALLOW_ANONYMOUS", False, environ):
        return False

    config = getattr(getattr(app, "state", None), "config", None)
    if not isinstance(config, dict) or config.get("loginMode") is True:
        return False

    config["loginMode"] = True
    save_config = getattr(core, "saveConfig", None)
    if callable(save_config):
        save_config(config)
    return True


def secret_backups_allowed(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether backups containing account and platform secrets are enabled."""

    return env_flag("ALLOW_SECRET_BACKUPS", False, environ)
