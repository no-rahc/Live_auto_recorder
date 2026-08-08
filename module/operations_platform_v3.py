"""Recording catalog, durable notification delivery, archive jobs, and scoped API tokens."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from module.recording_catalog import (
    _LOCK as DB_LOCK,
    _connect,
    get_recording,
    init_catalog,
    list_recordings,
    migrate_jsonl,
    update_recording,
)
from module.recording_verify import verify_recording

_RUNTIME: "PlatformRuntime | None" = None

DEFAULT_SETTINGS: dict[str, Any] = {
    "notifications": {
        "enabled": True,
        "max_attempts": 5,
        "quiet_start": "",
        "quiet_end": "",
        "events": {
            "recording.started": True,
            "recording.completed": True,
            "recording.failed": True,
            "recording.validated": True,
            "recording.reconnecting": True,
            "postprocess.failed": True,
            "storage.warning": True,
            "storage.cleaned": True,
            "archive.completed": True,
            "archive.failed": True,
        },
    },
    "archive": {
        "enabled": False,
        "remote": "",
        "auto_after_validation": False,
        "delete_after": False,
        "verify_size": True,
        "max_attempts": 5,
    },
    "webhooks": [],
}


def _deep_merge(default: dict[str, Any], value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {}
    for key, item in default.items():
        incoming = source.get(key)
        result[key] = _deep_merge(item, incoming) if isinstance(item, dict) else (incoming if incoming is not None else item)
    for key, item in source.items():
        if key not in result:
            result[key] = item
    return result


def _safe_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _error_text(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    return str(detail if detail is not None else exc)[:1200]


def emit_runtime_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    runtime = _RUNTIME
    if runtime is not None:
        runtime.enqueue_notification(event_type, payload or {})
        if event_type == "recording.validated":
            status = str((payload or {}).get("status") or "")
            recording_id = int((payload or {}).get("recording_id") or 0)
            archive = runtime.settings.get("archive", {})
            if (
                recording_id
                and status in {"ok", "repaired"}
                and archive.get("enabled")
                and archive.get("auto_after_validation")
            ):
                with suppress(Exception):
                    runtime.enqueue_archive(recording_id)


class PlatformRuntime:
    def __init__(self, app: Any, lar: Any, operations: Any) -> None:
        self.app = app
        self.lar = lar
        self.operations = operations
        self.data_dir = Path(getattr(lar, "CONFIG_PATH", Path.cwd() / "json" / "config.json")).parent
        self.settings_path = self.data_dir / "platform_v3.json"
        self.settings = _deep_merge(DEFAULT_SETTINGS, _safe_json(self.settings_path, {}))
        self.tasks: list[asyncio.Task[Any]] = []
        self._started = False

    def save_settings(self) -> None:
        _write_json(self.settings_path, self.settings)

    async def start(self) -> None:
        global _RUNTIME
        if self._started:
            return
        self._started = True
        init_catalog()
        migrate_jsonl(self.data_dir / "recording_history.jsonl")
        self._recover_archive_jobs()
        _RUNTIME = self
        self.tasks = [
            asyncio.create_task(self._notification_loop(), name="platform-notifications"),
            asyncio.create_task(self._archive_loop(), name="platform-archive"),
        ]

    async def stop(self) -> None:
        global _RUNTIME
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.tasks.clear()
        self._started = False
        if _RUNTIME is self:
            _RUNTIME = None

    def enqueue_notification(self, event_type: str, payload: dict[str, Any]) -> None:
        cfg = self.settings.get("notifications", {})
        if not cfg.get("enabled", True) or not cfg.get("events", {}).get(event_type, False):
            return
        init_catalog()
        now = time.time()
        with DB_LOCK, _connect() as conn:
            conn.execute(
                "INSERT INTO notification_queue(event_type,payload_json,status,attempts,next_attempt,created_epoch,delivery_json) VALUES(?,?,?,?,?,?,?)",
                (event_type, json.dumps(payload, ensure_ascii=False), "queued", 0, now, now, "{}"),
            )

    def _delivery_key(self, kind: str, value: str = "") -> str:
        if not value:
            return kind
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"{kind}:{digest}"

    def _quiet_now(self) -> bool:
        cfg = self.settings.get("notifications", {})
        start = str(cfg.get("quiet_start") or "").strip()
        end = str(cfg.get("quiet_end") or "").strip()
        if not start or not end:
            return False
        now = time.strftime("%H:%M")
        return (start <= now < end) if start < end else (now >= start or now < end)

    def _message(self, event_type: str, payload: dict[str, Any]) -> str:
        names = {
            "recording.started": "녹화를 시작했습니다.",
            "recording.completed": "녹화를 완료했습니다.",
            "recording.failed": "녹화에 실패했습니다.",
            "recording.validated": "녹화 파일 검증을 완료했습니다.",
            "recording.reconnecting": "녹화 자동 재연결을 시도합니다.",
            "postprocess.failed": "후처리에 실패했습니다.",
            "storage.warning": "저장소 여유 공간이 부족합니다.",
            "storage.cleaned": "저장소 자동 정리를 완료했습니다.",
            "archive.completed": "외부 보관을 완료했습니다.",
            "archive.failed": "외부 보관에 실패했습니다.",
        }
        channel = str(payload.get("channel_name") or payload.get("channel_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        detail = str(payload.get("detail") or payload.get("error") or "").strip()
        parts = [names.get(event_type, event_type)]
        if channel:
            parts.append(f"채널: {channel}")
        if status:
            parts.append(f"상태: {status}")
        if detail:
            parts.append(detail[:400])
        return "\n".join(parts)

    def _deliver_destinations(
        self,
        event_type: str,
        payload: dict[str, Any],
        delivery: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        message = self._message(event_type, payload)
        state = dict(delivery or {})
        errors: list[str] = []
        config = getattr(self.app.state, "config", {}) or {}

        def deliver(key: str, sender: Any) -> None:
            previous = state.get(key) if isinstance(state.get(key), dict) else {}
            if previous.get("status") == "sent":
                return
            try:
                sender()
                state[key] = {"status": "sent", "sent_epoch": time.time(), "error": ""}
            except Exception as exc:
                text = _error_text(exc)[:800]
                state[key] = {"status": "failed", "sent_epoch": 0, "error": text}
                errors.append(f"{key}: {text}")

        if config.get("telegram_enabled"):
            deliver("telegram", lambda: self.lar.sendTelegram(f"<b>Live Auto Recorder</b>\n{message}"))

        discord_url = str(config.get("discord_webhook_url") or "").strip()
        if config.get("discord_enabled") and discord_url.startswith("https://"):
            def send_discord() -> None:
                response = requests.post(discord_url, json={"content": message}, timeout=10)
                response.raise_for_status()
            deliver("discord", send_discord)

        for item in self.settings.get("webhooks", []):
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            events = item.get("events") or ["*"]
            if "*" not in events and event_type not in events:
                continue
            url = str(item.get("url") or "").strip()
            if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
                continue
            key = self._delivery_key("webhook", url)

            def send_webhook(item: dict[str, Any] = item, url: str = url) -> None:
                body = json.dumps(
                    {"event": event_type, "timestamp": time.time(), "data": payload},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                headers = {"Content-Type": "application/json", "User-Agent": "Live-Auto-Recorder/webhook"}
                secret = str(item.get("secret") or "")
                if secret:
                    headers["X-LAR-Signature-256"] = "sha256=" + hmac.new(
                        secret.encode("utf-8"), body, hashlib.sha256
                    ).hexdigest()
                response = requests.post(url, data=body, headers=headers, timeout=10)
                response.raise_for_status()

            deliver(key, send_webhook)

        return state, errors

    async def _process_notification_once(self) -> bool:
        if self._quiet_now():
            return False
        init_catalog()
        now = time.time()
        with DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM notification_queue WHERE status IN ('queued','retry') AND next_attempt<=? ORDER BY id LIMIT 1",
                (now,),
            ).fetchone()
        if not row:
            return False

        item = dict(row)
        try:
            payload = json.loads(item.get("payload_json") or "{}")
        except Exception:
            payload = {}
        try:
            delivery = json.loads(item.get("delivery_json") or "{}")
        except Exception:
            delivery = {}

        delivery, errors = await asyncio.to_thread(
            self._deliver_destinations, item["event_type"], payload, delivery
        )
        if not errors:
            with DB_LOCK, _connect() as conn:
                conn.execute(
                    "UPDATE notification_queue SET status='sent',sent_epoch=?,last_error='',delivery_json=? WHERE id=?",
                    (time.time(), json.dumps(delivery, ensure_ascii=False), item["id"]),
                )
            return True

        attempts = int(item.get("attempts") or 0) + 1
        maximum = max(1, min(int(self.settings["notifications"].get("max_attempts", 5)), 20))
        status = "failed" if attempts >= maximum else "retry"
        delay = min(3600, 15 * (2 ** min(attempts - 1, 7)))
        with DB_LOCK, _connect() as conn:
            conn.execute(
                "UPDATE notification_queue SET status=?,attempts=?,next_attempt=?,last_error=?,delivery_json=? WHERE id=?",
                (
                    status,
                    attempts,
                    time.time() + delay,
                    "; ".join(errors)[:800],
                    json.dumps(delivery, ensure_ascii=False),
                    item["id"],
                ),
            )
        return True

    async def _notification_loop(self) -> None:
        while True:
            try:
                processed = await self._process_notification_once()
                await asyncio.sleep(0.1 if processed else (30 if self._quiet_now() else 2))
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)

    def _recover_archive_jobs(self) -> int:
        init_catalog()
        now = time.time()
        with DB_LOCK, _connect() as conn:
            rows = conn.execute("SELECT id,recording_id FROM archive_jobs WHERE status='uploading'").fetchall()
            conn.execute(
                "UPDATE archive_jobs SET status='retry',next_attempt=?,last_error=CASE WHEN last_error='' THEN 'interrupted by restart' ELSE last_error END,updated_epoch=? WHERE status='uploading'",
                (now, now),
            )
        for row in rows:
            with suppress(Exception):
                update_recording(int(row["recording_id"]), archive_status="queued")
        return len(rows)

    def enqueue_archive(self, recording_id: int) -> int:
        cfg = self.settings.get("archive", {})
        if not cfg.get("enabled"):
            raise HTTPException(status_code=409, detail="외부 보관이 비활성화되어 있습니다.")
        recording = get_recording(recording_id)
        if not recording:
            raise HTTPException(status_code=404, detail="녹화 기록을 찾을 수 없습니다.")
        init_catalog()
        now = time.time()
        with DB_LOCK, _connect() as conn:
            existing = conn.execute(
                "SELECT id FROM archive_jobs WHERE recording_id=? AND status IN ('queued','retry','uploading') ORDER BY id DESC LIMIT 1",
                (int(recording_id),),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = conn.execute(
                "INSERT INTO archive_jobs(recording_id,status,attempts,next_attempt,target,last_error,created_epoch,updated_epoch) VALUES(?,?,?,?,?,?,?,?)",
                (int(recording_id), "queued", 0, now, "", "", now, now),
            )
            job_id = int(cursor.lastrowid)
        update_recording(recording_id, archive_status="queued")
        return job_id

    def _archive_once(self, recording_id: int) -> dict[str, Any]:
        cfg = self.settings.get("archive", {})
        if not cfg.get("enabled"):
            raise HTTPException(status_code=409, detail="외부 보관이 비활성화되어 있습니다.")
        remote = str(cfg.get("remote") or "").strip().rstrip("/")
        if not remote or ":" not in remote:
            raise HTTPException(status_code=400, detail="rclone remote 경로를 설정하세요. 예: gdrive:LiveAutoRecorder")
        recording = get_recording(recording_id)
        if not recording:
            raise HTTPException(status_code=404, detail="녹화 기록을 찾을 수 없습니다.")
        path = Path(str(recording.get("file_path") or ""))
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="녹화 파일을 찾을 수 없습니다.")

        target = f"{remote}/{path.name}"
        update_recording(recording_id, archive_status="uploading", archive_target=target)
        proc = subprocess.run(
            ["rclone", "copyto", str(path), target, "--retries", "3", "--low-level-retries", "5"],
            capture_output=True,
            text=True,
            timeout=86400,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "rclone 업로드 실패")[-1200:])
        if cfg.get("verify_size", True):
            size_proc = subprocess.run(
                ["rclone", "size", target, "--json"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if size_proc.returncode != 0:
                raise RuntimeError((size_proc.stderr or "원격 크기 확인 실패")[-800:])
            remote_size = int(json.loads(size_proc.stdout or "{}").get("bytes") or 0)
            local_size = path.stat().st_size
            if remote_size != local_size:
                raise RuntimeError(f"크기 불일치: local={local_size}, remote={remote_size}")

        update_recording(recording_id, archive_status="completed", archive_target=target, error="")
        self.enqueue_notification(
            "archive.completed",
            {"recording_id": recording_id, "channel_name": recording.get("channel_name"), "detail": target},
        )
        if cfg.get("delete_after"):
            path.unlink()
        return {"status": "completed", "target": target}

    async def _process_archive_once(self) -> bool:
        init_catalog()
        now = time.time()
        with DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM archive_jobs WHERE status IN ('queued','retry') AND next_attempt<=? ORDER BY id LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return False
            item = dict(row)
            conn.execute(
                "UPDATE archive_jobs SET status='uploading',updated_epoch=? WHERE id=?",
                (now, item["id"]),
            )

        try:
            result = await asyncio.to_thread(self._archive_once, int(item["recording_id"]))
            with DB_LOCK, _connect() as conn:
                conn.execute(
                    "UPDATE archive_jobs SET status='completed',target=?,last_error='',updated_epoch=? WHERE id=?",
                    (str(result.get("target") or ""), time.time(), item["id"]),
                )
            return True
        except Exception as exc:
            attempts = int(item.get("attempts") or 0) + 1
            maximum = max(1, min(int(self.settings.get("archive", {}).get("max_attempts", 5)), 20))
            status = "failed" if attempts >= maximum else "retry"
            delay = min(3600, 30 * (2 ** min(attempts - 1, 7)))
            text = _error_text(exc)
            with DB_LOCK, _connect() as conn:
                conn.execute(
                    "UPDATE archive_jobs SET status=?,attempts=?,next_attempt=?,last_error=?,updated_epoch=? WHERE id=?",
                    (status, attempts, time.time() + delay, text, time.time(), item["id"]),
                )
            update_recording(int(item["recording_id"]), archive_status=status, error=text[:1000])
            if status == "failed":
                recording = get_recording(int(item["recording_id"])) or {}
                self.enqueue_notification(
                    "archive.failed",
                    {
                        "recording_id": int(item["recording_id"]),
                        "channel_name": recording.get("channel_name"),
                        "error": text,
                    },
                )
            return True

    async def _archive_loop(self) -> None:
        while True:
            try:
                processed = await self._process_archive_once()
                await asyncio.sleep(0.1 if processed else 2)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)

    def create_token(self, name: str, scopes: list[str], expires_days: int = 0) -> dict[str, Any]:
        allowed = {"read", "control", "admin"}
        normalized = sorted({scope for scope in scopes if scope in allowed}) or ["read"]
        raw = "lar_" + secrets.token_urlsafe(32)
        now = time.time()
        expires = now + max(1, min(expires_days, 3650)) * 86400 if expires_days else 0
        with DB_LOCK, _connect() as conn:
            cursor = conn.execute(
                "INSERT INTO api_tokens(name,token_hash,token_prefix,scopes,created_epoch,expires_epoch) VALUES(?,?,?,?,?,?)",
                (name[:80] or "API token", _token_hash(raw), raw[:12], ",".join(normalized), now, expires),
            )
        return {"id": cursor.lastrowid, "name": name[:80] or "API token", "token": raw, "prefix": raw[:12], "scopes": normalized, "expires_epoch": expires}

    def verify_token(self, raw: str, required: str = "read") -> dict[str, Any] | None:
        if not raw:
            return None
        now = time.time()
        with DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT * FROM api_tokens WHERE token_hash=? AND revoked=0", (_token_hash(raw),)).fetchone()
            if not row:
                return None
            item = dict(row)
            if item["expires_epoch"] and float(item["expires_epoch"]) <= now:
                return None
            scopes = set(str(item["scopes"] or "").split(","))
            if required == "admin" and "admin" not in scopes:
                return None
            if required == "control" and not ({"control", "admin"} & scopes):
                return None
            if required == "read" and not ({"read", "control", "admin"} & scopes):
                return None
            conn.execute("UPDATE api_tokens SET last_used_epoch=? WHERE id=?", (now, item["id"]))
        item["scopes"] = sorted(scopes)
        return item


def install_platform_features(app: Any, lar: Any, operations: Any) -> PlatformRuntime:
    runtime = PlatformRuntime(app, lar, operations)
    router = APIRouter()

    def bearer(authorization: str | None) -> str:
        text = str(authorization or "")
        return text[7:].strip() if text.lower().startswith("bearer ") else ""

    async def automation_read(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        token = runtime.verify_token(bearer(authorization), "read")
        if not token:
            raise HTTPException(status_code=401, detail="Valid read API token required")
        return token

    async def automation_control(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        token = runtime.verify_token(bearer(authorization), "control")
        if not token:
            raise HTTPException(status_code=401, detail="Valid control API token required")
        return token

    @router.get("/api/v3/recordings")
    async def recordings(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), channel_id: str = "", status: str = "", q: str = ""):
        return list_recordings(limit=limit, offset=offset, channel_id=channel_id, status=status, query=q)

    @router.get("/api/v3/recordings/{recording_id}")
    async def recording(recording_id: int):
        item = get_recording(recording_id)
        if not item:
            raise HTTPException(status_code=404, detail="녹화 기록을 찾을 수 없습니다.")
        return item

    @router.post("/api/v3/recordings/{recording_id}/verify")
    async def verify(recording_id: int, payload: dict[str, Any] = Body(default={})):
        return await asyncio.to_thread(verify_recording, recording_id, attempt_repair=bool(payload.get("repair", True)))

    @router.post("/api/v3/recordings/{recording_id}/archive")
    async def archive(recording_id: int):
        job_id = runtime.enqueue_archive(recording_id)
        return {"status": "queued", "job_id": job_id}

    @router.get("/api/v3/archive-jobs")
    async def archive_jobs(limit: int = Query(100, ge=1, le=500)):
        with DB_LOCK, _connect() as conn:
            rows = conn.execute("SELECT * FROM archive_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.get("/api/v3/platform/settings")
    async def settings():
        safe = json.loads(json.dumps(runtime.settings))
        for item in safe.get("webhooks", []):
            if item.get("secret"):
                item["secret"] = "••••••••"
        return safe

    @router.put("/api/v3/platform/settings")
    async def put_settings(payload: dict[str, Any] = Body(...)):
        current_webhooks = runtime.settings.get("webhooks", [])
        candidate = _deep_merge(DEFAULT_SETTINGS, {**runtime.settings, **payload})
        for index, item in enumerate(candidate.get("webhooks", [])):
            if item.get("secret") == "••••••••" and index < len(current_webhooks):
                item["secret"] = current_webhooks[index].get("secret", "")
        runtime.settings = candidate
        runtime.save_settings()
        return await settings()

    @router.get("/api/v3/notifications")
    async def notifications(limit: int = Query(100, ge=1, le=500)):
        with DB_LOCK, _connect() as conn:
            rows = conn.execute("SELECT * FROM notification_queue ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["delivery"] = json.loads(item.get("delivery_json") or "{}")
            except Exception:
                item["delivery"] = {}
            items.append(item)
        return {"items": items}

    @router.post("/api/v3/notifications/{notification_id}/retry")
    async def retry_notification(notification_id: int):
        with DB_LOCK, _connect() as conn:
            conn.execute(
                "UPDATE notification_queue SET status='retry',attempts=0,next_attempt=?,last_error='' WHERE id=?",
                (time.time(), notification_id),
            )
        return {"status": "queued"}

    @router.get("/api/v3/tokens")
    async def tokens():
        with DB_LOCK, _connect() as conn:
            rows = conn.execute("SELECT id,name,token_prefix,scopes,created_epoch,expires_epoch,last_used_epoch,revoked FROM api_tokens ORDER BY id DESC").fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.post("/api/v3/tokens")
    async def create_token(payload: dict[str, Any] = Body(...)):
        return runtime.create_token(str(payload.get("name") or "API token"), list(payload.get("scopes") or ["read"]), int(payload.get("expires_days") or 0))

    @router.delete("/api/v3/tokens/{token_id}")
    async def revoke_token(token_id: int):
        with DB_LOCK, _connect() as conn:
            conn.execute("UPDATE api_tokens SET revoked=1 WHERE id=?", (token_id,))
        return {"status": "revoked"}

    @router.get("/api/v3/automation/status")
    async def api_status(token: Any = Depends(automation_read)):
        return operations.summary()

    @router.get("/api/v3/automation/recordings")
    async def api_recordings(limit: int = Query(50, ge=1, le=200), token: Any = Depends(automation_read)):
        return list_recordings(limit=limit)

    @router.post("/api/v3/automation/channels/{channel_id}/start")
    async def api_start(channel_id: str, token: Any = Depends(automation_control)):
        await app.state.fsm.userStart(channel_id, is_user_request=True)
        return {"status": "accepted", "channel_id": channel_id}

    @router.post("/api/v3/automation/channels/{channel_id}/stop")
    async def api_stop(channel_id: str, token: Any = Depends(automation_control)):
        await app.state.fsm.userStop(channel_id)
        return {"status": "accepted", "channel_id": channel_id}

    app.include_router(router)
    app.state.platform_v3 = runtime
    return runtime
