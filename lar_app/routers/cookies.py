"""Cookie-management routes extracted from the legacy web core."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse


def install_cookie_routes(app: Any, core: Any) -> None:
    router = APIRouter()

    @router.post("/api/save_chzzk_cookies")
    async def save_chzzk_cookies(
        request: Request,
        body: dict = Body(...),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        core.saveCookies(body)
        request.app.state.chzzk_cookies = body
        return {"status": "ok"}

    @router.post("/api/save_youtube_cookie_file")
    async def save_youtube_cookie_file(
        request: Request,
        login: Any = Depends(core.requireLogin),
    ):
        del login
        path = core.yloadCookies()
        request.app.state.youtube_cookie_path = path
        return {"status": "ok", "path": path}

    @router.get("/cookies", response_class=HTMLResponse)
    async def get_cookies(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        cookies = core.loadCookies()
        return core.templates.TemplateResponse(
            "cookies.html",
            {
                "request": request,
                "cookies": cookies,
                "program_version": core.PROGRAM_VERSION,
            },
        )

    @router.post("/cookies")
    async def update_cookies(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        try:
            new_cookies = await request.json()
            if not new_cookies:
                return JSONResponse(
                    content={"status": "error", "message": "쿠키 데이터가 비어 있습니다."},
                    status_code=400,
                )
            core.saveCookies(new_cookies)
            request.app.state.chzzk_cookies = new_cookies
            core.logger.info("쿠키가 성공적으로 저장되었습니다.")
            return JSONResponse(content={"status": "success"})
        except Exception as exc:
            core.logger.info(f"쿠키 업데이트 중 오류 발생: {exc}")
            return JSONResponse(
                content={"status": "error", "message": "쿠키 업데이트 중 오류 발생"},
                status_code=500,
            )

    app.include_router(router)
