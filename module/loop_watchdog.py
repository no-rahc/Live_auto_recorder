from __future__ import annotations
from module.log_setup import get_logger
logger = get_logger("loop_watchdog")
import asyncio
import contextlib
import time
from typing import Optional, Callable, Awaitable

from module.data_manager import RecorderManager

# 헬스체크 콜백(probe) 주입 True=OK / False=이상.
ProbeFn = Callable[[], Awaitable[bool]]

# 타입: 외부에서 넘겨주는 콜백들
StartFn = Callable[..., Awaitable[None]]   
StopFn  = Callable[[str], Awaitable[None]] 

_watchdog_task: Optional[asyncio.Task] = None



async def heartbeatLoop(channel_id: str, get_proc: Callable[[], Optional[asyncio.subprocess.Process]], interval: float = 5.0,
                          probe: Optional[ProbeFn] = None,rm: Optional[RecorderManager] = None,) -> None:

    rm = rm or RecorderManager()
    while True:
        proc = get_proc()
        if proc is None or proc.returncode is not None:
            break

        # 1) 하트비트 기록
        rm.watchdog_beat(channel_id)

        # 2) 선택: 추가 헬스 프로브 수행
        if probe is not None:
            try:
                ok = await probe()
                if not ok:
                    pass
            except Exception:
                # 프로브 자체 실패는 하트비트를 막지 않음
                pass

        await asyncio.sleep(interval)


def spawnHeartbeat(channel_id: str, get_proc: Callable[[], Optional[asyncio.subprocess.Process]], interval: float = 5.0,
                    probe: Optional[ProbeFn] = None, rm: Optional[RecorderManager] = None,) -> asyncio.Task:

    return asyncio.create_task(
        heartbeatLoop(channel_id, get_proc, interval=interval, probe=probe, rm=rm)
    )


# 안전취소 헬퍼
async def cancelTaskSafely(task: Optional[asyncio.Task]) -> None:
    if not task:
        return
    try:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    except Exception:
        pass


async def watchdogLoop(get_channels, start_recording_for_channel, stop_recording_for_channel,
                       interval_sec: int = 35, beat_timeout_sec: int = 120,):
    
    rm = RecorderManager()

    while True:
        started = time.monotonic()
        try:
            channels = get_channels() or []
            now = time.monotonic()

            for ch in channels:
                cid = ch.get("id") or ""
                if not cid: 
                    continue
                rec = bool(rm.get_status_recording(cid) or rm.get_status_reserved(cid))
                proc = rm.get_tasks_process(cid)
                last = rm.watchdog_get_last_beat(cid)
                unhealthy = False

                # Recorder worker ownership lives in ChannelFsm. This legacy
                # watchdog only needs to validate the externally observable
                # recorder process/heartbeat, not keep a duplicate task registry.
                if rm.get_status_recording(cid) and (not proc or proc.returncode is not None):
                    unhealthy = True
                if rec and last and (now - last) > beat_timeout_sec:
                    unhealthy = True

                if not unhealthy:
                    continue

                with contextlib.suppress(Exception):
                    await stop_recording_for_channel(cid)

                attempts = rm.watchdog_increase_backoff(cid)  # 기존 카운터 활용
                delay = min(600, 10 * attempts * attempts)
                until = time.monotonic() + delay
                while time.monotonic() < until:
                    await asyncio.sleep(1)

                with contextlib.suppress(Exception):
                    await start_recording_for_channel(cid)

        except Exception as e:
            logger.warning(f"watchdogLoop: {e}")

        elapsed = time.monotonic() - started
        if elapsed < interval_sec:
            await asyncio.sleep(interval_sec - elapsed)



def startWatchdog(get_channels: Callable[[], list], start_recording_for_channel: StartFn, stop_recording_for_channel: StopFn,
                  interval_sec: int = 35, beat_timeout_sec: int = 120,) -> asyncio.Task:

    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        return _watchdog_task
    _watchdog_task = asyncio.create_task(
        watchdogLoop(get_channels, start_recording_for_channel, stop_recording_for_channel,
                      interval_sec=interval_sec, beat_timeout_sec=beat_timeout_sec)
    )
    logger.info("started")
    return _watchdog_task


async def stopWatchdog():
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
        with contextlib.suppress(Exception):
            await _watchdog_task
    _watchdog_task = None
    logger.info("stopped")
