"""Recording health and post-processing job mixin."""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from module.operations_common import _bytes_human, _duration_seconds, _iso


class HealthJobsMixin:
    # --------------------------- health -------------------------------
    async def _monitor_loop(self) -> None:
        while True:
            try:
                await self.monitor_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.audit("monitor_error", str(exc), "error")
            interval = max(5, min(int(self.settings["health"].get("check_interval_seconds", 10)), 300))
            await asyncio.sleep(interval)

    async def monitor_once(self) -> None:
        storage = self.storage_info()
        level = str(storage.get("status", "error"))
        if level != self.last_storage_level:
            self.audit("storage_level", f"level={level}; free={storage.get('free_percent')}%")
            if level in {"warning", "critical"}:
                await self._notify(
                    "storage.warning",
                    f"녹화 저장소 여유 공간이 {storage.get('free_percent')}%입니다. ({level})",
                    {"status": level, "free_percent": storage.get("free_percent")},
                )
            self.last_storage_level = level
        if level == "critical" and self.settings["storage"].get("auto_cleanup"):
            with suppress(Exception):
                result = self.run_cleanup({"confirm": True, "mode": "free_space"})
                deleted = len(result.get("deleted", []))
                await self._notify(
                    "storage.cleaned",
                    f"저장소 자동 정리로 {deleted}개 파일을 삭제했습니다.",
                    {"deleted": deleted},
                )
        if level == "critical" and not self.storage_stopped:
            self.storage_stopped = True
        elif level != "critical" and self.storage_stopped:
            self.storage_stopped = False
            config = getattr(self.app.state, "config", {}) or {}
            if config.get("autoRecordingMode"):
                with suppress(Exception):
                    await self.app.state.fsm.startAllWatching()
                self.audit("storage_recovered", f"free={storage.get('free_percent')}%")

        channels = list(getattr(self.app.state, "channels", []) or [])
        active_ids = set()
        for channel in channels:
            channel_id = str(channel.get("id") or "")
            if not channel_id:
                continue
            active_ids.add(channel_id)
            await self._sample_channel(channel)
        for channel_id in list(self.health):
            if channel_id not in active_ids:
                self.health.pop(channel_id, None)
                self.samples.pop(channel_id, None)

    @staticmethod
    def _restart_detail(
        channel_id: str,
        attempt: int,
        reason: str,
        diagnostic: dict[str, Any],
        *,
        suffix: str = "",
    ) -> str:
        fields = [
            f"channel={channel_id}",
            f"attempt={attempt}",
            f"reason={reason}",
            f"exit={diagnostic.get('process_exit_code')}",
            f"file_size={diagnostic.get('file_size', 0)}",
            f"write_rate_bps={diagnostic.get('write_rate_bps', 0)}",
            f"growth_age={diagnostic.get('growth_age_seconds', 0)}s",
            f"write_age={diagnostic.get('write_age_seconds', 0)}s",
            f"stall_checks={diagnostic.get('stall_checks', 0)}",
            f"failed_checks={diagnostic.get('failed_checks', 0)}",
            f"last_write_at={diagnostic.get('last_write_at', '')}",
            f"fsm_state={diagnostic.get('fsm_state', '')}",
            f"filename={diagnostic.get('filename', '')}",
        ]
        if suffix:
            fields.append(suffix)
        return "; ".join(fields)

    def _restart_still_needed(
        self,
        channel_id: str,
        reason: str,
        diagnostic: dict[str, Any],
    ) -> tuple[bool, str]:
        """Revalidate a destructive health restart against live recorder state."""
        rm = self.lar.recorder_manager
        if reason == "fsm_error":
            fsm = getattr(self.app.state, "fsm", None)
            if fsm and fsm.getState(channel_id) == "ERROR":
                return True, "fsm remains in ERROR"
            return False, "fsm recovered"

        if not bool(rm.get_status_recording(channel_id)):
            return False, "recording flag cleared"

        proc = rm.get_tasks_process(channel_id)
        returncode = getattr(proc, "returncode", None) if proc is not None else None
        if reason == "failed":
            if proc is None:
                return False, "process handle cleared"
            if returncode is None:
                return False, "process recovered"
            if returncode == 0:
                return False, "process exited cleanly"
            return True, f"process still exited with code {returncode}"

        if reason == "stalled":
            if proc is None or returncode is not None:
                return False, "process state changed"
            path_raw = rm.get_recording_filename(channel_id) or ""
            if not path_raw:
                return False, "recording filename cleared"
            path = Path(path_raw)
            try:
                stat = path.stat()
            except OSError:
                return False, "recording file unavailable"
            previous_size = int(diagnostic.get("file_size", 0) or 0)
            previous_mtime = float(diagnostic.get("file_mtime", 0) or 0)
            if stat.st_size > previous_size:
                return False, "file size resumed"
            if previous_mtime and stat.st_mtime > previous_mtime:
                return False, "file write time resumed"
            return True, "file and process remain stalled"

        return False, f"unsupported restart reason {reason}"

    async def _sample_channel(self, channel: dict[str, Any]) -> None:
        channel_id = str(channel.get("id"))
        rm = self.lar.recorder_manager
        fsm = getattr(self.app.state, "fsm", None)
        fsm_state = fsm.getState(channel_id) if fsm else "STOPPED"
        recording = bool(rm.get_status_recording(channel_id))
        reserved = bool(rm.get_status_reserved(channel_id))
        proc = rm.get_tasks_process(channel_id)
        proc_returncode = getattr(proc, "returncode", None) if proc is not None else None
        path_raw = rm.get_recording_filename(channel_id) or ""
        path = Path(path_raw) if path_raw else None
        now = time.time()
        size = 0
        mtime = 0.0
        if path:
            with suppress(OSError):
                stat = path.stat()
                size, mtime = stat.st_size, stat.st_mtime

        previous = self.samples.get(channel_id, {})
        current_path = str(path or "")
        previous_path = str(previous.get("path") or "")
        path_changed = bool(previous_path and previous_path != current_path)
        previous_size = int(previous.get("size", size))
        previous_time = float(previous.get("sample_time", now))
        previous_mtime = float(previous.get("mtime", mtime) or 0.0)
        last_growth = float(previous.get("last_growth", now))
        proc_exit_seen_at = float(previous.get("proc_exit_seen_at", 0) or 0)
        previous_exit_code = previous.get("process_exit_code", proc_returncode if proc_exit_seen_at else None)
        failure_checks = int(previous.get("failure_checks", 0) or 0)
        stall_checks = int(previous.get("stall_checks", 0) or 0)

        if path_changed:
            # A restart normally creates a new unique output path. Never carry
            # the old file's stall clock or sample counters into that session.
            previous_size = size
            previous_time = now
            previous_mtime = mtime
            last_growth = now
            proc_exit_seen_at = 0.0
            failure_checks = 0
            stall_checks = 0
        elif size > previous_size or (mtime and mtime > previous_mtime):
            last_growth = now
            stall_checks = 0
        elapsed = max(0.001, now - previous_time)
        rate = max(0.0, (size - previous_size) / elapsed)
        growth_age = max(0.0, now - last_growth)
        write_age = max(0.0, now - mtime) if mtime else 0.0

        state = "waiting"
        label = "대기 중"
        error = ""
        health_cfg = self.settings["health"]
        restart_reason = ""
        start_ts = float(self.lar.RecorderManager.recording_start_time.get(channel_id, 0) or 0)
        startup_grace_seconds = max(0, min(int(health_cfg.get("startup_grace_seconds", 30)), 600))
        startup_grace_remaining = 0.0
        if recording and start_ts:
            startup_grace_remaining = max(0.0, startup_grace_seconds - (now - start_ts))
        failed_samples = max(1, min(int(health_cfg.get("failed_samples", 2) or 2), 10))

        if recording:
            if startup_grace_remaining > 0:
                proc_exit_seen_at = 0.0
                failure_checks = 0
                stall_checks = 0
                state, label = "recording", "녹화 시작 유예 중"
                error = f"startup grace {startup_grace_remaining:.0f}s"
            elif proc is not None and proc_returncode is not None:
                stall_checks = 0
                if previous_exit_code != proc_returncode or not proc_exit_seen_at:
                    proc_exit_seen_at = now
                    failure_checks = 0
                if proc_returncode == 0:
                    failure_checks = 0
                    state, label = "checking", "프로세스 종료 정리 중"
                    error = "exit=0; 정상 종료 후 recorder 상태 정리를 기다립니다."
                else:
                    grace = max(5, min(int(health_cfg.get("process_exit_grace_seconds", 20) or 20), 300))
                    exit_age = max(0.0, now - proc_exit_seen_at)
                    if exit_age >= grace:
                        failure_checks += 1
                        if failure_checks >= failed_samples:
                            state, label, error = "failed", "프로세스 종료", (
                                f"exit={proc_returncode}; grace={grace}s; "
                                f"checks={failure_checks}/{failed_samples}"
                            )
                            restart_reason = "failed"
                        else:
                            state, label = "checking", "프로세스 종료 재확인 중"
                            error = (
                                f"exit={proc_returncode}; grace={grace}s; "
                                f"checks={failure_checks}/{failed_samples}"
                            )
                    else:
                        failure_checks = 0
                        state, label = "checking", "프로세스 종료 확인 중"
                        error = f"exit={proc_returncode}; grace {exit_age:.0f}/{grace}s"
            elif proc is None:
                proc_exit_seen_at = 0.0
                failure_checks = 0
                stall_checks = 0
                state, label = "checking", "프로세스 확인 중"
                error = "recording 상태지만 프로세스 핸들이 없습니다. recorder 상태 정리를 기다립니다."
            else:
                proc_exit_seen_at = 0.0
                failure_checks = 0
                state, label = "recording", "녹화 중"
                stall_seconds = max(30, min(int(health_cfg.get("stall_seconds", 120) or 120), 3600))
                stall_confirmations = max(2, min(int(health_cfg.get("stall_confirmations", 3) or 3), 12))
                stalled_candidate = bool(
                    size
                    and mtime
                    and growth_age >= stall_seconds
                    and write_age >= stall_seconds
                )
                if stalled_candidate:
                    stall_checks += 1
                    if stall_checks >= stall_confirmations:
                        state, label = "stalled", "기록 멈춤"
                        error = (
                            f"파일 크기/mtime 무변화 {growth_age:.0f}s/"
                            f"{write_age:.0f}s; checks={stall_checks}/{stall_confirmations}"
                        )
                        restart_reason = "stalled"
                    else:
                        state, label = "checking", f"기록 지연 확인 {stall_checks}/{stall_confirmations}"
                        error = (
                            f"파일 크기/mtime 무변화 {growth_age:.0f}s/"
                            f"{write_age:.0f}s; 재확인 중"
                        )
                else:
                    stall_checks = 0
        elif fsm_state == "WATCHING" or reserved:
            proc_exit_seen_at = 0.0
            failure_checks = 0
            stall_checks = 0
            state, label = "checking", "라이브 확인 중"
        elif fsm_state == "ERROR":
            proc_exit_seen_at = 0.0
            stall_checks = 0
            failure_checks += 1
            health_reason = "녹화 상태가 ERROR입니다."
            if failure_checks >= failed_samples:
                state, label, error = "failed", "오류", f"{health_reason} checks={failure_checks}/{failed_samples}"
                restart_reason = "fsm_error"
            else:
                state, label, error = "checking", "오류 재확인 중", f"{health_reason} checks={failure_checks}/{failed_samples}"
        else:
            proc_exit_seen_at = 0.0
            failure_checks = 0
            stall_checks = 0

        self.samples[channel_id] = {
            "path": current_path,
            "size": size,
            "mtime": mtime,
            "sample_time": now,
            "last_growth": last_growth,
            "process_exit_code": proc_returncode,
            "proc_exit_seen_at": proc_exit_seen_at,
            "failure_checks": failure_checks,
            "stall_checks": stall_checks,
        }

        rule = self.settings.get("rules", {}).get(channel_id, {})
        max_minutes = int(rule.get("max_duration_minutes", 0) or 0)
        if recording and max_minutes and start_ts and now - start_ts >= max_minutes * 60:
            state, label = "stopping", "최대 시간 도달"
            restart_reason = ""
            with suppress(Exception):
                from module.recording_catalog import set_active_stop_reason
                set_active_stop_reason(channel_id, "max_duration")
            asyncio.create_task(self.lar.stopRecordingForChannel(self.app, channel_id))
            self.audit("max_duration_stop", f"channel={channel_id}; minutes={max_minutes}")

        allowed, rule_reason = self.evaluate_rule(channel)
        if not allowed and (recording or reserved or fsm_state == "WATCHING"):
            state, label, error = "blocked", "규칙 차단", rule_reason
            restart_reason = ""
            self.policy_blocked.add(channel_id)
            with suppress(Exception):
                if fsm and hasattr(fsm, "stop"):
                    await fsm.stop(channel_id, reason="rule")
                elif fsm:
                    await fsm.userStop(channel_id)
            self.audit("rule_enforced", f"channel={channel_id}; reason={rule_reason}", "blocked")
        elif allowed and channel_id in self.policy_blocked:
            self.policy_blocked.discard(channel_id)
            if channel.get("record_enabled", True):
                with suppress(Exception):
                    await self.app.state.fsm.userStart(channel_id)
                state, label = "checking", "규칙 해제 · 재확인"
                self.audit("rule_released", f"channel={channel_id}")

        current = self.health.get(channel_id, {})
        attempts = int(current.get("restart_attempts", 0))
        if state == "recording" and (rate > 0 or growth_age < 30):
            attempts = 0
        cooldown_until = float(current.get("cooldown_until", 0))
        last_restart = current.get("last_restart") if isinstance(current.get("last_restart"), dict) else {}

        if state in {"stalled", "failed"} and restart_reason and health_cfg.get("auto_restart"):
            max_attempts = int(health_cfg.get("max_restart_attempts", 3))
            if attempts < max_attempts and now >= cooldown_until:
                attempts += 1
                cooldown = max(10, int(health_cfg.get("restart_cooldown_seconds", 60)))
                cooldown_until = now + cooldown
                state, label = "reconnecting", f"재연결 {attempts}/{max_attempts}"
                diagnostic = {
                    "reason": restart_reason,
                    "process_exit_code": proc_returncode,
                    "file_size": size,
                    "file_mtime": mtime,
                    "last_write_at": _iso(mtime) if mtime else "",
                    "write_rate_bps": round(rate, 2),
                    "growth_age_seconds": round(growth_age, 1),
                    "write_age_seconds": round(write_age, 1),
                    "stall_checks": stall_checks,
                    "failed_checks": failure_checks,
                    "fsm_state": fsm_state,
                    "filename": str(path or ""),
                    "scheduled_at": _iso(now),
                }
                last_restart = diagnostic
                self.audit(
                    "health_restart_scheduled",
                    self._restart_detail(channel_id, attempts, restart_reason, diagnostic),
                    "warning",
                )
                asyncio.create_task(self._restart_channel(channel_id, attempts, restart_reason, diagnostic))

        self.health[channel_id] = {
            "channel_id": channel_id,
            "channel_name": channel.get("name") or channel_id,
            "platform": channel.get("platform") or "",
            "tool": "ytarchive" if str(channel.get("platform") or "").lower() == "youtube" else "Streamlink + FFmpeg",
            "state": state,
            "label": label,
            "recording": recording,
            "reserved": reserved,
            "fsm_state": fsm_state,
            "filename": str(path or ""),
            "file_size": size,
            "file_size_text": _bytes_human(size),
            "write_rate_bps": round(rate, 2),
            "write_rate_text": f"{_bytes_human(rate)}/s",
            "last_write_at": _iso(mtime) if mtime else "",
            "growth_age_seconds": round(growth_age, 1),
            "write_age_seconds": round(write_age, 1),
            "stall_checks": stall_checks,
            "failed_checks": failure_checks,
            "startup_grace_remaining": round(startup_grace_remaining, 2),
            "process_exit_code": proc_returncode,
            "process_exit_seen_at": _iso(proc_exit_seen_at) if proc_exit_seen_at else "",
            "restart_attempts": attempts,
            "cooldown_until": cooldown_until,
            "last_restart": last_restart,
            "last_error": error,
            "updated_at": _iso(),
        }

    async def _restart_channel(
        self,
        channel_id: str,
        attempt: int,
        reason: str = "unknown",
        diagnostic: dict[str, Any] | None = None,
    ) -> None:
        lock = self._restart_locks.setdefault(channel_id, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            snapshot = dict(diagnostic or {})
            try:
                # Give the recorder/FSM a short chance to settle naturally before
                # performing a destructive stop/start cycle, then revalidate the
                # exact condition that scheduled this restart.
                await asyncio.sleep(2)
                needed, recheck = self._restart_still_needed(channel_id, reason, snapshot)
                if not needed:
                    self.audit(
                        "health_restart_cancelled",
                        self._restart_detail(channel_id, attempt, reason, snapshot, suffix=f"recheck={recheck}"),
                        "recovered",
                    )
                    return

                fsm = self.app.state.fsm
                if hasattr(fsm, "stop"):
                    await fsm.stop(channel_id, reason="health_restart", diagnostics=snapshot)
                else:
                    await fsm.userStop(channel_id)
                await asyncio.sleep(2)
                await fsm.userStart(channel_id)
                self.audit(
                    "health_restart",
                    self._restart_detail(channel_id, attempt, reason, snapshot, suffix=f"recheck={recheck}"),
                )
                await self._notify(
                    "recording.reconnecting",
                    f"{channel_id} 녹화 이상({reason})을 확인해 자동 재연결을 시도했습니다. ({attempt}회)",
                    {
                        "channel_id": channel_id,
                        "status": f"attempt {attempt}",
                        "attempt": attempt,
                        "reason": reason,
                        "process_exit_code": snapshot.get("process_exit_code"),
                        "file_size": snapshot.get("file_size", 0),
                        "last_write_at": snapshot.get("last_write_at", ""),
                    },
                )
            except Exception as exc:
                self.audit(
                    "health_restart",
                    self._restart_detail(channel_id, attempt, reason, snapshot, suffix=f"error={exc}"),
                    "error",
                )

    async def _notify(self, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        try:
            from module.operations_platform_v3 import emit_runtime_event
            emit_runtime_event(event_type, {"detail": message, **(payload or {})})
        except Exception as exc:
            self.audit("notification_enqueue_failed", f"event={event_type}; error={exc}", "error")

    # --------------------------- post-processing jobs -----------------
    def _wrap_postprocess(self, kind: str, original: Callable[..., Awaitable[Any]]):
        async def wrapper(channel_id: str, *args: Any, **kwargs: Any):
            source = str(args[0]) if args else ""
            job = self._new_job(kind, channel_id, source)
            task = asyncio.current_task()
            if task:
                self.job_tasks[job["id"]] = task
            try:
                job["status"] = "running"
                job["progress"] = 10
                job["started_at"] = _iso()
                self.save_jobs()
                result = await original(channel_id, *args, **kwargs)
                job["status"] = "completed"
                job["progress"] = 100
                job["finished_at"] = _iso()
                await self._delete_short_recording(str(channel_id), source)
                self.audit("postprocess_completed", f"job={job['id']}; channel={channel_id}")
                return result
            except asyncio.CancelledError:
                job["status"] = "cancelled"
                job["progress"] = 0
                job["finished_at"] = _iso()
                self.audit("postprocess_cancelled", f"job={job['id']}", "cancelled")
                raise
            except Exception as exc:
                job["status"] = "failed"
                job["progress"] = 0
                job["error"] = str(exc)[:500]
                job["finished_at"] = _iso()
                self.audit("postprocess_failed", f"job={job['id']}; error={exc}", "error")
                raise
            finally:
                self.job_tasks.pop(job["id"], None)
                self.save_jobs()
        return wrapper

    async def _delete_short_recording(self, channel_id: str, source: str) -> None:
        rule = self.settings.get("rules", {}).get(channel_id, {})
        minimum = int(rule.get("minimum_duration_minutes", 0) or 0)
        if minimum <= 0 or not source:
            return
        try:
            from module.recording_history import get_history
            history = get_history(limit=30, channel_id=channel_id)
            stop = next((item for item in history if item.get("event") == "recording_stopped"), None)
            if not stop or _duration_seconds(stop.get("duration", "")) >= minimum * 60:
                return
            path = Path(source).resolve()
            root = self.recording_root.resolve()
            if root not in path.parents or path in self._busy_paths() or not path.exists():
                return
            await asyncio.to_thread(path.unlink)
            self.audit("short_recording_deleted", f"channel={channel_id}; file={path.name}; minimum={minimum}")
        except Exception as exc:
            self.audit("short_recording_delete_failed", f"channel={channel_id}; error={exc}", "error")

    def _new_job(self, kind: str, channel_id: str, source: str) -> dict[str, Any]:
        job = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "channel_id": str(channel_id),
            "channel_name": (self._channel(str(channel_id)) or {}).get("name", channel_id),
            "source": source,
            "status": "queued",
            "progress": 0,
            "created_at": _iso(),
            "started_at": "",
            "finished_at": "",
            "error": "",
        }
        self.jobs.append(job)
        self.save_jobs()
        return job

    async def retry_job(self, job_id: str) -> dict[str, Any]:
        job = next((item for item in self.jobs if item.get("id") == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        if job.get("status") not in {"failed", "cancelled", "completed"}:
            raise HTTPException(status_code=409, detail="현재 상태에서는 재시도할 수 없습니다.")
        source = str(job.get("source") or "")
        if source and not Path(source).exists():
            matches = list(self.recording_root.rglob(Path(source).name))
            source = str(matches[0]) if matches else source
        if job.get("kind") == "pattern" and self._core_queue_pattern:
            task = asyncio.create_task(self.lar.queueBatchPattern(job["channel_id"], source))
        elif self._core_queue_last:
            task = asyncio.create_task(self.lar.queueBatchLast(job["channel_id"]))
        else:
            raise HTTPException(status_code=500, detail="후처리 함수를 사용할 수 없습니다.")
        return {"status": "accepted", "task": id(task)}

    async def cancel_job(self, job_id: str) -> dict[str, Any]:
        task = self.job_tasks.get(job_id)
        job = next((item for item in self.jobs if item.get("id") == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        if task and not task.done():
            task.cancel()
            job["status"] = "cancelling"
            self.save_jobs()
            return {"status": "cancelling"}
        raise HTTPException(status_code=409, detail="실행 중인 작업이 아닙니다.")
