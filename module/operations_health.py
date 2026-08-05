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
                await self._notify(f"녹화 저장소 여유 공간이 {storage.get('free_percent')}%입니다. ({level})")
            self.last_storage_level = level
        if level == "critical" and self.settings["storage"].get("auto_cleanup"):
            with suppress(Exception):
                result = self.run_cleanup({"confirm": True, "mode": "free_space"})
                await self._notify(f"저장소 자동 정리로 {len(result.get('deleted', []))}개 파일을 삭제했습니다.")
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

    async def _sample_channel(self, channel: dict[str, Any]) -> None:
        channel_id = str(channel.get("id"))
        rm = self.lar.recorder_manager
        fsm = getattr(self.app.state, "fsm", None)
        fsm_state = fsm.getState(channel_id) if fsm else "STOPPED"
        recording = bool(rm.get_status_recording(channel_id))
        reserved = bool(rm.get_status_reserved(channel_id))
        proc = rm.get_tasks_process(channel_id)
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
        previous_size = int(previous.get("size", size))
        previous_time = float(previous.get("sample_time", now))
        last_growth = float(previous.get("last_growth", now))
        if size > previous_size:
            last_growth = now
        elapsed = max(0.001, now - previous_time)
        rate = max(0.0, (size - previous_size) / elapsed)
        self.samples[channel_id] = {"size": size, "sample_time": now, "last_growth": last_growth}

        state = "waiting"
        label = "대기 중"
        error = ""
        if recording:
            state, label = "recording", "녹화 중"
            if proc is not None and proc.returncode is not None:
                state, label, error = "failed", "프로세스 종료", f"exit={proc.returncode}"
            elif size and now - last_growth >= int(self.settings["health"].get("stall_seconds", 120)):
                state, label, error = "stalled", "기록 멈춤", "파일 크기가 증가하지 않습니다."
        elif fsm_state == "WATCHING" or reserved:
            state, label = "checking", "라이브 확인 중"
        elif fsm_state == "ERROR":
            state, label, error = "failed", "오류", "녹화 상태가 ERROR입니다."

        rule = self.settings.get("rules", {}).get(channel_id, {})
        start_ts = float(self.lar.RecorderManager.recording_start_time.get(channel_id, 0) or 0)
        max_minutes = int(rule.get("max_duration_minutes", 0) or 0)
        if recording and max_minutes and start_ts and now - start_ts >= max_minutes * 60:
            state, label = "stopping", "최대 시간 도달"
            asyncio.create_task(self.lar.stopRecordingForChannel(self.app, channel_id))
            self.audit("max_duration_stop", f"channel={channel_id}; minutes={max_minutes}")

        allowed, rule_reason = self.evaluate_rule(channel)
        if not allowed and (recording or reserved or fsm_state == "WATCHING"):
            state, label, error = "blocked", "규칙 차단", rule_reason
            self.policy_blocked.add(channel_id)
            with suppress(Exception):
                await self.app.state.fsm.userStop(channel_id)
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
        if state == "recording" and (rate > 0 or now - last_growth < 30):
            attempts = 0
        cooldown_until = float(current.get("cooldown_until", 0))
        if state in {"stalled", "failed"} and self.settings["health"].get("auto_restart"):
            max_attempts = int(self.settings["health"].get("max_restart_attempts", 3))
            if attempts < max_attempts and now >= cooldown_until:
                attempts += 1
                cooldown = max(10, int(self.settings["health"].get("restart_cooldown_seconds", 60)))
                cooldown_until = now + cooldown
                state, label = "reconnecting", f"재연결 {attempts}/{max_attempts}"
                asyncio.create_task(self._restart_channel(channel_id, attempts))

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
            "restart_attempts": attempts,
            "cooldown_until": cooldown_until,
            "last_error": error,
            "updated_at": _iso(),
        }

    async def _restart_channel(self, channel_id: str, attempt: int) -> None:
        lock = self._restart_locks.setdefault(channel_id, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            try:
                fsm = self.app.state.fsm
                await fsm.userStop(channel_id)
                await asyncio.sleep(2)
                await fsm.userStart(channel_id)
                self.audit("health_restart", f"channel={channel_id}; attempt={attempt}")
                await self._notify(f"{channel_id} 녹화 멈춤을 감지해 자동 재연결을 시도했습니다. ({attempt}회)")
            except Exception as exc:
                self.audit("health_restart", f"channel={channel_id}; error={exc}", "error")

    async def _notify(self, message: str) -> None:
        with suppress(Exception):
            await asyncio.to_thread(self.lar.sendTelegram, f"<b>Live Auto Recorder</b>\n{message}")
        config = getattr(self.app.state, "config", {}) or {}
        webhook = str(config.get("discord_webhook_url") or "").strip()
        if config.get("discord_enabled") and webhook.startswith("https://"):
            def send_discord() -> None:
                import requests
                requests.post(webhook, json={"content": message}, timeout=8)
            with suppress(Exception):
                await asyncio.to_thread(send_discord)

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
