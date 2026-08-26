"""Safe concat/remux support for reconnect-split recording broadcasts."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
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


def merge_broadcast(broadcast_id: str, *, delete_segments: bool = False) -> dict[str, Any]:
    """Concat compatible segment files with stream copy and verify the output exists."""
    group = get_broadcast(broadcast_id)
    if not group:
        raise ValueError("방송 묶음을 찾을 수 없습니다.")
    segments = [item for item in group.get("segments", []) if item.get("file_path")]
    if len(segments) < 2:
        raise ValueError("합칠 세그먼트가 2개 이상 필요합니다.")
    paths = [Path(str(item["file_path"])).expanduser() for item in segments]
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
    output = parent / f"{stem}.merged{suffix}"
    counter = 2
    while output.exists():
        output = parent / f"{stem}.merged-{counter}{suffix}"
        counter += 1

    set_broadcast_merge(broadcast_id, status="merging", output_path=str(output), error="")
    list_path = None
    # Keep the media suffix last so FFmpeg can infer the output muxer.
    temp_output = output.with_name(f"{output.stem}.partial{output.suffix}")
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", prefix="lar-concat-", dir=parent, delete=False) as handle:
            list_path = Path(handle.name)
            for path in paths:
                escaped = str(path).replace("'", "'\\''")
                handle.write(f"file '{escaped}'\n")
        proc = subprocess.run(
            [_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-y", str(temp_output)],
            capture_output=True,
            text=True,
            timeout=6 * 3600,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "FFmpeg concat failed")[-1200:])
        if not temp_output.exists() or temp_output.stat().st_size <= 0:
            raise RuntimeError("합친 결과 파일이 비어 있습니다.")
        os.replace(temp_output, output)
        _verify_merged(output)
        if delete_segments:
            for path in paths:
                if path != output:
                    try:
                        path.unlink()
                    except OSError:
                        pass
        set_broadcast_merge(broadcast_id, status="completed", output_path=str(output), error="")
        return {
            "broadcast_id": broadcast_id,
            "status": "completed",
            "output_path": str(output),
            "segment_count": len(paths),
            "size": output.stat().st_size,
            "deleted_segments": bool(delete_segments),
            "completed_epoch": time.time(),
        }
    except Exception as exc:
        set_broadcast_merge(broadcast_id, status="failed", output_path=str(output), error=str(exc)[:1000])
        try:
            temp_output.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if list_path:
            try:
                list_path.unlink(missing_ok=True)
            except OSError:
                pass
