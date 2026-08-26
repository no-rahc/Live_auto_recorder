"""System diagnostics, database protection, update checks, and cookie health."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from module.operations_common import _bytes_human, _iso
from module.recording_catalog import DB_PATH, _LOCK as DB_LOCK, _connect, init_catalog


_UPDATE_URL = "https://api.github.com/repos/no-rahc/Live_auto_recorder/releases/latest"
_AUTH_COOKIE_NAMES = {
    "SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO",
    "__Secure-1PAPISID", "__Secure-3PAPISID", "__Secure-1PSID", "__Secure-3PSID",
}


def _version_tuple(value: str) -> tuple[int, ...]:
    text = str(value or "").strip().lower().lstrip("v")
    parts: list[int] = []
    for token in text.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts or [0])


def _check(name: str, status: str, detail: str, remedy: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "remedy": remedy}


class MaintenanceOpsMixin:
    """Low-frequency operational checks that must never block recorder loops."""

    def _maintenance_init(self) -> None:
        if getattr(self, "_maintenance_ready", False):
            return
        self._maintenance_ready = True
        self.database_backup_dir = self.data_dir / "database_backups"
        self.database_backup_dir.mkdir(parents=True, exist_ok=True)
        self._version_cache: dict[str, Any] = {}
        self._cookie_cache: dict[str, Any] = {}
        self._cookie_alert_signature = ""
        self._db_alert_signature = ""
        self._last_cookie_check = 0.0
        self._last_db_check = 0.0
        self._last_update_check = 0.0

    # --------------------------- database -----------------------------
    def database_health(self) -> dict[str, Any]:
        self._maintenance_init()
        init_catalog()
        result: dict[str, Any] = {
            "path": str(DB_PATH),
            "exists": DB_PATH.exists(),
            "size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
            "size_text": _bytes_human(DB_PATH.stat().st_size if DB_PATH.exists() else 0),
            "integrity": "unknown",
            "checkpoint": None,
            "checked_at": _iso(),
        }
        try:
            with DB_LOCK, _connect() as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                result["integrity"] = str(row[0] if row else "unknown")
                checkpoint = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                result["checkpoint"] = list(checkpoint) if checkpoint else None
            result["status"] = "ok" if result["integrity"].lower() == "ok" else "problem"
        except Exception as exc:
            result["status"] = "problem"
            result["integrity"] = "error"
            result["error"] = str(exc)[:500]
        return result

    def _database_backup_meta(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "name": path.name,
            "size": stat.st_size,
            "size_text": _bytes_human(stat.st_size),
            "created_at": _iso(stat.st_mtime),
        }

    def list_database_backups(self) -> list[dict[str, Any]]:
        self._maintenance_init()
        return [
            self._database_backup_meta(path)
            for path in sorted(
                self.database_backup_dir.glob("recordings_*.sqlite3"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        ]

    def _trim_database_backups(self) -> None:
        keep = max(1, min(int(self.settings.get("database", {}).get("keep", 7) or 7), 100))
        paths = sorted(
            self.database_backup_dir.glob("recordings_*.sqlite3"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for path in paths[keep:]:
            with suppress(OSError):
                path.unlink()

    def create_database_backup(self, reason: str = "manual") -> dict[str, Any]:
        self._maintenance_init()
        health = self.database_health()
        if health.get("status") != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {health.get('integrity') or health.get('error')}")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_reason = "".join(ch for ch in str(reason) if ch.isalnum() or ch in "_-")[:32] or "manual"
        destination = self.database_backup_dir / f"recordings_{stamp}_{safe_reason}.sqlite3"
        with DB_LOCK:
            source = sqlite3.connect(DB_PATH, timeout=15)
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
                row = target.execute("PRAGMA integrity_check").fetchone()
                if not row or str(row[0]).lower() != "ok":
                    raise RuntimeError(f"backup integrity_check failed: {row[0] if row else 'no result'}")
            finally:
                target.close()
                source.close()
        self._trim_database_backups()
        self.audit("database_backup_created", f"name={destination.name}; reason={safe_reason}")
        return {**self._database_backup_meta(destination), "integrity": "ok", "reason": safe_reason}

    # --------------------------- cookies ------------------------------
    def cookie_health(self) -> dict[str, Any]:
        self._maintenance_init()
        now = time.time()
        items: list[dict[str, Any]] = []

        chzzk_path = self.data_dir / "cookie.json"
        chzzk_status = "not_configured"
        chzzk_detail = "CHZZK 쿠키가 설정되지 않았습니다. 익명 접근 가능한 방송은 그대로 녹화할 수 있습니다."
        try:
            if chzzk_path.exists():
                data = json.loads(chzzk_path.read_text(encoding="utf-8") or "{}")
                configured = isinstance(data, dict) and any(str(v or "").strip() for v in data.values())
                if configured:
                    expected = [name for name in ("NID_AUT", "NID_SES") if str(data.get(name) or "").strip()]
                    age_days = max(0.0, (now - chzzk_path.stat().st_mtime) / 86400)
                    if expected:
                        chzzk_status = "warning" if age_days >= 90 else "ok"
                        chzzk_detail = f"인증 쿠키 {len(expected)}개 확인 · 파일 갱신 {age_days:.0f}일 전"
                    else:
                        chzzk_status = "warning"
                        chzzk_detail = "쿠키 파일은 있으나 NID_AUT/NID_SES 인증 값이 확인되지 않습니다."
        except Exception as exc:
            chzzk_status, chzzk_detail = "problem", f"cookie.json을 읽을 수 없습니다: {exc}"
        items.append({
            "platform": "chzzk", "status": chzzk_status, "detail": chzzk_detail,
            "remedy": "CHZZK 로그인이 필요한 방송에서 401/403이 발생하면 쿠키를 다시 등록하세요." if chzzk_status != "ok" else "",
        })

        youtube_path = self.data_dir / "ycookie.txt"
        youtube_status = "not_configured"
        youtube_detail = "YouTube 쿠키가 설정되지 않았습니다. 공개 방송은 쿠키 없이도 녹화할 수 있습니다."
        try:
            if youtube_path.exists():
                rows = []
                for raw in youtube_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        rows.append(parts)
                if rows:
                    auth_rows = [row for row in rows if row[5] in _AUTH_COOKIE_NAMES or row[5].startswith("__Secure-")]
                    relevant = auth_rows or rows
                    expiries = []
                    for row in relevant:
                        with suppress(ValueError):
                            expiry = int(row[4])
                            if expiry > 0:
                                expiries.append(expiry)
                    valid = [expiry for expiry in expiries if expiry > now]
                    if expiries and not valid:
                        youtube_status = "problem"
                        youtube_detail = "저장된 YouTube 인증 쿠키의 만료 시각이 모두 지났습니다."
                    elif valid:
                        days = (min(valid) - now) / 86400
                        youtube_status = "warning" if days <= 7 else "ok"
                        youtube_detail = f"쿠키 {len(rows)}개 확인 · 가장 가까운 만료까지 {max(0, days):.1f}일"
                    else:
                        youtube_status = "ok"
                        youtube_detail = f"세션형 쿠키 {len(rows)}개 확인 · 만료 시각 정보 없음"
        except Exception as exc:
            youtube_status, youtube_detail = "problem", f"ycookie.txt를 읽을 수 없습니다: {exc}"
        items.append({
            "platform": "youtube", "status": youtube_status, "detail": youtube_detail,
            "remedy": "YouTube 로그인/연령 제한 방송에서 인증 오류가 나면 cookies.txt를 다시 등록하세요." if youtube_status in {"warning", "problem"} else "",
        })

        severity = {"problem": 3, "warning": 2, "not_configured": 1, "ok": 0}
        overall = max(items, key=lambda item: severity.get(str(item.get("status")), 0))["status"] if items else "ok"
        result = {"status": overall, "items": items, "checked_at": _iso(now)}
        self._cookie_cache = result
        return result

    async def _check_cookie_alerts(self) -> None:
        state = self.cookie_health()
        actionable = [item for item in state["items"] if item["status"] in {"warning", "problem"}]
        signature = "|".join(f"{item['platform']}:{item['status']}:{item['detail']}" for item in actionable)
        if actionable and signature != self._cookie_alert_signature:
            detail = " / ".join(f"{item['platform']}: {item['detail']}" for item in actionable)
            await self._notify("auth.cookie_warning", detail, {"items": actionable})
            self.audit("cookie_health_warning", detail, "warning")
        self._cookie_alert_signature = signature

    # --------------------------- update -------------------------------
    def version_status(self, force: bool = False) -> dict[str, Any]:
        self._maintenance_init()
        now = time.time()
        if self._version_cache and not force and now - float(self._version_cache.get("checked_epoch", 0) or 0) < 3600:
            return self._version_cache
        current = str(getattr(self.lar, "PROGRAM_VERSION", "") or getattr(self.lar, "RELEASE_VERSION", "") or "unknown")
        result: dict[str, Any] = {"current": current, "checked_at": _iso(now), "checked_epoch": now}
        try:
            response = requests.get(
                _UPDATE_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "Live-Auto-Recorder/update-check"},
                timeout=3,
            )
            response.raise_for_status()
            data = response.json()
            latest = str(data.get("tag_name") or data.get("name") or "").strip()
            result.update({
                "status": "ok",
                "latest": latest,
                "update_available": bool(latest and _version_tuple(latest) > _version_tuple(current)),
                "name": str(data.get("name") or latest),
                "published_at": str(data.get("published_at") or ""),
                "url": str(data.get("html_url") or ""),
                "notes": str(data.get("body") or "")[:1800],
            })
        except Exception as exc:
            result.update({"status": "warning", "latest": "", "update_available": False, "error": str(exc)[:500]})
        self._version_cache = result
        return result

    # --------------------------- diagnostics --------------------------
    def _tool_diagnostic(self, label: str, command: str, getter: Any = None) -> dict[str, str]:
        path = ""
        try:
            path = str(getter() or "") if getter else str(shutil.which(command) or "")
        except BaseException:
            path = str(shutil.which(command) or "")
        if path and (Path(path).exists() or shutil.which(path)):
            return _check(label, "ok", path)
        return _check(label, "problem", f"{command} 실행 파일을 찾지 못했습니다.", f"{command}를 설치하고 PATH 또는 프로그램 설정을 확인하세요.")

    def system_diagnostics(self) -> dict[str, Any]:
        self._maintenance_init()
        checks: list[dict[str, str]] = []
        checks.append(self._tool_diagnostic("FFmpeg", "ffmpeg", getattr(self.lar, "getFFmpeg", None)))
        checks.append(self._tool_diagnostic("Streamlink", "streamlink", getattr(self.lar, "getStreamlink", None)))
        checks.append(self._tool_diagnostic("ytarchive", "ytarchive", getattr(self.lar, "getYtarchive", None)))
        checks.append(self._tool_diagnostic("rclone", "rclone"))

        try:
            self.recording_root.mkdir(parents=True, exist_ok=True)
            fd, raw = tempfile.mkstemp(prefix=".lar-write-check-", dir=self.recording_root)
            os.close(fd)
            Path(raw).unlink(missing_ok=True)
            checks.append(_check("녹화 저장소 쓰기", "ok", str(self.recording_root)))
        except Exception as exc:
            checks.append(_check("녹화 저장소 쓰기", "problem", str(exc), "RECORDINGS_ROOT 마운트와 UID/GID 쓰기 권한을 확인하세요."))

        db = self.database_health()
        checks.append(_check(
            "SQLite",
            "ok" if db.get("status") == "ok" else "problem",
            f"integrity={db.get('integrity')} · {db.get('size_text')}",
            "data/recordings.sqlite3와 최근 database_backups를 확인하세요." if db.get("status") != "ok" else "",
        ))

        cookies = self.cookie_health()
        for item in cookies["items"]:
            status = "warning" if item["status"] == "not_configured" else item["status"]
            checks.append(_check(f"{item['platform'].upper()} 쿠키", status, item["detail"], item.get("remedy", "")))

        config = getattr(self.app.state, "config", {}) or {}
        telegram_ready = bool(config.get("telegram_enabled"))
        discord_ready = bool(config.get("discord_enabled")) and bool(str(config.get("discord_webhook_url") or "").strip())
        if telegram_ready or discord_ready:
            channels = []
            if telegram_ready:
                channels.append("Telegram")
            if discord_ready:
                channels.append("Discord")
            checks.append(_check("알림", "ok", ", ".join(channels) + " 활성화"))
        else:
            checks.append(_check("알림", "warning", "활성화된 Telegram/Discord 알림이 없습니다.", "필요하면 설정 관리에서 알림 채널을 구성하세요."))

        storage = self.storage_info()
        storage_status = str(storage.get("status") or "error")
        checks.append(_check(
            "저장 공간",
            "ok" if storage_status == "ok" else ("warning" if storage_status == "warning" else "problem"),
            f"남은 공간 {storage.get('free_percent', 0)}% · {_bytes_human(storage.get('free', 0))}",
            "오래된 녹화를 정리하거나 저장소 용량을 늘리세요." if storage_status != "ok" else "",
        ))

        network_errors: list[str] = []
        for url in ("https://www.youtube.com", "https://chzzk.naver.com"):
            try:
                response = requests.head(url, allow_redirects=True, timeout=3, headers={"User-Agent": "Live-Auto-Recorder/diagnostics"})
                if response.status_code >= 500:
                    network_errors.append(f"{url}: HTTP {response.status_code}")
            except Exception as exc:
                network_errors.append(f"{url}: {exc}")
        checks.append(_check(
            "네트워크",
            "ok" if not network_errors else "problem",
            "CHZZK/YouTube DNS·HTTPS 연결 정상" if not network_errors else "; ".join(network_errors)[:500],
            "DNS, 방화벽, 프록시/VPN 및 인터넷 연결을 확인하세요." if network_errors else "",
        ))

        counts = {status: sum(item["status"] == status for item in checks) for status in ("ok", "warning", "problem")}
        overall = "problem" if counts["problem"] else ("warning" if counts["warning"] else "ok")
        return {"status": overall, "counts": counts, "checks": checks, "checked_at": _iso()}

    # --------------------------- lifecycle ----------------------------
    async def _maintenance_loop(self) -> None:
        self._maintenance_init()
        while True:
            try:
                now = time.time()
                db_cfg = self.settings.get("database", {})
                if now - self._last_db_check >= 6 * 3600:
                    self._last_db_check = now
                    health = await asyncio.to_thread(self.database_health)
                    signature = "" if health.get("status") == "ok" else str(health.get("integrity") or health.get("error") or "problem")
                    if signature and signature != self._db_alert_signature:
                        await self._notify("database.integrity_failed", signature, {"database": str(DB_PATH), "health": health})
                        self.audit("database_integrity_failed", signature, "error")
                    self._db_alert_signature = signature
                if db_cfg.get("scheduled", True):
                    interval = max(1, min(int(db_cfg.get("interval_hours", 24) or 24), 720)) * 3600
                    backups = self.list_database_backups()
                    latest_epoch = 0.0
                    if backups:
                        latest = self.database_backup_dir / backups[0]["name"]
                        latest_epoch = latest.stat().st_mtime
                    if now - latest_epoch >= interval:
                        try:
                            await asyncio.to_thread(self.create_database_backup, "scheduled")
                        except Exception as exc:
                            self.audit("database_backup_error", str(exc), "error")
                            await self._notify("database.integrity_failed", str(exc), {"database": str(DB_PATH)})
                cookie_interval = max(1, min(int(self.settings.get("maintenance", {}).get("cookie_check_hours", 6) or 6), 168)) * 3600
                if now - self._last_cookie_check >= cookie_interval:
                    self._last_cookie_check = now
                    await asyncio.to_thread(self.cookie_health)
                    await self._check_cookie_alerts()
                update_interval = max(1, min(int(self.settings.get("maintenance", {}).get("update_check_hours", 24) or 24), 168)) * 3600
                if now - self._last_update_check >= update_interval:
                    self._last_update_check = now
                    status = await asyncio.to_thread(self.version_status, True)
                    if status.get("update_available"):
                        await self._notify(
                            "system.update_available",
                            f"새 버전 {status.get('latest')}을 사용할 수 있습니다. 현재 {status.get('current')}",
                            {"current": status.get("current"), "latest": status.get("latest"), "url": status.get("url")},
                        )
                group_cfg = self.settings.get("recording_groups", {})
                if group_cfg.get("auto_merge"):
                    from module.recording_catalog import list_merge_candidates
                    from module.recording_merge import merge_broadcast
                    candidates = list_merge_candidates(
                        quiet_seconds=max(30, int(group_cfg.get("quiet_seconds", 900) or 900)),
                        limit=2,
                    )
                    for broadcast_id in candidates:
                        try:
                            result = await asyncio.to_thread(
                                merge_broadcast,
                                broadcast_id,
                                delete_segments=bool(group_cfg.get("delete_segments_after_merge", False)),
                            )
                            await self._notify("recording.merged", f"방송 세그먼트 {result.get('segment_count')}개를 합쳤습니다.", result)
                            self.audit("broadcast_merged", f"broadcast={broadcast_id}; output={result.get('output_path')}")
                        except Exception as exc:
                            await self._notify("recording.merge_failed", str(exc), {"broadcast_id": broadcast_id})
                            self.audit("broadcast_merge_failed", f"broadcast={broadcast_id}; error={exc}", "error")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.audit("maintenance_error", str(exc), "error")
            # Merge candidates should not wait an extra hour after the quiet
            # window. Expensive checks above are independently rate-limited.
            await asyncio.sleep(300)
