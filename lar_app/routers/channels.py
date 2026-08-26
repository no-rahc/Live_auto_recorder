"""Channel management routes extracted from the legacy web core."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse


def _normalize_exclude_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        items = []

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def install_channel_routes(app: Any, core: Any) -> None:
    router = APIRouter()

    @router.get("/channels", response_class=HTMLResponse)
    async def channels_page(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        async with request.app.state.channels_lock:
            channels = list(request.app.state.channels)
        return core.templates.TemplateResponse("channels.html", {
            "request": request,
            "channels": channels,
            "program_version": core.PROGRAM_VERSION,
        })

    @router.post("/api/channels")
    async def add_channel(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        try:
            body = await request.body()
            if not body:
                raise HTTPException(status_code=400, detail="요청 본문이 비어 있습니다.")
            channel = await request.json()

            if channel["platform"] == "youtube":
                channel["extension"] = ".mp4"
            watch_party = core.toBool(channel.get("recordWatchParty", False))
            if channel.get("platform") == "youtube":
                watch_party = False
            channel["recordWatchParty"] = watch_party
            channel["watchPartyExcludeTags"] = _normalize_exclude_tags(channel.get("watchPartyExcludeTags"))

            if "channelId" in channel:
                channel["id"] = channel.pop("channelId")
            if channel["platform"] not in ["chzzk", "youtube"]:
                raise HTTPException(status_code=400, detail="잘못된 플랫폼 값입니다.")
            required = ("platform", "id", "name", "output_dir", "quality", "extension")
            if not all(key in channel for key in required):
                raise HTTPException(status_code=400, detail="필수 필드가 누락되었습니다.")
            channel.setdefault("record_enabled", True)

            async with request.app.state.channels_lock:
                channels = request.app.state.channels
                channels.append(channel)
                snapshot = list(channels)

            request.app.state.save_debounced(None)
            try:
                core.RecorderManager.setChannels(snapshot)
            except Exception as exc:
                core.logger.warning(f"setChannels 실패(무시): {exc}")
            core.logger.debug("새 채널이 추가되었습니다.")
            return JSONResponse(content={"status": "success"})
        except HTTPException as exc:
            core.logger.error(f"채널 추가 중 오류 발생: {exc.detail}")
            raise
        except Exception as exc:
            core.logger.error(f"채널 추가 중 오류 발생: {exc}")
            raise HTTPException(status_code=500, detail="채널 추가 중 오류 발생")

    @router.put("/api/channels/{channel_id}")
    async def edit_channel(channel_id: str, request: Request, login: Any = Depends(core.requireLogin)):
        del login
        try:
            updated = await request.json()
            async with request.app.state.channels_lock:
                channels = request.app.state.channels
                target = next((item for item in channels if item.get("id") == channel_id), None)
                if not target:
                    raise HTTPException(status_code=404, detail="Channel not found")

                platform = updated.get("platform", target.get("platform"))
                if platform == "youtube":
                    updated["extension"] = ".mp4"
                if "recordWatchParty" in updated:
                    watch_party = core.toBool(updated["recordWatchParty"])
                    if platform == "youtube":
                        watch_party = False
                    updated["recordWatchParty"] = watch_party
                if "watchPartyExcludeTags" in updated:
                    updated["watchPartyExcludeTags"] = _normalize_exclude_tags(updated["watchPartyExcludeTags"])

                updated["id"] = channel_id
                target.update(updated)
                snapshot = list(channels)

            request.app.state.save_debounced(None)
            try:
                core.RecorderManager.setChannels(snapshot)
            except Exception as exc:
                core.logger.warning(f"setChannels 실패(무시): {exc}")
            return JSONResponse(content={"status": "success"})
        except HTTPException:
            raise
        except Exception as exc:
            core.logger.error(f"채널 수정 중 오류 발생: {exc}")
            raise HTTPException(status_code=500, detail="채널 수정 중 오류 발생")

    @router.delete("/api/channels/{channel_id}")
    async def delete_channel(channel_id: str, request: Request, login: Any = Depends(core.requireLogin)):
        del login
        try:
            async with request.app.state.channels_lock:
                channels = request.app.state.channels
                new_list = [item for item in channels if item.get("id") != channel_id]
                if len(new_list) == len(channels):
                    raise HTTPException(status_code=404, detail="Channel not found")
                channels[:] = new_list
                snapshot = list(channels)

            request.app.state.save_debounced(None)
            try:
                core.RecorderManager.setChannels(snapshot)
            except Exception as exc:
                core.logger.warning(f"setChannels 실패(무시): {exc}")
            return JSONResponse(content={"status": "success"})
        except HTTPException:
            raise
        except Exception as exc:
            core.logger.error(f"채널 삭제 중 오류 발생: {exc}")
            raise HTTPException(status_code=500, detail="채널 삭제 중 오류 발생")

    app.include_router(router)
