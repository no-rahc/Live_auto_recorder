"""Docker-friendly application entrypoint with consolidated UI assets."""
from __future__ import annotations

import os
import re
from html import escape
from pathlib import Path

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import live_auto_recorder as lar


ROOT_DIR = Path(__file__).resolve().parent
VERSION_FILE = ROOT_DIR / "VERSION"
RELEASE_VERSION = (
    VERSION_FILE.read_text(encoding="utf-8").strip()
    if VERSION_FILE.exists()
    else str(getattr(lar, "PROGRAM_VERSION", "v0.0.0"))
)
PROGRAM_NAME = str(getattr(lar, "PROGRAM_NAME", "Live Auto Recorder"))

# Keep template cache keys and UI version labels consistent with the release file.
lar.PROGRAM_VERSION = RELEASE_VERSION
lar.templates.env.globals.update(
    program_name=PROGRAM_NAME,
    program_version=RELEASE_VERSION,
)
app = lar.app

HTML_ROUTES = {
    "/",
    "/recording",
    "/config",
    "/channels",
    "/cookies",
    "/files",
    "/register",
}

_VERSION_IN_TITLE = re.compile(
    r"(<title>[^<]*?)\s+v\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?\s*(</title>)",
    re.IGNORECASE,
)


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

        # Browser tabs show the product/page name only; release versions stay in
        # deployment metadata and Docker tags instead of the document title.
        html = _VERSION_IN_TITLE.sub(r"\1\2", html)

        version = escape(RELEASE_VERSION, quote=True)
        head_assets = (
            '<meta name="color-scheme" content="light">'
            '<link rel="stylesheet" href="/static/css/app-v3.css?v='
            + version
            + '" data-lar-ui-v3>'
            '<style data-lar-ui-v3-critical>'
            '@media (min-width:1100px){body.lar-sidebar-v3 .menu-icon{display:none!important}}'
            '</style>'
            '<script src="/static/js/system-metrics-v2.js?v='
            + version
            + '" data-lar-metrics-v2></script>'
        )
        body_assets = (
            '<script src="/static/js/sidebar-v3.js?v='
            + version
            + '" defer data-lar-sidebar-v3></script>'
            '<script src="/static/js/dashboard-v4.js?v='
            + version
            + '" defer data-lar-dashboard-v4></script>'
            '<script src="/static/js/app-ui-v3.js?v='
            + version
            + '" defer data-lar-ui-v3></script>'
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


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level, access_log=True)


if __name__ == "__main__":
    main()
