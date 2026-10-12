#!/usr/bin/env python3
"""Offline, additive v2 migration. Default invocation is a read-only dry run.

No version pointer or original file is changed. --apply requires --stopped and
an explicit image identifier, saves verified database backups and sanitized
configuration snapshots, then imports into the separate recorder_v2.sqlite3.
Keep the previous image and original data. After v2 writes, an image-only
rollback is unsafe: preserve the sidecar and reindex new recordings first.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from module.v2_repository import V2Repository, FutureSchema, SCHEMA_VERSION, DEFAULT_DB_NAME
from module.v2_storage import StorageRoot, preflight_database_location, preflight_storage

def redact_secrets(value):
    # Keep the offline migration command standard-library-only. Match the live
    # backup policy recursively without importing the FastAPI application.
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(key)).lower().replace('-', '_')
            secret = (normalized in {'authorization', 'auth', 'authentication', 'webhooks', 'credentials', 'credential', 'cookie', 'cookies', 'telegram_chat_id', 'chat_id', 'nid_aut', 'nid_ses'}
                      or any(part in normalized for part in ('password', 'passwd', 'secret', 'token', 'api_key', 'apikey', 'private_key', 'webhook_url'))
                      or normalized.endswith('_cookie'))
            if not secret:
                result[key] = redact_secrets(item)
        return result
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value

JSON_FILES = ('config.json', 'channels.json', 'operations_v2.json', 'operations_jobs.json')
SECRET_FILES = ('cookie.json', 'ycookie.txt', 'login.json', 'telegram.json', 'api_tokens.json')
HISTORY_FILES = ('recording_history.jsonl', 'operations_audit.jsonl')


def _digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


@contextmanager
def _readonly_db(path, *, immutable=False):
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    if immutable:
        uri += '&immutable=1'
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def preflight(source_dir, data_dir=None, recording_root=None):
    """Inspect without creating files or directories, including SQLite sidecars."""
    source_dir = Path(source_dir).absolute()
    data_dir = Path(data_dir or source_dir).absolute()
    result = {'ok': True, 'phase': 'preflight', 'dry_run': True,
              'source_dir': str(source_dir), 'data_dir': str(data_dir),
              'errors': [], 'warnings': [], 'files': {}, 'databases': {},
              'secrets': {}, 'invalid_rows': [], 'storage': None}
    location = preflight_database_location(data_dir)
    result['database_location'] = location
    if not location['ok']:
        result['errors'].extend(location['errors'])
    for filename in JSON_FILES:
        path = source_dir / filename
        if not path.exists():
            continue
        if path.is_symlink():
            result['errors'].append(f'{filename}: symbolic links are not accepted')
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if filename in ('channels.json', 'operations_jobs.json') and not isinstance(value, list):
                raise ValueError('expected a JSON array')
            if filename in ('config.json', 'operations_v2.json') and not isinstance(value, dict):
                raise ValueError('expected a JSON object')
            result['files'][filename] = {'sha256': _digest(path), 'size': path.stat().st_size, 'entries': len(value)}
        except (OSError, ValueError) as exc:
            result['errors'].append(f'{filename}: {exc}')
    for filename in HISTORY_FILES:
        path = source_dir / filename
        if not path.exists():
            continue
        if path.is_symlink():
            result['errors'].append(f'{filename}: symbolic links are not accepted')
            continue
        count = 0
        try:
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    if not isinstance(json.loads(line), dict):
                        raise ValueError('expected an object')
                    count += 1
                except ValueError:
                    result['invalid_rows'].append({'file': filename, 'line': number, 'sha256': hashlib.sha256(line.encode()).hexdigest()})
            result['files'][filename] = {'sha256': _digest(path), 'size': path.stat().st_size, 'entries': count}
        except (OSError, ValueError) as exc:
            result['errors'].append(f'{filename}: {exc}')
    for filename in SECRET_FILES:
        # Do not read/hash/copy secrets during dry-run; only inventory existence.
        path = source_dir / filename
        result['secrets'][filename] = {'present': path.exists(), 'excluded_from_default_backup': True}
    for filename, path, supported in (('legacy', source_dir / 'recordings.sqlite3', 4), ('v2', data_dir / DEFAULT_DB_NAME, SCHEMA_VERSION)):
        if not path.exists():
            continue
        if path.is_symlink():
            result['errors'].append(f'{filename}: symbolic database paths are not accepted')
            continue
        # Immutable avoids even a read-only connection creating a -shm file.
        # Never ignore outstanding WAL data while evaluating a migration.
        wal = Path(str(path) + '-wal')
        if wal.exists() and wal.stat().st_size > 0:
            result['errors'].append(f'{filename}: an outstanding WAL requires a clean stop/checkpoint before offline migration')
            continue
        try:
            with _readonly_db(path, immutable=True) as conn:
                version = int(conn.execute('PRAGMA user_version').fetchone()[0])
                integrity = conn.execute('PRAGMA quick_check').fetchone()[0]
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts = {name: conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('recordings', 'notification_queue', 'archive_jobs', 'jobs') if name in tables}
            result['databases'][filename] = {'schema_version': version, 'integrity': integrity, 'counts': counts, 'size': path.stat().st_size, 'sha256': _digest(path)}
            if version > supported:
                result['errors'].append(f'{filename}: future schema {version}; supported maximum is {supported}')
            if integrity != 'ok':
                result['errors'].append(f'{filename}: integrity check failed')
        except sqlite3.DatabaseError as exc:
            result['errors'].append(f'{filename}: {exc}')
    if recording_root is not None:
        result['storage'] = preflight_storage(StorageRoot('recordings', recording_root), probe_writes=False)
        if not result['storage']['ok']:
            result['errors'].extend(result['storage']['errors'])
        result['warnings'].extend(result['storage']['warnings'])
    if result['invalid_rows']:
        result['warnings'].append('Malformed JSONL rows will be reported and skipped; originals are preserved')
    needed = 16 * 1024 * 1024 + 2 * sum(item.get('size', 0) for item in [*result['files'].values(), *result['databases'].values()])
    result['database_location']['checks']['estimated_required_bytes'] = needed
    if result['database_location']['checks'].get('free_bytes', 0) < needed:
        result['errors'].append('Insufficient estimated space for verified backups and the additive v2 import')
    result['ok'] = not result['errors']
    return result


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temporary.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sqlite_backup(source, destination):
    if destination.exists():
        raise FileExistsError('Backup already exists')
    with destination.open('xb'):
        pass
    target = sqlite3.connect(destination)
    try:
        with _readonly_db(source) as conn:
            conn.backup(target)
        target.execute('PRAGMA journal_mode=DELETE')
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite backup failed integrity check')
    finally:
        target.close()
    with destination.open('rb') as handle:
        os.fsync(handle.fileno())
    return {'name': destination.name, 'sha256': _digest(destination), 'size': destination.stat().st_size, 'sqlite_integrity': 'ok'}


def migrate(source_dir, *, data_dir=None, recording_root=None, apply=False,
            stopped=False, image_id='', backup_dir=None, include_secrets=False):
    source_dir = Path(source_dir).absolute()
    data_dir = Path(data_dir or source_dir).absolute()
    report = preflight(source_dir, data_dir, recording_root)
    if include_secrets:
        report['errors'].append('--include-secrets is disabled: only sanitized backups are supported; original settings are preserved')
        report['ok'] = False
        return report
    if not apply:
        return report
    if not stopped:
        report['errors'].append('--apply requires --stopped after stopping the recorder and its jobs')
    if not image_id:
        report['errors'].append('--apply requires --image-id so the previous image can be identified')
    if report['errors']:
        report['ok'] = False
        return report
    directory = Path(backup_dir) if backup_dir else data_dir / 'backups' / ('v2-migration-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    try:
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(directory, 0o700)
    except OSError as exc:
        return {**report, 'ok': False, 'dry_run': False, 'phase': 'failed', 'errors': [*report['errors'], 'Cannot create private backup directory: ' + str(exc)]}
    manifest = {'format': 1, 'phase': 'backup_started', 'created_at': time.time(), 'image_id': image_id,
                'source_dir': str(source_dir), 'v2_path': str(data_dir / DEFAULT_DB_NAME),
                'include_secrets': False, 'files': [], 'invalid_rows': report['invalid_rows'],
                'rollback': 'Before v2 writes, keep the previous image and original files. After v2 writes, stop the service, preserve v2 data/new videos, restore backups and reindex new files; never simply downgrade the image.'}
    manifest_path = directory / 'manifest.json'
    _write_json(manifest_path, manifest)
    try:
        for name, path in (('recordings.sqlite3', source_dir / 'recordings.sqlite3'), (DEFAULT_DB_NAME, data_dir / DEFAULT_DB_NAME)):
            if path.exists():
                manifest['files'].append(_sqlite_backup(path, directory / name))
        for filename in JSON_FILES:
            path = source_dir / filename
            if path.exists():
                value = json.loads(path.read_text(encoding='utf-8'))
                _write_json(directory / filename, redact_secrets(value))
                manifest['files'].append({'name': filename, 'sha256': _digest(directory / filename), 'sanitized': True})
        for filename in HISTORY_FILES:
            path = source_dir / filename
            if not path.exists():
                continue
            # Back up valid historical rows without copying credentials from
            # structured fields. Malformed rows remain in the untouched source
            # and are inventoried by line/hash in the manifest.
            snapshot = directory / filename
            with snapshot.open('x', encoding='utf-8') as out:
                for line in path.read_text(encoding='utf-8').splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    out.write(json.dumps(redact_secrets(row), ensure_ascii=False) + '\n')
                out.flush()
                os.fsync(out.fileno())
            manifest['files'].append({'name': filename, 'sha256': _digest(snapshot), 'sanitized': True})
        manifest['phase'] = 'backup_complete'
        _write_json(manifest_path, manifest)
        repo = V2Repository(data_dir / DEFAULT_DB_NAME)
        repo.initialize()
        manifest['phase'] = 'importing'
        _write_json(manifest_path, manifest)
        imports = {}
        channels = source_dir / 'channels.json'
        if channels.exists():
            for row in json.loads(channels.read_text(encoding='utf-8')):
                if not isinstance(row, dict) or not row.get('id'):
                    report['invalid_rows'].append({'file': channels.name, 'error': 'channel has no id'})
                    continue
                enabled = row.get('record_enabled', False)
                if isinstance(enabled, str):
                    enabled = enabled.lower() in ('true', '1', 'yes', 'on')
                repo.upsert_channel(str(row['id']), platform=str(row.get('platform') or ''), name=str(row.get('name') or ''), desired_mode='auto' if enabled else 'paused', metadata=redact_secrets(row))
        imports['catalog'] = repo.sync_legacy_catalog(source_dir / 'recordings.sqlite3', recording_root)
        jobs = source_dir / 'operations_jobs.json'
        if jobs.exists():
            rows = json.loads(jobs.read_text(encoding='utf-8'))
            records = [(str(row.get('id') or _hash_row(row)), redact_secrets(row)) for row in rows if isinstance(row, dict)]
            imports['jobs'] = repo.import_legacy_records('json:' + str(jobs.resolve()), records, kind='job')
        for filename in HISTORY_FILES:
            path = source_dir / filename
            if not path.exists():
                continue
            records = []
            for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        continue
                except ValueError:
                    continue
                # Original ID where present, otherwise content+line identity is
                # stable across reruns and unaffected by appended history.
                key = str(row.get('id') or f'{line_number}:{hashlib.sha256(line.encode()).hexdigest()}')
                records.append((key, redact_secrets(row)))
            imports[filename] = repo.import_legacy_records('jsonl:' + str(path.resolve()), records)
        catalog = source_dir / 'recordings.sqlite3'
        if catalog.exists():
            with _readonly_db(catalog) as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('notification_queue', 'archive_jobs'):
                    if table in tables:
                        records = [(str(row['id']), dict(row)) for row in conn.execute(f'SELECT * FROM {table} ORDER BY id')]
                        imports[table] = repo.import_legacy_records('sqlite:' + str(catalog.resolve()) + ':' + table, records, kind=table)
        integrity = repo.integrity_check()
        if not integrity['ok']:
            raise ValueError('v2 integrity or foreign-key reconciliation failed')
        manifest.update(phase='validated', imports=imports, validation=integrity, invalid_rows=report['invalid_rows'])
        manifest['originals_unchanged'] = all(_digest(source_dir / name) == entry['sha256'] for name, entry in report['files'].items())
        legacy_digest = report['databases'].get('legacy', {}).get('sha256')
        if legacy_digest and _digest(source_dir / 'recordings.sqlite3') != legacy_digest:
            manifest['originals_unchanged'] = False
        if not manifest['originals_unchanged']:
            raise ValueError('A source file changed during offline migration; do not switch to v2')
        manifest['phase'] = 'ready_for_opt_in'
        manifest['activation'] = 'Set LAR_V2_ENABLED=true only after reviewing this manifest. No version pointer was changed.'
        _write_json(manifest_path, manifest)
        return {**report, 'ok': True, 'dry_run': False, 'phase': manifest['phase'], 'manifest': str(manifest_path), 'imports': imports, 'validation': integrity}
    except Exception as exc:
        manifest.update(phase='failed', error=str(exc))
        _write_json(manifest_path, manifest)
        return {**report, 'ok': False, 'dry_run': False, 'phase': 'failed', 'manifest': str(manifest_path), 'errors': [*report['errors'], str(exc)]}


def _hash_row(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-dir', default=os.getenv('LAR_DATA_DIR', str(Path(__file__).resolve().parents[1] / 'json')))
    parser.add_argument('--data-dir')
    parser.add_argument('--recording-root', default=os.getenv('RECORDINGS_ROOT'))
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument('--apply', action='store_true')
    execution.add_argument('--dry-run', action='store_true', help='Read-only inventory; this is the default')
    parser.add_argument('--stopped', action='store_true', help='Confirm the app and media jobs are stopped')
    parser.add_argument('--image-id', default='', help='Previous image digest or exact source commit')
    parser.add_argument('--backup-dir')
    parser.add_argument('--include-secrets', action='store_true', help='Disabled: secret backups are not supported; originals remain unchanged')
    arguments = vars(parser.parse_args(argv))
    arguments.pop('dry_run', None)
    result = migrate(**arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
