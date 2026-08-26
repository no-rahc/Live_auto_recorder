from module.log_setup import get_logger
logger = get_logger("channel_fsm")
import asyncio
import os
import signal
import random
import subprocess
import contextlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from module.data_manager import RecorderManager, loadConfig
from module.recording_adapter import startSession
from module.recording_session import SessionOutcome

try:
    from module.common_errors import NotLiveError
except Exception:  # 폴백
    class NotLiveError(Exception):
        pass


@dataclass(slots=True)
class ChannelRuntime:
    state: str = "STOPPED"
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    watch_task: Optional[asyncio.Task[Any]] = None
    respawn_task: Optional[asyncio.Task[Any]] = None
    stop_requested: bool = True
    last_outcome: Optional[SessionOutcome] = None
    retry_attempts: int = 0


class ChannelFsm:
    def __init__(self):
        self.rm = RecorderManager()
        self.runtimes: Dict[str, ChannelRuntime] = {}

    def _runtime(self, cid: str) -> ChannelRuntime:
        runtime = self.runtimes.get(cid)
        if runtime is None:
            runtime = ChannelRuntime()
            self.runtimes[cid] = runtime
        return runtime

    @property
    def respawnTask(self) -> Dict[str, asyncio.Task[Any]]:
        """Compatibility view for diagnostics/tests while runtime ownership stays per channel."""
        return {cid: rt.respawn_task for cid, rt in self.runtimes.items() if rt.respawn_task is not None}

    # 공용 API
    def getState(self, channelId: str) -> str:
        runtime = self.runtimes.get(channelId)
        return runtime.state if runtime is not None else "STOPPED"

    def isStopRequested(self, channelId: str) -> bool:
        runtime = self.runtimes.get(channelId)
        return runtime.stop_requested if runtime is not None else True

    # 실제 녹화 프로세스 생존 확인 유틸
    def _procAlive(self, cid: str) -> bool:
        proc = self.rm.get_tasks_process(cid)
        return bool(proc and proc.returncode is None)  # None이면 아직 종료되지 않음

    async def userStart(self, channelId: str, is_user_request: bool = False):
        async with self._lock(channelId):
            ch = self._findChannel(channelId)
            if not ch:
                self._setStopped(channelId)
                return

            # 자동/대량 시작은 record_enabled 필요, 수동은 1회 시작 허용
            if (not ch.get("record_enabled", True)) and (not is_user_request):
                self._setStopped(channelId)
                return

            # 1) 이미 실제 녹화 프로세스가 살아있으면: 상태만 동기화
            if self.rm.get_status_recording(channelId) or self._procAlive(channelId):
                self._setRecording(channelId)
                return

            # 2) 아이돔포턴트 가드
            if not self.rm.guard_try_acquire_start(channelId):
                return
            try:
                cur = self.getState(channelId)

                if cur == "RECORDING":
                    return

                if cur == "WATCHING":
                    wt = self._runtime(channelId).watch_task
                    if wt and not wt.done():
                        return
                    self._setWatching(channelId)
                    self._spawnWatch(channelId, is_user_request=is_user_request)
                    return

                self._setWatching(channelId)
                self._spawnWatch(channelId, is_user_request=is_user_request)
            finally:
                self.rm.guard_release_start(channelId)

    def _recordStopReason(self, channelId: str, reason: str, channel: Optional[dict] = None) -> None:
        ch = channel or self._findChannel(channelId)
        was_active = bool(
            self.rm.get_status_recording(channelId)
            or self.rm.get_status_reserved(channelId)
            or self._procAlive(channelId)
            or self.getState(channelId) != "STOPPED"
        )
        if not was_active:
            return
        try:
            from module.recording_catalog import set_active_stop_reason
            set_active_stop_reason(channelId, reason)
        except Exception as exc:
            logger.warning(f"stop reason catalog write failed: {exc}")
        try:
            from module.recording_history import log_event
            log_event(
                channelId,
                str((ch or {}).get("name") or channelId),
                str((ch or {}).get("platform") or ""),
                "recording_stop_requested",
                extra={"reason": str(reason)[:80]},
            )
        except Exception as exc:
            logger.warning(f"stop reason history write failed: {exc}")

    async def stop(self, channelId: str, reason: str = "user"):
        """Stop a channel while preserving the control reason for history and diagnostics."""
        async with self._lock(channelId):
            self._runtime(channelId).stop_requested = True
            ch = self._findChannel(channelId)
            self._recordStopReason(channelId, reason, ch)

            # 1) 루프가 즉시 감지할 수 있도록 먼저 STOP 플래그
            self.rm.set_is_user_stopped(channelId, True)
            self.rm.set_status_reserved(channelId, False)

            # 2) 워커/프로세스 정지
            await self._stopAllWorkers(channelId)

            # 3) 상태 마킹
            self._setStopped(channelId)
            logger.info(f"channel stopped: channel={channelId}; reason={reason}")

    async def userStop(self, channelId: str):
        await self.stop(channelId, reason="user")

    async def startAllWatching(self):
        tasks = []
        for ch in (self.rm.getChannels() or []):
            if ch.get("record_enabled", True):
                tasks.append(asyncio.create_task(self.userStart(ch.get("id"))))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stopAll(self):
        for ch in (self.rm.getChannels() or []):
            await self.stop(ch.get("id"), reason="shutdown")

    async def _killProcessTree(self, cid: str, timeout: float = 3.0):
        proc = self.rm.get_tasks_process(cid)
        if not proc or proc.returncode is not None:
            return

        try:
            if os.name == "nt":
                # 1차: CTRL_BREAK (CREATE_NEW_PROCESS_GROUP 필요)
                with contextlib.suppress(Exception):
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                    await asyncio.wait_for(proc.wait(), timeout=2.0)

                # 2차: 트리 강제 종료
                if proc.returncode is None:
                    with contextlib.suppress(Exception):
                        subprocess.run(
                            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                            check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(proc.wait(), timeout=2.0)

                # 3차: 최종 강제
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()

            else:
                # POSIX: 세션/그룹 단위 종료
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.terminate()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(proc.wait(), timeout=timeout)

                if proc.returncode is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception:
                        proc.kill()
                    await proc.wait()
        finally:
            # 프로세스 핸들 정리
            with contextlib.suppress(Exception):
                self.rm.clear_tasks_process(cid)

    # WEB/Worker에서 상태 전환 반응성 상승
    async def onRecordEnabledChanged(self, channelId, enabled: bool):
        async with self._lock(channelId):
            cur = self.getState(channelId)

            if enabled:
                if cur == "STOPPED":
                    self._setWatching(channelId)
                    self._spawnWatch(channelId)
                return

            # 녹화 중이면 현재 회차는 녹화유지
            if self.rm.get_status_recording(channelId) or self._procAlive(channelId):
                self.rm.set_status_reserved(channelId, False)
                return

            # 녹화 중이 아니면 감시/워커만 정리
            await self._stopAllWorkers(channelId)
            self._setStopped(channelId)

    # 내부 유틸
    def _lock(self, cid: str) -> asyncio.Lock:
        return self._runtime(cid).lock

    def _findChannel(self, cid: str) -> Optional[dict]:
        return next((c for c in (self.rm.getChannels() or []) if c.get("id") == cid), None)

    def _setStopped(self, cid: str):
        runtime = self._runtime(cid)
        runtime.state = "STOPPED"
        runtime.stop_requested = True
        self.rm.set_status_reserved(cid, False)
        self.rm.set_status_recording(cid, False)
        self.rm.set_is_user_stopped(cid, True)

    def _setWatching(self, cid: str):
        runtime = self._runtime(cid)
        runtime.state = "WATCHING"
        runtime.stop_requested = False
        self.rm.set_is_user_stopped(cid, False)
        self.rm.set_status_reserved(cid, True)
        self.rm.set_status_recording(cid, False)

    def _setRecording(self, cid: str):
        runtime = self._runtime(cid)
        runtime.state = "RECORDING"
        runtime.stop_requested = False
        self.rm.set_status_reserved(cid, False)
        self.rm.set_status_recording(cid, True)
        self.rm.set_is_user_stopped(cid, False)

    async def _stopAllWorkers(self, cid: str):
        runtime = self._runtime(cid)
        respawn_task, runtime.respawn_task = runtime.respawn_task, None
        watch_task, runtime.watch_task = runtime.watch_task, None
        await self._cancelTask(respawn_task)
        await self._cancelTask(watch_task)
        await self._killProcessTree(cid)

    async def _cancelTask(self, task: Optional[asyncio.Task]):
        if not task:
            return
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _sleepWithJitter(self, base_seconds: int):
        jitter = random.uniform(0.85, 1.15)
        await asyncio.sleep(max(5, int(base_seconds * jitter)))

    def _scheduleRespawn(self, cid: str, base_seconds: int):
        runtime = self._runtime(cid)
        existing = runtime.respawn_task
        if existing and not existing.done():
            return

        async def _respawn():
            try:
                await self._sleepWithJitter(base_seconds)
                ch = self._findChannel(cid)
                if ch and ch.get("record_enabled", True) and not runtime.stop_requested:
                    self._spawnWatch(cid)
            finally:
                if runtime.respawn_task is asyncio.current_task():
                    runtime.respawn_task = None

        runtime.respawn_task = asyncio.create_task(_respawn())

    # Watch Loop
    def _spawnWatch(self, cid: str, is_user_request: bool = False):
        runtime = self._runtime(cid)
        if runtime.watch_task and not runtime.watch_task.done():
            return

        async def _run():
            outcome = None
            ch = self._findChannel(cid)
            if not ch:
                self._setStopped(cid)
                return

            if runtime.stop_requested:
                self._setStopped(cid)
                return

            if (not ch.get("record_enabled", True)) and (not is_user_request):
                self._setStopped(cid)
                return

            self._setWatching(cid)

            try:
                cfg = loadConfig() or {}
                outcome = await startSession(
                    ch,
                    (ch.get("platform") or "").lower(),
                    cfg,
                    is_user_request=is_user_request,
                )
                runtime.last_outcome = outcome
                if outcome == SessionOutcome.RETRYABLE_ERROR:
                    runtime.retry_attempts += 1
                else:
                    runtime.retry_attempts = 0

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.info(f"[ERROR] watch task crashed for {cid}: {e}")
                self._setWatching(cid)

            finally:
                ch2 = self._findChannel(cid)
                unsupported = outcome == SessionOutcome.UNSUPPORTED
                if unsupported:
                    logger.error(f"unsupported recording platform: channel={cid}; platform={(ch or {}).get('platform')}")
                terminal = outcome in {
                    SessionOutcome.USER_STOPPED,
                    SessionOutcome.DISABLED,
                    SessionOutcome.FATAL_ERROR,
                    SessionOutcome.UNSUPPORTED,
                }
                if terminal or not ch2 or not ch2.get("record_enabled", True) or runtime.stop_requested:
                    self._setStopped(cid)

                else:
                    self._setWatching(cid)

                    try:
                        cfg = loadConfig() or {}
                        recheck = max(5, int(cfg.get("recheckInterval", 60)))
                    except Exception:
                        recheck = 60

                    if outcome == SessionOutcome.RETRYABLE_ERROR:
                        base = min(300, max(5, 5 * (2 ** max(0, runtime.retry_attempts - 1))))
                    elif outcome == SessionOutcome.COMPLETED:
                        base = min(recheck, 10)
                    else:
                        base = recheck

                    self._scheduleRespawn(cid, base)

        runtime.watch_task = asyncio.create_task(_run())
