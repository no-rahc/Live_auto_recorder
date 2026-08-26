"""Higher-level recorder operations: recovery, reconciliation, retention and metrics."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from module.operations_common import _bytes_human, _iso


class FeatureOpsMixin:
    def health_config(self, channel_id: str) -> dict[str, Any]:
        base = dict(self.settings.get("health", {}) or {})
        per_channel = base.pop("per_channel", {}) if isinstance(base.get("per_channel"), dict) else {}
        override = per_channel.get(str(channel_id), {}) if isinstance(per_channel, dict) else {}
        if isinstance(override, dict):
            base.update(override)
        return base

    def protected_paths(self) -> set[Path]:
        root = self.recording_root.resolve()
        result: set[Path] = set()
        for raw in self.settings.get("storage", {}).get("protected_files", []) or []:
            try:
                path = Path(str(raw)).expanduser()
                if not path.is_absolute():
                    path = root / path
                resolved = path.resolve()
                if resolved == root or root in resolved.parents:
                    result.add(resolved)
            except Exception:
                continue
        return result

    def set_file_protected(self, raw_path: str, protected: bool = True) -> dict[str, Any]:
        root = self.recording_root.resolve()
        path = Path(str(raw_path or "")).expanduser()
        if not path.is_absolute():
            path = root / path
        resolved = path.resolve()
        if resolved == root or root not in resolved.parents:
            raise HTTPException(status_code=400, detail="녹화 저장소 밖의 파일은 보호할 수 없습니다.")
        storage = self.settings.setdefault("storage", {})
        current = {str(item) for item in storage.get("protected_files", []) or []}
        rel = str(resolved.relative_to(root))
        if protected:
            current.add(rel)
        else:
            current.discard(rel)
        storage["protected_files"] = sorted(current)
        self.save_settings()
        self.audit("file_protection", f"path={rel}; protected={protected}")
        return {"path": rel, "protected": protected}

    def retention_excluded_paths(self) -> set[Path]:
        excluded = set(self.protected_paths())
        keep_recent = max(0, int(self.settings.get("storage", {}).get("keep_recent_per_channel", 0) or 0))
        retention_by_channel = self.settings.get("storage", {}).get("retention_days_by_channel", {}) or {}
        try:
            from module.recording_catalog import list_recordings
            items = list_recordings(limit=500).get("items", [])
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in items:
                grouped[str(item.get("channel_id") or "")].append(item)
            now = time.time()
            for channel_id, rows in grouped.items():
                for item in rows[:keep_recent] if keep_recent else []:
                    raw = str(item.get("file_path") or item.get("filename") or "")
                    if not raw:
                        continue
                    path = Path(raw)
                    if not path.is_absolute():
                        path = self.recording_root / path
                    try:
                        excluded.add(path.resolve())
                    except Exception:
                        pass
                channel_days = max(0, int(retention_by_channel.get(channel_id, 0) or 0)) if isinstance(retention_by_channel, dict) else 0
                if channel_days:
                    cutoff = now - channel_days * 86400
                    for item in rows:
                        started = float(item.get("started_epoch") or 0)
                        if not started or started < cutoff:
                            continue
                        raw = str(item.get("file_path") or item.get("filename") or "")
                        if not raw:
                            continue
                        path = Path(raw)
                        if not path.is_absolute():
                            path = self.recording_root / path
                        try:
                            excluded.add(path.resolve())
                        except Exception:
                            pass
        except Exception:
            pass
        return excluded

    def channel_schedule(self, channel_id: str) -> dict[str, Any]:
        rule = dict(self.settings.get("rules", {}).get(str(channel_id), {}) or {})
        return {
            "enabled": rule.get("enabled", True),
            "days": list(rule.get("days", []) or []),
            "time_start": str(rule.get("time_start") or ""),
            "time_end": str(rule.get("time_end") or ""),
            "start_delay_seconds": int(rule.get("start_delay_seconds", 0) or 0),
            "max_duration_minutes": int(rule.get("max_duration_minutes", 0) or 0),
        }

    def set_channel_schedule(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._channel(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        rules = self.settings.setdefault("rules", {})
        rule = dict(rules.get(channel_id, {}) or {})
        rule.update({
            "enabled": bool(payload.get("enabled", rule.get("enabled", True))),
            "days": [int(day) for day in (payload.get("days") or []) if 0 <= int(day) <= 6],
            "time_start": str(payload.get("time_start") or "")[:5],
            "time_end": str(payload.get("time_end") or "")[:5],
            "start_delay_seconds": max(0, min(int(payload.get("start_delay_seconds", 0) or 0), 3600)),
            "max_duration_minutes": max(0, min(int(payload.get("max_duration_minutes", 0) or 0), 10080)),
        })
        rules[channel_id] = rule
        self.save_settings()
        self.audit("schedule_updated", f"channel={channel_id}")
        return self.channel_schedule(channel_id)

    def channel_health_settings(self, channel_id: str) -> dict[str, Any]:
        if not self._channel(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        return self.health_config(channel_id)

    def set_channel_health_settings(self, channel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._channel(channel_id):
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        health = self.settings.setdefault("health", {})
        per_channel = health.setdefault("per_channel", {})
        allowed = {
            "stall_seconds", "stall_confirmations", "auto_restart", "max_restart_attempts",
            "restart_cooldown_seconds", "process_exit_grace_seconds", "missed_recording_seconds",
            "circuit_breaker_after", "circuit_breaker_seconds",
        }
        per_channel[channel_id] = {key: value for key, value in payload.items() if key in allowed}
        self.save_settings()
        self.audit("channel_health_updated", f"channel={channel_id}")
        return self.health_config(channel_id)

    def storage_runway(self) -> dict[str, Any]:
        info = self.storage_info()
        free = int(info.get("free", 0) or 0)
        now = time.time()
        files = [item for item in self._recording_files() if now - float(item.get("mtime", 0) or 0) <= 7 * 86400]
        if not files:
            return {"bytes_per_hour": 0, "bytes_per_hour_text": "0 B/h", "hours_remaining": None, "detail": "최근 7일 녹화량이 없습니다."}
        oldest = min(float(item["mtime"]) for item in files)
        span_hours = max(1.0, (now - oldest) / 3600)
        rate = int(sum(int(item.get("size", 0) or 0) for item in files) / span_hours)
        hours = round(free / rate, 1) if rate > 0 else None
        return {
            "bytes_per_hour": rate,
            "bytes_per_hour_text": f"{_bytes_human(rate)}/h",
            "hours_remaining": hours,
            "estimated_until": _iso(now + hours * 3600) if hours is not None else "",
        }

    def channel_metrics(self, days: int = 30) -> dict[str, Any]:
        days = max(1, min(int(days), 3650))
        cutoff = time.time() - days * 86400
        try:
            from module.recording_catalog import _LOCK, _connect, init_catalog
            init_catalog()
            with _LOCK, _connect() as conn:
                rows = conn.execute(
                    """SELECT channel_id, MAX(channel_name) AS channel_name,
                              COUNT(*) AS sessions,
                              SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                              SUM(reconnects) AS reconnects,
                              AVG(CASE WHEN ended_epoch>started_epoch THEN ended_epoch-started_epoch END) AS avg_duration
                         FROM recordings WHERE started_epoch>=? GROUP BY channel_id ORDER BY sessions DESC""",
                    (cutoff,),
                ).fetchall()
            items = [dict(row) for row in rows]
        except Exception:
            items = []
        for item in items:
            sessions = int(item.get("sessions") or 0)
            completed = int(item.get("completed") or 0)
            item["success_rate"] = round(completed * 100 / sessions, 1) if sessions else 0.0
            item["avg_duration_seconds"] = round(float(item.get("avg_duration") or 0), 1)
            item.pop("avg_duration", None)
        return {"days": days, "items": items}

    def channel_trace(self, channel_id: str) -> dict[str, Any]:
        from module.recording_trace import trace_fields
        return trace_fields(channel_id, include_tail=True)

    async def reconcile_startup(self) -> dict[str, Any]:
        rm = self.lar.recorder_manager
        fixed: list[str] = []
        channels = list(getattr(self.app.state, "channels", []) or [])
        for channel in channels:
            cid = str(channel.get("id") or "")
            if not cid:
                continue
            proc = rm.get_tasks_process(cid)
            alive = bool(proc is not None and getattr(proc, "returncode", None) is None)
            recording = bool(rm.get_status_recording(cid))
            if recording and not alive:
                rm.set_status_recording(cid, False)
                rm.clear_tasks_process(cid)
                with __import__("contextlib").suppress(Exception):
                    rm.recording_remove_start_time(cid)
                fixed.append(cid)
                self.audit("startup_reconcile", f"channel={cid}; cleared stale recording state", "recovered")
        return {"fixed_channels": fixed, "count": len(fixed)}

    async def manual_recover(self, channel_id: str, action: str = "restart") -> dict[str, Any]:
        channel = self._channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="채널을 찾을 수 없습니다.")
        action = str(action or "restart").lower()
        fsm = self.app.state.fsm
        rm = self.lar.recorder_manager
        if action == "sync":
            proc = rm.get_tasks_process(channel_id)
            alive = bool(proc is not None and getattr(proc, "returncode", None) is None)
            if alive:
                fsm._setRecording(channel_id)
            elif rm.get_status_recording(channel_id):
                rm.set_status_recording(channel_id, False)
                fsm._setWatching(channel_id)
            self.audit("manual_recovery_sync", f"channel={channel_id}; alive={alive}")
            return {"action": action, "alive": alive, "state": fsm.getState(channel_id)}
        if action == "verify":
            from module.recording_catalog import find_latest_recording
            from module.recording_verify import verify_recording
            row = find_latest_recording(channel_id)
            if not row:
                raise HTTPException(status_code=404, detail="검증할 녹화 기록이 없습니다.")
            return {"action": action, "result": verify_recording(int(row["id"]), attempt_repair=True)}
        if action == "recheck":
            rm.set_is_user_stopped(channel_id, False)
            await fsm.userStart(channel_id, is_user_request=True)
            self.audit("manual_recovery_recheck", f"channel={channel_id}")
            return {"action": action, "state": fsm.getState(channel_id)}
        if action != "restart":
            raise HTTPException(status_code=400, detail="지원하지 않는 복구 동작입니다.")
        if not channel.get("record_enabled", True):
            raise HTTPException(status_code=409, detail="이 채널은 녹화가 비활성화되어 있습니다.")
        await fsm.stop(channel_id, reason="manual_recovery")
        await asyncio.sleep(0)
        rm.set_is_user_stopped(channel_id, False)
        await fsm.userStart(channel_id, is_user_request=True)
        self.audit("manual_recovery_restart", f"channel={channel_id}")
        return {"action": action, "state": fsm.getState(channel_id)}

    def recovery_strategy(self, channel_id: str, reason: str, attempts: int) -> dict[str, Any]:
        cfg = self.health_config(channel_id)
        breaker_after = max(1, int(cfg.get("circuit_breaker_after", 5) or 5))
        breaker_seconds = max(30, int(cfg.get("circuit_breaker_seconds", 300) or 300))
        if attempts >= breaker_after:
            return {"action": "circuit_breaker", "delay_seconds": breaker_seconds}
        if reason in {"failed", "fsm_error", "missed"}:
            return {"action": "restart", "delay_seconds": int(cfg.get("restart_cooldown_seconds", 60) or 60)}
        if reason == "stalled":
            return {"action": "restart", "delay_seconds": max(10, int(cfg.get("restart_cooldown_seconds", 60) or 60))}
        return {"action": "recheck", "delay_seconds": 10}
