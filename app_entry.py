"""Docker-friendly application entrypoint with modular UI enhancement layers."""
from __future__ import annotations

import os
from html import escape

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from live_auto_recorder import PROGRAM_VERSION, app


HTML_ROUTES = {
    "/",
    "/recording",
    "/config",
    "/channels",
    "/cookies",
    "/files",
    "/register",
}


class ConsoleAssetsMiddleware(BaseHTTPMiddleware):
    """Inject modular UI assets into the small set of dashboard pages.

    API, static-file, websocket, and download responses bypass the response-body
    buffering path entirely. The original templates and their functional element
    IDs remain unchanged while presentation and live-metrics behavior can evolve
    in isolated static assets.
    """

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

        version = escape(str(PROGRAM_VERSION), quote=True)
        head_assets = (
            '<meta name="color-scheme" content="light dark">'
            '<link rel="stylesheet" href="/static/css/console-v2.css?v='
            + version
            + '" data-lar-console-v2>'
            '<link rel="stylesheet" href="/static/css/shell-v3.css?v='
            + version
            + '" data-lar-shell-v3>'
            '<link rel="stylesheet" href="/static/css/sidebar-v3.css?v='
            + version
            + '" data-lar-sidebar-v3>'
            '<link rel="stylesheet" href="/static/css/system-metrics-v2.css?v='
            + version
            + '" data-lar-metrics-v2>'
            '<link rel="stylesheet" href="/static/css/dashboard-v4.css?v='
            + version
            + '" data-lar-dashboard-v4>'
            '<link rel="stylesheet" href="/static/css/recording-v3.css?v='
            + version
            + '" data-lar-recording-v3>'
            '<link rel="stylesheet" href="/static/css/metrics-compact-v1.css?v='
            + version
            + '" data-lar-metrics-compact-v1>'
            '<link rel="stylesheet" href="/static/css/carrot-ui-v1.css?v='
            + version
            + '" data-lar-carrot-ui-v1>'
            '<script src="/static/js/system-metrics-v2.js?v='
            + version
            + '" data-lar-metrics-v2></script>'
        )
        body_assets = (
            '<script src="/static/js/console-v2.js?v='
            + version
            + '" defer data-lar-console-v2></script>'
            '<script src="/static/js/sidebar-v3.js?v='
            + version
            + '" defer data-lar-sidebar-v3></script>'
            '<script src="/static/js/dashboard-v4.js?v='
            + version
            + '" defer data-lar-dashboard-v4></script>'
            '<script src="/static/js/metrics-compact-v1.js?v='
            + version
            + '" defer data-lar-metrics-compact-v1></script>'
            '<script src="/static/js/carrot-ui-v1.js?v='
            + version
            + '" defer data-lar-carrot-ui-v1></script>'
        )

        if "data-lar-console-v2" not in html:
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
