"""Assemble the legacy recorder core into the production ASGI application."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from lar_app.template_compat import install_template_response_compat

# Starlette 1.x removed TemplateResponse(name, context). The legacy core still
# contains that calling convention, so install the adapter before importing it.
install_template_response_compat()

import live_auto_recorder as recorder_core

from lar_app.release import ReleaseInfo, apply_release_info, load_release_info
from lar_app.routers.channels import install_channel_routes
from lar_app.routers.cookies import install_cookie_routes
from lar_app.routers.config import install_config_routes
from lar_app.routers.files import install_file_routes
from lar_app.routers.recording import install_recording_routes
from lar_app.routers.v2 import install_v2_routes
from lar_app.web.v2_security import V2OriginMiddleware
from module.v2_runtime import enabled as v2_enabled, get_repository
from lar_app.security import configure_session_middleware, enforce_local_mode
from lar_app.web.middleware import ConsoleAssetsMiddleware, SecurityMiddleware
from module.config_tools_v1 import install_config_tools
from module.operations_platform_v3 import install_platform_features
from module.operations_v2 import install_operations
from module.readiness import readiness_snapshot
from module.recording_trace import install_live_recorder_stderr_capture


@dataclass(frozen=True, slots=True)
class ApplicationRuntime:
    """Objects produced while assembling the production application."""

    app: Any
    core: Any
    operations: Any
    platform: Any
    release: ReleaseInfo


def _install_operations_lifespan(app: Any, operations: Any, platform: Any, core: Any) -> None:
    core_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def application_lifespan(application):
        worker = None
        if v2_enabled():
            from module.v2_storage import preflight_database_location
            from module.v2_worker import V2Worker
            repository = get_repository()
            database = preflight_database_location(repository.db_path.parent)
            if not database['ok']:
                raise RuntimeError('V2 database preflight failed; use local persistent storage with sufficient free space')
            worker = V2Worker(repository)
            # Fence the whole app before legacy startup can spawn recorders.
            worker.acquire_instance_lock()
            from module.v2_runtime import begin_capture_guard
            try:
                begin_capture_guard(repository)
            except BaseException:
                worker.release_instance_lock()
                raise
            application.state.v2_worker = worker
        try:
            async with core_lifespan(application):
                enforce_local_mode(application, core)
                await operations.start()
                try:
                    await platform.start()
                    try:
                        if worker is not None:
                            from module.v2_runtime import sync_catalog
                            await asyncio.to_thread(sync_catalog)
                            await worker.start()
                            from module.v2_runtime import capture_storage_report
                            application.state.v2_storage = await asyncio.to_thread(capture_storage_report)
                            controller = getattr(application.state, 'v2_channels', None)
                            if controller is not None:
                                await controller.start_watching()
                        yield
                    finally:
                        await platform.stop()
                finally:
                    await operations.stop()
        finally:
            # Keep accepting durable verification intents until engine shutdown
            # has finished. Unclaimed intents remain in SQLite for next boot.
            if worker is not None:
                from module.v2_runtime import finish_capture_guard
                finish_capture_guard(shutdown_confirmed=getattr(application.state, 'v2_capture_shutdown_clean', False))
                await worker.stop()

    app.router.lifespan_context = application_lifespan


def _install_health_route(app: Any, release: ReleaseInfo) -> None:
    if any(getattr(route, "path", None) == "/healthz" for route in app.routes):
        return

    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": release.version}

    app.add_api_route("/healthz", healthz, methods=["GET"], include_in_schema=False)


def _install_readiness_route(app: Any, release: ReleaseInfo, operations: Any, platform: Any) -> None:
    if any(getattr(route, "path", None) == "/readyz" for route in app.routes):
        return

    async def readyz():
        snapshot = readiness_snapshot(operations, platform)
        snapshot["version"] = release.version
        if v2_enabled():
            worker = getattr(app.state, "v2_worker", None)
            snapshot["v2"] = worker.snapshot() if worker else {"running": False}
            if not snapshot["v2"].get("ready", False) or not getattr(app.state, "v2_storage", {}).get("ok", False):
                snapshot["ready"] = False
        return JSONResponse(status_code=200 if snapshot["ready"] else 503, content=snapshot)

    app.add_api_route("/readyz", readyz, methods=["GET"], include_in_schema=False)


def _install_local_http_exception_handler(app: Any) -> None:
    """Replace the legacy 401-to-/login redirect with normal HTTP errors."""

    async def local_http_exception_handler(request: Request, exc: HTTPException):
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    app.add_exception_handler(HTTPException, local_http_exception_handler)


def build_application(
    core: Any = recorder_core,
    *,
    root_dir: Path | None = None,
) -> ApplicationRuntime:
    """Build the local-only application while preserving the legacy public API."""

    app = core.app
    existing = getattr(app.state, "lar_runtime", None)
    if isinstance(existing, ApplicationRuntime):
        return existing

    release = load_release_info(core, root_dir=root_dir)
    apply_release_info(core, release)
    install_channel_routes(app, core)
    install_cookie_routes(app, core)
    install_config_routes(app, core)
    install_file_routes(app, core)
    install_recording_routes(app, core)
    install_v2_routes(app, core, root_dir=root_dir)
    configure_session_middleware(app)
    install_live_recorder_stderr_capture()
    _install_local_http_exception_handler(app)
    _install_health_route(app, release)

    operations = install_operations(app, core)
    platform = install_platform_features(app, core, operations)
    install_config_tools(app, core)
    _install_readiness_route(app, release, operations, platform)
    _install_operations_lifespan(app, operations, platform, core)

    # Preserve the original middleware order: security wraps HTML injection.
    app.add_middleware(ConsoleAssetsMiddleware, release_version=release.version)
    app.add_middleware(SecurityMiddleware, operations=operations)
    app.add_middleware(V2OriginMiddleware)

    runtime = ApplicationRuntime(
        app=app,
        core=core,
        operations=operations,
        platform=platform,
        release=release,
    )
    app.state.lar_runtime = runtime
    return runtime
