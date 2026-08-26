"""Configuration routes extracted from the legacy web core."""
from __future__ import annotations

from typing import Any, List, Optional

import requests
from fastapi import APIRouter, Body, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from lar_app.config_safety import resolve_secret, validate_file_manager_transition


def install_config_routes(app: Any, core: Any) -> None:
    router = APIRouter()

    loadConfig = core.loadConfig
    saveConfig = core.saveConfig
    loadAccount = core.loadAccount
    loadTelegram = core.loadTelegram
    saveTelegram = core.saveTelegram
    toBool = core.toBool
    _normalizeAllowedRoots = core._normalizeAllowedRoots
    templates = core.templates
    PROGRAM_VERSION = core.PROGRAM_VERSION
    requireLogin = core.requireLogin
    logger = core.logger

    @router.post("/api/save_config")
    async def save_config_api(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
        merged = saveConfig(body)                  
        request.app.state.config = merged            
        return {"status": "ok", "config": merged}


    # 텔레그램 알림 API 테스트 함수
    @router.get("/api/test_telegram")
    async def testTelegram(request: Request, login: Any = Depends(requireLogin)):
        try:
            cfg = loadConfig() or {}
            tel = loadTelegram() or {}

            enabled = toBool(cfg.get("telegram_enabled", False))
            token   = (tel.get("telegram_bot_token") or "").strip()
            chat_id = (tel.get("telegram_chat_id") or "").strip()

            if not enabled:
                return JSONResponse(
                    content={'status': 'error', 'message': '텔레그램 알림 사용이 OFF입니다. ON으로 저장 후 다시 시도하세요.'},
                    status_code=400
                )
            if not token or not chat_id:
                return JSONResponse(
                    content={'status': 'error', 'message': '봇 토큰 또는 채팅 ID가 비어 있습니다.'},
                    status_code=400
                )

            # 실제 Telegram API 호출 (테스트용)
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            params = {"chat_id": chat_id, "text": "Live Auto Recorder 테스트 메시지입니다.", "parse_mode": "HTML"}
            r = requests.get(url, params=params, timeout=10)

            if r.status_code == 200:
                return JSONResponse(content={'status': 'success', 'message': '테스트 메시지를 전송했습니다.'})
            else:
                # 텔레그램에서 내려주는 에러 바디 그대로 전달
                return JSONResponse(
                    content={'status': 'error', 'message': f"전송 실패: {r.status_code} {r.text}"},
                    status_code=400
                )
        except Exception as e:
            return JSONResponse(content={'status': 'error', 'message': str(e)}, status_code=500)


    # 설정 페이지 라우트
    @router.get("/config", response_class=HTMLResponse)
    async def configPage(request: Request, login: Any = Depends(requireLogin)):
        config_data = loadConfig()           
        request.app.state.config = config_data   
        account = loadAccount()             
        telegram = loadTelegram()

        return templates.TemplateResponse('config.html', {
            'request': request,
            'config': config_data,
            'account': account,
            'telegram': telegram,
            'program_version': PROGRAM_VERSION
        })


    @router.get("/api/config")
    async def get_config_api():
        return loadConfig()


    @router.post("/config")
    async def updateConfig(
        request: Request,
        autoRecordingMode: Optional[str] = Form(None),
        enableTray: Optional[str] = Form(None),
        minimizeToTrayOnClose: Optional[str] = Form(None),
        minimizeToTrayOnStart: Optional[str] = Form(None),
        plugin_type: Optional[str] = Form(None),
        timemachine_time_shift: Optional[int] = Form(None),
        autoPostProcessing: Optional[str] = Form(None),
        deleteAfterPostProcessing: Optional[str] = Form(None),
        removeFixedPrefix: Optional[str] = Form(None),
        moveAfterProcessingEnabled: Optional[str] = Form(None),
        moveAfterProcessing: Optional[str] = Form(None),
        postNewWindow: Optional[str] = Form(None),
        recheckInterval: Optional[int] = Form(None),
        filenamePattern: Optional[str] = Form(None),
        splitRecordingMode: Optional[str] = Form(None),
        splitPostProcessing: Optional[str] = Form(None),
        autoStopInterval: Optional[int] = Form(None),
        splitOverlapSec: Optional[int] = Form(None),
        stream_copy: Optional[str] = Form(None),
        video_codec: str = Form("libx264"),
        preset: str = Form("medium"),
        use_bitrate_mode: Optional[str] = Form(None),
        video_quality: int = Form(23),
        video_bitrate: str = Form("1000k"),
        vbv_maxrate: str = Form(""),
        vbv_bufsize: str = Form(""),
        extra_ffmpeg_options: str = Form(""),
        audio_codec: str = Form("aac"),
        audio_bitrate: str = Form("192k"),
        loginMode: Optional[str] = Form(None),
        fileManagerEnabled: Optional[str] = Form(None),
        fileManagerRoots: List[str] = Form([]),
        fileManagerMode: str = Form("blacklist"),
        fileManagerReadOnly: Optional[str] = Form(None),
        trashEnabled: Optional[str] = Form(None),
        telegram_enabled: str = Form("off"),
        telegram_bot_token: str = Form(""),
        telegram_bot_token_action: str = Form("keep"),
        telegram_chat_id: str = Form(""),
        telegram_chat_id_action: str = Form("keep"),
        discord_enabled: str = Form("off"),
        discord_webhook_url: str = Form(""),
        discord_webhook_url_action: str = Form("keep"),
        danger_ack: str = Form(""),
        login: Any = Depends(requireLogin)
    ):
        try:
            # 1) 기존 설정 로드
            current_config = loadConfig() or {}

            # 2) 플러그인/시프트
            posted_plugin = (plugin_type or "").strip().lower() if plugin_type is not None else None
            if posted_plugin in ("basic", "timemachine_plus"):
                normalized_plugin = posted_plugin
            else:
                normalized_plugin = (current_config.get("plugin_type") or "basic")

            try:
                if timemachine_time_shift is None:
                    _shift = int(current_config.get("timemachine_time_shift", 0) or 0)
                else:
                    _shift = int(timemachine_time_shift or 0)
            except Exception:
                _shift = int(current_config.get("timemachine_time_shift", 0) or 0)

            normalized_shift = (
                max(0, min(10, _shift)) if normalized_plugin == "basic"
                else max(0, min(3600, _shift))
            )

            # 3) 파일매니저(웹 전용)
            normalized_roots = _normalizeAllowedRoots(fileManagerRoots)
            effective_fm_enabled = toBool(fileManagerEnabled)
            normalized_fm_mode = fileManagerMode if fileManagerMode in ("blacklist", "whitelist") else "blacklist"
            normalized_fm_read_only = toBool(fileManagerReadOnly)
            normalized_trash = toBool(trashEnabled)
            fm_error = validate_file_manager_transition(
                current_config,
                enabled=effective_fm_enabled,
                mode=normalized_fm_mode,
                read_only=normalized_fm_read_only,
                trash_enabled=normalized_trash,
                acknowledgement=danger_ack,
            )
            if fm_error:
                return JSONResponse(content={"status": "error", "message": fm_error}, status_code=400)

            # 4) 분할/오버랩/오토스탑
            _split_on = toBool(splitRecordingMode) if splitRecordingMode is not None else bool(current_config.get("splitRecordingMode", False))
            try:
                if splitOverlapSec is None:
                    ov = int(current_config.get("splitOverlapSec", 0) or 0)
                else:
                    ov = int(splitOverlapSec or 0)
            except Exception:
                ov = int(current_config.get("splitOverlapSec", 0) or 0)
            if ov < 0: ov = 0
            if ov > 30: ov = 30
            if not _split_on:
                ov = 0

            # autoStopInterval: 분할 ON일 때만, 누락 시 기존값 유지
            try:
                if _split_on:
                    _auto_stop = int(autoStopInterval) if autoStopInterval is not None else int(current_config.get("autoStopInterval", 0) or 0)
                else:
                    _auto_stop = 0
            except Exception:
                _auto_stop = 0 if not _split_on else int(current_config.get("autoStopInterval", 0) or 0)

            # 5) 트레이/텔레그램
            _enable_tray   = toBool(enableTray) if enableTray is not None else bool(current_config.get("enableTray", False))
            _tray_on_close = toBool(minimizeToTrayOnClose) if minimizeToTrayOnClose is not None else bool(current_config.get("minimizeToTrayOnClose", False))
            _tray_on_start = toBool(minimizeToTrayOnStart) if minimizeToTrayOnStart is not None else bool(current_config.get("minimizeToTrayOnStart", False))
            if not _enable_tray:
                _tray_on_close = False
                _tray_on_start = False

            tel_on = toBool(telegram_enabled)
            current_telegram = loadTelegram() or {}
            resolved_bot_token = resolve_secret(
                telegram_bot_token,
                telegram_bot_token_action,
                current_telegram.get("telegram_bot_token"),
            )
            resolved_chat_id = resolve_secret(
                telegram_chat_id,
                telegram_chat_id_action,
                current_telegram.get("telegram_chat_id"),
            )
            resolved_discord_webhook = resolve_secret(
                discord_webhook_url,
                discord_webhook_url_action,
                current_config.get("discord_webhook_url"),
            )

            # 6) 재탐색/파일명
            try:
                _recheck = int(recheckInterval) if recheckInterval is not None else int(current_config.get("recheckInterval", 60))
            except Exception:
                _recheck = int(current_config.get("recheckInterval", 60))
            _pattern = filenamePattern if (filenamePattern not in (None, "")) else current_config.get("filenamePattern", "[{start_time}] {safe_live_title}")

            # 7) 이동경로: 누락 시 기존값 유지(빈 문자열은 None)
            _move_path = (
                current_config.get("moveAfterProcessing")
                if moveAfterProcessing is None
                else (moveAfterProcessing or None)
            )

            # 8) 새 설정 구성(없으면 기존값 유지 원칙)
            new_config = {
                **current_config,
                "autoRecordingMode":            toBool(autoRecordingMode),
                "enableTray":                   _enable_tray,
                "minimizeToTrayOnClose":        _tray_on_close,
                "minimizeToTrayOnStart":        _tray_on_start,
                "plugin_type":                  normalized_plugin,
                "timemachine_time_shift":       normalized_shift,
                "autoPostProcessing":           toBool(autoPostProcessing),
                "deleteAfterPostProcessing":    toBool(deleteAfterPostProcessing),
                "removeFixedPrefix":            toBool(removeFixedPrefix),
                "moveAfterProcessingEnabled":   toBool(moveAfterProcessingEnabled),
                "moveAfterProcessing":          _move_path,
                "postNewWindow":                toBool(postNewWindow),
                "recheckInterval":              _recheck,
                "filenamePattern":              _pattern,
                "splitRecordingMode":           _split_on,
                "splitPostProcessing":          toBool(splitPostProcessing),
                "autoStopInterval":             _auto_stop,
                "splitOverlapSec":              ov,
                "stream_copy":                  toBool(stream_copy),
                "video_codec":                  video_codec,
                "preset":                       preset,
                "use_bitrate_mode":             toBool(use_bitrate_mode),
                "video_quality":                video_quality,
                "video_bitrate":                video_bitrate,
                "vbv_maxrate":                  vbv_maxrate,
                "vbv_bufsize":                  vbv_bufsize,
                "extra_ffmpeg_options":         extra_ffmpeg_options,
                "audio_codec":                  audio_codec,
                "audio_bitrate":                audio_bitrate,
                "telegram_enabled":             tel_on,
                "loginMode":                    False,
                "fileManagerEnabled":           effective_fm_enabled,
                "fileManagerRoots":             normalized_roots,
                "fileManagerMode":              normalized_fm_mode,
                "fileManagerReadOnly":          normalized_fm_read_only,
                "trashEnabled":                 normalized_trash,
                "discord_enabled":              toBool(discord_enabled),
                "discord_webhook_url":          resolved_discord_webhook,
            }

            # 9) 텔레그램 필수 체크
            if new_config.get("telegram_enabled"):
                if not resolved_bot_token or not resolved_chat_id:
                    error_message = "텔레그램 알림 사용 시 봇 토큰과 채팅방 ID를 모두 입력해야 합니다."
                    config_data = loadConfig()
                    account = loadAccount()

                    return templates.TemplateResponse('config.html', {
                        'request': request,
                        'config': config_data,
                        'account': account,
                        'telegram': loadTelegram(),
                        'error_message': error_message,
                        'program_version': PROGRAM_VERSION
                    }, status_code=400)


            # 10) 저장
            logger.debug("설정 저장 중...")
            saveConfig(new_config)
            request.app.state.config = new_config
            logger.debug("설정 저장 완료")

            saveTelegram({
                'telegram_bot_token': resolved_bot_token,
                'telegram_chat_id':   resolved_chat_id
            })

            return RedirectResponse(url="/", status_code=303)

        except Exception as e:
            logger.error(f"설정 저장 중 오류 발생: {e}")
            return JSONResponse(
                content={"status": "error", "message": "설정 저장 중 오류 발생: " + str(e)},
                status_code=500
            )


    @router.get("/get_config")
    async def get_config(request: Request):
        try:
            return {"status": "success", "config": request.app.state.config}
        except Exception as e:
            return {"status": "error", "message": str(e)}


    # ── #2: Discord 테스트 API ───────────────────────────────────
    @router.post("/api/discord_test")
    async def api_discord_test(request: Request, login: Any = Depends(requireLogin)):
        """Discord 웹훅 테스트 메시지 전송."""
        try:
            body = await request.json()
            webhook_url = (body.get("webhook_url") or "").strip()
            if not webhook_url.startswith("https://"):
                return JSONResponse(
                    content={"status": "error", "message": "유효한 웹훅 URL이 아닙니다."},
                    status_code=400
                )
            import requests as req_lib
            payload = {
                "embeds": [{
                    "title": "🔔 Live Auto Recorder 테스트 알림",
                    "description": "Discord 웹훅 설정이 정상적으로 완료되었습니다!",
                    "color": 0x57F287,
                    "footer": {"text": "Live Auto Recorder"},
                }]
            }
            resp = req_lib.post(webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                return {"status": "success", "message": "테스트 메시지 전송 성공"}
            else:
                return JSONResponse(
                    content={"status": "error", "message": f"Discord 응답: {resp.status_code}"},
                    status_code=400
                )
        except Exception as e:
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

    app.include_router(router)
