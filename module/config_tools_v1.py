"""Small local helpers used by the compact settings workspace."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import Body, HTTPException


_ENCODERS = (
    ("libx264", "H.264 CPU"),
    ("libx265", "HEVC CPU"),
    ("h264_qsv", "H.264 Intel QSV"),
    ("hevc_qsv", "HEVC Intel QSV"),
    ("h264_nvenc", "H.264 NVIDIA NVENC"),
    ("hevc_nvenc", "HEVC NVIDIA NVENC"),
    ("h264_amf", "H.264 AMD AMF"),
    ("hevc_amf", "HEVC AMD AMF"),
)


def _nearest_existing_parent(path: Path) -> Path | None:
    current = path
    while True:
        if current.exists():
            return current if current.is_dir() else current.parent
        if current.parent == current:
            return None
        current = current.parent


def _check_path(raw_path: str) -> dict[str, Any]:
    value = (raw_path or "").strip()
    if not value:
        raise ValueError("경로를 입력하세요.")

    requested = Path(value).expanduser()
    if not requested.is_absolute():
        raise ValueError("컨테이너 내부의 절대 경로를 입력하세요. 예: /app/chzzk")

    resolved = requested.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("폴더 경로만 확인할 수 있습니다.")

    target = resolved if resolved.exists() else _nearest_existing_parent(resolved)
    if target is None:
        raise ValueError("확인할 수 있는 상위 경로가 없습니다.")

    writable = os.access(target, os.W_OK | os.X_OK)
    usage = shutil.disk_usage(target)
    exists = resolved.exists()
    status = "ok" if writable else "error"
    message = (
        "경로가 존재하며 쓰기 권한이 있습니다."
        if exists and writable
        else "경로는 아직 없지만 상위 폴더에 생성할 수 있습니다."
        if writable
        else "상위 폴더에 쓰기 권한이 없습니다."
    )
    return {
        "status": status,
        "requested": value,
        "resolved": str(resolved),
        "checked_parent": str(target),
        "exists": exists,
        "writable": writable,
        "free_gb": round(usage.free / (1024 ** 3), 2),
        "total_gb": round(usage.total / (1024 ** 3), 2),
        "message": message,
    }


def _probe_encoders(ffmpeg_path: str) -> dict[str, Any]:
    completed = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        raise RuntimeError(output.strip() or "FFmpeg 인코더 목록을 읽지 못했습니다.")

    encoders = [
        {"id": encoder_id, "label": label, "available": encoder_id in output}
        for encoder_id, label in _ENCODERS
    ]
    return {
        "status": "ok",
        "ffmpeg": ffmpeg_path,
        "encoders": encoders,
        "hardware_available": any(
            item["available"] and item["id"] not in {"libx264", "libx265"}
            for item in encoders
        ),
    }


def install_config_tools(app, lar) -> None:
    """Register local read-only diagnostics for settings-page helpers."""

    @app.post("/api/config-tools/path-check")
    async def config_path_check(payload: dict[str, Any] = Body(default_factory=dict)):
        try:
            return await asyncio.to_thread(_check_path, str(payload.get("path", "")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"경로 확인 실패: {exc}") from exc

    @app.get("/api/config-tools/encoders")
    async def config_encoder_check():
        ffmpeg = None
        try:
            ffmpeg = lar.getFFmpeg()
        except Exception:
            ffmpeg = None
        ffmpeg_path = str(ffmpeg or shutil.which("ffmpeg") or "").strip()
        if not ffmpeg_path:
            raise HTTPException(status_code=503, detail="FFmpeg 실행 파일을 찾지 못했습니다.")
        try:
            return await asyncio.to_thread(_probe_encoders, ffmpeg_path)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise HTTPException(status_code=500, detail=f"인코더 확인 실패: {exc}") from exc
