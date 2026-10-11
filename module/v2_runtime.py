"""Explicit opt-in runtime bridge; legacy installs do not create v2 state."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

_repository: Any = None

def enabled() -> bool:
    return os.getenv('LAR_V2_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}

def get_repository():
    global _repository
    if not enabled():
        return None
    if _repository is None:
        from module.v2_repository import V2Repository
        from module.v2_storage import preflight_database_location
        candidate = V2Repository()
        ancestor = candidate.db_path.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        report = preflight_database_location(ancestor)
        if not report['ok']:
            raise RuntimeError('V2 metadata requires writable local persistent storage with sufficient free space')
        candidate.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not preflight_database_location(candidate.db_path.parent)['ok']:
            raise RuntimeError('V2 data-directory preflight failed')
        candidate.initialize()
        _repository = candidate
    return _repository

def queue_verification(channel_id: str, filename: str = '') -> bool:
    """Commit intent synchronously before returning to the recording engine."""
    from module.recording_catalog import find_latest_recording
    recording = find_latest_recording(str(channel_id), str(filename))
    if recording is None:
        return False
    repo = get_repository()
    if repo is None:
        return False
    sync_catalog()
    artifact = repo.get_artifact(str(recording['id']))
    repo.create_job('verify', artifact['id'], input_revision=artifact['revision'],
                    options={}, idempotency_key=f"auto-verify:{recording['id']}")
    return True


def sync_catalog():
    """Refresh the compatibility projection without mutating legacy sources."""
    from module import recording_catalog
    repo = get_repository()
    if repo is not None and recording_catalog.DB_PATH.exists():
        return repo.sync_legacy_catalog(recording_catalog.DB_PATH, recording_root=os.getenv('RECORDINGS_ROOT') or None)
    return None

def enqueue_legacy_job(kind: str, target_id: str):
    """Compatibility adapter: legacy callers receive acceptance, never fake success."""
    sync_catalog()
    repo = get_repository()
    target = repo.get_broadcast(str(target_id)) if kind == 'merge' else repo.get_artifact(str(target_id))
    if target.get('status') == 'recording' or target.get('metadata', {}).get('status') == 'recording':
        from module.v2_repository import Conflict
        raise Conflict('Wait until recording finishes before processing this item')
    job = repo.create_job(kind, target['id'], input_revision=target['revision'], options={})
    return {'status': 'queued' if job['state'] not in {'succeeded', 'failed', 'cancelled', 'blocked'} else job['state'],
            'job_id': job['id'], 'state': job['state'], 'originals_preserved': True,
            'detail': 'Durable job accepted; inspect its observed result in the v2 job queue.',
            'status_url': f"/api/v2/jobs/{job['id']}"}

def capture_storage_report(channel=None):
    """Require an existing identity marker before any v2 recorder admission."""
    from module.recording_verify import _recording_root
    from module.v2_storage import StorageRoot, preflight_storage, resolve_storage_path
    if _capture_reconciliation_required:
        return {'ok': False, 'reason_code': 'CAPTURE_RECONCILIATION_REQUIRED', 'storage_id': 'recordings', 'checks': {}, 'errors': ['CAPTURE_RECONCILIATION_REQUIRED: prior shutdown was unclean; verify old capture processes have exited before offline reconciliation'], 'warnings': []}
    root = _recording_root()
    storage = StorageRoot('recordings', root,
        marker=os.getenv('LAR_V2_RECORDINGS_MARKER', '.lar-storage-id').strip() or '.lar-storage-id',
        expected_marker=os.getenv('LAR_V2_RECORDINGS_MARKER_VALUE') or None,
        min_free_bytes=64 * 1024 * 1024)
    report = preflight_storage(storage, probe_writes=False)
    if report['ok'] and not report['checks'].get('writable'):
        report['ok'] = False
        report['errors'].append('Recording storage is not writable')
    if report['ok'] and channel:
        raw = channel.get('output_dir') or channel.get('outputDir')
        if raw:
            try:
                relative = Path(raw).expanduser().absolute().relative_to(root).as_posix()
                if relative != '.':
                    resolve_storage_path(storage, relative, must_exist=False)
            except (ValueError, OSError):
                report['ok'] = False
                report['errors'].append('Channel output is outside the registered recordings root')
    return report

_capture_dirty_path = None
_capture_reconciliation_required = False

def begin_capture_guard(repo):
    """A crash leaves a durable admission block, never permission to duplicate capture.

    Legacy capture engines do not yet gate child launch with persisted process
    identity. This conservative marker therefore requires offline reconciliation
    after an unclean shutdown instead of pretending automatic recovery is safe.
    Must run while holding the application instance lock.
    """
    global _capture_dirty_path, _capture_reconciliation_required, _capture_processes, _capture_tracking_uncertain
    import json
    _capture_processes = []
    _capture_tracking_uncertain = False
    _capture_dirty_path = repo.db_path.parent / 'v2-capture-active.json'
    _capture_reconciliation_required = _capture_dirty_path.exists()
    if _capture_reconciliation_required:
        return
    descriptor = os.open(_capture_dirty_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump({'pid': os.getpid(), 'reason': 'Verify all legacy capture processes stopped before removing after an unclean shutdown.'}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(repo.db_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

def finish_capture_guard(*, shutdown_confirmed):
    from module.v2_worker import process_confirmed_absent
    proven = not _capture_tracking_uncertain and all(process_confirmed_absent(item) is True for item in _capture_processes)
    if shutdown_confirmed and proven and not _capture_reconciliation_required and _capture_dirty_path is not None:
        _capture_dirty_path.unlink(missing_ok=True)

_capture_processes = []
_capture_tracking_uncertain = False

def record_capture_process(process):
    """Keep launch identities for shutdown proof; the dirty marker covers the launch gap."""
    global _capture_tracking_uncertain, _capture_reconciliation_required
    import json
    import psutil
    from module.v2_worker import boot_identity, _group_members
    try:
        identity = {'pid': int(process.pid), 'process_started_at': psutil.Process(process.pid).create_time(), 'boot_id': boot_identity()}
        _capture_processes.append(identity)
        if _capture_dirty_path is not None:
            # Append-only launch journal: a torn append still leaves dirty state.
            with _capture_dirty_path.open('a') as handle:
                handle.write('\n' + json.dumps(identity))
                handle.flush()
                os.fsync(handle.fileno())
    except psutil.NoSuchProcess:
        if _group_members(int(process.pid)) != []:
            _capture_tracking_uncertain = True
    except Exception:
        _capture_tracking_uncertain = True
        _capture_reconciliation_required = True
        try:
            process.terminate()
        except (OSError, ProcessLookupError):
            pass
        raise
