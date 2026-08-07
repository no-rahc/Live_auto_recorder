"""Recording catalog, notification queue, rclone archive, and scoped API tokens."""
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
            "postprocess.failed": True,
            "storage.warning": True,
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


def emit_runtime_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    runtime = _RUNTIME
    if runtime is not None:
        runtime.enqueue_notification(event_type, payload or {})
        if event_type == "recording.validated":
            status = str((payload or {}).get("status") or "")
            recording_id = int((payload or {}).get("recording_id") or 0)
            if recording_id and status in {"ok", "repaired"} and runtime.settings["archive"].get("auto_after_validation"):
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
        self.archive_queue: asyncio.Queue[int] = asyncio.Queue()
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
        with DB_LOCK, _connect() as conn:
            conn.execute(
                "INSERT INTO notification_queue(event_type,payload_json,status,attempts,next_attempt,created_epoch) VALUES(?,?,?,?,?,?)",
                (event_type, json.dumps(payload, ensure_ascii=False), "queued", 0, time.time(), time.time()),
            )

    def enqueue_archive(self, recording_id: int) -> None:
        try:
            self.archive_queue.put_nowait(int(recording_id))
        except Exception:
            pass

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
            "postprocess.failed": "후처리에 실패했습니다.",
            "storage.warning": "저장소 여유 공간이 부족합니다.",
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

    def _send_destinations(self, event_type: str, payload: dict[str, Any]) -> None:
        message = self._message(event_type, payload)
        config = getattr(self.app.state, "config", {}) or {}
        if config.get("telegram_enabled"):
            self.lar.sendTelegram(f"<b>Live Auto Recorder</b>\n{message}")
        webhook = str(config.get("discord_webhook_url") or "").strip()
        if config.get("discord_enabled") and webhook.startswith("https://"):
            response = requests.post(webhook, json={"content": message}, timeout=10)
            response.raise_for_status()
        for item in self.settings.get("webhooks", []):
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            events = item.get("events") or ["*"]
            if "*" not in events and event_type not in events:
                continue
            url = str(item.get("url") or "").strip()
            if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
                continue
            body = json.dumps({"event": event_type, "timestamp": time.time(), "data": payload}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers = {"Content-Type": "application/json", "User-Agent": "Live-Auto-Recorder/webhook"}
            secret = str(item.get("secret") or "")
            if secret:
                headers["X-LAR-Signature-256"] = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            response = requests.post(url, data=body, headers=headers, timeout=10)
            response.raise_for_status()

    async def _notification_loop(self) -> None:
        while True:
            try:
                if self._quiet_now():
                    await asyncio.sleep(30)
                    continue
                with DB_LOCK, _connect() as conn:
                    row = conn.execute(
                        "SELECT * FROM notification_queue WHERE status IN ('queued','retry') AND next_attempt<=? ORDER BY id LIMIT 1",
                        (time.time(),),
                    ).fetchone()
                if not row:
                    await asyncio.sleep(2)
                    continue
                item = dict(row)
                try:
                    payload = json.loads(item["payload_json"] or "{}")
                    await asyncio.to_thread(self._send_destinations, item["event_type"], payload)
                    with DB_LOCK, _connect() as conn:
                        conn.execute("UPDATE notification_queue SET status='sent',sent_epoch=?,last_error='' WHERE id=?", (time.time(), item["id"]))
                except Exception as exc:
                    attempts = int(item["attempts"] or 0) + 1
                    maximum = max(1, min(int(self.settings["notifications"].get("max_attempts", 5)), 20))
                    status = "failed" if attempts >= maximum else "retry"
                    delay = min(3600, 15 * (2 ** min(attempts - 1, 7)))
                    with DB_LOCK, _connect() as conn:
                        conn.execute(
                            "UPDATE notification_queue SET status=?,attempts=?,next_attempt=?,last_error=? WHERE id=?",
                            (status, attempts, time.time() + delay, str(exc)[:800], item["id"]),
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(5)

    async def _archive_loop(self) -> None:
        while True:
            recording_id = await self.archive_queue.get()
            try:
                await asyncio.to_thread(self.archive_recording, recording_id)
            except Exception:
                pass
            finally:
                self.archive_queue.task_done()

    def archive_recording(self, recording_id: int) -> dict[str, Any]:
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
        try:
            proc = subprocess.run(["rclone", "copyto", str(path), target, "--retries", "3", "--low-level-retries", "5"], capture_output=True, text=True, timeout=86400, check=False)
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or "rclone 업로드 실패")[-1200:])
            if cfg.get("verify_size", True):
                size_proc = subprocess.run(["rclone", "size", target, "--json"], capture_output=True, text=True, timeout=120, check=False)
                if size_proc.returncode != 0:
                    raise RuntimeError((size_proc.stderr or "원격 크기 확인 실패")[-800:])
                remote_size = int(json.loads(size_proc.stdout or "{}").get("bytes") or 0)
                if remote_size != path.stat().st_size:
                    raise RuntimeError(f"크기 불일치: local={path.stat().st_size}, remote={remote_size}")
            update_recording(recording_id, archive_status="completed", archive_target=target)
            self.enqueue_notification("archive.completed", {"recording_id": recording_id, "channel_name": recording.get("channel_name"), "detail": target})
            if cfg.get("delete_after"):
                path.unlink()
            return {"status": "completed", "target": target}
        except Exception as exc:
            update_recording(recording_id, archive_status="failed", archive_target=target, error=str(exc)[:1000])
            self.enqueue_notification("archive.failed", {"recording_id": recording_id, "channel_name": recording.get("channel_name"), "error": str(exc)})
            raise HTTPException(status_code=502, detail=str(exc)) from exc

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
        runtime.enqueue_archive(recording_id)
        return {"status": "queued"}

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
        return {"items": [dict(row) for row in rows]}

    @router.post("/api/v3/notifications/{notification_id}/retry")
    async def retry_notification(notification_id: int):
        with DB_LOCK, _connect() as conn:
            conn.execute("UPDATE notification_queue SET status='retry',next_attempt=?,last_error='' WHERE id=?", (time.time(), notification_id))
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
