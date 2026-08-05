"""
recording_history.py — 녹화 세션 이력 관리

JSONL 파일에 녹화 시작/종료/실패 이벤트를 기록하고,
최근 N건 조회 API를 제공한다.
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
_MAX_ENTRIES = 500  # 파일 최대 유지 라인 수


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _trim_file():
    """파일이 너무 커지면 오래된 항목 제거."""
    try:
        if not os.path.exists(HISTORY_PATH):
            return
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _MAX_ENTRIES:
            keep = lines[-_MAX_ENTRIES:]
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                f.writelines(keep)
    except Exception:
        pass


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
    """
    녹화 이벤트 기록.

    event 종류:
      - "recording_started"  : 녹화 시작
      - "recording_stopped"  : 녹화 정상 종료 (방종/사용자 중지)
      - "recording_failed"   : 녹화 실패/에러
      - "postprocess_done"   : 후처리 완료
      - "postprocess_failed" : 후처리 실패
    """
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
    if extra:
        entry.update(extra)

    with _lock:
        try:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            with open(HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"recording_history write failed: {e}")

    # 주기적으로 트리밍 (10회 기록마다)
    try:
        with _lock:
            if os.path.exists(HISTORY_PATH):
                size = os.path.getsize(HISTORY_PATH)
                if size > 200_000:  # ~200KB
                    _trim_file()
    except Exception:
        pass


def get_history(
    limit: int = 50,
    channel_id: Optional[str] = None,
    event: Optional[str] = None,
) -> List[Dict]:
    """
    최근 녹화 이력 조회 (최신순).

    Args:
        limit: 반환 최대 건수
        channel_id: 채널 필터 (None = 전체)
        event: 이벤트 타입 필터 (None = 전체)
    """
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

    # 최신순 정렬 후 limit
    entries.sort(key=lambda x: x.get("epoch", 0), reverse=True)
    return entries[:limit]


def get_stats() -> Dict:
    """간단한 통계: 오늘 녹화 횟수, 총 이력 수."""
    entries = get_history(limit=9999)
    today = datetime.now().strftime("%Y-%m-%d")
    today_starts = sum(
        1 for e in entries
        if e.get("event") == "recording_started"
        and e.get("ts", "").startswith(today)
    )
    today_fails = sum(
        1 for e in entries
        if e.get("event") == "recording_failed"
        and e.get("ts", "").startswith(today)
    )
    return {
        "total_entries": len(entries),
        "today_recordings": today_starts,
        "today_failures": today_fails,
    }
