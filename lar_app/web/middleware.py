"""HTTP middleware for local-mode policy and shared console assets."""
from __future__ import annotations

import html as html_module
import re
import time
from typing import Any, Protocol
from urllib.parse import urlencode

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from lar_app.web.assets import HTML_ROUTES, inject_console_assets
from module.data_manager import loadConfig, loadTelegram, saveConfig


NO_STORE_ROUTES = frozenset({"/config", "/cookies", "/operations"})
AUTH_ROUTES = frozenset({"/login", "/register", "/logout", "/updateAccount"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SECRET_FIELDS = (
    ("telegram_bot_token", "telegram"),
    ("telegram_chat_id", "telegram"),
    ("discord_webhook_url", "config"),
)
_INPUT_TAG_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)


class AuditSink(Protocol):
    def audit(self, event: str, detail: str, status: str = "ok") -> Any: ...


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "on", "yes"}


def _first(pairs: list[tuple[str, str]], name: str, default: str = "") -> str:
    for key, value in pairs:
        if key == name:
            return value
    return default


def _replace_pair(pairs: list[tuple[str, str]], name: str, value: str) -> None:
    pairs[:] = [(key, item) for key, item in pairs if key != name]
    pairs.append((name, value))


def _apply_secret_actions(
    pairs: list[tuple[str, str]],
    current_config: dict[str, Any],
    current_telegram: dict[str, Any],
) -> None:
    """Preserve stored secrets unless the settings UI explicitly replaces or clears them."""

    sources = {"config": current_config, "telegram": current_telegram}
    for field, source_name in _SECRET_FIELDS:
        stored = str(sources[source_name].get(field) or "")
        posted = _first(pairs, field)
        action = _first(pairs, f"{field}_action").strip().lower()

        if action == "clear":
            value = ""
        elif action == "replace":
            value = posted.strip()
        elif action == "keep" or not posted.strip():
            value = stored
        else:
            value = posted.strip()

        _replace_pair(pairs, field, value)


def _file_manager_risk(values: dict[str, Any]) -> bool:
    return bool(
        _truthy(values.get("fileManagerEnabled"))
        and (
            str(values.get("fileManagerMode") or "whitelist") == "blacklist"
            or not _truthy(values.get("fileManagerReadOnly"))
            or not _truthy(values.get("trashEnabled"))
        )
    )


def _validate_dangerous_config(
    pairs: list[tuple[str, str]],
    current_config: dict[str, Any],
    account: dict[str, Any] | None = None,
    bind_address: str = "127.0.0.1",
) -> str | None:
    """Require explicit confirmation for risky file-manager transitions."""

    del account, bind_address  # Legacy parameters retained for compatibility.
    current_risk = _file_manager_risk(current_config)
    next_values = {
        "fileManagerEnabled": _first(
            pairs,
            "fileManagerEnabled",
            str(current_config.get("fileManagerEnabled", False)).lower(),
        ),
        "fileManagerMode": _first(
            pairs,
            "fileManagerMode",
            str(current_config.get("fileManagerMode", "whitelist")),
        ),
        "fileManagerReadOnly": _first(
            pairs,
            "fileManagerReadOnly",
            str(current_config.get("fileManagerReadOnly", True)).lower(),
        ),
        "trashEnabled": _first(
            pairs,
            "trashEnabled",
            str(current_config.get("trashEnabled", True)).lower(),
        ),
    }
    next_risk = _file_manager_risk(next_values)
    risk_fields_changed = any(
        str(next_values[name]).lower() != str(current_config.get(name, default)).lower()
        for name, default in (
            ("fileManagerEnabled", False),
            ("fileManagerMode", "whitelist"),
            ("fileManagerReadOnly", True),
            ("trashEnabled", True),
        )
    )

    if next_risk and (not current_risk or risk_fields_changed):
        acknowledgement = _first(pairs, "danger_ack").strip()
        if acknowledgement != "위험 설정 적용":
            return "위험한 파일 관리자 설정을 적용하려면 확인 문구 ‘위험 설정 적용’을 입력하세요."

    return None


