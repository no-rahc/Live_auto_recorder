"""Platform recording-session orchestration kept separate from metadata adapters."""
from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Any

from module.data_manager import RecorderManager, loadCookies, yloadCookies
from module.live_recorder import chzzkStartRecording
from module.recording_filename import (
    begin_filename_context,
    end_filename_context,
    install_live_recorder_filename_sanitizer,
)
from module.recording_trace import begin_session, end_session
from module.youtube_recorder import ytStartRecording
from module.recording_attempt import RecorderAttemptOutcome


class SessionOutcome(str, Enum):
    RECHECK = "recheck"
    COMPLETED = "completed"
    OFFLINE = "offline"
    RETRYABLE_ERROR = "retryable_error"
    USER_STOPPED = "user_stopped"
    DISABLED = "disabled"
    FATAL_ERROR = "fatal_error"
    UNSUPPORTED = "unsupported"


_ATTEMPT_OUTCOME_MAP = {
    RecorderAttemptOutcome.COMPLETED: SessionOutcome.COMPLETED,
    RecorderAttemptOutcome.OFFLINE: SessionOutcome.OFFLINE,
    RecorderAttemptOutcome.RETRYABLE_ERROR: SessionOutcome.RETRYABLE_ERROR,
    RecorderAttemptOutcome.USER_STOPPED: SessionOutcome.USER_STOPPED,
    RecorderAttemptOutcome.DISABLED: SessionOutcome.DISABLED,
    RecorderAttemptOutcome.FATAL_ERROR: SessionOutcome.FATAL_ERROR,
}


def _map_attempt_outcome(value: Any, channel: dict[str, Any]) -> SessionOutcome:
    if isinstance(value, RecorderAttemptOutcome):
        return _ATTEMPT_OUTCOME_MAP[value]
    # Compatibility for patched/legacy recorder call sites that still return None.
    return _classify_returned_attempt(channel)


def _classify_returned_attempt(channel: dict[str, Any]) -> SessionOutcome:
    channel_id = str((channel or {}).get("id") or "unknown")
    manager = RecorderManager()
    if manager.get_is_user_stopped(channel_id):
        return SessionOutcome.USER_STOPPED

    latest = next(
        (item for item in (RecorderManager.getChannels() or []) if str(item.get("id")) == channel_id),
        channel,
    )
    if latest and not latest.get("record_enabled", True):
        return SessionOutcome.DISABLED
    if manager.get_status_reserved(channel_id) and not manager.get_status_recording(channel_id):
        return SessionOutcome.OFFLINE
    return SessionOutcome.COMPLETED


async def record_once(
    channel: dict[str, Any],
    platform: str,
    cfg: dict[str, Any],
    is_user_request: bool = False,
) -> SessionOutcome:
    """Run one platform orchestration boundary and return the next FSM action.

    The platform recorders still contain compatibility retry loops today. Keeping
    this boundary explicit lets those loops be peeled out incrementally without
    changing the FSM/session contract again.
    """
    p = (platform or "").lower()
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

        try:
            attempt = await chzzkStartRecording(
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
                single_attempt=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return SessionOutcome.RETRYABLE_ERROR
        return _map_attempt_outcome(attempt, channel)

    if p == "youtube":
        ycookie_path = yloadCookies()
        if not (isinstance(ycookie_path, str) and os.path.isfile(ycookie_path)):
            ycookie_path = None

        try:
            attempt = await ytStartRecording(
                channel=channel,
                recheckInterval=cfg.get("recheckInterval", 60),
                filenamePattern=cfg.get("filenamePattern", "{recording_time}{file_extension}"),
                moveAfterProcessingEnabled=cfg.get("moveAfterProcessingEnabled", False),
                moveAfterProcessing=cfg.get("moveAfterProcessing", ""),
                ycookie_path=ycookie_path,
                is_user_request=is_user_request,
                single_attempt=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return SessionOutcome.RETRYABLE_ERROR
        return _map_attempt_outcome(attempt, channel)

    return SessionOutcome.UNSUPPORTED


async def start_session(
    channel: dict[str, Any],
    platform: str,
    cfg: dict[str, Any],
    is_user_request: bool = False,
) -> SessionOutcome:
    """Wrap one platform boundary with tracing and filename-context lifecycle."""
    p = (platform or "").lower()
    channel_id = str((channel or {}).get("id") or "unknown")
    session_id, trace_token = begin_session(channel_id, p)
    filename_token = None

    if p == "chzzk":
        install_live_recorder_filename_sanitizer()
        filename_token = begin_filename_context(channel)

    try:
        return await record_once(channel, p, cfg, is_user_request=is_user_request)
    finally:
        if filename_token is not None:
            end_filename_context(filename_token)
        end_session(channel_id, session_id, trace_token)
