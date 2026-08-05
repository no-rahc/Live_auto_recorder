"""Docker-friendly application entrypoint with the Console v2 UI layer."""
from __future__ import annotations

import os
from html import escape

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from live_auto_recorder import PROGRAM_VERSION, app


class ConsoleAssetsMiddleware(BaseHTTPMiddleware):
    """Inject the optional UI layer into every HTML response.

    The original templates, element IDs, forms, and page-specific JavaScript stay
    untouched. This keeps application behavior stable while allowing the visual
    layer to evolve independently.
    """

    async def dispatch(self, request: Request, call_next):
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
        )
        body_assets = (
            '<script src="/static/js/console-v2.js?v='
            + version
            + '" defer data-lar-console-v2></script>'
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
