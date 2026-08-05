import asyncio
import time
import random
from typing import Any, Dict, List, Callable, Awaitable, Tuple, Optional

from module.common_errors import debugThrottle


# 기본 주기
FAST_TTL        = 20       # 라이브 메타 TTL
PLACEHOLDER_TTL = 5        # 라이브인데 제목이 준비/기본 문구인 경우 빠른 재확인
OFFLINE_TTL     = 90       # 종료 상태일 때 메타 TTL
THUMB_TTL       = 300      # 썸네일 TTL (5분)
BACKOFF_STEPS   = [30, 60, 120, 300]  # 에러 시 지수 백오프
JITTER_SEC      = 3

PLACEHOLDER_TITLES = {
    "",
    "방송 준비 중",
    "방송 제목 없음",
    "불러오는 중...",
    "정보 없음",
}


def _now() -> float:
    return time.time()


def _first_value(data: Optional[Dict[str, Any]], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = data.get(key) if isinstance(data, dict) else None
        if value is not None and value != "":
            return value
    return default


def _live_title(data: Optional[Dict[str, Any]]) -> str:
    return str(_first_value(data, ("live_title", "liveTitle", "video_title", "title"), "") or "").strip()


def _metadata_ttl(platform: str, data: Optional[Dict[str, Any]]) -> int:
    if not isOpen(platform, data):
        return OFFLINE_TTL
    if _live_title(data) in PLACEHOLDER_TITLES:
        return PLACEHOLDER_TTL
    return FAST_TTL


# app.state에 캐시 관련 상태를 보장
def ensure(app) -> None:
    if not hasattr(app.state, "meta_cache"):
        app.state.meta_cache = {}  # {cid: {"data":dict|None,"ts_meta":float,"ts_thumb":float,"err":int}}
    if not hasattr(app.state, "meta_lock"):
        app.state.meta_lock = asyncio.Lock()
    if not hasattr(app.state, "refreshing"):
        app.state.refreshing = set()


def isOpen(platform: str, data: Optional[Dict[str, Any]]) -> bool:
    if not data:
        return False
    p = (platform or "").lower()
    if p == "chzzk":
        return str(data.get("status") or "").upper() == "OPEN" or data.get("is_live") is True
    if p == "youtube":
        return bool(data.get("is_live"))
    return bool(data.get("is_live"))


async def getCached(app, cid: str) -> Optional[Dict[str, Any]]:
    async with app.state.meta_lock:
        return app.state.meta_cache.get(cid)


async def setCached(
    app,
    cid: str,
    data: Optional[Dict[str, Any]] = None,
    touch_meta: bool = False,
    touch_thumb: bool = False,
    clear_error: bool = False,
) -> None:
    async with app.state.meta_lock:
        ent = app.state.meta_cache.get(cid) or {"data": None, "ts_meta": 0.0, "ts_thumb": 0.0, "err": 0}
        if data is not None:
            ent["data"] = data
        if touch_meta:
            ent["ts_meta"] = _now()
        if touch_thumb:
            ent["ts_thumb"] = _now()
        if clear_error:
            ent["err"] = 0
        app.state.meta_cache[cid] = ent


async def bumpError(app, cid: str) -> None:
    async with app.state.meta_lock:
        ent = app.state.meta_cache.get(cid) or {"data": None, "ts_meta": _now(), "ts_thumb": _now(), "err": 0}
        ent["err"] = min(ent.get("err", 0) + 1, len(BACKOFF_STEPS))
        app.state.meta_cache[cid] = ent


# 채널 dict에 제목/카테고리/썸네일만 반영
def mergeChannelFields(real: Dict[str, Any], data: Dict[str, Any]) -> bool:
    changed = False
    mapping = [
        ("live_title", ("live_title", "liveTitle", "video_title", "title"), "방송 제목 없음"),
        ("category", ("category", "liveCategoryValue", "category_name", "game_name"), "카테고리 없음"),
        ("thumbnail_url", ("thumbnail_url", "thumbnailUrl", "thumbnail"), "/static/img/default_thumbnail.png"),
    ]

    for dst, sources, default in mapping:
        value = _first_value(data, sources, default)
        if not value:
            continue

        old = real.get(dst)
        if dst == "live_title" and old and str(value).strip() in PLACEHOLDER_TITLES and str(old).strip() not in PLACEHOLDER_TITLES:
            continue
        if old and value == default:
            continue
        if old != value:
            real[dst] = value
            changed = True

    return changed


async def _fetchAndCacheNow(
    app,
    channel: Dict[str, Any],
    fetcher: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
    channels_lock: asyncio.Lock,
    *,
    need_meta: bool,
    need_thumb: bool,
) -> Optional[Dict[str, Any]]:
    cid = channel["id"]
    try:
        data = await fetcher(channel)
        if not data:
            await bumpError(app, cid)
            return None

        await setCached(
            app,
            cid,
            data,
            touch_meta=need_meta,
            touch_thumb=need_thumb,
            clear_error=True,
        )

        async with channels_lock:
            real = next((c for c in app.state.channels if c["id"] == cid), None)
            if real:
                mergeChannelFields(real, data)
        return data
    except Exception:
        await bumpError(app, cid)
        return None


async def refreshOneChannel(
    app,
    channel: Dict[str, Any],
    fetcher: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
    saveChannels: Callable[[List[Dict[str, Any]]], None],
    channels_lock: asyncio.Lock,
    need_meta: bool = True,
    need_thumb: bool = True,
) -> None:
    try:
        await _fetchAndCacheNow(
            app,
            channel,
            fetcher,
            channels_lock,
            need_meta=need_meta,
            need_thumb=need_thumb,
        )
    finally:
        app.state.refreshing.discard(channel["id"])


async def refreshLoop(
    app,
    fetcher: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
    saveChannels: Callable[[List[Dict[str, Any]]], None],
    channels_lock: asyncio.Lock,
) -> None:
    # 주기적으로 채널 메타/썸네일 캐시 갱신
    ensure(app)
    while True:
        async with channels_lock:
            chs = list(app.state.channels)
        now = _now()

        for ch in chs:
            cid = ch["id"]
            platform = (ch.get("platform") or "").lower()
            ent = await getCached(app, cid) or {"data": None, "ts_meta": 0.0, "ts_thumb": 0.0, "err": 0}
            data = ent["data"]
            ttl_meta = _metadata_ttl(platform, data)
            backoff = BACKOFF_STEPS[min(ent.get("err", 0), len(BACKOFF_STEPS) - 1)] if ent.get("err", 0) > 0 else 0

            need_meta = now - ent["ts_meta"] > max(ttl_meta, backoff)
            need_thumb = now - ent["ts_thumb"] > max(THUMB_TTL, backoff)
            if not (need_meta or need_thumb) or cid in app.state.refreshing:
                continue

            app.state.refreshing.add(cid)
            asyncio.create_task(
                refreshOneChannel(app, ch, fetcher, saveChannels, channels_lock, need_meta, need_thumb)
            )

        await asyncio.sleep(3 + random.uniform(-JITTER_SEC, JITTER_SEC))


async def getMetadataCached(
    app,
    channel_id: str,
    platform: str,
    fetcher: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
    saveChannels: Callable[[List[Dict[str, Any]]], None],
    channels_lock: asyncio.Lock,
) -> Tuple[Dict[str, Any], bool, bool]:
    ensure(app)
    ent = await getCached(app, channel_id)
    data = ent["data"] if ent else None
    now = _now()
    ttl = _metadata_ttl(platform, data)
    fresh = bool(ent and now - ent["ts_meta"] <= ttl)

    # 캐시 미스 또는 stale이면 요청 중에 한 번 즉시 수집한다.
    if data is None or not fresh:
        async with channels_lock:
            ch = next((c for c in app.state.channels if c["id"] == channel_id), None)

        if ch and channel_id not in app.state.refreshing:
            app.state.refreshing.add(channel_id)
            try:
                refreshed = await _fetchAndCacheNow(
                    app,
                    ch,
                    fetcher,
                    channels_lock,
                    need_meta=True,
                    need_thumb=data is None,
                )
                if refreshed:
                    return refreshed, False, True
            finally:
                app.state.refreshing.discard(channel_id)

    if data is None:
        default = {
            "live_title": "방송 제목 없음",
            "category": "카테고리 없음",
            "thumbnail_url": "/static/img/youtube_thumbnail.png" if platform == "youtube" else "/static/img/default_thumbnail.png",
            "is_live": False if platform == "youtube" else None,
        }
        return default, False, False

    return data, True, fresh


# 각 채널 썸네일 URL 리스트 반환
async def getThumbnailsCached(
    app,
    channels: List[Dict[str, Any]],
    fetcher: Callable[[Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]],
    saveChannels: Callable[[List[Dict[str, Any]]], None],
    channels_lock: asyncio.Lock,
) -> List[Dict[str, Any]]:
    ensure(app)
    out = []
    now = _now()

    for ch in channels:
        cid = ch["id"]
        platform = (ch.get("platform") or "").lower()
        ent = await getCached(app, cid)
        data = ent["data"] if ent else None
        fresh_thumb = bool(ent and now - ent["ts_thumb"] <= THUMB_TTL)

        if not fresh_thumb and cid not in app.state.refreshing:
            app.state.refreshing.add(cid)
            asyncio.create_task(
                refreshOneChannel(app, ch, fetcher, saveChannels, channels_lock, need_meta=False, need_thumb=True)
            )

        if data and isinstance(data, dict):
            thumb = _first_value(data, ("thumbnail_url", "thumbnailUrl", "thumbnail"))
        else:
            thumb = "/static/img/youtube_thumbnail.png" if platform == "youtube" else "/static/img/default_thumbnail.png"

        if isinstance(thumb, str) and thumb.startswith("http"):
            debugThrottle(
                f"thumb:{platform}:{cid}",
                f"Generated thumbnail URL: {thumb}",
                min_secs=60.0,
            )

        status = str(_first_value(data, ("status",), "") or "")
        is_live = _first_value(data, ("is_live", "isLive", "live", "online"), None)
        if is_live is None and status:
            is_live = status.upper() == "OPEN"

        out.append({
            "id": cid,
            "platform": platform,
            "thumbnail_url": thumb,
            "live_title": _live_title(data),
            "category": _first_value(data, ("category", "liveCategoryValue", "category_name", "game_name"), ""),
            "is_live": is_live,
            "status": status,
            "adult": bool(data.get("adult", False)) if isinstance(data, dict) else False,
        })

    async with channels_lock:
        changed = False
        for item in out:
            real = next((c for c in app.state.channels if c["id"] == item["id"]), None)
            if real and real.get("thumbnail_url") != item["thumbnail_url"]:
                real["thumbnail_url"] = item["thumbnail_url"]
                changed = True
        if changed:
            saveChannels(app.state.channels)

    return out
