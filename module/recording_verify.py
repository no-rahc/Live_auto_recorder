"""Completed recording validation and safe remux repair using ffprobe/ffmpeg."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from module.log_setup import get_logger
from module.recording_catalog import find_latest_recording, update_recording

logger = get_logger("recording_verify")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


_VALIDATION_WORKER_COUNT = _env_int("RECORDING_VALIDATION_WORKERS", 2, 1, 8)
_VALIDATION_QUEUE_SIZE = _env_int("RECORDING_VALIDATION_QUEUE_SIZE", 64, 4, 512)
_VALIDATION_QUEUE: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=_VALIDATION_QUEUE_SIZE)
_VALIDATION_LOCK = threading.RLock()
_VALIDATION_PENDING: set[tuple[str, str]] = set()
_VALIDATION_WORKERS_STARTED = False


def _recording_root() -> Path:
    raw = os.getenv("RECORDINGS_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    docker = Path("/app/chzzk")
    return docker if docker.exists() else (Path(__file__).resolve().parents[1] / "chzzk").resolve()


def _resolve_file(recording: dict[str, Any]) -> Path | None:
    raw = str(recording.get("file_path") or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    name = str(recording.get("filename") or "").strip()
    if not name:
        return None
    root = _recording_root()
    try:
        return next(path.resolve() for path in root.rglob(name) if path.is_file())
    except StopIteration:
        return None


def _probe(path: Path) -> tuple[bool, dict[str, Any], str]:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration,format_name:stream=codec_type,codec_name", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=45, check=False,
        )
    except Exception as exc:
        return False, {}, f"ffprobe 실행 실패: {exc}"
    if proc.returncode != 0:
        return False, {}, (proc.stderr or "ffprobe 검사 실패").strip()[:1000]
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False, {}, "ffprobe 결과를 해석하지 못했습니다."
    streams = data.get("streams") or []
    video = any(item.get("codec_type") == "video" for item in streams)
    audio = any(item.get("codec_type") == "audio" for item in streams)
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except Exception:
        duration = 0.0
    if not video:
        return False, data, "영상 스트림이 없습니다."
    if duration <= 0:
        return False, data, "재생 시간을 확인할 수 없습니다."
    return True, data, f"영상 {'+ 오디오' if audio else ''} · {duration:.1f}초"


def _repair(path: Path) -> tuple[bool, str]:
    suffix = path.suffix or ".mkv"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.repair-", suffix=suffix, dir=str(path.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy", str(temp)],
            capture_output=True, text=True, timeout=1800, check=False,
        )
        if proc.returncode != 0 or not temp.exists() or temp.stat().st_size <= 0:
            return False, (proc.stderr or "FFmpeg remux 실패").strip()[-1000:]
        valid, _, detail = _probe(temp)
        if not valid:
            return False, f"복구 파일 검증 실패: {detail}"
        backup = path.with_suffix(path.suffix + ".unrepaired")
        if backup.exists():
            backup.unlink()
        os.replace(path, backup)
        os.replace(temp, path)
        try:
            backup.unlink()
        except OSError:
            pass
        return True, detail
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def verify_recording(recording_id: int, *, attempt_repair: bool = True) -> dict[str, Any]:
    from module.recording_catalog import get_recording

    recording = get_recording(recording_id)
    if not recording:
        return {"status": "missing", "detail": "녹화 기록을 찾을 수 없습니다."}
    path = _resolve_file(recording)
    if not path:
        update_recording(recording_id, validation_status="missing", validation_detail="녹화 파일을 찾을 수 없습니다.")
        return {"status": "missing", "detail": "녹화 파일을 찾을 수 없습니다."}
    valid, _, detail = _probe(path)
    if valid:
        update_recording(recording_id, file_path=str(path), file_size=path.stat().st_size, validation_status="ok", validation_detail=detail)
        return {"status": "ok", "detail": detail, "path": str(path), "size": path.stat().st_size}
    if attempt_repair:
        repaired, repair_detail = _repair(path)
        if repaired:
            update_recording(recording_id, file_path=str(path), file_size=path.stat().st_size, validation_status="repaired", validation_detail=repair_detail)
            return {"status": "repaired", "detail": repair_detail, "path": str(path), "size": path.stat().st_size}
        detail = f"{detail} / 복구 실패: {repair_detail}"
    update_recording(recording_id, file_path=str(path), file_size=path.stat().st_size, validation_status="invalid", validation_detail=detail[:1500])
    return {"status": "invalid", "detail": detail[:1500], "path": str(path), "size": path.stat().st_size}


def _run_validation(channel_id: str, filename: str) -> None:
    recording = find_latest_recording(str(channel_id), str(filename or ""))
    if not recording:
        return
    result = verify_recording(int(recording["id"]), attempt_repair=True)
    try:
        from module.operations_platform_v3 import emit_runtime_event
        emit_runtime_event("recording.validated", {"recording_id": int(recording["id"]), **result})
    except Exception as exc:
        logger.debug(f"validation event skipped: {exc}")


def _process_validation_item(item: tuple[str, str]) -> None:
    try:
        _run_validation(*item)
    except Exception as exc:
        logger.warning(f"recording validation worker failed: channel={item[0]}; file={item[1]}; error={exc}")
    finally:
        if item[1]:
            with _VALIDATION_LOCK:
                _VALIDATION_PENDING.discard(item)


def _validation_worker() -> None:
    while True:
        item = _VALIDATION_QUEUE.get()
        try:
            _process_validation_item(item)
        finally:
            _VALIDATION_QUEUE.task_done()


def _ensure_validation_workers() -> None:
    global _VALIDATION_WORKERS_STARTED
    with _VALIDATION_LOCK:
        if _VALIDATION_WORKERS_STARTED:
            return
        for index in range(_VALIDATION_WORKER_COUNT):
            threading.Thread(
                target=_validation_worker,
                name=f"lar-verify-worker-{index + 1}",
                daemon=True,
            ).start()
        _VALIDATION_WORKERS_STARTED = True


def queue_validation(channel_id: str, filename: str = "") -> bool:
    """Queue validation on a bounded worker pool without blocking the recorder loop."""
    _ensure_validation_workers()
    item = (str(channel_id or ""), str(filename or ""))
    dedupe = bool(item[1])

    if dedupe:
        with _VALIDATION_LOCK:
            if item in _VALIDATION_PENDING:
                return False
            _VALIDATION_PENDING.add(item)

    try:
        _VALIDATION_QUEUE.put_nowait(item)
    except queue.Full:
        if dedupe:
            with _VALIDATION_LOCK:
                _VALIDATION_PENDING.discard(item)
        logger.warning(
            "recording validation queue full: channel=%s; file=%s; capacity=%s",
            item[0],
            item[1],
            _VALIDATION_QUEUE_SIZE,
        )
        return False
    return True
