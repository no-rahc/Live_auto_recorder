from typing import Any, Dict, Optional

from module.common_errors import debugThrottle
from module.data_manager import RecorderManager, loadCookies, yloadCookies
from module.live_recorder import getLiveMetadata
from module.recording_session import start_session
from module.youtube_recorder import getYoutubeMetadata

recorder_manager = RecorderManager()

# 외부에서 필요한 심볼만 노출
__all__ = ["fetchMetadata", "startSession"]


def _normalize_metadata(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize platform-specific metadata keys for the cache and web UI."""
    if not isinstance(data, dict):
        return data

    normalized = dict(data)

    title = (
        normalized.get("live_title")
        or normalized.get("liveTitle")
        or normalized.get("video_title")
        or normalized.get("title")
    )
    if title:
        normalized["live_title"] = title

    category = (
        normalized.get("category")
        or normalized.get("liveCategoryValue")
        or normalized.get("category_name")
        or normalized.get("game_name")
    )
    if category:
        normalized["category"] = category

    if "is_live" not in normalized:
        status = str(normalized.get("status") or "").upper()
        if status:
            normalized["is_live"] = status == "OPEN"

    return normalized


async def fetchMetadata(channel: dict, platform: str) -> Optional[Dict[str, Any]]:
    p = (platform or "").lower()
    cid = (channel.get("id") or "unknown")

    if p == "chzzk":
        debugThrottle(
            f"meta:chzzk:{cid}",
            f"[DEBUG] fetchMetadata(chzzk:{cid}) : 채널정보 업데이트 중",
            min_secs=30.0,
        )
        cookies = loadCookies() or {}
        return _normalize_metadata(await getLiveMetadata(channel, cookies))

    if p == "youtube":
        debugThrottle(
            f"meta:youtube:{cid}",
            f"[DEBUG] fetchMetadata(youtube:{cid}) : 채널정보 업데이트 중",
            min_secs=30.0,
        )
        ycookie_path = yloadCookies()
        return _normalize_metadata(await getYoutubeMetadata(channel, ycookie_path))

    return None


async def startSession(channel, platform, cfg, is_user_request: bool = False):
    """Compatibility wrapper for the isolated recording-session orchestrator."""
    return await start_session(channel, platform, cfg, is_user_request=is_user_request)
