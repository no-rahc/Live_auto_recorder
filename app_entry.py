"""Docker-friendly application entrypoint with consolidated UI assets."""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import live_auto_recorder as lar
from module.config_tools_v1 import install_config_tools
from module.operations_v2 import install_operations


ROOT_DIR = Path(__file__).resolve().parent
VERSION_FILE = ROOT_DIR / "VERSION"
RELEASE_VERSION = (
    VERSION_FILE.read_text(encoding="utf-8").strip()
    if VERSION_FILE.exists()
    else str(getattr(lar, "PROGRAM_VERSION", "v0.0.0"))
)
PROGRAM_NAME = str(getattr(lar, "PROGRAM_NAME", "Live Auto Recorder"))

# VERSION is the single runtime source used by templates, assets, logs and Docker.
lar.PROGRAM_VERSION = RELEASE_VERSION
lar.templates.env.globals.update(
    program_name=PROGRAM_NAME,
    program_version=RELEASE_VERSION,
)
app = lar.app
operations = install_operations(app, lar)
install_config_tools(app, lar)

# Extend the recorder lifespan without changing the legacy core module.
_core_lifespan = app.router.lifespan_context


@asynccontextmanager
async def application_lifespan(application):
    async with _core_lifespan(application):
        await operations.start()
        try:
            yield
        finally:
            await operations.stop()


app.router.lifespan_context = application_lifespan

HTML_ROUTES = {
    "/",
    "/recording",
    "/config",
    "/channels",
    "/cookies",
    "/files",
    "/operations",
    "/register",
}

_VERSION_IN_TITLE = re.compile(
    r"(<title>[^<]*?)\s+v\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?\s*(</title>)",
    re.IGNORECASE,
)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Add conservative security headers, login throttling, and audit events."""

    failures = defaultdict(deque)
    window_seconds = 600
    max_failures = 5

    @staticmethod
    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        key = self.client_key(request)
        now = time.time()
        attempts = self.failures[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()

        if request.method == "POST" and request.url.path == "/login" and len(attempts) >= self.max_failures:
            operations.audit("login_throttled", f"client={key}", "blocked")
            return JSONResponse(
                {"status": "error", "message": "로그인 시도가 너무 많습니다. 10분 후 다시 시도하세요."},
                status_code=429,
            )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path in {"/login", "/register", "/config", "/cookies", "/operations"}:
            response.headers.setdefault("Cache-Control", "no-store")

        if request.method == "POST" and request.url.path == "/login":
            if response.status_code == 401:
                attempts.append(now)
                operations.audit("login_failed", f"client={key}", "error")
            elif response.status_code < 400:
                attempts.clear()
                operations.audit("login_succeeded", f"client={key}")
        elif request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/api/sys_metrics"):
            operations.audit("http_mutation", f"{request.method} {request.url.path}; status={response.status_code}", "ok" if response.status_code < 400 else "error")
        return response


class ConsoleAssetsMiddleware(BaseHTTPMiddleware):
    """Inject the consolidated light UI only into dashboard HTML routes."""

    async def dispatch(self, request: Request, call_next):
        if request.method != "GET" or request.url.path not in HTML_ROUTES:
            return await call_next(request)

        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return response

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(bytes(chunk))
        raw = b"".join(chunks)

        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                content=raw,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=content_type,
            )

        html = _VERSION_IN_TITLE.sub(r"\1\2", html)

        version = escape(RELEASE_VERSION, quote=True)
        head_assets = (
            '<meta name="color-scheme" content="light">'
            '<link rel="stylesheet" href="/static/css/app-v3.css?v=' + version + '" data-lar-ui-v3>'
            '<link rel="stylesheet" href="/static/css/dashboard-glance-v1.css?v=' + version + '" data-lar-dashboard-glance-v1>'
            '<link rel="stylesheet" href="/static/css/dashboard-channel-modal-v1.css?v=' + version + '" data-lar-dashboard-channel-modal-v1>'
            '<link rel="stylesheet" href="/static/css/recording-density-v1.css?v=' + version + '" data-lar-recording-density-v1>'
            '<link rel="stylesheet" href="/static/css/operations-v2.css?v=' + version + '" data-lar-operations-v2>'
            '<link rel="stylesheet" href="/static/css/ui-polish-v1.css?v=' + version + '" data-lar-ui-polish-v1>'
            '<link rel="stylesheet" href="/static/css/config-workspace-v1.css?v=' + version + '" data-lar-config-workspace-v1>'
            '<link rel="stylesheet" href="/static/css/project-ui-audit-v1.css?v=' + version + '" data-lar-project-ui-audit-v1>'
            '<link rel="stylesheet" href="/static/css/project-ui-audit-fixes-v1.css?v=' + version + '" data-lar-project-ui-audit-fixes-v1>'
            '<link rel="stylesheet" href="/static/css/operations-controls-v1.css?v=' + version + '" data-lar-operations-controls-v1>'
            '<style data-lar-ui-v3-critical>@media (min-width:1100px){body.lar-sidebar-v3 .menu-icon{display:none!important}}</style>'
            '<script src="/static/js/system-metrics-v2.js?v=' + version + '" data-lar-metrics-v2></script>'
        )
        body_assets = (
            '<script src="/static/js/sidebar-v3.js?v=' + version + '" defer data-lar-sidebar-v3></script>'
            '<script src="/static/js/dashboard-v4.js?v=' + version + '" defer data-lar-dashboard-v4></script>'
            '<script src="/static/js/dashboard-channel-modal-v1.js?v=' + version + '" defer data-lar-dashboard-channel-modal-v1></script>'
            '<script src="/static/js/app-ui-v3.js?v=' + version + '" defer data-lar-ui-v3></script>'
            '<script src="/static/js/recording-live-meta-v1.js?v=' + version + '" defer data-lar-recording-live-meta-v1></script>'
            '<script src="/static/js/config-workspace-v1.js?v=' + version + '" defer data-lar-config-workspace-v1></script>'
            '<script src="/static/js/project-ui-audit-v1.js?v=' + version + '" defer data-lar-project-ui-audit-v1></script>'
            '<script src="/static/js/operations-v2.js?v=' + version + '" defer data-lar-operations-v2></script>'
            '<script src="/static/js/operations-controls-v1.js?v=' + version + '" defer data-lar-operations-controls-v1></script>'
        )

        if "data-lar-ui-v3" not in html:
            if "</head>" in html:
                html = html.replace("</head>", head_assets + "</head>", 1)
            else:
                html = head_assets + html

            if "</body>" in html:
                html = html.replace("</body>", body_assets + "</body>", 1)
            else:
                html += body_assets

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=html,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )


app.add_middleware(ConsoleAssetsMiddleware)
app.add_middleware(SecurityMiddleware)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level, access_log=True)


if __name__ == "__main__":
    main()
