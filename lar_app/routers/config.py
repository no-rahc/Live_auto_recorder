"""Configuration routes extracted from the legacy web core."""
from __future__ import annotations

from typing import Any

import requests
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from lar_app.config_safety import resolve_secret
from lar_app.config_validation import ConfigValidationError, normalize_config_update


def install_config_routes(app: Any, core: Any) -> None:
    router = APIRouter()

    loadConfig = core.loadConfig
    saveConfig = core.saveConfig
    loadAccount = core.loadAccount
    loadTelegram = core.loadTelegram
    saveTelegram = core.saveTelegram
    toBool = core.toBool
    templates = core.templates
    PROGRAM_VERSION = core.PROGRAM_VERSION
    requireLogin = core.requireLogin
    logger = core.logger

    @router.post("/api/save_config")
    async def save_config_api(request: Request, body: dict = Body(...), login: Any = Depends(requireLogin)):
        try:
            merged = normalize_config_update(
                loadConfig() or {}, body, acknowledgement=body.get("danger_ack", ""),
            )
        except ConfigValidationError as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)
        merged = saveConfig(merged)
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
    async def updateConfig(request: Request, login: Any = Depends(requireLogin)):
        try:
            current_config = loadConfig() or {}
            form = await request.form()
            updates = dict(form)
            if "fileManagerRoots" in form:
                updates["fileManagerRoots"] = form.getlist("fileManagerRoots")
            current_telegram = loadTelegram() or {}
            telegram = {
                field: resolve_secret(form.get(field), form.get(field + "_action"), current_telegram.get(field))
                for field in ("telegram_bot_token", "telegram_chat_id")
            }
            if "discord_webhook_url" in form or "discord_webhook_url_action" in form:
                updates["discord_webhook_url"] = resolve_secret(
                    form.get("discord_webhook_url"), form.get("discord_webhook_url_action"),
                    current_config.get("discord_webhook_url"),
                )
            new_config = normalize_config_update(current_config, updates, acknowledgement=form.get("danger_ack", ""))
            if new_config.get("telegram_enabled") and not all(telegram.values()):
                raise ConfigValidationError("텔레그램 알림 사용 시 봇 토큰과 채팅방 ID를 모두 입력해야 합니다.")
            merged = saveConfig(new_config)
            request.app.state.config = merged
            saveTelegram(telegram)
            return RedirectResponse(url="/", status_code=303)
        except ConfigValidationError as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)
        except Exception as exc:
            logger.error(f"설정 저장 중 오류 발생: {exc}")
            return JSONResponse({"status": "error", "message": "설정 저장 중 오류 발생"}, status_code=500)


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
