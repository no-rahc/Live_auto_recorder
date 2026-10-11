"""Backup, statistics, and settings mixin."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import os
import stat
import tempfile
import uuid
import threading
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

from lar_app.backup_policy import preserve_existing_secrets, sanitize_secrets, secret_backups_allowed
from module.operations_common import DEFAULT_SETTINGS, _bytes_human, _deep_merge, _duration_seconds, _iso, _safe_json


_BACKUP_LOCK = threading.RLock()
_PROTECTED_BACKUPS: set[Path] = set()


def _validate_settings(value: dict[str, Any], defaults: dict[str, Any], prefix: str = "") -> None:
    for key, default in defaults.items():
        if key not in value:
            continue
        item = value[key]
        field = f"{prefix}{key}"
        if isinstance(default, dict):
            if not isinstance(item, dict):
                raise ValueError(f"Invalid settings section: {field}")
            _validate_settings(item, default, field + ".")
        elif isinstance(default, bool):
            if not isinstance(item, bool):
                raise ValueError(f"Invalid boolean setting: {field}")
        elif isinstance(default, (int, float)):
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError(f"Invalid numeric setting: {field}")
            if isinstance(default, int) and not isinstance(item, int):
                raise ValueError(f"Invalid integer setting: {field}")
            if item < 0:
                raise ValueError(f"Negative setting: {field}")
        elif not isinstance(item, type(default)):
            raise ValueError(f"Invalid setting: {field}")


class BackupStatsMixin:
    # --------------------------- backups ------------------------------
    def _backup_sources(self, include_secrets: bool) -> list[Path]:
        names = ["config.json", "channels.json", "operations_v2.json"]
        if include_secrets:
            names += ["cookie.json", "ycookie.txt", "login.json", "telegram.json"]
        return [self.data_dir / name for name in names if (self.data_dir / name).exists()]

    def create_backup(self, include_secrets: bool | None = None, reason: str = "manual") -> dict[str, Any]:
        with _BACKUP_LOCK:
            return self._create_backup(include_secrets, reason)

    def _create_backup(self, include_secrets: bool | None = None, reason: str = "manual") -> dict[str, Any]:
        include = self.settings["backup"].get("include_secrets", False) if include_secrets is None else bool(include_secrets)
        if include and not secret_backups_allowed():
            if include_secrets is True and reason == "manual":
                raise HTTPException(status_code=403, detail="Secret backups require ALLOW_SECRET_BACKUPS=true.")
            include = False
        if not re.fullmatch(r"[A-Za-z0-9_-]+", reason):
            raise HTTPException(status_code=400, detail="Invalid backup reason.")
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{reason}_{uuid.uuid4().hex[:8]}.zip"
        path = self.backup_dir / filename
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".partial")
        temporary_owned = False
        try:
            # Exclusive private creation: no partially written downloadable zip.
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            temporary_owned = True
            os.close(descriptor)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                manifest = {"created_at": _iso(), "include_secrets": include, "reason": reason, "version": 2}
                omitted: list[str] = []
                for source in self._backup_sources(include):
                    if source.is_symlink() or not source.is_file():
                        raise ValueError(f"Unsafe backup source: {source.name}")
                    if not include and source.suffix == ".json":
                        try:
                            value = json.loads(source.read_text(encoding="utf-8"))
                        except (ValueError, UnicodeError):
                            if reason != "pre_restore":
                                raise
                            # Never copy malformed JSON verbatim: it can still
                            # contain credentials that cannot be safely parsed.
                            omitted.append(source.name)
                            continue
                        archive.writestr(source.name, json.dumps(sanitize_secrets(value), ensure_ascii=False, indent=2))
                    else:
                        archive.write(source, arcname=source.name)
                if omitted:
                    manifest["omitted_files"] = omitted
                    manifest["omission_reason"] = "invalid JSON"
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            # Atomic publication without replacing an existing archive, even
            # when a generated name collides with another process's output.
            os.link(temporary, path)
            temporary.unlink()
        except Exception:
            if temporary_owned:
                temporary.unlink(missing_ok=True)
            raise
        self._trim_backups()
        self.audit("backup_created", f"name={filename}; secrets={include}")
        result = self._backup_meta(path)
        if omitted:
            result.update(omitted_files=omitted, omission_reason="invalid JSON")
        return result

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
            if path.resolve() in _PROTECTED_BACKUPS:
                continue
            with suppress(OSError):
                path.unlink()

    def backup_path(self, name: str) -> Path:
        if not re.fullmatch(r"backup_[A-Za-z0-9_.-]+\.zip", name):
            raise HTTPException(status_code=400, detail="잘못된 백업 이름입니다.")
        path = (self.backup_dir / name).resolve()
        if self.backup_dir.resolve() not in path.parents or not path.exists():
            raise HTTPException(status_code=404, detail="백업을 찾을 수 없습니다.")
        return path

    def restore_backup(self, name: str, *, acknowledgement: str = "") -> dict[str, Any]:
        with _BACKUP_LOCK:
            path = self.backup_path(name)
            _PROTECTED_BACKUPS.add(path)
            completed = False
            try:
                result = self._restore_backup(name, acknowledgement=acknowledgement)
                completed = True
                return result
            finally:
                _PROTECTED_BACKUPS.discard(path)
                if completed:
                    self._trim_backups()

    def _restore_backup(self, name: str, *, acknowledgement: str = "") -> dict[str, Any]:
        """Validate and stage all content before backup retention or live writes.

        Each replacement is atomic; a failed commit/runtime reload rolls back
        every changed file. The staged source survives pre-restore retention.
        """
        from lar_app.config_validation import normalize_config_update

        path = self.backup_path(name)
        allowed = {"config.json", "channels.json", "operations_v2.json", "cookie.json", "ycookie.txt", "login.json", "telegram.json"}
        staged: dict[str, bytes] = {}
        originals: dict[str, bytes | None] = {}
        config = None
        settings = self.settings
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > len(allowed) + 1 or sum(info.file_size for info in infos) > 32 * 1024 * 1024:
                    raise ValueError("Backup is too large.")
                seen: set[str] = set()
                for info in infos:
                    base = info.filename
                    if base not in allowed | {"manifest.json"} or base in seen or info.is_dir():
                        raise ValueError("Backup contains unexpected or duplicate paths.")
                    if stat.S_ISLNK(info.external_attr >> 16):
                        raise ValueError("Backup contains a symbolic link.")
                    seen.add(base)
                    raw = archive.read(info)  # Verify CRC of every member before any writes.
                    if base == "manifest.json":
                        if not isinstance(json.loads(raw), dict):
                            raise ValueError("Invalid backup manifest.")
                        continue
                    target = self.data_dir / base
                    if target.is_symlink() or (target.exists() and not target.is_file()):
                        raise ValueError("Restore destination is not a regular file.")
                    originals[base] = target.read_bytes() if target.exists() else None
                    if base.endswith(".json"):
                        value = json.loads(raw)
                        if base == "channels.json":
                            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                                raise ValueError("channels.json must contain a list of objects.")
                            ids = [str(item.get("id", "")).strip() for item in value]
                            if any(not identifier for identifier in ids) or len(ids) != len(set(ids)):
                                raise ValueError("Channels require unique, nonempty IDs.")
                        elif not isinstance(value, dict):
                            raise ValueError(f"{base} must contain an object.")
                        empty = [] if base == "channels.json" else {}
                        try:
                            old = json.loads(originals[base]) if originals[base] is not None else empty
                        except (ValueError, UnicodeError):
                            old = empty
                        if not isinstance(old, type(empty)):
                            old = empty
                        value = preserve_existing_secrets(value, old)
                        if base == "config.json":
                            current = dict(getattr(self.app.state, "config", {}) or {})
                            current.update(old)
                            value = normalize_config_update(current, value, acknowledgement=acknowledgement)
                            config = value
                        if base == "operations_v2.json":
                            _validate_settings(value, DEFAULT_SETTINGS)
                            settings = _deep_merge(DEFAULT_SETTINGS, value)
                        raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
                    else:
                        raw.decode("utf-8")
                    staged[base] = raw
            if not staged:
                raise ValueError("Backup contains no restorable files.")
        except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid backup: {exc}") from exc

        # Stage on the destination filesystem before creation can trim source.
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=self.data_dir) as directory:
            stage_dir = Path(directory)
            for base, raw in staged.items():
                (stage_dir / base).write_bytes(raw)
                os.chmod(stage_dir / base, 0o600)
            pre = self.create_backup(include_secrets=secret_backups_allowed(), reason="pre_restore")
            changed: list[str] = []
            old_config = getattr(self.app.state, "config", None)
            old_channels = list(getattr(self.app.state, "channels", []))
            old_settings = self.settings
            try:
                for base in staged:
                    os.replace(stage_dir / base, self.data_dir / base)
                    changed.append(base)
                if config is not None:
                    self.app.state.config = config
                if "channels.json" in staged:
                    channels = self.lar.loadChannels()
                    self.app.state.channels[:] = channels
                    self.lar.RecorderManager.setChannels(channels)
                self.settings = settings
            except Exception as exc:
                for base in reversed(changed):
                    original = originals[base]
                    if original is None:
                        (self.data_dir / base).unlink(missing_ok=True)
                    else:
                        rollback = stage_dir / base
                        rollback.write_bytes(original)
                        os.chmod(rollback, 0o600)
                        os.replace(rollback, self.data_dir / base)
                self.app.state.config = old_config
                self.app.state.channels[:] = old_channels
                self.settings = old_settings
                with suppress(Exception):
                    self.lar.RecorderManager.setChannels(old_channels)
                raise HTTPException(status_code=500, detail="Restore failed; original files restored.") from exc
        restored = list(staged)
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
        health["max_restart_attempts"] = max(0, min(int(health["max_restart_attempts"]), 20))
        backup = candidate["backup"]
        backup["keep"] = max(1, min(int(backup["keep"]), 100))
        backup["interval_hours"] = max(1, min(int(backup["interval_hours"]), 720))
        database = candidate["database"]
        database["keep"] = max(1, min(int(database["keep"]), 100))
        database["interval_hours"] = max(1, min(int(database["interval_hours"]), 720))
        maintenance = candidate["maintenance"]
        maintenance["cookie_check_hours"] = max(1, min(int(maintenance["cookie_check_hours"]), 168))
        maintenance["update_check_hours"] = max(1, min(int(maintenance["update_check_hours"]), 168))
        groups = candidate["recording_groups"]
        groups["quiet_seconds"] = max(30, min(int(groups["quiet_seconds"]), 7200))
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
