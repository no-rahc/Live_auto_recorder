"""Platform recording-session orchestration kept separate from metadata adapters."""
from __future__ import annotations

import os
from typing import Any

from module.data_manager import loadCookies, yloadCookies
from module.live_recorder import chzzkStartRecording
from module.recording_trace import begin_session, end_session
from module.youtube_recorder import ytStartRecording


async def start_session(
    channel: dict[str, Any],
    platform: str,
    cfg: dict[str, Any],
    is_user_request: bool = False,
) -> None:
    """Run one platform recorder attempt while preserving the legacy call contract."""
    p = (platform or "").lower()
    channel_id = str((channel or {}).get("id") or "unknown")
    session_id, trace_token = begin_session(channel_id, p)

    try:
        if p == "chzzk":
            raw_plugin = (channel.get("plugin_type") or cfg.get("plugin_type", "basic")).lower()
            plugin = raw_plugin if raw_plugin in ("basic", "timemachine_plus") else "basic"

            try:
                shift = int(cfg.get("timemachine_time_shift", 0) or 0)
            except Exception:
                shift = 0
            if plugin == "basic":
                shift = max(0, min(10, shift))
            else:
                shift = max(0, min(3600, shift))

            cookies = loadCookies() or {}
            post_cfg = {
                "dscMinimize": cfg.get("dscMinimize", False),
                "stream_copy": cfg.get("stream_copy", True),
                "preset": cfg.get("preset", "medium"),
                "use_bitrate_mode": cfg.get("use_bitrate_mode", False),
                "video_bitrate": cfg.get("video_bitrate", "1000k"),
                "video_codec": cfg.get("video_codec", "libx264"),
                "video_quality": cfg.get("video_quality", "23"),
                "audio_codec": cfg.get("audio_codec", "aac"),
                "audio_bitrate": cfg.get("audio_bitrate", "192k"),
                "extra_ffmpeg_options": cfg.get("extra_ffmpeg_options", ""),
                "moveAfterProcessingEnabled": cfg.get("moveAfterProcessingEnabled", False),
                "moveAfterProcessing": cfg.get("moveAfterProcessing", ""),
                "postNewWindow": cfg.get("postNewWindow", False),
            }

            await chzzkStartRecording(
                channel=channel,
                cookies=cookies,
                recheckInterval=cfg.get("recheckInterval", 60),
                autoStopInterval=cfg.get("autoStopInterval", 0),
                autoPostProcessing=cfg.get("autoPostProcessing", False),
                filenamePattern=cfg.get("filenamePattern", "[{start_time}] {safe_live_title}"),
                plugin_type=plugin,
                timemachine_time_shift=shift,
                is_user_request=is_user_request,
                splitRecordingMode=cfg.get("splitRecordingMode", False),
                post_cfg=post_cfg,
            )
            return

        if p == "youtube":
            ycookie_path = yloadCookies()
            if not (isinstance(ycookie_path, str) and os.path.isfile(ycookie_path)):
                ycookie_path = None

            await ytStartRecording(
                channel=channel,
                recheckInterval=cfg.get("recheckInterval", 60),
                filenamePattern=cfg.get("filenamePattern", "{recording_time}{file_extension}"),
                moveAfterProcessingEnabled=cfg.get("moveAfterProcessingEnabled", False),
                moveAfterProcessing=cfg.get("moveAfterProcessing", ""),
                ycookie_path=ycookie_path,
                is_user_request=is_user_request,
            )
    finally:
        end_session(channel_id, session_id, trace_token)
