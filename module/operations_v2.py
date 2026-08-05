"""Install the operational safety extension and its API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from module.operations_backup import BackupStatsMixin
from module.operations_common import OperationsBase, _iso
from module.operations_health import HealthJobsMixin


class OperationsRuntime(HealthJobsMixin, BackupStatsMixin, OperationsBase):
    pass


def install_operations(app: Any, lar: Any) -> OperationsRuntime:
    """Register operational routes and return the runtime lifecycle object."""
    runtime = OperationsRuntime(app, lar)
    runtime.install_hooks()
    router = APIRouter()
    auth = Depends(lar.requireLogin)

    @router.get("/operations", response_class=HTMLResponse)
    async def operations_page(request: Request, login: Any = auth):
        return lar.templates.TemplateResponse("operations.html", {
            "request": request,
            "loginMode": bool((getattr(app.state, "config", {}) or {}).get("loginMode", False)),
            "program_version": getattr(lar, "PROGRAM_VERSION", ""),
            "channels": list(getattr(app.state, "channels", []) or []),
        })

    @router.get("/api/operations/summary")
    async def summary(login: Any = auth):
        return runtime.summary()

    @router.get("/api/operations/settings")
    async def get_settings(login: Any = auth):
        return runtime.settings

    @router.put("/api/operations/settings")
    async def put_settings(payload: dict[str, Any] = Body(...), login: Any = auth):
        return runtime.update_settings(payload)

    @router.get("/api/operations/health")
    async def health(login: Any = auth):
        return {"channels": list(runtime.health.values()), "updated_at": _iso()}

    @router.get("/api/operations/jobs")
    async def jobs(login: Any = auth):
        return {"jobs": sorted(runtime.jobs, key=lambda item: item.get("created_at", ""), reverse=True)}

    @router.post("/api/operations/jobs/{job_id}/retry")
    async def retry_job(job_id: str, login: Any = auth):
        return await runtime.retry_job(job_id)

    @router.post("/api/operations/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, login: Any = auth):
        return await runtime.cancel_job(job_id)

    @router.post("/api/operations/cleanup/preview")
    async def cleanup_preview(payload: dict[str, Any] = Body(default={}), login: Any = auth):
        result = runtime.cleanup_candidates(payload)
        result.pop("_all", None)
        return result

    @router.post("/api/operations/cleanup/run")
    async def cleanup_run(payload: dict[str, Any] = Body(...), login: Any = auth):
        return runtime.run_cleanup(payload)

    @router.get("/api/operations/backups")
    async def backups(login: Any = auth):
        return {"backups": runtime.list_backups()}

    @router.post("/api/operations/backups")
    async def create_backup(payload: dict[str, Any] = Body(default={}), login: Any = auth):
        return runtime.create_backup(payload.get("include_secrets"), reason="manual")

    @router.get("/api/operations/backups/{name}/download")
    async def download_backup(name: str, login: Any = auth):
        path = runtime.backup_path(name)
        return FileResponse(path, filename=path.name, media_type="application/zip")

    @router.post("/api/operations/backups/{name}/restore")
    async def restore_backup(name: str, payload: dict[str, Any] = Body(...), login: Any = auth):
        if payload.get("confirm") != name:
            raise HTTPException(status_code=400, detail="confirm 값에 백업 파일명을 입력해야 합니다.")
        return runtime.restore_backup(name)

    @router.get("/api/operations/statistics")
    async def statistics(login: Any = auth):
        return runtime.statistics()

    @router.get("/api/operations/statistics.csv")
    async def statistics_csv(login: Any = auth):
        content = runtime.statistics_csv()
        headers = {"Content-Disposition": 'attachment; filename="recording-statistics.csv"'}
        return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers=headers)

    @router.get("/api/operations/rules/{channel_id}")
    async def get_rule(channel_id: str, login: Any = auth):
        return runtime.settings.get("rules", {}).get(channel_id, {})

    @router.put("/api/operations/rules/{channel_id}")
    async def put_rule(channel_id: str, payload: dict[str, Any] = Body(...), login: Any = auth):
        return runtime.set_rule(channel_id, payload)

    @router.get("/api/operations/audit")
    async def audit(limit: int = 100, login: Any = auth):
        return {"entries": runtime.read_audit(limit)}

    app.include_router(router)
    app.state.operations_v2 = runtime
    return runtime
