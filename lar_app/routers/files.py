"""File-manager routes extracted from the legacy web core."""
from __future__ import annotations

import asyncio
import os
from typing import Any, List

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse


def install_file_routes(app: Any, core: Any) -> None:
    """Register file-manager page/API routes using the legacy domain helpers."""

    router = APIRouter()

    @router.get("/files", response_class=HTMLResponse)
    async def files_page(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        cfg = request.app.state.config
        enabled = bool(cfg.get("fileManagerEnabled"))
        roots = cfg.get("fileManagerRoots") or []
        return core.templates.TemplateResponse(
            "files.html",
            {
                "request": request,
                "loginMode": cfg.get("loginMode", False),
                "fm_enabled": enabled,
                "fm_roots": roots,
                "program_version": core.PROGRAM_VERSION,
            },
        )

    @router.get("/api/files/usage")
    async def api_files_usage(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        cfg = request.app.state.config
        async with request.app.state.channels_lock:
            roots = core.buildAllowedRoots(cfg, request.app.state.channels)
        return {"status": "ok", "volumes": core.listDisks(roots)}

    async def _roots_and_busy(request: Request):
        async with request.app.state.channels_lock:
            roots = core.buildAllowedRoots(request.app.state.config, request.app.state.channels)
            busy = core.busyFilePaths(core.recorder_manager, request.app.state.channels)
        return roots, busy

    @router.get("/api/files/list")
    async def api_files_list(
        request: Request,
        path: str,
        show_hidden: bool = Query(False),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        roots, busy = await _roots_and_busy(request)
        rp = core.ensureInRoots(path, roots)
        items = core.listDir(rp, show_hidden=show_hidden)
        for item in items:
            item["locked"] = core.isLocked(item["path"], busy)
        return {"status": "ok", "path": rp, "items": items}

    @router.get("/api/files/roots")
    async def api_files_roots(request: Request, login: Any = Depends(core.requireLogin)):
        del login
        cfg = request.app.state.config
        if not cfg.get("fileManagerEnabled", False):
            raise HTTPException(status_code=403, detail="File manager disabled")
        async with request.app.state.channels_lock:
            roots = core.buildAllowedRoots(cfg, request.app.state.channels)
        if roots == ["*"]:
            roots_list = core.listMountRoots()
            home = os.path.expanduser("~")
            default_path = home if os.path.isdir(home) else (roots_list[0] if roots_list else None)
        else:
            roots_list = roots
            default_path = roots_list[0] if roots_list else None
        return {"roots": roots_list, "default": default_path}

    @router.get("/api/files/ls")
    async def api_files_ls(
        request: Request,
        path: str,
        show_hidden: bool = Query(False),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        roots, busy = await _roots_and_busy(request)
        try:
            rp = core.ensureInRoots(path, roots)
        except PermissionError:
            raise HTTPException(status_code=403, detail="outside allowed roots")
        except Exception:
            raise HTTPException(status_code=400, detail="invalid path")
        if not os.path.isdir(rp):
            raise HTTPException(status_code=404, detail="path not found")
        try:
            items = core.listDir(rp, show_hidden=show_hidden)
        except PermissionError:
            raise HTTPException(status_code=403, detail="permission denied")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="path not found")
        except OSError:
            raise HTTPException(status_code=403, detail="access denied")
        for item in items:
            item["locked"] = core.isLocked(item["path"], busy)
        return {"status": "ok", "path": rp, "items": items}

    @router.get("/api/files/disk-usage")
    async def api_files_disk_usage(
        request: Request,
        paths: List[str] = Query(default=None),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        cfg = request.app.state.config
        if paths:
            roots = [path for path in paths if os.path.isdir(path)]
        else:
            async with request.app.state.channels_lock:
                built = core.buildAllowedRoots(cfg, request.app.state.channels)
            roots = core.listMountRoots() if built == ["*"] else built
        usages = []
        for root in roots:
            try:
                data = core.diskUsageFor(root)
                data["label"] = root
                usages.append(data)
            except Exception:
                continue
        return {"status": "ok", "usages": usages}

    @router.get("/api/files/download")
    async def api_files_download(request: Request, path: str, login: Any = Depends(core.requireLogin)):
        del login
        async with request.app.state.channels_lock:
            roots = core.buildAllowedRoots(request.app.state.config, request.app.state.channels)
        rp = core.ensureInRoots(path, roots)
        if not os.path.isfile(rp):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(rp, filename=os.path.basename(rp), media_type="application/octet-stream")

    def _ensure_writable(request: Request) -> None:
        if request.app.state.config.get("fileManagerReadOnly", False):
            raise HTTPException(status_code=403, detail="Read-only mode")

    @router.post("/api/files/mkdir")
    async def api_files_mkdir(
        request: Request,
        body: dict = Body(...),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        _ensure_writable(request)
        parent = body.get("path")
        new_name = body.get("new_name")
        if not parent or not new_name:
            raise HTTPException(status_code=400, detail="path/new_name required")
        async with request.app.state.channels_lock:
            roots = core.buildAllowedRoots(request.app.state.config, request.app.state.channels)
        parent = core.ensureInRoots(parent, roots)
        return {"status": "ok", "created": core.mkdirPath(parent, new_name)}

    @router.post("/api/files/rename")
    async def api_files_rename(
        request: Request,
        body: dict = Body(...),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        _ensure_writable(request)
        src = body.get("path")
        new_name = body.get("new_name")
        if not src or not new_name:
            raise HTTPException(status_code=400, detail="path/new_name required")
        roots, busy = await _roots_and_busy(request)
        src = core.ensureInRoots(src, roots)
        if core.isLocked(src, busy):
            raise HTTPException(status_code=423, detail="Locked (recording)")
        return {"status": "ok", "path": core.renamePath(src, new_name)}

    @router.post("/api/files/move")
    async def api_files_move(
        request: Request,
        body: dict = Body(...),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        _ensure_writable(request)
        srcs = body.get("srcs") or ([] if not body.get("src") else [body.get("src")])
        dst_dir = body.get("dst_dir")
        if not srcs or not dst_dir:
            raise HTTPException(status_code=400, detail="src/srcs and dst_dir required")
        roots, busy = await _roots_and_busy(request)
        dst_dir = core.ensureInRoots(dst_dir, roots)
        moved = []
        for src in srcs:
            rp = core.ensureInRoots(src, roots)
            if core.isLocked(rp, busy):
                raise HTTPException(status_code=423, detail=f"Locked: {rp}")
            moved.append(core.movePath(rp, dst_dir))
        return {"status": "ok", "moved": moved}

    @router.post("/api/files/delete")
    async def api_files_delete(
        request: Request,
        body: dict = Body(...),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        _ensure_writable(request)
        paths = body.get("paths") or ([] if not body.get("path") else [body.get("path")])
        hard = bool(body.get("hard", False))
        if not paths:
            raise HTTPException(status_code=400, detail="paths or path required")
        roots, busy = await _roots_and_busy(request)

        def pick_root_for(path: str) -> str:
            rp = core.normPath(path)
            if roots == ["*"]:
                return os.path.dirname(rp)
            candidates = [root for root in roots if rp.startswith(core.normPath(root))]
            if not candidates:
                raise PermissionError("Outside roots")
            return max(candidates, key=lambda root: len(core.normPath(root)))

        deleted = []
        for path in paths:
            rp = core.ensureInRoots(path, roots)
            if core.isLocked(rp, busy):
                raise HTTPException(status_code=423, detail=f"Locked: {rp}")
            if hard or not request.app.state.config.get("trashEnabled", True):
                core.hardDelete(rp)
                deleted.append(rp)
            else:
                deleted.append(core.softDelete(rp, pick_root_for(rp)))
        return {"status": "ok", "deleted": deleted}

    @router.post("/api/files/streamcopy")
    async def api_files_streamcopy(
        request: Request,
        body: dict = Body(...),
        login: Any = Depends(core.requireLogin),
    ):
        del login
        _ensure_writable(request)
        srcs = body.get("paths") or []
        if not srcs:
            raise HTTPException(status_code=400, detail="paths required")
        roots, busy = await _roots_and_busy(request)
        results = []
        for src in srcs:
            try:
                rp = core.ensureInRoots(src, roots)
                if not os.path.isfile(rp):
                    raise HTTPException(status_code=400, detail=f"Not a file: {rp}")
                if core.isLocked(rp, busy):
                    raise HTTPException(status_code=423, detail=f"Locked (recording): {rp}")
                from module.file_manager import streamCopyFile
                dst = await asyncio.to_thread(streamCopyFile, rp)
                results.append({"src": rp, "dst": dst, "ok": True})
            except HTTPException as exc:
                results.append({"src": src, "error": exc.detail, "ok": False})
            except Exception as exc:
                results.append({"src": src, "error": str(exc), "ok": False})
        return {"status": "ok", "results": results}

    app.include_router(router)
