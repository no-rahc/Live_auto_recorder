"""Backup, statistics, and settings mixin."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import shutil
import time
import zipfile
from collections import Counter
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from module.operations_common import DEFAULT_SETTINGS, _bytes_human, _deep_merge, _duration_seconds, _iso, _safe_json


class BackupStatsMixin:
    # --------------------------- backups ------------------------------
    def _backup_sources(self, include_secrets: bool) -> list[Path]:
        names = ["config.json", "channels.json", "operations_v2.json"]
        if include_secrets:
            names += ["cookie.json", "ycookie.txt", "login.json", "telegram.json"]
        return [self.data_dir / name for name in names if (self.data_dir / name).exists()]

    def create_backup(self, include_secrets: bool | None = None, reason: str = "manual") -> dict[str, Any]:
        include = self.settings["backup"].get("include_secrets", False) if include_secrets is None else bool(include_secrets)
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{reason}.zip"
        path = self.backup_dir / filename
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            manifest = {"created_at": _iso(), "include_secrets": include, "reason": reason, "version": 2}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for source in self._backup_sources(include):
                archive.write(source, arcname=source.name)
        self._trim_backups()
        self.audit("backup_created", f"name={filename}; secrets={include}")
        return self._backup_meta(path)

    def _backup_meta(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {"name": path.name, "size": stat.st_size, "size_text": _bytes_human(stat.st_size), "created_at": _iso(stat.st_mtime)}

    def list_backups(self) -> list[dict[str, Any]]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        return [self._backup_meta(path) for path in sorted(self.backup_dir.glob("backup_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)]

    def _trim_backups(self) -> None:
        keep = max(1, min(int(self.settings["backup"].get("keep", 7)), 100))
        backups = sorted(self.backup_dir.glob("backup_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in backups[keep:]:
            with suppress(OSError):
                path.unlink()

    def backup_path(self, name: str) -> Path:
        if not re.fullmatch(r"backup_[A-Za-z0-9_.-]+\.zip", name):
            raise HTTPException(status_code=400, detail="잘못된 백업 이름입니다.")
        path = (self.backup_dir / name).resolve()
        if self.backup_dir.resolve() not in path.parents or not path.exists():
            raise HTTPException(status_code=404, detail="백업을 찾을 수 없습니다.")
        return path

    def restore_backup(self, name: str) -> dict[str, Any]:
        path = self.backup_path(name)
        pre = self.create_backup(include_secrets=True, reason="pre_restore")
        allowed = {"config.json", "channels.json", "operations_v2.json", "cookie.json", "ycookie.txt", "login.json", "telegram.json"}
        restored: list[str] = []
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                base = Path(info.filename).name
                if base not in allowed or info.is_dir():
                    continue
                target = (self.data_dir / base).resolve()
                if self.data_dir.resolve() not in target.parents:
                    continue
                target.write_bytes(archive.read(info))
                restored.append(base)
        with suppress(Exception):
            self.app.state.config = self.lar.loadConfig()
        with suppress(Exception):
            channels = self.lar.loadChannels()
            self.app.state.channels[:] = channels
            self.lar.RecorderManager.setChannels(channels)
        self.settings = _deep_merge(DEFAULT_SETTINGS, _safe_json(self.settings_path, {}))
        self.audit("backup_restored", f"name={name}; files={','.join(restored)}")
        return {"restored": restored, "pre_restore_backup": pre}

    async def _backup_loop(self) -> None:
        while True:
            try:
                if self.settings["backup"].get("scheduled"):
                    interval = max(1, int(self.settings["backup"].get("interval_hours", 24))) * 3600
                    backups = self.list_backups()
                    latest = 0.0
                    if backups:
                        latest_path = self.backup_path(backups[0]["name"])
                        latest = latest_path.stat().st_mtime
                    if time.time() - latest >= interval:
                        self.create_backup(reason="scheduled")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.audit("backup_error", str(exc), "error")
            await asyncio.sleep(3600)

    # --------------------------- statistics ---------------------------
    def statistics(self) -> dict[str, Any]:
        from module.recording_history import get_history
        entries = get_history(limit=9999)
        today = datetime.now().date()
        daily: list[dict[str, Any]] = []
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            day_entries = [item for item in entries if str(item.get("ts", "")).startswith(key)]
            daily.append({
                "date": key,
                "recordings": sum(item.get("event") == "recording_started" for item in day_entries),
                "failures": sum(item.get("event") in {"recording_failed", "postprocess_failed"} for item in day_entries),
                "duration_seconds": sum(_duration_seconds(item.get("duration", "")) for item in day_entries),
            })
        size_by_name: dict[str, int] = {}
        for file_item in self._recording_files():
            size_by_name[file_item["name"]] = max(size_by_name.get(file_item["name"], 0), int(file_item["size"]))
        seen_channel_files: set[tuple[str, str]] = set()
        by_channel: dict[str, dict[str, Any]] = {}
        for entry in entries:
            name = str(entry.get("channel_name") or entry.get("channel_id") or "알 수 없음")
            bucket = by_channel.setdefault(name, {"channel": name, "recordings": 0, "failures": 0, "duration_seconds": 0, "storage_bytes": 0})
            if entry.get("event") == "recording_started":
                bucket["recordings"] += 1
            if entry.get("event") in {"recording_failed", "postprocess_failed"}:
                bucket["failures"] += 1
            bucket["duration_seconds"] += _duration_seconds(entry.get("duration", ""))
            filename = str(entry.get("filename") or "")
            file_key = (name, filename)
            if filename and file_key not in seen_channel_files:
                bucket["storage_bytes"] += size_by_name.get(filename, 0)
                seen_channel_files.add(file_key)
        failures = Counter(str(item.get("error") or "원인 미기록")[:120] for item in entries if item.get("event") in {"recording_failed", "postprocess_failed"})
        starts = sum(item.get("event") == "recording_started" for item in entries)
        failed = sum(item.get("event") in {"recording_failed", "postprocess_failed"} for item in entries)
        return {
            "total_recordings": starts,
            "total_failures": failed,
            "success_rate": round((max(0, starts - failed) / starts * 100), 1) if starts else 100.0,
            "total_duration_seconds": sum(_duration_seconds(item.get("duration", "")) for item in entries),
            "daily": daily,
            "by_channel": [
                {**item, "storage_text": _bytes_human(item.get("storage_bytes", 0))}
                for item in sorted(by_channel.values(), key=lambda item: item["recordings"], reverse=True)
            ],
            "failure_reasons": [{"reason": reason, "count": count} for reason, count in failures.most_common(10)],
        }

    def statistics_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "recordings", "failures", "duration_seconds"])
        for row in self.statistics()["daily"]:
            writer.writerow([row["date"], row["recordings"], row["failures"], row["duration_seconds"]])
        return output.getvalue()

    # --------------------------- settings -----------------------------
    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate = _deep_merge(DEFAULT_SETTINGS, {**self.settings, **payload})
        storage = candidate["storage"]
        storage["block_free_percent"] = max(1.0, min(float(storage["block_free_percent"]), 50.0))
        storage["warning_free_percent"] = max(storage["block_free_percent"], min(float(storage["warning_free_percent"]), 80.0))
        health = candidate["health"]
        health["stall_seconds"] = max(30, min(int(health["stall_seconds"]), 3600))
        health["startup_grace_seconds"] = max(0, min(int(health.get("startup_grace_seconds", 30)), 600))
        health["process_exit_grace_seconds"] = max(5, min(int(health.get("process_exit_grace_seconds", 20)), 300))
        health["failed_samples"] = max(1, min(int(health.get("failed_samples", 2)), 10))
        health["stall_confirmations"] = max(2, min(int(health.get("stall_confirmations", 3)), 12))
        health["max_restart_attempts"] = max(0, min(int(health["max_restart_attempts"]), 20))
        backup = candidate["backup"]
        backup["keep"] = max(1, min(int(backup["keep"]), 100))
        backup["interval_hours"] = max(1, min(int(backup["interval_hours"]), 720))
        self.settings = candidate
        self.save_settings()
        self.audit("settings_updated")
        return self.settings

    def summary(self) -> dict[str, Any]:
        health_values = list(self.health.values())
        return {
            "storage": self.storage_info(),
            "health_counts": dict(Counter(item.get("state", "unknown") for item in health_values)),
            "active_recordings": sum(bool(item.get("recording")) for item in health_values),
            "jobs": dict(Counter(item.get("status", "unknown") for item in self.jobs)),
            "backups": len(self.list_backups()),
            "settings": self.settings,
        }