def _mask_secret_input(html: str, field_id: str) -> str:
    """Remove a secret value from one input tag before HTML reaches the browser."""

    id_re = re.compile(rf"\bid\s*=\s*(['\"]){re.escape(field_id)}\1", re.IGNORECASE)
    value_re = re.compile(r"\bvalue\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
    type_re = re.compile(r"\btype\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
    cleanup_re = re.compile(
        r"\s+(?:data-stored-secret|autocomplete|placeholder)\s*=\s*(['\"])(.*?)\1",
        re.IGNORECASE | re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        if not id_re.search(tag):
            return tag

        value_match = value_re.search(tag)
        stored = bool(value_match and html_module.unescape(value_match.group(2)).strip())
        if value_match:
            tag = value_re.sub('value=""', tag, count=1)
        else:
            tag = tag[:-1] + ' value="">'

        if type_re.search(tag):
            tag = type_re.sub('type="password"', tag, count=1)
        else:
            tag = tag[:-1] + ' type="password">'

        tag = cleanup_re.sub("", tag)
        suffix = (
            f' data-stored-secret="{str(stored).lower()}"'
            ' autocomplete="new-password"'
            ' placeholder="저장된 값은 표시되지 않습니다"'
        )
        return tag[:-1] + suffix + ">"

    return _INPUT_TAG_RE.sub(replace, html)


def mask_config_secrets(html: str) -> str:
    for field, _source in _SECRET_FIELDS:
        html = _mask_secret_input(html, field)
    return html


class SecurityMiddleware(BaseHTTPMiddleware):
    """Apply local-mode routing, config guards, security headers, and audit events."""

    def __init__(self, app: Any, operations: AuditSink) -> None:
        super().__init__(app)
        self.operations = operations

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

    def _audit_response(self, request: Request, response: Response) -> None:
        if request.method in MUTATING_METHODS and not request.url.path.startswith("/api/sys_metrics"):
            status = "ok" if response.status_code < 400 else "error"
            self.operations.audit(
                "http_mutation",
                f"{request.method} {request.url.path}; status={response.status_code}",
                status,
            )

    @staticmethod
    async def _prepare_config_request(request: Request) -> Response | None:
        try:
            submitted = await request.form()
            pairs = [(str(key), str(value)) for key, value in submitted.multi_items()]
        except Exception:
            return JSONResponse(
                {"status": "error", "message": "설정 요청을 읽을 수 없습니다."},
                status_code=400,
            )

        current_config = loadConfig() or {}
        current_telegram = loadTelegram() or {}
        _apply_secret_actions(pairs, current_config, current_telegram)

        # The legacy core still couples fileManagerEnabled to loginMode. Feed it
        # local mode explicitly, then restore the requested file-manager state
        # after the legacy handler completes.
        requested_file_manager = _first(
            pairs,
            "fileManagerEnabled",
            str(current_config.get("fileManagerEnabled", False)).lower(),
        )
        request.state.local_file_manager_enabled = requested_file_manager
        _replace_pair(pairs, "loginMode", "false")

        local_current = dict(current_config)
        local_current["loginMode"] = False
        error = _validate_dangerous_config(pairs, local_current)
        if error:
            return JSONResponse({"status": "error", "message": error}, status_code=400)

        body = urlencode(pairs, doseq=True).encode("utf-8")
        request._body = body  # Starlette's cached request replays this body to the downstream app.

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive
        headers = [
            (key, value)
            for key, value in request.scope.get("headers", [])
            if key.lower() not in {b"content-type", b"content-length"}
        ]
        headers.extend(
            [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body)).encode("ascii")),
            ]
        )
        request.scope["headers"] = headers
        return None

    @staticmethod
    def _normalize_local_config(request: Request) -> None:
        config = loadConfig() or {}
        config["loginMode"] = False
        requested = getattr(request.state, "local_file_manager_enabled", None)
        if requested is not None:
            config["fileManagerEnabled"] = _truthy(requested)
        saveConfig(config)
        request.app.state.config = config

    async def dispatch(self, request: Request, call_next):
        if request.url.path in AUTH_ROUTES:
            response = RedirectResponse(url="/", status_code=302 if request.method == "GET" else 303)
            self._apply_headers(request, response)
            return response

        if request.method == "POST" and request.url.path == "/config":
            blocked = await self._prepare_config_request(request)
            if blocked is not None:
                self._apply_headers(request, blocked)
                self._audit_response(request, blocked)
                return blocked

        response = await call_next(request)

        if request.method == "POST" and request.url.path == "/config" and response.status_code < 400:
            self._normalize_local_config(request)
            location = response.headers.get("location", "")
            if location.startswith("/register") or location.startswith("/login"):
                response.headers["location"] = "/"

        self._apply_headers(request, response)
        self._audit_response(request, response)
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
        if request.url.path == "/config":
            content = mask_config_secrets(content)
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
