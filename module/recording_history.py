"""
recording_history.py — 녹화 세션 이력 관리

기존 JSONL 호환 로그를 유지하면서 SQLite 카탈로그에도 같은 이벤트를 기록한다.
"""
from __future__ import annotations
from module.log_setup import get_logger
logger = get_logger("recording_history")

import json
import os
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional

base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_PATH = os.path.join(base_directory, "json", "recording_history.jsonl")

_lock = threading.Lock()
_MAX_ENTRIES = 500  # 레거시 JSONL은 최근 상태 호환용으로만 유지


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _trim_file():
    try:
        if not os.path.exists(HISTORY_PATH):
            return
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _MAX_ENTRIES:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-_MAX_ENTRIES:])
    except Exception:
        pass


def _mirror_event(entry: dict) -> None:
    try:
        from module.recording_catalog import record_event
        record_event(entry)
    except Exception as exc:
        logger.warning(f"recording catalog write failed: {exc}")

    try:
        from module.operations_platform_v3 import emit_runtime_event
        event_map = {
            "recording_started": "recording.started",
            "recording_stopped": "recording.completed",
            "recording_failed": "recording.failed",
            "postprocess_failed": "postprocess.failed",
        }
        mapped = event_map.get(str(entry.get("event") or ""))
        if mapped:
            emit_runtime_event(mapped, entry)
    except Exception:
        pass

    if entry.get("event") == "recording_stopped":
        try:
            from module.recording_verify import queue_validation
            queue_validation(str(entry.get("channel_id") or ""), str(entry.get("filename") or ""))
        except Exception as exc:
            logger.warning(f"recording validation queue failed: {exc}")


def _trace_fields(channel_id: str, event: str) -> dict:
    try:
        from module.recording_trace import trace_fields
        return trace_fields(
            channel_id,
            include_tail=event in {"recording_failed", "recording_stop_requested"},
        )
    except Exception:
        return {}


def log_event(
    channel_id: str,
    channel_name: str,
    platform: str,
    event: str,
    *,
    filename: str = "",
    duration: str = "",
    error: str = "",
    extra: Optional[dict] = None,
):
    """Record one lifecycle event to the legacy JSONL and durable catalog."""
    entry = {
        "ts": _now_iso(),
        "epoch": time.time(),
        "channel_id": channel_id,
        "channel_name": channel_name,
        "platform": (platform or "").lower(),
        "event": event,
        "filename": os.path.basename(filename) if filename else "",
        "duration": duration,
        "error": error[:500] if error else "",
    }
    trace = _trace_fields(channel_id, event)
    if trace:
        entry.update(trace)
    if extra:
        entry.update(extra)
    if filename and not entry.get("file_path"):
        entry["file_path"] = str(filename)

    with _lock:
        try:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            with open(HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"recording_history write failed: {e}")

    _mirror_event(entry)

    try:
        with _lock:
            if os.path.exists(HISTORY_PATH) and os.path.getsize(HISTORY_PATH) > 200_000:
                _trim_file()
    except Exception:
        pass


def get_history(
    limit: int = 50,
    channel_id: Optional[str] = None,
    event: Optional[str] = None,
) -> List[Dict]:
    # SQLite is the primary read source. Import an existing legacy JSONL once
    # when the catalog is still empty, then keep JSONL only as a compatibility
    # mirror for older deployments/tools.
    try:
        from module.recording_catalog import list_events, migrate_jsonl
        migrate_jsonl(HISTORY_PATH)
        return list_events(
            limit=limit,
            channel_id=channel_id or "",
            event=event or "",
        )
    except Exception as exc:
        logger.warning(f"recording catalog read failed; falling back to JSONL: {exc}")

    entries: List[Dict] = []
    with _lock:
        try:
            if not os.path.exists(HISTORY_PATH):
                return []
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if channel_id and obj.get("channel_id") != channel_id:
                        continue
                    if event and obj.get("event") != event:
                        continue
                    entries.append(obj)
        except Exception as e:
            logger.warning(f"recording_history read failed: {e}")
            return []
    entries.sort(key=lambda x: x.get("epoch", 0), reverse=True)
    return entries[:limit]


def get_stats() -> Dict:
    entries = get_history(limit=9999)
    today = datetime.now().strftime("%Y-%m-%d")
    today_starts = sum(1 for e in entries if e.get("event") == "recording_started" and e.get("ts", "").startswith(today))
    today_fails = sum(1 for e in entries if e.get("event") == "recording_failed" and e.get("ts", "").startswith(today))
    return {"total_entries": len(entries), "today_recordings": today_starts, "today_failures": today_fails}
