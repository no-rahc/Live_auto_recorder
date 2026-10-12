"""Additive opt-in v2 API. The old API and media paths remain intact."""
from __future__ import annotations
import hashlib
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from module import recording_catalog as catalog
from module.v2_runtime import enabled, get_repository, sync_catalog

class IntentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    desired_mode: Literal['auto', 'paused']
    expected_revision: int = Field(ge=1)

class CommandRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['start_once', 'stop_current']
    broadcast_id: str | None = None

class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['verify', 'recover', 'merge', 'archive']
    target_id: str = Field(min_length=1, max_length=512)
    input_revision: int = Field(default=1, ge=1)
    options: dict[str, Any] = Field(default_factory=dict)


def failure(code: str, message: str, status: int = 400, *, details: Any = None):
    return JSONResponse(status_code=status, content={
        'code': code, 'message': message, 'retryable': status == 503,
        'request_id': uuid.uuid4().hex, 'details': details or {},
    })


class V2Route(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return failure('INVALID_REQUEST', 'Request fields are missing or invalid', 422)
            except ValueError:
                return failure('INVALID_REQUEST', 'Invalid cursor or job options', 422)
            except HTTPException as exc:
                return failure('NOT_FOUND' if exc.status_code == 404 else 'REQUEST_REJECTED', str(exc.detail), exc.status_code)
            except Exception as exc:
                if exc.__class__.__module__ not in {'module.v2_repository', 'module.v2_channels'}:
                    raise
                code = getattr(exc, 'code', 'CONFLICT')
                status = getattr(exc, 'status_code', 404 if code == 'NOT_FOUND' else 409)
                return failure(code, str(exc), status, details=getattr(exc, 'details', None))
        return handler


def _public_job(item):
    result = dict(item)
    result['attempts'] = item.get('attempt_count', 0)
    result['error_message'] = item.get('error_detail', '')
    result['cancel_requested'] = bool(item.get('cancel_requested')) or item.get('state') == 'cancel_requested'
    return result


def _storage_status(request):
    from module.v2_runtime import capture_storage_report
    report = capture_storage_report()
    request.app.state.v2_storage = report
    checks = report.get('checks', {})
    return {'status': 'ok' if report['ok'] else 'blocked', 'message': 'Storage identity verified; originals are preserved' if report['ok'] else 'Storage is unavailable; check the configured volume and local diagnostics', 'free_bytes': checks.get('free_bytes'), 'total_bytes': checks.get('total_bytes'), 'observed_at': time.time()}


def public_worker_health(worker):
    """Expose health counters, never internal exception or filesystem diagnostics."""
    if worker is None:
        return {'running': False, 'ready': False}
    snapshot = worker.snapshot()
    return {'ready': bool(snapshot.get('ready')), 'running': int(snapshot.get('running', 0)),
            'reconciled': bool(snapshot.get('reconciled')),
            'error': 'Worker needs attention; check local diagnostics' if snapshot.get('error') else ''}


def _revision(item: dict) -> int:
    # Stable revision changes whenever observable source metadata changes.
    encoded = json.dumps(item, sort_keys=True, default=str).encode()
    return int(hashlib.sha256(encoded).hexdigest()[:12], 16)


def _broadcast(item: dict) -> dict:
    value = dict(item)
    value['id'] = str(value.get('broadcast_id', value.get('id', '')))
    value['total_size'] = int(value.get('file_size') or 0)
    value['revision'] = _revision(item)
    value['observed_at'] = time.time()
    return value


def install_v2_routes(app: Any, core: Any, *, root_dir: Path | None = None) -> None:
    root = root_dir or Path(__file__).resolve().parents[2]
    async def available():
        if not enabled():
            raise HTTPException(404, 'v2 is not enabled')
    router = APIRouter(prefix='/api/v2', route_class=V2Route, dependencies=[Depends(available), Depends(core.requireLogin)])

    def service(request):
        value = getattr(request.app.state, 'v2_channels', None)
        if value is None:
            raise HTTPException(503, 'Channel controller is starting')
        return value

    @router.get('/channels')
    async def channels(request: Request, limit: int = Query(50, ge=1, le=200), cursor: int = Query(0, ge=0)):
        items = sorted(service(request).list_channels(), key=lambda item: item['id'])
        return {'items': items[cursor:cursor+limit], 'next_cursor': str(cursor+limit) if cursor+limit < len(items) else None, 'observed_at': time.time()}

    @router.patch('/channels/{channel_id}')
    async def patch_channel(channel_id: str, body: IntentRequest, request: Request):
        return await service(request).patch_mode(channel_id, body.desired_mode, body.expected_revision)

    @router.post('/channels/{channel_id}/commands', status_code=202)
    async def command(channel_id: str, body: CommandRequest, request: Request, idempotency_key: str = Header(alias='Idempotency-Key', min_length=1, max_length=200)):
        result = await service(request).command(channel_id, body.kind, idempotency_key, broadcast_id=body.broadcast_id)
        return {**result, 'command_id': result['id'], 'status_url': f"/api/v2/commands/{result['id']}"}

    @router.get('/commands/{command_id}')
    async def get_command(command_id: str, request: Request):
        result = service(request).get_command(command_id)
        if result is None:
            raise HTTPException(404, 'Unknown command')
        return result

    @router.get('/broadcasts')
    async def broadcasts(limit: int = Query(50, ge=1, le=200), cursor: int = Query(0, ge=0), query: str = '', channel_id: str = '', platform: str = '', status: str = '', date_from: date | None = None, date_to: date | None = None):
        result = catalog.list_broadcasts(limit=limit, offset=cursor, query=query, channel_id=channel_id, platform=platform, status=status, started_from=datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc).timestamp() if date_from else None, started_to=datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp() if date_to else None)
        items = [_broadcast(item) for item in result['items']]
        if platform:
            items = [item for item in items if item.get('platform') == platform]
        if status:
            items = [item for item in items if item.get('status') == status]
        return {'items': items, 'next_cursor': str(cursor+limit) if cursor+limit < result['total'] else None, 'observed_at': time.time()}

    @router.get('/broadcasts/{broadcast_id}')
    async def broadcast(broadcast_id: str):
        source = catalog.get_broadcast(broadcast_id)
        if source is None:
            raise HTTPException(404, 'Unknown broadcast')
        sync_catalog()
        normalized = get_repository().get_broadcast(broadcast_id)
        result = _broadcast(source)
        result['revision'] = normalized['revision']
        result['sessions'] = normalized.get('sessions', [])
        result['segments'] = [{**row, 'sequence': row.get('segment_index'), 'session_id': row.get('session_key'), 'captured_from': row.get('started_at'), 'captured_to': row.get('ended_at'), 'gap_before': None} for row in source.get('segments', [])]
        result['artifacts'] = normalized.get('artifacts', [])
        jobs = get_repository().list_jobs(limit=200)
        jobs = jobs['items'] if isinstance(jobs, dict) else jobs
        ids = {str(row['id']) for row in source.get('segments', [])} | {str(row['id']) for row in result['artifacts']} | {broadcast_id}
        result['jobs'] = [job for job in jobs if str(job.get('target_id')) in ids]
        return result

    @router.get('/jobs')
    async def jobs(limit: int = Query(50, ge=1, le=200), cursor: str | None = None, state: str | None = None, kind: str | None = None):
        result = get_repository().list_jobs(states=[state] if state else None, kind=kind, limit=limit, cursor=cursor)
        result = result if isinstance(result, dict) else {'items': result, 'next_cursor': None, 'observed_at': time.time()}
        result['items'] = [_public_job(item) for item in result['items']]
        return result

    @router.get('/jobs/{job_id}')
    async def job(job_id: str):
        result = get_repository().get_job(job_id)
        if result is None:
            raise HTTPException(404, 'Unknown job')
        result['attempt_history'] = get_repository().get_attempts(job_id)
        return _public_job(result)

    @router.post('/jobs', status_code=202)
    async def create_job(body: JobRequest, idempotency_key: str = Header(alias='Idempotency-Key', min_length=1, max_length=200)):
        if set(body.options) - {'output_storage_id', 'output_relative_path', 'suffix'}:
            return failure('INVALID_OPTIONS', 'Only output storage, relative output path, and container suffix may be selected', 422)
        sync_catalog()
        repo = get_repository()
        canonical_target = ('legacy-recording-' + body.target_id) if body.kind != 'merge' and body.target_id.isdigit() else body.target_id
        source = repo.get_broadcast(canonical_target) if body.kind == 'merge' else repo.get_artifact(canonical_target)
        canonical_target = source['id']
        replay = repo.lookup_job_request(body.kind, canonical_target, input_revision=body.input_revision, options=body.options, idempotency_key=idempotency_key)
        if replay is not None:
            return {**replay, 'job_id': replay['id'], 'status_url': f"/api/v2/jobs/{replay['id']}"}
        if source.get('status') == 'recording' or source.get('metadata', {}).get('status') == 'recording':
            return failure('INPUT_ACTIVE', 'Wait until recording finishes', 409)
        if str(body.input_revision) != str(source['revision']):
            return failure('INPUT_CHANGED', 'Refresh this item before creating a job', 409, details={'revision': source['revision']})
        result = get_repository().create_job(body.kind, source['id'], input_revision=body.input_revision, options=body.options, idempotency_key=idempotency_key)
        return {**result, 'job_id': result['id'], 'status_url': f"/api/v2/jobs/{result['id']}"}

    @router.post('/jobs/{job_id}/cancel', status_code=202)
    async def cancel(job_id: str):
        return get_repository().request_cancel(job_id)

    @router.post('/jobs/{job_id}/retry', status_code=202)
    async def retry(job_id: str):
        return get_repository().retry_job(job_id)

    @router.get('/status')
    async def status(request: Request):
        values = service(request).list_channels()
        result = get_repository().list_jobs(limit=200)
        items = result['items'] if isinstance(result, dict) else result
        worker = getattr(request.app.state, 'v2_worker', None)
        return {'enabled': True, 'observed_at': time.time(), 'version': getattr(core, 'VERSION', '2.0 preview'),
                'channels': {'total': len(values), 'recording': sum(c['actual_state'] == 'recording' for c in values), 'watching': sum(c['actual_state'] == 'watching' for c in values), 'attention': sum(c['actual_state'] in {'blocked', 'error'} for c in values)},
                'jobs': get_repository().job_counts(),
                'worker': public_worker_health(worker),
                'storage': _storage_status(request)}

    @router.get('/settings')
    async def settings():
        return {'enabled': True, 'version': getattr(core, 'VERSION', '2.0 preview'), 'storage': {'database': 'local persistent volume', 'recordings': 'existing paths preserved', 'originals_preserved': True}, 'features': {'durable_jobs': True, 'legacy_ui': True}, 'links': {'configuration': '/config', 'files': '/files', 'operations': '/operations'}}

    app.include_router(router)

    async def ui(request: Request):
        await available()
        index = root / 'templates/static/v2/index.html'
        if not index.is_file():
            raise HTTPException(503, 'Build the v2 frontend first')
        return FileResponse(index, headers={'Cache-Control': 'no-store'})
    app.add_api_route('/v2', ui, methods=['GET'], include_in_schema=False)
    app.add_api_route('/v2/{path:path}', ui, methods=['GET'], include_in_schema=False)
