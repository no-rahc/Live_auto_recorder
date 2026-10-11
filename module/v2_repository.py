"""Additive v2 domain repository. Never opens or mutates the v4 catalog.

Worker writes are fenced by owner, generation and lease. An expired lease does
not prove that a process exited: recovery requires external process evidence.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import random
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4C415232
DEFAULT_DB_NAME = 'recorder_v2.sqlite3'
ACTIVE_STATES = ('running', 'cancel_requested')
JOB_STATES = frozenset(('queued', 'running', 'cancel_requested', 'retry_wait', 'blocked', 'failed', 'succeeded', 'cancelled', 'interrupted'))
ACTUAL_STATES = frozenset(('idle', 'watching', 'starting', 'recording', 'reconnecting', 'stopping', 'blocked', 'error'))

class RepositoryError(Exception):
    code = 'REPOSITORY_ERROR'
    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details
class Conflict(RepositoryError):
    code = 'CONFLICT'
class NotFound(RepositoryError):
    code = 'NOT_FOUND'
class LeaseLost(Conflict):
    code = 'LEASE_LOST'
class FutureSchema(RepositoryError):
    code = 'FUTURE_SCHEMA'

def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def _hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
def _id(prefix):
    return prefix + '_' + uuid.uuid4().hex
def _decode(row):
    if row is None:
        return None
    result = dict(row)
    for key in list(result):
        if key.endswith('_json'):
            result[key[:-5]] = json.loads(result.pop(key) or '{}')
    return result

_SCHEMA = '''
CREATE TABLE channels (
 id TEXT PRIMARY KEY, platform TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
 desired_mode TEXT NOT NULL DEFAULT 'paused' CHECK(desired_mode IN ('auto','paused')),
 actual_state TEXT NOT NULL DEFAULT 'idle', reason_code TEXT NOT NULL DEFAULT '',
 current_broadcast_id TEXT, observed_at REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE broadcasts (
 id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES channels(id), platform TEXT NOT NULL,
 provider_live_id TEXT, title TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL DEFAULT '',
 ended_at TEXT NOT NULL DEFAULT '', identity_basis TEXT NOT NULL DEFAULT 'heuristic',
 status TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1, observed_at REAL NOT NULL,
 metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(platform,channel_id,provider_live_id)
);
CREATE TABLE sessions (
 id TEXT PRIMARY KEY, broadcast_id TEXT NOT NULL REFERENCES broadcasts(id), engine TEXT NOT NULL DEFAULT '',
 started_at TEXT NOT NULL DEFAULT '', ended_at TEXT NOT NULL DEFAULT '', outcome TEXT NOT NULL DEFAULT '',
 stop_reason TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE segments (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), sequence INTEGER NOT NULL DEFAULT 1,
 captured_from TEXT NOT NULL DEFAULT '', captured_to TEXT NOT NULL DEFAULT '', gap_before REAL,
 timing_estimated INTEGER NOT NULL DEFAULT 1, UNIQUE(session_id,sequence)
);
CREATE TABLE artifacts (
 id TEXT PRIMARY KEY, broadcast_id TEXT REFERENCES broadcasts(id), segment_id TEXT REFERENCES segments(id),
 kind TEXT NOT NULL DEFAULT 'original', storage_id TEXT NOT NULL DEFAULT 'legacy', relative_path TEXT NOT NULL,
 legacy_path TEXT NOT NULL DEFAULT '', size INTEGER NOT NULL DEFAULT 0, validation TEXT NOT NULL DEFAULT '',
 validation_detail TEXT NOT NULL DEFAULT '', exists_status TEXT NOT NULL DEFAULT 'unknown', revision INTEGER NOT NULL DEFAULT 1,
 metadata_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, UNIQUE(storage_id,relative_path)
);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, target_id TEXT NOT NULL, input_revision TEXT NOT NULL,
 params_hash TEXT NOT NULL, options_json TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN
 ('queued','running','cancel_requested','retry_wait','blocked','failed','succeeded','cancelled','interrupted')),
 next_run_at REAL NOT NULL, owner TEXT, generation INTEGER NOT NULL DEFAULT 0, lease_until REAL,
 attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5, cancel_requested INTEGER NOT NULL DEFAULT 0,
 attempt_id TEXT, error_code TEXT NOT NULL DEFAULT '', error_detail TEXT NOT NULL DEFAULT '',
 progress_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
 request_id TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
 observed_at REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 1, UNIQUE(kind,target_id,input_revision,params_hash)
);
CREATE INDEX jobs_queue ON jobs(state,next_run_at,created_at,id);
CREATE TABLE job_attempts (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), attempt_no INTEGER NOT NULL,
 owner TEXT NOT NULL, lease_generation INTEGER NOT NULL, started_at REAL NOT NULL,
 ended_at REAL, outcome TEXT NOT NULL DEFAULT 'running', pid INTEGER, process_started_at TEXT, boot_id TEXT,
 work_dir TEXT NOT NULL DEFAULT '', error_code TEXT NOT NULL DEFAULT '', error_detail TEXT NOT NULL DEFAULT '',
 result_json TEXT NOT NULL DEFAULT '{}', UNIQUE(job_id,attempt_no), UNIQUE(job_id,lease_generation)
);
CREATE TABLE idempotency_keys (
 scope TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL, entity_id TEXT NOT NULL,
 created_at REAL NOT NULL, PRIMARY KEY(scope,key)
);
CREATE TABLE commands (
 id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES channels(id), kind TEXT NOT NULL,
 broadcast_id TEXT, state TEXT NOT NULL DEFAULT 'accepted', request_id TEXT NOT NULL DEFAULT '',
 result_json TEXT NOT NULL DEFAULT '{}', error_code TEXT NOT NULL DEFAULT '',
 created_at REAL NOT NULL, updated_at REAL NOT NULL, observed_at REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE broadcast_suppressions (
 channel_id TEXT NOT NULL REFERENCES channels(id), broadcast_id TEXT NOT NULL,
 command_id TEXT REFERENCES commands(id), created_at REAL NOT NULL, PRIMARY KEY(channel_id,broadcast_id)
);
CREATE TABLE publications (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), attempt_id TEXT NOT NULL REFERENCES job_attempts(id),
 generation INTEGER NOT NULL, owner TEXT NOT NULL, temporary_path TEXT NOT NULL, final_path TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', metadata_json TEXT NOT NULL DEFAULT '{}',
 artifact_id TEXT REFERENCES artifacts(id), created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(job_id,generation)
);
CREATE TABLE legacy_imports (
 source TEXT NOT NULL, source_key TEXT NOT NULL, source_hash TEXT NOT NULL,
 entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, imported_at REAL NOT NULL, PRIMARY KEY(source,source_key)
);
CREATE TABLE legacy_records (
 source TEXT NOT NULL, source_key TEXT NOT NULL, payload_json TEXT NOT NULL,
 imported_at REAL NOT NULL, PRIMARY KEY(source,source_key)
);
'''

class V2Repository:
    def __init__(self, db_path: str | Path | None = None, *, clock: Callable[[], float] = time.time):
        root = Path(os.getenv('LAR_DATA_DIR', Path(__file__).resolve().parents[1] / 'json'))
        self.db_path = Path(db_path) if db_path is not None else root / DEFAULT_DB_NAME
        self.clock = clock

    def initialize(self):
        existed = self.db_path.exists() and self.db_path.stat().st_size > 0
        if existed:
            wal = Path(str(self.db_path) + '-wal')
            with self._readonly(immutable=not wal.exists() or wal.stat().st_size == 0) as conn:
                current = int(conn.execute('PRAGMA user_version').fetchone()[0])
                app_id = int(conn.execute('PRAGMA application_id').fetchone()[0])
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if current > SCHEMA_VERSION:
                    raise FutureSchema(f'Schema {current} is newer than supported {SCHEMA_VERSION}')
                if app_id not in (0, APPLICATION_ID) or (tables and app_id != APPLICATION_ID):
                    raise RepositoryError('Refusing an unrecognized database; choose a separate v2 path')
                if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise RepositoryError('Database integrity check failed')
            if current < SCHEMA_VERSION:
                self.backup(self.db_path.with_name(f'{self.db_path.name}.pre-v{SCHEMA_VERSION}-{uuid.uuid4().hex}.bak'))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            version = int(conn.execute('PRAGMA user_version').fetchone()[0])
            if version > SCHEMA_VERSION:
                raise FutureSchema('Database schema changed during initialization')
            if version == 0:
                for statement in _SCHEMA.split(';'):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute(f'PRAGMA application_id={APPLICATION_ID}')
                conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        return {'path': str(self.db_path), 'schema_version': SCHEMA_VERSION, 'created': not existed}

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=15000')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
        return conn

    @contextmanager
    def _readonly(self, *, immutable=False):
        uri = self.db_path.resolve().as_uri() + '?mode=ro' + ('&immutable=1' if immutable else '')
        conn = sqlite3.connect(uri, uri=True, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise Conflict('Backup destination already exists')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb'):
            pass
        try:
            with self._readonly() as source:
                target = sqlite3.connect(destination)
                try:
                    source.backup(target)
                    target.execute('PRAGMA journal_mode=DELETE')
                    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RepositoryError('Backup integrity check failed')
                finally:
                    target.close()
            with destination.open('rb') as handle:
                os.fsync(handle.fileno())
            return {'path': str(destination), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'size': destination.stat().st_size}
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _required(conn, table, entity_id):
        row = _decode(conn.execute(f'SELECT * FROM {table} WHERE id=?', (entity_id,)).fetchone())
        if row is None:
            raise NotFound(f'{table.rstrip("s")} not found')
        return row

    @staticmethod
    def _key(conn, scope, key, digest):
        if not key:
            return None
        row = conn.execute('SELECT * FROM idempotency_keys WHERE scope=? AND key=?', (scope, key)).fetchone()
        if row is not None:
            if row['request_hash'] != digest:
                raise Conflict('Idempotency key was already used with a different request')
            return str(row['entity_id'])
        return None

    def _bind_key(self, conn, scope, key, digest, entity_id):
        if key:
            conn.execute('INSERT OR IGNORE INTO idempotency_keys VALUES (?,?,?,?,?)', (scope, key, digest, entity_id, self.clock()))

    def create_job(self, kind, target_id, input_revision=1, options=None, idempotency_key=None, request_id='', max_attempts=5):
        target_id = str(target_id)
        if not kind or not target_id or not 1 <= max_attempts <= 100:
            raise ValueError('kind, target_id and max_attempts 1..100 are required')
        if options is not None and not isinstance(options, dict):
            raise ValueError('options must be an object')
        options = {} if options is None else options
        normalized, params_hash = canonical_json(options), _hash(options)
        digest = _hash({'kind': kind, 'target_id': target_id, 'input_revision': str(input_revision), 'options': options, 'max_attempts': max_attempts})
        with self._transaction() as conn:
            existing = self._key(conn, 'jobs', idempotency_key, digest)
            if existing:
                return self._required(conn, 'jobs', existing)
            row = conn.execute('SELECT id FROM jobs WHERE kind=? AND target_id=? AND input_revision=? AND params_hash=?', (kind, target_id, str(input_revision), params_hash)).fetchone()
            job_id = row[0] if row else _id('job')
            if row is None:
                now = self.clock()
                conn.execute("INSERT INTO jobs(id,kind,target_id,input_revision,params_hash,options_json,state,next_run_at,max_attempts,request_id,created_at,updated_at,observed_at) VALUES (?,?,?,?,?,?,'queued',?,?,?,?,?,?)", (job_id, kind, target_id, str(input_revision), params_hash, normalized, now, max_attempts, request_id, now, now, now))
            self._bind_key(conn, 'jobs', idempotency_key, digest, job_id)
            return self._required(conn, 'jobs', job_id)

    def get_job(self, job_id):
        with self._readonly() as conn:
            return self._required(conn, 'jobs', job_id)

    def get_attempts(self, job_id):
        with self._readonly() as conn:
            self._required(conn, 'jobs', job_id)
            return [_decode(row) for row in conn.execute('SELECT * FROM job_attempts WHERE job_id=? ORDER BY attempt_no', (job_id,))]

    def list_jobs(self, *, states=None, kind=None, limit=50, cursor=None):
        filters, args = [], []
        if states:
            states = list(states)
            filters.append('state IN (' + ','.join('?' for _ in states) + ')')
            args.extend(states)
        if kind:
            filters.append('kind=?')
            args.append(kind)
        return self._page('jobs', filters, args, limit, cursor)

    def _page(self, table, filters, args, limit, cursor):
        limit = max(1, min(int(limit), 200))
        order = 'created_at' if table in ('jobs', 'commands') else 'id'
        if cursor:
            try:
                last = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if not isinstance(last, list) or len(last) != 2:
                    raise ValueError()
            except Exception as exc:
                raise ValueError('Invalid cursor') from exc
            filters.append(f'({order}<? OR ({order}=? AND id<?))')
            args.extend((last[0], last[0], last[1]))
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        with self._readonly() as conn:
            rows = conn.execute(f'SELECT * FROM {table}{where} ORDER BY {order} DESC,id DESC LIMIT ?', [*args, limit + 1]).fetchall()
        items = [_decode(row) for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit and items:
            next_cursor = base64.urlsafe_b64encode(canonical_json([items[-1][order], items[-1]['id']]).encode()).decode()
        return {'items': items, 'next_cursor': next_cursor, 'observed_at': self.clock()}

    def claim_job(self, owner, *, kinds=None, lease_seconds=90):
        if not owner or lease_seconds <= 0:
            raise ValueError('owner and positive lease_seconds required')
        now = self.clock()
        with self._transaction() as conn:
            where, args = "state IN ('queued','retry_wait') AND next_run_at<=? AND attempt_count<max_attempts", [now]
            if kinds is not None:
                kinds = list(kinds)
                if not kinds:
                    return None
                where += ' AND kind IN (' + ','.join('?' for _ in kinds) + ')'
                args.extend(kinds)
            row = conn.execute('SELECT * FROM jobs WHERE ' + where + ' ORDER BY next_run_at,created_at,id LIMIT 1', args).fetchone()
            if row is None:
                return None
            generation, attempt_no, attempt_id = row['generation'] + 1, row['attempt_count'] + 1, _id('attempt')
            conn.execute("UPDATE jobs SET state='running',owner=?,generation=?,lease_until=?,attempt_count=?,attempt_id=?,error_code='',error_detail='',updated_at=?,observed_at=?,revision=revision+1 WHERE id=?", (owner, generation, now + lease_seconds, attempt_no, attempt_id, now, now, row['id']))
            conn.execute('INSERT INTO job_attempts(id,job_id,attempt_no,owner,lease_generation,started_at) VALUES (?,?,?,?,?,?)', (attempt_id, row['id'], attempt_no, owner, generation, now))
            return self._required(conn, 'jobs', row['id'])

    def _fenced(self, conn, job_id, owner, generation):
        job = self._required(conn, 'jobs', job_id)
        if job['state'] not in ACTIVE_STATES or job['owner'] != owner or job['generation'] != generation or (job['lease_until'] or 0) <= self.clock():
            raise LeaseLost('Worker no longer owns an active lease')
        return job

    def assert_lease(self, job_id, owner, generation):
        with self._readonly() as conn:
            return self._fenced(conn, job_id, owner, generation)

    def heartbeat(self, job_id, owner, generation, *, lease_seconds=90, progress=None):
        if lease_seconds <= 0:
            raise ValueError('positive lease_seconds required')
        with self._transaction() as conn:
            job = self._fenced(conn, job_id, owner, generation)
            now = self.clock()
            conn.execute('UPDATE jobs SET lease_until=?,progress_json=?,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?', (now + lease_seconds, canonical_json(job['progress'] if progress is None else progress), now, now, job_id))
            return self._required(conn, 'jobs', job_id)

    def set_process(self, job_id, owner, generation, pid, process_started_at='', boot_id=''):
        with self._transaction() as conn:
            job = self._fenced(conn, job_id, owner, generation)
            conn.execute('UPDATE job_attempts SET pid=?,process_started_at=?,boot_id=? WHERE id=?', (pid, str(process_started_at), boot_id, job['attempt_id']))
            return self._required(conn, 'job_attempts', job['attempt_id'])

    def set_attempt_context(self, job_id, owner, generation, work_dir):
        with self._transaction() as conn:
            job = self._fenced(conn, job_id, owner, generation)
            conn.execute('UPDATE job_attempts SET work_dir=? WHERE id=?', (str(work_dir), job['attempt_id']))
            return self._required(conn, 'job_attempts', job['attempt_id'])

    def record_publication(self, job_id, owner, generation, temporary_path, final_path, metadata=None):
        with self._transaction() as conn:
            job = self._fenced(conn, job_id, owner, generation)
            if job['state'] == 'cancel_requested':
                raise Conflict('Cancellation was requested before publication')
            existing = _decode(conn.execute('SELECT * FROM publications WHERE job_id=? AND generation=?', (job_id, generation)).fetchone())
            if existing:
                if existing['temporary_path'] != str(temporary_path) or existing['final_path'] != str(final_path):
                    raise Conflict('Attempt already has a different publication intent')
                return existing
            pub_id, now = _id('publication'), self.clock()
            conn.execute('INSERT INTO publications(id,job_id,attempt_id,generation,owner,temporary_path,final_path,metadata_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)', (pub_id, job_id, job['attempt_id'], generation, owner, str(temporary_path), str(final_path), canonical_json(metadata or {}), now, now))
            return self._required(conn, 'publications', pub_id)

    def list_publications(self, *, states=('pending',)):
        where, args = '', []
        if states:
            args = list(states)
            where = ' WHERE state IN (' + ','.join('?' for _ in args) + ')'
        with self._readonly() as conn:
            results = [_decode(row) for row in conn.execute('SELECT * FROM publications' + where + ' ORDER BY created_at,id', args)]
            for result in results:
                result['job'] = self._required(conn, 'jobs', result['job_id'])
                result['attempt'] = self._required(conn, 'job_attempts', result['attempt_id'])
            return results

    def _save_artifact(self, conn, artifact):
        allowed = {'id', 'broadcast_id', 'segment_id', 'kind', 'storage_id', 'relative_path', 'legacy_path', 'size', 'validation', 'validation_detail', 'exists_status', 'metadata'}
        values = {key: value for key, value in artifact.items() if key in allowed}
        artifact_id = values.pop('id', None) or _id('artifact')
        if 'metadata' in values:
            values['metadata_json'] = canonical_json(values.pop('metadata'))
        exists = conn.execute('SELECT * FROM artifacts WHERE id=?', (artifact_id,)).fetchone()
        if exists:
            if values:
                content_keys = {'storage_id', 'relative_path', 'legacy_path', 'size'}
                changed = int(any(key in values and values[key] != exists[key] for key in content_keys))
                conn.execute('UPDATE artifacts SET ' + ','.join(key + '=?' for key in values) + ',revision=revision+? WHERE id=?', [*values.values(), changed, artifact_id])
        else:
            values.setdefault('relative_path', values.get('legacy_path') or artifact_id)
            values.update(id=artifact_id, created_at=self.clock())
            conn.execute(f"INSERT INTO artifacts({','.join(values)}) VALUES ({','.join('?' for _ in values)})", list(values.values()))
        return artifact_id

    def upsert_artifact(self, artifact):
        with self._transaction() as conn:
            return self._required(conn, 'artifacts', self._save_artifact(conn, artifact))

    def finish_job(self, job_id, owner, generation, *, state='succeeded', result=None,
                   error_code='', error_detail='', retry_delay=None, artifact=None):
        if state not in {'succeeded', 'failed', 'blocked', 'cancelled', 'retry_wait'}:
            raise ValueError('Invalid terminal/retry state')
        with self._transaction() as conn:
            job = self._fenced(conn, job_id, owner, generation)
            now, result = self.clock(), dict(result or {})
            publication = conn.execute("SELECT * FROM publications WHERE job_id=? AND generation=? AND state='pending'", (job_id, generation)).fetchone()
            if publication and state != 'succeeded':
                state, error_code = 'blocked', 'PUBLICATION_RECONCILE_REQUIRED'
            if state == 'retry_wait' and job['attempt_count'] >= job['max_attempts']:
                state = 'failed'
            if artifact is not None and state != 'succeeded':
                existing_artifact = conn.execute('SELECT id FROM artifacts WHERE id=?', (artifact.get('id'),)).fetchone()
                if state != 'failed' or job['kind'] != 'verify' or not existing_artifact or artifact.get('id') not in (job['target_id'], 'legacy-recording-' + job['target_id']) or set(artifact) - {'id', 'validation', 'validation_detail', 'size'}:
                    raise ValueError('Only validation metadata may be saved for a failed job')
            if artifact is not None:
                target_id = 'legacy-recording-' + job['target_id'] if job['target_id'].isdigit() else job['target_id']
                target_table = 'broadcasts' if job['kind'] == 'merge' else 'artifacts'
                target = conn.execute(f'SELECT revision FROM {target_table} WHERE id=?', (target_id,)).fetchone()
                if target is not None and str(target[0]) != str(job['input_revision']):
                    raise Conflict('Input changed before commit', details={'code': 'INPUT_CHANGED'})
                revisions = (artifact.get('metadata') or {}).get('input_revisions') or result.get('input_revisions') or {}
                for input_id, expected_revision in revisions.items():
                    current = conn.execute('SELECT revision FROM artifacts WHERE id=?', (input_id,)).fetchone()
                    if current is None or str(current[0]) != str(expected_revision):
                        raise Conflict('Input artifact changed before commit', details={'code': 'INPUT_CHANGED'})
            if job['cancel_requested'] and state == 'succeeded':
                result['cancellation_race'] = 'completed_before_cancellation'
            artifact_id = self._save_artifact(conn, artifact) if artifact is not None else None
            if artifact_id:
                result['artifact_id'] = artifact_id
            if publication and state == 'succeeded':
                conn.execute("UPDATE publications SET state='committed',artifact_id=?,updated_at=? WHERE id=?", (artifact_id, now, publication['id']))
            delay = retry_delay if retry_delay is not None else min(900, 30 * (2 ** min(job['attempt_count'] - 1, 10))) * random.uniform(.8, 1.2)
            delay = max(0, min(900, delay))
            conn.execute('UPDATE jobs SET state=?,next_run_at=?,lease_until=NULL,owner=NULL,result_json=?,error_code=?,error_detail=?,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?', (state, now + delay if state == 'retry_wait' else now, canonical_json(result), error_code, error_detail[:2000], now, now, job_id))
            conn.execute('UPDATE job_attempts SET ended_at=?,outcome=?,error_code=?,error_detail=?,result_json=? WHERE id=?', (now, state, error_code, error_detail[:2000], canonical_json(result), job['attempt_id']))
            return self._required(conn, 'jobs', job_id)

    def request_cancel(self, job_id):
        with self._transaction() as conn:
            job = self._required(conn, 'jobs', job_id)
            if job['state'] in {'succeeded', 'cancelled', 'failed'}:
                return job
            if job['error_code'] in {'PROCESS_IDENTITY_UNCERTAIN', 'PUBLICATION_RECONCILE_REQUIRED', 'LEGACY_PROCESS_UNRECONCILED'}:
                raise Conflict('Reconcile the previous process/publication before cancelling')
            state = 'cancel_requested' if job['state'] in ACTIVE_STATES else 'cancelled'
            now = self.clock()
            conn.execute('UPDATE jobs SET state=?,cancel_requested=1,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?', (state, now, now, job_id))
            return self._required(conn, 'jobs', job_id)

    def retry_job(self, job_id):
        with self._transaction() as conn:
            job = self._required(conn, 'jobs', job_id)
            if job['state'] not in {'failed', 'blocked', 'cancelled', 'interrupted'}:
                raise Conflict('Only failed, blocked, interrupted or cancelled jobs may be retried')
            if job['error_code'] in {'PROCESS_IDENTITY_UNCERTAIN', 'PUBLICATION_RECONCILE_REQUIRED', 'LEGACY_PROCESS_UNRECONCILED'}:
                raise Conflict('Unsafe retry: previous process/publication is unresolved')
            now = self.clock()
            conn.execute("UPDATE jobs SET state='queued',cancel_requested=0,next_run_at=?,owner=NULL,lease_until=NULL,max_attempts=MAX(max_attempts,attempt_count+5),error_code='',error_detail='',updated_at=?,observed_at=?,revision=revision+1 WHERE id=?", (now, now, now, job_id))
            return self._required(conn, 'jobs', job_id)

    def recover_expired(self, process_checker, *, include_unexpired=False):
        """Checker receives an attempt; True means confirmed absent, not alive.

        External checks run outside write transactions. Unknown process identity
        remains blocked. Unreconciled publication intents can never reexecute.
        """
        with self._readonly() as conn:
            rows = conn.execute("SELECT * FROM jobs WHERE (state IN ('running','cancel_requested') AND (lease_until<=? OR ?)) OR (state='blocked' AND error_code='PROCESS_IDENTITY_UNCERTAIN')", (self.clock(), int(include_unexpired))).fetchall()
            candidates = [(dict(row), self._required(conn, 'job_attempts', row['attempt_id'])) for row in rows]
        results = []
        for candidate, attempt in candidates:
            try:
                absent = process_checker(attempt) is True
            except Exception:
                absent = False
            with self._transaction() as conn:
                job = self._required(conn, 'jobs', candidate['id'])
                if job['generation'] != candidate['generation'] or job['state'] != candidate['state'] or (not include_unexpired and (job['lease_until'] or 0) > self.clock()):
                    continue
                pending = conn.execute("SELECT 1 FROM publications WHERE job_id=? AND state='pending'", (job['id'],)).fetchone()
                if not absent:
                    state, code = 'blocked', 'PROCESS_IDENTITY_UNCERTAIN'
                elif pending:
                    state, code = 'blocked', 'PUBLICATION_RECONCILE_REQUIRED'
                elif job['cancel_requested']:
                    state, code = 'cancelled', ''
                else:
                    state, code = ('retry_wait' if job['attempt_count'] < job['max_attempts'] else 'failed'), 'WORKER_INTERRUPTED'
                now = self.clock()
                detail = 'cancel_requested' if job['state'] == 'cancel_requested' else job['error_detail']
                conn.execute('UPDATE jobs SET state=?,error_code=?,error_detail=?,owner=NULL,lease_until=NULL,next_run_at=?,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?', (state, code, detail, now, now, now, job['id']))
                conn.execute('UPDATE job_attempts SET ended_at=?,outcome=?,error_code=? WHERE id=?', (now, 'interrupted' if absent else 'unknown', code, job['attempt_id']))
                results.append(self._required(conn, 'jobs', job['id']))
        return results

    def reconcile_publication(self, publication_id, *, artifact=None, result=None,
                              expected_generation=None, process_confirmed_absent=False, published=True):
        if process_confirmed_absent is not True:
            raise Conflict('Process exit must be confirmed before reconciliation')
        with self._transaction() as conn:
            publication = self._required(conn, 'publications', publication_id)
            job = self._required(conn, 'jobs', publication['job_id'])
            if publication['state'] != 'pending':
                return job
            if job['generation'] != publication['generation'] or (expected_generation is not None and job['generation'] != expected_generation):
                raise LeaseLost('Publication belongs to an older generation')
            now, result = self.clock(), dict(result or {})
            if published and job['cancel_requested']:
                result['cancellation_race'] = 'completed_before_cancellation'
            artifact_id = self._save_artifact(conn, artifact) if published and artifact is not None else None
            if artifact_id:
                result['artifact_id'] = artifact_id
            cancelled = bool(job['cancel_requested'])
            state = 'succeeded' if published else ('cancelled' if cancelled else ('retry_wait' if job['attempt_count'] < job['max_attempts'] else 'failed'))
            conn.execute('UPDATE publications SET state=?,artifact_id=?,updated_at=? WHERE id=?', ('committed' if published else 'abandoned', artifact_id, now, publication_id))
            conn.execute('UPDATE jobs SET state=?,result_json=?,owner=NULL,lease_until=NULL,next_run_at=?,error_code=?,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?', (state, canonical_json(result), now, '' if published else 'WORKER_INTERRUPTED', now, now, job['id']))
            conn.execute('UPDATE job_attempts SET ended_at=?,outcome=?,result_json=? WHERE id=?', (now, 'succeeded' if published else ('cancelled' if cancelled else 'interrupted'), canonical_json(result), publication['attempt_id']))
            return self._required(conn, 'jobs', job['id'])

    def reject_publication(self, publication_id, error_code='PUBLICATION_RECONCILE_REQUIRED', error_detail=''):
        with self._transaction() as conn:
            publication = self._required(conn, 'publications', publication_id)
            job = self._required(conn, 'jobs', publication['job_id'])
            if job['generation'] != publication['generation'] or publication['state'] != 'pending':
                raise Conflict('Publication is not pending for the current generation')
            now = self.clock()
            conn.execute("UPDATE jobs SET state='blocked',error_code='PUBLICATION_RECONCILE_REQUIRED',error_detail=?,owner=NULL,lease_until=NULL,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?", ((error_code + ': ' + error_detail)[:2000], now, now, job['id']))
            return self._required(conn, 'jobs', job['id'])

    def abandon_publication(self, publication_id, owner, generation, *, final_confirmed_absent=False):
        if final_confirmed_absent is not True:
            raise Conflict('Must prove no final output was published')
        with self._transaction() as conn:
            publication = self._required(conn, 'publications', publication_id)
            self._fenced(conn, publication['job_id'], owner, generation)
            if publication['generation'] != generation or publication['owner'] != owner:
                raise LeaseLost('Publication belongs to another attempt')
            conn.execute("UPDATE publications SET state='abandoned',updated_at=? WHERE id=? AND state='pending'", (self.clock(), publication_id))
            return self._required(conn, 'publications', publication_id)

    def upsert_channel(self, channel_id, *, platform='', name='', desired_mode=None, metadata=None):
        if not channel_id or desired_mode not in (None, 'auto', 'paused'):
            raise ValueError('Invalid channel id or desired mode')
        with self._transaction() as conn:
            conn.execute('INSERT INTO channels(id,platform,name,desired_mode,observed_at,metadata_json) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,name=excluded.name', (channel_id, platform, name, desired_mode or 'paused', self.clock(), canonical_json(metadata or {})))
            return self._required(conn, 'channels', channel_id)

    def get_channel(self, channel_id):
        with self._readonly() as conn:
            return self._required(conn, 'channels', channel_id)

    def list_channels(self, *, limit=50, cursor=None):
        return self._page('channels', [], [], limit, cursor)

    def set_desired_mode(self, channel_id, desired_mode, expected_revision):
        if desired_mode not in ('auto', 'paused'):
            raise ValueError('desired_mode must be auto or paused')
        with self._transaction() as conn:
            channel = self._required(conn, 'channels', channel_id)
            if channel['revision'] != expected_revision:
                raise Conflict('Channel revision changed', details=channel)
            conn.execute('UPDATE channels SET desired_mode=?,revision=revision+1 WHERE id=?', (desired_mode, channel_id))
            return self._required(conn, 'channels', channel_id)

    def observe_channel(self, channel_id, actual_state, *, reason_code='', observed_at=None, current_broadcast_id=None):
        if actual_state not in ACTUAL_STATES:
            raise ValueError('Unknown actual state')
        with self._transaction() as conn:
            channel = self._required(conn, 'channels', channel_id)
            observed_at = self.clock() if observed_at is None else observed_at
            if observed_at >= channel['observed_at']:
                changed = int((actual_state, reason_code, current_broadcast_id) != (channel['actual_state'], channel['reason_code'], channel['current_broadcast_id']))
                conn.execute('UPDATE channels SET actual_state=?,reason_code=?,observed_at=?,current_broadcast_id=?,revision=revision+? WHERE id=?', (actual_state, reason_code, observed_at, current_broadcast_id, changed, channel_id))
            return self._required(conn, 'channels', channel_id)

    def create_command(self, channel_id, kind, *, idempotency_key, broadcast_id=None, request_id=''):
        if not idempotency_key or kind not in ('start_once', 'stop_current'):
            raise ValueError('A command kind and idempotency key are required')
        if kind == 'stop_current' and not broadcast_id:
            raise ValueError('stop_current requires broadcast_id')
        digest = _hash({'channel_id': channel_id, 'kind': kind, 'broadcast_id': broadcast_id})
        with self._transaction() as conn:
            existing = self._key(conn, 'commands', idempotency_key, digest)
            if existing:
                return {**self._required(conn, 'commands', existing), 'created': False}
            channel = self._required(conn, 'channels', channel_id)
            if kind == 'stop_current' and channel['current_broadcast_id'] != broadcast_id:
                raise Conflict('Current broadcast changed', details=channel)
            command_id, now = _id('command'), self.clock()
            conn.execute('INSERT INTO commands(id,channel_id,kind,broadcast_id,request_id,created_at,updated_at,observed_at) VALUES (?,?,?,?,?,?,?,?)', (command_id, channel_id, kind, broadcast_id, request_id, now, now, now))
            if kind == 'stop_current':
                conn.execute('INSERT INTO broadcast_suppressions(channel_id,broadcast_id,command_id,created_at) VALUES (?,?,?,?) ON CONFLICT(channel_id,broadcast_id) DO NOTHING', (channel_id, broadcast_id, command_id, now))
            if kind == 'stop_current':
                broadcast = conn.execute('SELECT provider_live_id FROM broadcasts WHERE id=?', (broadcast_id,)).fetchone()
                if broadcast_id.startswith('heuristic-') or (broadcast is not None and not broadcast[0]):
                    conn.execute("INSERT OR IGNORE INTO broadcast_suppressions VALUES (?, '*', ?, ?)", (channel_id, command_id, now))
            self._bind_key(conn, 'commands', idempotency_key, digest, command_id)
            return {**self._required(conn, 'commands', command_id), 'created': True}

    def get_command(self, command_id):
        with self._readonly() as conn:
            return self._required(conn, 'commands', command_id)

    def list_commands(self, *, states=None, limit=100, cursor=None):
        filters, args = [], []
        if states:
            states = list(states)
            filters.append('state IN (' + ','.join('?' for _ in states) + ')')
            args.extend(states)
        return self._page('commands', filters, args, limit, cursor)

    def update_command(self, command_id, state, *, result=None, error_code=''):
        if state not in ('accepted', 'running', 'succeeded', 'failed', 'interrupted', 'blocked'):
            raise ValueError('Unknown command state')
        with self._transaction() as conn:
            command = self._required(conn, 'commands', command_id)
            if command['state'] in ('succeeded', 'failed') and command['state'] != state:
                raise Conflict('Command has already finished')
            now = self.clock()
            conn.execute('UPDATE commands SET state=?,result_json=?,error_code=?,updated_at=?,observed_at=?,revision=revision+1 WHERE id=?', (state, canonical_json(result or {}), error_code, now, now, command_id))
            return self._required(conn, 'commands', command_id)

    def set_channel_suppression(self, channel_id, broadcast_id, command_id=None):
        with self._transaction() as conn:
            self._required(conn, 'channels', channel_id)
            conn.execute('INSERT INTO broadcast_suppressions(channel_id,broadcast_id,command_id,created_at) VALUES (?,?,?,?) ON CONFLICT(channel_id,broadcast_id) DO NOTHING', (channel_id, broadcast_id, command_id, self.clock()))

    def is_suppressed(self, channel_id, broadcast_id):
        with self._readonly() as conn:
            return conn.execute("SELECT 1 FROM broadcast_suppressions WHERE channel_id=? AND broadcast_id IN (?, '*')", (channel_id, broadcast_id)).fetchone() is not None

    def upsert_broadcast(self, broadcast_id, channel_id, *, platform='', provider_live_id=None, title='', started_at='', ended_at='', identity_basis='heuristic', status='', metadata=None):
        with self._transaction() as conn:
            self._required(conn, 'channels', channel_id)
            if provider_live_id:
                existing = conn.execute('SELECT id FROM broadcasts WHERE platform=? AND channel_id=? AND provider_live_id=?', (platform, channel_id, str(provider_live_id))).fetchone()
                if existing:
                    broadcast_id = existing[0]
            conn.execute('INSERT INTO broadcasts(id,channel_id,platform,provider_live_id,title,started_at,ended_at,identity_basis,status,observed_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,ended_at=excluded.ended_at,status=excluded.status,observed_at=excluded.observed_at,revision=broadcasts.revision+1', (broadcast_id, channel_id, platform, str(provider_live_id) if provider_live_id else None, title, started_at, ended_at, identity_basis, status, self.clock(), canonical_json(metadata or {})))
            return self._required(conn, 'broadcasts', broadcast_id)

    def get_artifact(self, artifact_id):
        artifact_id = str(artifact_id)
        if artifact_id.isdigit():
            artifact_id = 'legacy-recording-' + artifact_id
        with self._readonly() as conn:
            row = _decode(conn.execute('SELECT * FROM artifacts WHERE id=?', (artifact_id,)).fetchone())
            if row is not None:
                return row
            if artifact_id.startswith('legacy-recording-'):
                mapped = conn.execute("SELECT entity_id FROM legacy_imports WHERE entity_type='artifact' AND source_key=? ORDER BY imported_at DESC LIMIT 1", (artifact_id[len('legacy-recording-'):],)).fetchone()
                if mapped:
                    return self._required(conn, 'artifacts', mapped[0])
            raise NotFound('artifact not found')

    def list_artifacts(self, broadcast_id=None):
        with self._readonly() as conn:
            sql = 'SELECT artifacts.* FROM artifacts LEFT JOIN segments ON segments.id=artifacts.segment_id'
            args = []
            if broadcast_id:
                sql += ' WHERE artifacts.broadcast_id=?'
                args.append(broadcast_id)
            sql += ' ORDER BY segments.sequence,artifacts.created_at,artifacts.id'
            return [_decode(row) for row in conn.execute(sql, args)]

    def get_broadcast(self, broadcast_id):
        with self._readonly() as conn:
            result = self._required(conn, 'broadcasts', broadcast_id)
            result['sessions'] = [_decode(row) for row in conn.execute('SELECT * FROM sessions WHERE broadcast_id=? ORDER BY started_at,id', (broadcast_id,))]
            result['segments'] = [_decode(row) for row in conn.execute('SELECT segments.* FROM segments JOIN sessions ON sessions.id=segments.session_id WHERE sessions.broadcast_id=? ORDER BY segments.sequence,sessions.started_at', (broadcast_id,))]
            result['artifacts'] = [_decode(row) for row in conn.execute('SELECT artifacts.* FROM artifacts LEFT JOIN segments ON segments.id=artifacts.segment_id WHERE artifacts.broadcast_id=? ORDER BY segments.sequence,artifacts.created_at,artifacts.id', (broadcast_id,))]
            ids = [broadcast_id] + [item['id'] for item in result['artifacts']]
            ids.extend(str(item.get('metadata', {}).get('legacy_recording_id')) for item in result['artifacts'] if item.get('metadata', {}).get('legacy_recording_id') is not None)
            ids.extend(str(alias) for item in result['artifacts'] for alias in item.get('metadata', {}).get('legacy_recording_ids', []))
            result['jobs'] = [_decode(row) for row in conn.execute('SELECT * FROM jobs WHERE target_id IN (' + ','.join('?' for _ in ids) + ') ORDER BY created_at,id', ids)]
            return result

    def list_broadcasts(self, *, channel_id=None, platform=None, status=None, search=None, limit=50, cursor=None):
        filters, args = [], []
        for key, value in (('channel_id', channel_id), ('platform', platform), ('status', status)):
            if value:
                filters.append(key + '=?')
                args.append(value)
        if search:
            filters.append("title LIKE ? ESCAPE '\\'")
            args.append('%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        return self._page('broadcasts', filters, args, limit, cursor)

    def sync_legacy_catalog(self, catalog_path, recording_root=None):
        """Incremental one-way projection; completed v2 outputs are never reset.

        Legacy IDs and paths remain in provenance. No file is moved, renamed,
        opened for writing or guessed into a different storage root.
        """
        catalog_path = Path(catalog_path)
        if not catalog_path.exists():
            return {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': []}
        if catalog_path.resolve() == self.db_path.resolve():
            raise Conflict('The legacy and v2 databases must be different files')
        root = Path(recording_root or os.getenv('RECORDINGS_ROOT', catalog_path.parent.parent / 'chzzk')).expanduser().absolute()
        source = 'sqlite:' + str(catalog_path.resolve()) + ':recordings'
        report = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': []}
        legacy = sqlite3.connect(catalog_path.resolve().as_uri() + '?mode=ro', uri=True)
        legacy.row_factory = sqlite3.Row
        try:
            version = int(legacy.execute('PRAGMA user_version').fetchone()[0])
            if version > 4:
                raise FutureSchema(f'Legacy catalog schema {version} is newer than supported 4')
            if legacy.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RepositoryError('Legacy catalog integrity check failed')
            legacy.execute('BEGIN')
            rows = legacy.execute('SELECT * FROM recordings ORDER BY id').fetchall()
            for row in rows:
                entry = dict(row)
                try:
                    outcome = self._import_recording(entry, source, root)
                    report[outcome] += 1
                except (ValueError, sqlite3.IntegrityError, RepositoryError) as exc:
                    report['errors'].append({'source': 'recordings', 'key': str(entry.get('id', '')), 'error': str(exc)})
        finally:
            legacy.close()
        self._refresh_legacy_artifact_status(source)
        return report

    def _import_recording(self, entry, source, root):
        source_key = str(entry['id'])
        digest = _hash(entry)
        now = self.clock()
        artifact_id = 'legacy-recording-' + source_key
        channel_id = str(entry.get('channel_id') or 'legacy-unknown')
        broadcast_id = str(entry.get('broadcast_id') or 'legacy-' + source_key)
        session_id, segment_id = 'legacy-session-' + source_key, 'legacy-segment-' + source_key
        original_path = str(entry.get('file_path') or entry.get('filename') or '')
        storage_id, relative_path = 'recordings', original_path
        if original_path:
            path = Path(original_path)
            try:
                relative_path = str(path.relative_to(root)) if path.is_absolute() else str(path)
                if '\\' in relative_path or '..' in Path(relative_path).parts or relative_path in ('', '.'):
                    raise ValueError()
            except ValueError:
                storage_id, relative_path = 'legacy-unmapped', artifact_id
        else:
            storage_id, relative_path = 'legacy-unmapped', artifact_id
        with self._transaction() as conn:
            provenance = conn.execute('SELECT * FROM legacy_imports WHERE source=? AND source_key=?', (source, source_key)).fetchone()
            if provenance and provenance['source_hash'] == digest:
                return 'skipped'
            conn.execute('INSERT INTO channels(id,platform,name,observed_at) VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING', (channel_id, str(entry.get('platform') or ''), str(entry.get('channel_name') or ''), now))
            existing_broadcast = conn.execute('SELECT * FROM broadcasts WHERE id=?', (broadcast_id,)).fetchone()
            if existing_broadcast and existing_broadcast['channel_id'] != channel_id:
                raise Conflict('Legacy broadcast identity belongs to a different channel')
            if existing_broadcast is None:
                conn.execute('INSERT INTO broadcasts(id,channel_id,platform,title,started_at,ended_at,identity_basis,status,observed_at,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)', (broadcast_id, channel_id, str(entry.get('platform') or ''), str(entry.get('title') or ''), str(entry.get('started_at') or ''), str(entry.get('ended_at') or ''), 'legacy' if broadcast_id.startswith('legacy-') else 'heuristic', str(entry.get('status') or ''), now, canonical_json({'legacy_broadcast_id': broadcast_id})))
            else:
                conn.execute('UPDATE broadcasts SET title=?,ended_at=MAX(ended_at,?),status=?,observed_at=?,revision=revision+1 WHERE id=?', (str(entry.get('title') or existing_broadcast['title']), str(entry.get('ended_at') or ''), str(entry.get('status') or ''), now, broadcast_id))
            conn.execute('INSERT INTO sessions(id,broadcast_id,engine,started_at,ended_at,outcome,stop_reason,metadata_json) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ended_at=excluded.ended_at,outcome=excluded.outcome,stop_reason=excluded.stop_reason', (session_id, broadcast_id, str(entry.get('platform') or ''), str(entry.get('started_at') or ''), str(entry.get('ended_at') or ''), str(entry.get('status') or ''), str(entry.get('stop_reason') or ''), canonical_json({'legacy_recording_id': entry['id'], 'legacy_session_key': entry.get('session_key', '')})))
            conn.execute('INSERT INTO segments(id,session_id,sequence,captured_from,captured_to) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET captured_to=excluded.captured_to,sequence=excluded.sequence', (segment_id, session_id, max(1, int(entry.get('segment_index') or 1)), str(entry.get('started_at') or ''), str(entry.get('ended_at') or '')))
            artifact = _decode(conn.execute('SELECT * FROM artifacts WHERE id=?', (artifact_id,)).fetchone())
            size = max(0, int(entry.get('file_size') or 0))
            if artifact is None:
                collision = conn.execute('SELECT id FROM artifacts WHERE storage_id=? AND relative_path=?', (storage_id, relative_path)).fetchone()
                if collision:
                    # Preserve a duplicate source row without creating two
                    # independently mutable artifacts for one physical path.
                    artifact_id = collision[0]
                else:
                    self._save_artifact(conn, {'id': artifact_id, 'broadcast_id': broadcast_id, 'segment_id': segment_id, 'kind': 'original', 'storage_id': storage_id, 'relative_path': relative_path, 'legacy_path': original_path, 'size': size, 'validation': str(entry.get('validation_status') or ''), 'validation_detail': str(entry.get('validation_detail') or ''), 'metadata': {'legacy_recording_id': entry['id'], 'legacy_filename': entry.get('filename', ''), 'duration': entry.get('duration', ''), 'status': entry.get('status', ''), 'source': source}})
            elif (artifact['storage_id'], artifact['relative_path'], artifact['size']) != (storage_id, relative_path, size):
                # Input content/path changes invalidate its revision. A previous
                # validation cannot remain current when the source changed.
                self._save_artifact(conn, {'id': artifact_id, 'storage_id': storage_id, 'relative_path': relative_path, 'legacy_path': original_path, 'size': size, 'validation': '', 'validation_detail': ''})
            if artifact is not None:
                metadata = dict(artifact['metadata'])
                metadata['status'] = entry.get('status', '')
                metadata['duration'] = entry.get('duration', '')
                conn.execute('UPDATE artifacts SET metadata_json=? WHERE id=?', (canonical_json(metadata), artifact_id))
            conn.execute('INSERT INTO legacy_imports VALUES (?,?,?,?,?,?) ON CONFLICT(source,source_key) DO UPDATE SET source_hash=excluded.source_hash,entity_id=excluded.entity_id,imported_at=excluded.imported_at', (source, source_key, digest, 'artifact', artifact_id, now))
            conn.execute('INSERT INTO legacy_records VALUES (?,?,?,?) ON CONFLICT(source,source_key) DO UPDATE SET payload_json=excluded.payload_json,imported_at=excluded.imported_at', (source, source_key, canonical_json(entry), now))
            return 'updated' if provenance else 'imported'

    def import_legacy_records(self, source, records, *, kind='history'):
        """Import non-executable legacy provenance, preserving completed history.

        records contains (stable_source_key, original_dict). A malformed row is
        reported separately and never invalidates successfully imported rows.
        """
        report = {'imported': 0, 'skipped': 0, 'errors': []}
        for source_key, entry in records:
            try:
                if not isinstance(entry, dict):
                    raise ValueError('Expected a JSON object')
                digest = _hash(entry)
                with self._transaction() as conn:
                    existing = conn.execute('SELECT 1 FROM legacy_imports WHERE source=? AND source_key=?', (source, str(source_key))).fetchone()
                    if existing:
                        report['skipped'] += 1
                        continue
                    entity_id = str(entry.get('id') or source_key)
                    now = self.clock()
                    if kind == 'job':
                        entity_id = 'legacy-job-' + hashlib.sha256((source + ':' + str(source_key)).encode()).hexdigest()[:32]
                        status = str(entry.get('status') or entry.get('state') or '')
                        state = {'done': 'succeeded', 'completed': 'succeeded', 'success': 'succeeded', 'succeeded': 'succeeded', 'cancelled': 'cancelled', 'failed': 'failed', 'error': 'failed'}.get(status, 'interrupted')
                        code = 'LEGACY_PROCESS_UNRECONCILED' if state == 'interrupted' else ''
                        conn.execute('INSERT INTO jobs(id,kind,target_id,input_revision,params_hash,options_json,state,next_run_at,error_code,result_json,created_at,updated_at,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (entity_id, str(entry.get('kind') or entry.get('type') or 'legacy'), str(entry.get('target_id') or entry.get('channel_id') or entity_id), 'legacy', digest, '{}', state, now, code, canonical_json({'legacy': True, 'status': status}), now, now, now))
                    conn.execute('INSERT INTO legacy_imports VALUES (?,?,?,?,?,?)', (source, str(source_key), digest, kind, entity_id, now))
                    conn.execute('INSERT INTO legacy_records VALUES (?,?,?,?)', (source, str(source_key), canonical_json(entry), now))
                report['imported'] += 1
            except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
                report['errors'].append({'key': str(source_key), 'error': str(exc)})
        return report

    def integrity_check(self):
        with self._readonly() as conn:
            integrity = [row[0] for row in conn.execute('PRAGMA integrity_check')]
            foreign_keys = [list(row) for row in conn.execute('PRAGMA foreign_key_check')]
            counts = {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('channels', 'broadcasts', 'sessions', 'segments', 'artifacts', 'jobs', 'job_attempts', 'legacy_imports')}
            return {'ok': integrity == ['ok'] and not foreign_keys, 'integrity': integrity, 'foreign_keys': foreign_keys, 'counts': counts}

    def job_counts(self):
        with self._readonly() as conn:
            counts = {state: 0 for state in JOB_STATES}
            counts.update({row[0]: row[1] for row in conn.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state')})
            return counts

    def lookup_job_request(self, kind, target_id, input_revision=1, options=None, idempotency_key=None, max_attempts=5):
        """Resolve replay before mutable target checks; never creates a job."""
        options = {} if options is None else options
        digest = _hash({'kind': kind, 'target_id': str(target_id), 'input_revision': str(input_revision), 'options': options, 'max_attempts': max_attempts})
        with self._readonly() as conn:
            existing = self._key(conn, 'jobs', idempotency_key, digest)
            if existing:
                return self._required(conn, 'jobs', existing)
            return _decode(conn.execute('SELECT * FROM jobs WHERE kind=? AND target_id=? AND input_revision=? AND params_hash=?', (kind, str(target_id), str(input_revision), _hash(options))).fetchone())

    def _refresh_legacy_artifact_status(self, source):
        # Multiple historical catalog rows may name the same file. Keep one
        # artifact, resolve every alias, and fail closed if any row is active.
        with self._transaction() as conn:
            rows = conn.execute("SELECT i.entity_id,r.payload_json FROM legacy_imports i JOIN legacy_records r ON r.source=i.source AND r.source_key=i.source_key WHERE i.source=? AND i.entity_type='artifact'", (source,)).fetchall()
            grouped = {}
            for row in rows:
                grouped.setdefault(row['entity_id'], []).append(json.loads(row['payload_json']))
            for artifact_id, entries in grouped.items():
                artifact = self._required(conn, 'artifacts', artifact_id)
                metadata = dict(artifact['metadata'])
                active = any(entry.get('status') in ('recording', 'starting', 'reconnecting', 'stopping') for entry in entries)
                metadata['status'] = 'recording' if active else str(entries[-1].get('status') or '')
                metadata['legacy_recording_ids'] = [entry['id'] for entry in entries]
                if metadata != artifact['metadata']:
                    conn.execute('UPDATE artifacts SET metadata_json=? WHERE id=?', (canonical_json(metadata), artifact_id))
