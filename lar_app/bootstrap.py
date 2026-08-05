"""Assemble the legacy recorder core into the production ASGI application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import live_auto_recorder as recorder_core

from lar_app.release import ReleaseInfo, apply_release_info, load_release_info
from lar_app.web.middleware import ConsoleAssetsMiddleware, SecurityMiddleware
from module.config_tools_v1 import install_config_tools
from module.operations_v2 import install_operations


@dataclass(frozen=True, slots=True)
class ApplicationRuntime:
    """Objects produced while assembling the production application."""

    app: Any
    core: Any
    operations: Any
    release: ReleaseInfo


def _install_operations_lifespan(app: Any, operations: Any) -> None:
    core_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def application_lifespan(application):
        async with core_lifespan(application):
            await operations.start()
            try:
                yield
            finally:
                await operations.stop()

    app.router.lifespan_context = application_lifespan


def build_application(
    core: Any = recorder_core,
    *,
    root_dir: Path | None = None,
) -> ApplicationRuntime:
    """Build the application once while preserving the legacy public API."""

    app = core.app
    existing = getattr(app.state, "lar_runtime", None)
    if isinstance(existing, ApplicationRuntime):
        return existing

    release = load_release_info(core, root_dir=root_dir)
    apply_release_info(core, release)

    operations = install_operations(app, core)
    install_config_tools(app, core)
    _install_operations_lifespan(app, operations)

    # Preserve the original middleware order: security wraps HTML injection.
    app.add_middleware(ConsoleAssetsMiddleware, release_version=release.version)
    app.add_middleware(SecurityMiddleware, operations=operations)

    runtime = ApplicationRuntime(
        app=app,
        core=core,
        operations=operations,
        release=release,
    )
    app.state.lar_runtime = runtime
    return runtime
