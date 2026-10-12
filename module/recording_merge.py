"""Safe concat/remux support for reconnect-split recording broadcasts."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from module.recording_catalog import get_broadcast, set_broadcast_merge


def _ffmpeg_path() -> str:
    try:
        from module.data_manager import getFFmpeg
        return str(getFFmpeg() or "ffmpeg")
    except BaseException:
        return str(shutil.which("ffmpeg") or "ffmpeg")


def _ffprobe_path() -> str:
    try:
        from module.data_manager import getFFprobe
        return str(getFFprobe() or "ffprobe")
    except BaseException:
        return str(shutil.which("ffprobe") or "ffprobe")


def _verify_merged(path: Path) -> None:
    proc = subprocess.run(
        [_ffprobe_path(), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffprobe validation failed")[-1000:])
    try:
        duration = float((proc.stdout or "0").strip())
    except ValueError as exc:
        raise RuntimeError("합친 파일의 재생 시간을 확인하지 못했습니다.") from exc
    if duration <= 0:
        raise RuntimeError("합친 파일의 재생 시간이 0초입니다.")


class MergeInProgressError(RuntimeError):
    """A merge for this broadcast is already running in this recorder process."""


_MERGE_LOCK = threading.Lock()
_ACTIVE_MERGES: set[str] = set()


def merge_broadcast(broadcast_id: str, *, delete_segments: bool = False) -> dict[str, Any]:
    """Admit one merge per broadcast across API and maintenance worker threads."""
    from module.v2_runtime import enabled, enqueue_legacy_job
    if enabled():
        return enqueue_legacy_job('merge', str(broadcast_id))
    broadcast_id = str(broadcast_id)
    with _MERGE_LOCK:
        if broadcast_id in _ACTIVE_MERGES:
            raise MergeInProgressError("이미 이 방송의 세그먼트를 합치고 있습니다.")
        _ACTIVE_MERGES.add(broadcast_id)
    try:
        return _merge_broadcast(broadcast_id, delete_segments=delete_segments)
    finally:
        with _MERGE_LOCK:
            _ACTIVE_MERGES.discard(broadcast_id)


def _publish_merged(temp_output: Path, parent: Path, stem: str, suffix: str) -> Path:
    """Atomically publish verified media without replacing any existing directory entry.

    A hard link on the same filesystem is an atomic no-clobber operation. Fail
    safely on filesystems that cannot provide it; never fall back to replace().
    """
    counter = 1
    while True:
        number = "" if counter == 1 else f"-{counter}"
        output = parent / f"{stem}.merged{number}{suffix}"
        try:
            os.link(temp_output, output)
            return output
        except FileExistsError:
            counter += 1


def _merge_broadcast(broadcast_id: str, *, delete_segments: bool) -> dict[str, Any]:
    """Concat compatible segments, validate privately, then publish without clobbering."""
    group = get_broadcast(broadcast_id)
    if not group:
        raise ValueError("방송 묶음을 찾을 수 없습니다.")
    segments = [item for item in group.get("segments", []) if item.get("file_path")]
    if len(segments) < 2:
        raise ValueError("합칠 세그먼트가 2개 이상 필요합니다.")
    paths = [Path(str(item["file_path"])).expanduser().absolute() for item in segments]
    missing = [str(path) for path in paths if not path.exists() or not path.is_file()]
    if missing:
        raise FileNotFoundError(f"세그먼트 파일을 찾을 수 없습니다: {missing[0]}")
    suffixes = {path.suffix.lower() for path in paths}
    if len(suffixes) != 1:
        raise ValueError("서로 다른 컨테이너 확장자는 자동 합치기를 지원하지 않습니다.")
    parent = paths[0].parent
    if any(path.parent != parent for path in paths):
        raise ValueError("서로 다른 폴더의 세그먼트는 자동 합치기를 지원하지 않습니다.")

    suffix = paths[0].suffix
    stem = paths[0].stem
    output = None
    try:
        set_broadcast_merge(broadcast_id, status="merging", output_path="", error="")
        # Every attempt owns a private directory. Neither FFmpeg nor cleanup
        # touches another attempt's temporary file or a pre-existing output.
        with tempfile.TemporaryDirectory(prefix="lar-merge-", dir=parent) as workdir:
            list_path = Path(workdir) / "concat.txt"
            # Keep the media suffix last so FFmpeg can infer the output muxer.
            temp_output = Path(workdir) / f"output.partial{suffix}"
            with list_path.open("w", encoding="utf-8") as handle:
                for path in paths:
                    escaped = str(path).replace("'", "'\\''")
                    handle.write(f"file '{escaped}'\n")
            proc = subprocess.run(
                [_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-n", str(temp_output)],
                capture_output=True,
                text=True,
                timeout=6 * 3600,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or "FFmpeg concat failed")[-1200:])
            if not temp_output.exists() or temp_output.stat().st_size <= 0:
                raise RuntimeError("합친 결과 파일이 비어 있습니다.")
            _verify_merged(temp_output)
            size = temp_output.stat().st_size
            output = _publish_merged(temp_output, parent, stem, suffix)
            set_broadcast_merge(broadcast_id, status="completed", output_path=str(output), error="")
        if delete_segments:
            for path in paths:
                if path != output:
                    try:
                        path.unlink()
                    except OSError:
                        pass
        return {
            "broadcast_id": broadcast_id,
            "status": "completed",
            "output_path": str(output),
            "segment_count": len(paths),
            "size": size,
            "deleted_segments": bool(delete_segments),
            "completed_epoch": time.time(),
        }
    except Exception as exc:
        # Once published, verified media is never deleted on a bookkeeping or
        # cleanup failure. In particular, never unlink an unowned final path.
        set_broadcast_merge(broadcast_id, status="failed", output_path=str(output) if output else "", error=str(exc)[:1000])
        raise
