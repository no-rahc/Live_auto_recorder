"""Operational safety, health, backup, statistics, and policy extension.

The extension is installed by ``app_entry.py`` and intentionally stores its
settings separately from the legacy configuration files.  This keeps existing
installations compatible while allowing operational features to evolve without
changing the recorder's core data schema.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".ts", ".flv", ".avi", ".webm", ".mov"}
MAX_AUDIT_LINES = 2000
MAX_JOBS = 300

DEFAULT_SETTINGS: dict[str, Any] = {
    "storage": {
        "warning_free_percent": 10.0,
        "block_free_percent": 5.0,
        "auto_cleanup": False,
        "cleanup_mode": "age",
        "retention_days": 30,
        "max_total_gb": 0.0,
        "minimum_file_age_minutes": 10,
    },
    "health": {
        "enabled": True,
        "check_interval_seconds": 10,
        "stall_seconds": 120,
        "startup_grace_seconds": 30,
        "process_exit_grace_seconds": 20,
        "failed_samples": 2,
        "stall_confirmations": 3,
        "auto_restart": True,
        "max_restart_attempts": 3,
        "restart_cooldown_seconds": 60,
    },
    "backup": {
        "scheduled": True,
        "interval_hours": 24,
        "keep": 7,
        "include_secrets": False,
    },
    "rules": {},
}


def _deep_merge(default: dict[str, Any], value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    source = value if isinstance(value, dict) else {}
    for key, item in default.items():
        incoming = source.get(key)
        if isinstance(item, dict):
            result[key] = _deep_merge(item, incoming)
        else:
            result[key] = incoming if incoming is not None else item
    for key, item in source.items():
        if key not in result:
            result[key] = item
    return result


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _safe_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        with suppress(Exception):
            shutil.copy2(path, path.with_suffix(path.suffix + ".corrupt"))
    return default


def _iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d %H:%M:%S")


def _duration_seconds(value: str) -> int:
    try:
        parts = [int(part) for part in str(value or "").split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        pass
    return 0


def _bytes_human(value: int | float) -> str:
    number = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} TB"


class OperationsBase:
    def __init__(self, app: Any, lar: Any) -> None:
        self.app = app
        self.lar = lar
        self.data_dir = Path(getattr(lar, "CONFIG_PATH", Path.cwd() / "json" / "config.json")).parent
        configured_root = os.getenv("RECORDINGS_ROOT", "").strip()
        if configured_root:
            self.recording_root = Path(configured_root).expanduser().resolve()
        elif Path("/app/chzzk").exists():
            self.recording_root = Path("/app/chzzk")
        else:
            self.recording_root = (Path(__file__).resolve().parents[1] / "chzzk").resolve()

        self.settings_path = self.data_dir / "operations_v2.json"
        self.jobs_path = self.data_dir / "operations_jobs.json"
        self.audit_path = self.data_dir / "operations_audit.jsonl"
        self.backup_dir = self.data_dir / "backups"
        self.settings = _deep_merge(DEFAULT_SETTINGS, _safe_json(self.settings_path, {}))
        self.jobs: list[dict[str, Any]] = list(_safe_json(self.jobs_path, []))[-MAX_JOBS:]
        self.health: dict[str, dict[str, Any]] = {}
        self.samples: dict[str, dict[str, Any]] = {}
        self.job_tasks: dict[str, asyncio.Task[Any]] = {}
        self.background_tasks: list[asyncio.Task[Any]] = []
        self.last_storage_level = "unknown"
        self.last_backup_check = 0.0
        self._core_user_start: Callable[..., Awaitable[Any]] | None = None
        self._core_queue_pattern: Callable[..., Awaitable[Any]] | None = None
        self._core_queue_last: Callable[..., Awaitable[Any]] | None = None
        self._started = False
        self._restart_locks: dict[str, asyncio.Lock] = {}
        self.policy_blocked: set[str] = set()
        self.storage_stopped = False

    # --------------------------- persistence ---------------------------
    def save_settings(self) -> None:
        _json_write(self.settings_path, self.settings)

    def save_jobs(self) -> None:
        self.jobs = self.jobs[-MAX_JOBS:]
        _json_write(self.jobs_path, self.jobs)

    def audit(self, action: str, detail: str = "", result: str = "ok") -> None:
        entry = {"ts": _iso(), "epoch": time.time(), "action": action, "detail": detail[:500], "result": result}
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()
            if len(lines) > MAX_AUDIT_LINES:
                self.audit_path.write_text("\n".join(lines[-MAX_AUDIT_LINES:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    def read_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        try:
            for line in self.audit_path.read_text(encoding="utf-8").splitlines():
                with suppress(json.JSONDecodeError):
                    entries.append(json.loads(line))
        except FileNotFoundError:
            return []
        return sorted(entries, key=lambda item: item.get("epoch", 0), reverse=True)[: max(1, min(limit, 500))]

    # --------------------------- lifecycle ----------------------------
    def install_hooks(self) -> None:
        if self._core_queue_pattern is None:
            self._core_queue_pattern = self.lar.queueBatchPattern
            self.lar.queueBatchPattern = self._wrap_postprocess("pattern", self._core_queue_pattern)
        if self._core_queue_last is None:
            self._core_queue_last = self.lar.queueBatchLast
            self.lar.queueBatchLast = self._wrap_postprocess("last", self._core_queue_last)

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.recording_root.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.install_hooks()
        self._install_start_guard()
        if self.storage_info().get("recording_blocked"):
            with suppress(Exception):
                await self.app.state.fsm.stopAll()
            self.storage_stopped = True
            self.audit("startup_storage_block", "automatic watchers stopped because storage is critical", "blocked")
        with suppress(Exception):
            await self.monitor_once()
        self.background_tasks = [
            asyncio.create_task(self._monitor_loop(), name="operations-health"),
            asyncio.create_task(self._backup_loop(), name="operations-backup"),
        ]
        self.audit("runtime_started", f"recording_root={self.recording_root}")

    async def stop(self) -> None:
        for task in self.background_tasks:
            task.cancel()
        for task in self.background_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.background_tasks.clear()
        self._started = False

    def _install_start_guard(self) -> None:
        fsm = getattr(self.app.state, "fsm", None)
        if not fsm or getattr(fsm, "_operations_v2_guarded", False):
            return
        self._core_user_start = fsm.userStart

        async def guarded_user_start(channel_id: str, is_user_request: bool = False):
            allowed, reason, delay = self.can_start(channel_id)
            if not allowed:
                self.health.setdefault(channel_id, {}).update({
                    "state": "blocked",
                    "label": "정책 차단",
                    "last_error": reason,
                    "updated_at": _iso(),
                })
                self.audit("recording_blocked", f"channel={channel_id}; reason={reason}", "blocked")
                return None
            channel = self._channel(channel_id)
            rule = self.settings.get("rules", {}).get(str(channel_id), {})
            quality = str(rule.get("quality_override") or "").strip()
            if channel is not None and quality:
                channel["quality"] = quality
            if delay > 0 and not is_user_request:
                self.health.setdefault(channel_id, {}).update({"state": "delayed", "label": f"{delay}초 지연"})
                await asyncio.sleep(delay)
            assert self._core_user_start is not None
            return await self._core_user_start(channel_id, is_user_request=is_user_request)

        fsm.userStart = guarded_user_start
        fsm._operations_v2_guarded = True

    # --------------------------- storage ------------------------------
    def storage_info(self) -> dict[str, Any]:
        try:
            usage = shutil.disk_usage(self.recording_root)
            free_percent = (usage.free / usage.total * 100.0) if usage.total else 0.0
            used_percent = 100.0 - free_percent
        except Exception as exc:
            return {"path": str(self.recording_root), "status": "error", "error": str(exc)}

        cfg = self.settings["storage"]
        block = float(cfg.get("block_free_percent", 5))
        warning = max(block, float(cfg.get("warning_free_percent", 10)))
        level = "critical" if free_percent <= block else "warning" if free_percent <= warning else "ok"
        return {
            "path": str(self.recording_root),
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "free_percent": round(free_percent, 2),
            "used_percent": round(used_percent, 2),
            "total_text": _bytes_human(usage.total),
            "used_text": _bytes_human(usage.used),
            "free_text": _bytes_human(usage.free),
            "status": level,
            "recording_blocked": level == "critical",
        }

    def can_start(self, channel_id: str) -> tuple[bool, str, int]:
        storage = self.storage_info()
        if storage.get("recording_blocked"):
            return False, f"녹화 저장소 여유 공간이 {storage.get('free_percent', 0)}%입니다.", 0
        channel = self._channel(channel_id)
        allowed, reason = self.evaluate_rule(channel)
        rule = self.settings.get("rules", {}).get(channel_id, {}) if channel else {}
        delay = max(0, min(int(rule.get("start_delay_seconds", 0) or 0), 3600))
        return allowed, reason, delay

    def _busy_paths(self) -> set[Path]:
        busy: set[Path] = set()
        with suppress(Exception):
            channels = list(getattr(self.app.state, "channels", []) or [])
            for raw in self.lar.busyFilePaths(self.lar.recorder_manager, channels):
                busy.add(Path(raw).resolve())
        with suppress(Exception):
            for raw in self.lar.RecorderManager.recording_filename.values():
                if raw:
                    busy.add(Path(raw).resolve())
        return busy

    def _recording_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        if not self.recording_root.exists():
            return files
        root = self.recording_root.resolve()
        for path in root.rglob("*"):
            try:
                if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if root not in resolved.parents:
                    continue
                stat = path.stat()
                files.append({"path": str(resolved), "name": path.name, "size": stat.st_size, "mtime": stat.st_mtime})
            except OSError:
                continue
        return sorted(files, key=lambda item: item["mtime"])

    def cleanup_candidates(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = dict(self.settings["storage"])
        cfg.update(payload or {})
        mode = str(cfg.get("mode") or cfg.get("cleanup_mode") or "age")
        days = max(1, min(int(cfg.get("retention_days", 30) or 30), 3650))
        max_total_gb = max(0.0, float(cfg.get("max_total_gb", 0) or 0))
        min_age = max(1, int(cfg.get("minimum_file_age_minutes", 10) or 10))
        now = time.time()
        busy = self._busy_paths()
        all_files = self._recording_files()
        eligible = [
            item for item in all_files
            if Path(item["path"]).resolve() not in busy and now - item["mtime"] >= min_age * 60
        ]
        candidates: list[dict[str, Any]] = []

        if mode == "age":
            cutoff = now - days * 86400
            candidates = [item for item in eligible if item["mtime"] < cutoff]
        elif mode == "size" and max_total_gb > 0:
            max_bytes = int(max_total_gb * 1024**3)
            current = sum(item["size"] for item in all_files)
            for item in eligible:
                if current <= max_bytes:
                    break
                candidates.append(item)
                current -= item["size"]
        elif mode == "free_space":
            info = self.storage_info()
            target = float(cfg.get("warning_free_percent", 10))
            total = int(info.get("total", 0))
            free = int(info.get("free", 0))
            required = max(0, int(total * target / 100) - free)
            reclaimed = 0
            for item in eligible:
                if reclaimed >= required:
                    break
                candidates.append(item)
                reclaimed += item["size"]
        else:
            raise HTTPException(status_code=400, detail="지원하지 않는 정리 방식입니다.")

        return {
            "mode": mode,
            "candidate_count": len(candidates),
            "candidate_bytes": sum(item["size"] for item in candidates),
            "candidate_text": _bytes_human(sum(item["size"] for item in candidates)),
            "protected_count": len(all_files) - len(eligible),
            "candidates": [
                {**item, "size_text": _bytes_human(item["size"]), "modified_at": _iso(item["mtime"])}
                for item in candidates[:200]
            ],
            "_all": candidates,
        }

    def run_cleanup(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("confirm"):
            raise HTTPException(status_code=400, detail="confirm=true가 필요합니다.")
        preview = self.cleanup_candidates(payload)
        deleted: list[str] = []
        errors: list[dict[str, str]] = []
        root = self.recording_root.resolve()
        for item in preview.pop("_all", []):
            path = Path(item["path"]).resolve()
            if root not in path.parents or path in self._busy_paths():
                continue
            try:
                path.unlink()
                deleted.append(str(path))
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})
        self.audit("cleanup", f"deleted={len(deleted)}; errors={len(errors)}")
        return {**preview, "deleted": deleted, "errors": errors}

    # --------------------------- channel rules ------------------------
    def _channel(self, channel_id: str) -> dict[str, Any] | None:
        return next((item for item in (getattr(self.app.state, "channels", []) or []) if str(item.get("id")) == str(channel_id)), None)

    def evaluate_rule(self, channel: dict[str, Any] | None) -> tuple[bool, str]:
        if not channel:
            return False, "채널을 찾을 수 없습니다."
        rule = self.settings.get("rules", {}).get(str(channel.get("id")), {})
        if not rule or not rule.get("enabled", True):
            return True, "규칙 없음"

        title = str(channel.get("live_title") or channel.get("liveTitle") or "").lower()
        category = str(channel.get("category") or "").lower()
        if any(marker in title for marker in ("불러오는 중", "정보 없음", "방송 제목 없음")):
            title = ""
        if any(marker in category for marker in ("불러오는 중", "정보 없음", "카테고리 없음")):
            category = ""
        includes = [str(item).strip().lower() for item in rule.get("title_include", []) if str(item).strip()]
        excludes = [str(item).strip().lower() for item in rule.get("title_exclude", []) if str(item).strip()]
        categories = [str(item).strip().lower() for item in rule.get("categories", []) if str(item).strip()]
        if includes and title and not any(item in title for item in includes):
            return False, "제목 포함 규칙과 일치하지 않습니다."
        if excludes and any(item in title for item in excludes):
            return False, "제목 제외 규칙과 일치합니다."
        if categories and category and category not in categories:
            return False, "허용된 카테고리가 아닙니다."

        days = rule.get("days") or []
        now = datetime.now()
        if days and now.weekday() not in {int(item) for item in days}:
            return False, "허용된 요일이 아닙니다."
        start = str(rule.get("time_start") or "").strip()
        end = str(rule.get("time_end") or "").strip()
        if start and end:
            current = now.strftime("%H:%M")
            inside = start <= current <= end if start <= end else current >= start or current <= end
            if not inside:
                return False, "허용된 시간대가 아닙니다."
        return True, "허용"

    def set_rule(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._channel(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        normalized = {
            "enabled": bool(payload.get("enabled", True)),
            "title_include": list(payload.get("title_include") or []),
            "title_exclude": list(payload.get("title_exclude") or []),
            "categories": list(payload.get("categories") or []),
            "days": [int(day) for day in payload.get("days", []) if str(day).isdigit() and 0 <= int(day) <= 6],
            "time_start": str(payload.get("time_start") or ""),
            "time_end": str(payload.get("time_end") or ""),
            "start_delay_seconds": max(0, min(int(payload.get("start_delay_seconds", 0) or 0), 3600)),
            "max_duration_minutes": max(0, min(int(payload.get("max_duration_minutes", 0) or 0), 10080)),
            "minimum_duration_minutes": max(0, min(int(payload.get("minimum_duration_minutes", 0) or 0), 1440)),
            "quality_override": str(payload.get("quality_override") or "").strip()[:40],
        }
        self.settings.setdefault("rules", {})[str(channel_id)] = normalized
        self.save_settings()
        self.audit("rule_updated", f"channel={channel_id}")
        return normalized
