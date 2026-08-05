"""HTTP middleware for security policy and shared console assets."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from lar_app.web.assets import HTML_ROUTES, inject_console_assets


NO_STORE_ROUTES = frozenset({"/login", "/register", "/config", "/cookies", "/operations"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuditSink(Protocol):
    def audit(self, event: str, detail: str, status: str = "ok") -> Any: ...


class SecurityMiddleware(BaseHTTPMiddleware):
    """Add security headers, login throttling, and mutation audit events."""

    def __init__(
        self,
        app: Any,
        operations: AuditSink,
        *,
        window_seconds: int = 600,
        max_failures: int = 5,
    ) -> None:
        super().__init__(app)
        self.operations = operations
        self.window_seconds = window_seconds
        self.max_failures = max_failures
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def _recent_attempts(self, key: str, now: float) -> deque[float]:
        attempts = self.failures[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        return attempts

    @staticmethod
    def _apply_headers(request: Request, response: Response) -> None:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if request.url.path in NO_STORE_ROUTES:
            response.headers.setdefault("Cache-Control", "no-store")

    def _audit_response(self, request: Request, response: Response, key: str, now: float) -> None:
        if request.method == "POST" and request.url.path == "/login":
            attempts = self._recent_attempts(key, now)
            if response.status_code == 401:
                attempts.append(now)
                self.operations.audit("login_failed", f"client={key}", "error")
            elif response.status_code < 400:
                attempts.clear()
                self.operations.audit("login_succeeded", f"client={key}")
            return

        if request.method in MUTATING_METHODS and not request.url.path.startswith("/api/sys_metrics"):
            status = "ok" if response.status_code < 400 else "error"
            self.operations.audit(
                "http_mutation",
                f"{request.method} {request.url.path}; status={response.status_code}",
                status,
            )

    async def dispatch(self, request: Request, call_next):
        key = self._client_key(request)
        now = time.monotonic()
        attempts = self._recent_attempts(key, now)

        if request.method == "POST" and request.url.path == "/login" and len(attempts) >= self.max_failures:
            self.operations.audit("login_throttled", f"client={key}", "blocked")
            return JSONResponse(
                {"status": "error", "message": "로그인 시도가 너무 많습니다. 10분 후 다시 시도하세요."},
                status_code=429,
            )

        response = await call_next(request)
        self._apply_headers(request, response)
        self._audit_response(request, response, key, now)
        return response


class ConsoleAssetsMiddleware(BaseHTTPMiddleware):
    """Inject the versioned console asset manifest into HTML routes."""

    def __init__(self, app: Any, release_version: str) -> None:
        super().__init__(app)
        self.release_version = release_version

    async def dispatch(self, request: Request, call_next):
        if request.method != "GET" or request.url.path not in HTML_ROUTES:
            return await call_next(request)

        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return response

        chunks = [bytes(chunk) async for chunk in response.body_iterator]
        raw = b"".join(chunks)
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            return self._rebuild_response(response, raw)

        content = inject_console_assets(html, self.release_version)
        return self._rebuild_response(response, content)

    @staticmethod
    def _rebuild_response(response: Response, content: str | bytes) -> Response:
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=content,
            status_code=response.status_code,
            headers=headers,
        )
