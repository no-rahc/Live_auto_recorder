"""
cifs_watchdog.py — CIFS 마운트 상태 감시 워치독

/app/chzzk 마운트가 끊기면 notify()로 알림.
회복 시에도 회복 알림 전송.
"""
from __future__ import annotations

import asyncio
import os
import time

from module.log_setup import get_logger

logger = get_logger("cifs_watchdog")

MOUNT_POINT = "/app/chzzk"
CHECK_INTERVAL = 60  # 초
COOLDOWN = 600       # 알림 후 재알림까지 최소 간격 (초)

_task: asyncio.Task | None = None
_last_alert: float = 0.0
_was_down: bool = False


def _is_mounted() -> bool:
    """마운트 포인트가 접근 가능한지 확인."""
    try:
        # statfs가 성공하면 마운트 살아있음
        os.stat(MOUNT_POINT)
        # 실제 파일 접근 테스트 (CIFS 끊기면 stat은 되지만 readdir 실패)
        os.listdir(MOUNT_POINT)
        return True
    except OSError:
        return False


async def _watch_loop():
    global _last_alert, _was_down

    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        try:
            ok = await asyncio.to_thread(_is_mounted)
        except Exception:
            ok = False

        now = time.monotonic()

        if not ok and not _was_down:
            _was_down = True
            logger.error(f"CIFS 마운트 유실 감지: {MOUNT_POINT}")
            if now - _last_alert > COOLDOWN:
                _last_alert = now
                try:
                    from module.notifier import notify, COLOR_REC_ERROR
                    notify(
                        f"<b>⚠️ CIFS 마운트 유실</b><br>"
                        f"<code>{MOUNT_POINT}</code> 접근 불가.<br>"
                        f"녹화 파일 저장이 실패할 수 있습니다.",
                        title="Live Auto Recorder 마운트 경고",
                        color=COLOR_REC_ERROR,
                    )
                except Exception as e:
                    logger.warning(f"CIFS 알림 전송 실패: {e}")

        elif ok and _was_down:
            _was_down = False
            logger.info(f"CIFS 마운트 회복: {MOUNT_POINT}")
            try:
                from module.notifier import notify, COLOR_REC_STOP
                notify(
                    f"<b>✅ CIFS 마운트 회복</b><br>"
                    f"<code>{MOUNT_POINT}</code> 접근 정상.",
                    title="Live Auto Recorder 마운트 회복",
                    color=COLOR_REC_STOP,
                )
            except Exception as e:
                logger.warning(f"CIFS 회복 알림 실패: {e}")


def start_cifs_watchdog() -> asyncio.Task:
    global _task
    if _task and not _task.done():
        return _task
    _task = asyncio.create_task(_watch_loop())
    logger.info("CIFS watchdog started (interval=%ds)", CHECK_INTERVAL)
    return _task


async def stop_cifs_watchdog():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
    _task = None
    logger.info("CIFS watchdog stopped")
