"""Recording control routes extracted from the legacy web core."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse


def install_recording_routes(app: Any, core: Any) -> None:
    """Register recording-control endpoints while delegating domain work to the core."""

    router = APIRouter()

    @router.post("/api/start_recording/{channel_id}")
    async def api_start_recording(
        channel_id: str,
        request: Request,
        login: Any = Depends(core.requireLogin),
    ):
        del login
        try:
            body = await request.json()
            is_user_request = bool(body.get("is_user_request", False))
        except Exception:
            is_user_request = False

        await core.startRecordingForChannel(request.app, channel_id, is_user_request=is_user_request)

        for _ in range(20):
            recording = core.recorder_manager.get_status_recording(channel_id)
            process = core.recorder_manager.get_tasks_process(channel_id)
            if recording or (process and process.returncode is None):
                effective_reserved = False
                break
            await asyncio.sleep(0.1)
        else:
            recording = core.recorder_manager.get_status_recording(channel_id)
            reserved = core.recorder_manager.get_status_reserved(channel_id)
            fsm_state = request.app.state.fsm.getState(channel_id)
            effective_reserved = bool(reserved or fsm_state == "WATCHING")

        state = "녹화 중" if recording else ("예약녹화 중" if effective_reserved else "대기 중")
        return JSONResponse({
            "status": "success",
            "message": "시작 요청을 접수했습니다.",
            "state": state,
        })

    @router.post("/api/stop_recording/{channel_id}")
    async def api_stop_recording(
        channel_id: str,
        request: Request,
        login: Any = Depends(core.requireLogin),
    ):
        del login
        last = await core.stopRecordingForChannel(request.app, channel_id)
        recording = core.recorder_manager.get_status_recording(channel_id)
        reserved = core.recorder_manager.get_status_reserved(channel_id)
        fsm_state = request.app.state.fsm.getState(channel_id)
        effective_reserved = bool(reserved or fsm_state == "WATCHING")
        resolved = "녹화 중" if recording else ("예약녹화 중" if effective_reserved else "대기 중")
        return JSONResponse({
            "status": "success",
            "state": resolved,
            "filename": last or "녹화 파일이 없습니다.",
        })

    @router.post("/api/start_all_recording")
    async def api_start_all_recording(
        request: Request,
        login: Any = Depends(core.requireLogin),
    ):
        del login
        try:
            body = await request.json()
            is_user_request = bool(body.get("is_user_request", False))
        except Exception:
            is_user_request = False
        results = await core.startRecordingForAllChannels(request.app, is_user_request=is_user_request)
        return JSONResponse({
            "status": "success",
            "message": "일괄 시작 요청 접수",
            "channels_status": results,
        })

    @router.post("/api/stop_all_recording")
    async def api_stop_all_recording(
        request: Request,
        login: Any = Depends(core.requireLogin),
    ):
        del login
        await core.stopRecordingForAllChannels(request.app)
        return JSONResponse({"status": "success", "message": "일괄 중지 요청 접수"})

    @router.post("/api/toggle_record_enabled/{channel_id}")
    async def toggle_record_enabled(
        channel_id: str,
        request: Request,
        login: Any = Depends(core.requireLogin),
    ):
        del login
        async with request.app.state.channels_lock:
            channels = request.app.state.channels
            channel = next((item for item in channels if item["id"] == channel_id), None)
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            before = core.toBool(channel.get("record_enabled", True))
            channel["record_enabled"] = not before

        request.app.state.save_debounced(None)
        if channel["record_enabled"] is False:
            await request.app.state.fsm.onRecordEnabledChanged(channel_id, enabled=False)
        else:
            channel["status"] = "대기 중"

        core.logger.debug(
            "toggle_record_enabled: %s(%s) %s -> %s",
            channel["name"],
            channel_id,
            before,
            channel["record_enabled"],
        )
        return {
            "status": "success",
            "channel_id": channel_id,
            "record_enabled": channel["record_enabled"],
        }

    app.include_router(router)
