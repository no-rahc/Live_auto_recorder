"""Deterministic durable-job, migration and storage fault regressions."""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from module.v2_repository import APPLICATION_ID, Conflict, FutureSchema, LeaseLost, NotFound, V2Repository
from module.v2_storage import StorageError, StorageRoot, preflight_database_location, preflight_storage, resolve_storage_path
from scripts.migrate_v2 import migrate, preflight

class Clock:
    def __init__(self):
        self.now = 1000.0
    def __call__(self):
        return self.now

class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.repo = V2Repository(self.root / 'v2.sqlite3', clock=self.clock)
        self.repo.initialize()

    def claim(self, kind='verify', target='a', **kwargs):
        job = self.repo.create_job(kind, target, **kwargs)
        return self.repo.claim_job('worker')

    def domain(self, artifact_id='a'):
        self.repo.upsert_channel('c', name='Channel')
        self.repo.upsert_broadcast('b', 'c', title='Broadcast')
        return self.repo.upsert_artifact({'id': artifact_id, 'broadcast_id': 'b', 'storage_id': 'recordings', 'relative_path': artifact_id + '.ts', 'size': 12})

    def test_parallel_idempotency_and_single_claim(self):
        def create(_):
            return self.repo.create_job('verify', 'a', options={'z': 1, 'a': 2}, idempotency_key='request')['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(create, range(24)))
        self.assertEqual(len(set(ids)), 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            claimed = list(pool.map(lambda i: self.repo.claim_job('worker-' + str(i)), range(16)))
        self.assertEqual(sum(item is not None for item in claimed), 1)
        self.assertEqual(len(self.repo.get_attempts(ids[0])), 1)
        with self.assertRaises(Conflict):
            self.repo.create_job('verify', 'different', idempotency_key='request')
        self.assertEqual(self.repo.lookup_job_request('verify', 'a', options={'a': 2, 'z': 1}, idempotency_key='request')['id'], ids[0])

    def test_logical_uniqueness_independent_of_request_key(self):
        first = self.repo.create_job('merge', 'b', options={'b': [1, 2], 'a': True}, idempotency_key='one')
        same = self.repo.create_job('merge', 'b', options={'a': True, 'b': [1, 2]}, idempotency_key='two')
        different = self.repo.create_job('merge', 'b', options={'a': True, 'b': [2, 1]})
        self.assertEqual(first['id'], same['id'])
        self.assertNotEqual(first['id'], different['id'])
        with self.assertRaises(Conflict):
            self.repo.lookup_job_request('merge', 'changed', idempotency_key='one')

    def test_expired_lease_is_not_automatically_claimed(self):
        job = self.claim()
        self.clock.now += 91
        self.assertIsNone(self.repo.claim_job('new'))
        for operation in (lambda: self.repo.heartbeat(job['id'], 'worker', job['generation']),
                          lambda: self.repo.finish_job(job['id'], 'worker', job['generation'])):
            with self.assertRaises(LeaseLost):
                operation()
        result = self.repo.recover_expired(lambda attempt: None)[0]
        self.assertEqual(result['state'], 'blocked')
        with self.assertRaises(Conflict):
            self.repo.retry_job(job['id'])
        self.assertIsNone(self.repo.claim_job('new'))
        self.repo.recover_expired(lambda attempt: True)
        new = self.repo.claim_job('new')
        self.assertEqual(new['generation'], 2)
        self.assertEqual(new['attempt_count'], 2)
        with self.assertRaises(LeaseLost):
            self.repo.finish_job(job['id'], 'worker', 1)

    def test_owner_fencing_even_with_correct_generation(self):
        job = self.claim()
        with self.assertRaises(LeaseLost):
            self.repo.finish_job(job['id'], 'another', job['generation'])
        self.assertEqual(self.repo.get_job(job['id'])['state'], 'running')

    def test_startup_known_dead_recovery_without_waiting_for_lease(self):
        job = self.claim()
        self.assertEqual(self.repo.recover_expired(lambda _: True), [])
        recovered = self.repo.recover_expired(lambda _: True, include_unexpired=True)
        self.assertEqual(recovered[0]['state'], 'retry_wait')
        self.assertEqual(self.repo.get_attempts(job['id'])[0]['outcome'], 'interrupted')

    def test_recovery_checker_exception_blocks(self):
        job = self.claim()
        self.clock.now += 91
        def broken(_):
            raise OSError('cannot inspect PID')
        self.assertEqual(self.repo.recover_expired(broken)[0]['state'], 'blocked')
        self.assertEqual(self.repo.get_job(job['id'])['error_code'], 'PROCESS_IDENTITY_UNCERTAIN')

    def test_cancel_requires_execution_acknowledgement(self):
        job = self.claim()
        self.assertEqual(self.repo.request_cancel(job['id'])['state'], 'cancel_requested')
        self.assertEqual(self.repo.heartbeat(job['id'], 'worker', job['generation'])['state'], 'cancel_requested')
        final = self.repo.finish_job(job['id'], 'worker', job['generation'], state='cancelled')
        self.assertEqual(final['state'], 'cancelled')
        queued = self.repo.create_job('verify', 'b')
        self.assertEqual(self.repo.request_cancel(queued['id'])['state'], 'cancelled')

    def test_unknown_process_recovery_keeps_cancellation(self):
        job = self.claim()
        self.repo.request_cancel(job['id'])
        self.clock.now += 91
        self.repo.recover_expired(lambda _: None)
        self.repo.recover_expired(lambda _: True)
        self.assertEqual(self.repo.get_job(job['id'])['state'], 'cancelled')

    def test_retry_budget_and_attempt_history(self):
        job = self.claim(max_attempts=2)
        self.repo.finish_job(job['id'], 'worker', 1, state='retry_wait', retry_delay=30)
        self.assertIsNone(self.repo.claim_job('worker'))
        self.clock.now += 30
        job = self.repo.claim_job('worker')
        final = self.repo.finish_job(job['id'], 'worker', 2, state='retry_wait')
        self.assertEqual(final['state'], 'failed')
        self.repo.retry_job(job['id'])
        self.assertEqual(self.repo.claim_job('worker')['attempt_count'], 3)
        self.assertEqual(len(self.repo.get_attempts(job['id'])), 3)

    def test_pending_publication_never_requeues_on_crash(self):
        job = self.claim('recover')
        self.repo.record_publication(job['id'], 'worker', 1, 'temp', 'final')
        self.clock.now += 91
        self.assertEqual(self.repo.recover_expired(lambda _: True)[0]['error_code'], 'PUBLICATION_RECONCILE_REQUIRED')
        self.assertIsNone(self.repo.claim_job('new'))
        with self.assertRaises(Conflict):
            self.repo.retry_job(job['id'])
        publications = self.repo.list_publications()
        self.assertEqual(publications[0]['job']['id'], job['id'])
        self.assertEqual(publications[0]['attempt']['lease_generation'], 1)

    def test_cancel_then_absent_publication_stays_cancelled(self):
        job = self.claim('recover')
        pub = self.repo.record_publication(job['id'], 'worker', 1, 'temp', 'final')
        self.repo.request_cancel(job['id'])
        final = self.repo.reconcile_publication(pub['id'], published=False, expected_generation=1, process_confirmed_absent=True)
        self.assertEqual(final['state'], 'cancelled')
        self.assertEqual(self.repo.get_attempts(job['id'])[0]['outcome'], 'cancelled')
        self.assertIsNone(self.repo.claim_job('new'))

    def test_rejected_publication_keeps_cancellation_intent(self):
        job = self.claim('recover')
        pub = self.repo.record_publication(job['id'], 'worker', 1, 'temp', 'final')
        self.repo.request_cancel(job['id'])
        self.repo.reject_publication(pub['id'], error_code='PROCESS_UNCERTAIN', error_detail='Cannot inspect old process')
        final = self.repo.reconcile_publication(pub['id'], published=False, expected_generation=1, process_confirmed_absent=True)
        self.assertEqual(final['state'], 'cancelled')
        self.assertIsNone(self.repo.claim_job('new'))

    def test_published_output_wins_cancellation_race_without_delete(self):
        self.domain()
        job = self.claim('recover')
        pub = self.repo.record_publication(job['id'], 'worker', 1, 'temp', 'final')
        self.repo.request_cancel(job['id'])
        final = self.repo.finish_job(job['id'], 'worker', 1, artifact={'id': 'out', 'broadcast_id': 'b', 'storage_id': 'recordings', 'relative_path': 'out.mp4'})
        self.assertEqual(final['state'], 'succeeded')
        self.assertIn('cancellation_race', final['result'])
        self.assertEqual(self.repo.list_publications(states=('committed',))[0]['artifact_id'], 'out')

    def test_publication_requires_absence_evidence(self):
        job = self.claim('recover')
        pub = self.repo.record_publication(job['id'], 'worker', 1, 'temp', 'final')
        with self.assertRaises(Conflict):
            self.repo.reconcile_publication(pub['id'], published=False)
        with self.assertRaises(Conflict):
            self.repo.abandon_publication(pub['id'], 'worker', 1)
        self.repo.abandon_publication(pub['id'], 'worker', 1, final_confirmed_absent=True)
        self.assertEqual(self.repo.finish_job(job['id'], 'worker', 1, state='cancelled')['state'], 'cancelled')

    def test_validation_metadata_does_not_invalidate_input_retry(self):
        self.domain()
        job = self.claim()
        self.repo.finish_job(job['id'], 'worker', 1, state='failed', error_code='MEDIA_INVALID', artifact={'id': 'a', 'validation': 'invalid', 'size': 12})
        self.assertEqual(self.repo.get_artifact('a')['revision'], 1)
        self.repo.retry_job(job['id'])
        retried = self.repo.claim_job('worker')
        self.repo.finish_job(job['id'], 'worker', retried['generation'], artifact={'id': 'a', 'validation': 'ok', 'size': 12})
        self.assertEqual(self.repo.get_artifact('a')['revision'], 1)

    def test_failed_job_cannot_create_or_modify_unrelated_artifact(self):
        self.domain()
        self.repo.upsert_artifact({'id': 'other', 'storage_id': 'recordings', 'relative_path': 'other'})
        job = self.claim()
        for target in ('out', 'other'):
            with self.assertRaises(ValueError):
                self.repo.finish_job(job['id'], 'worker', 1, state='failed', artifact={'id': target, 'validation': 'invalid'})
        self.assertEqual(self.repo.get_job(job['id'])['state'], 'running')

    def test_content_change_before_commit_rolls_back_artifact_and_job(self):
        self.domain()
        job = self.claim('recover')
        self.repo.upsert_artifact({'id': 'a', 'size': 13})
        with self.assertRaises(Conflict):
            self.repo.finish_job(job['id'], 'worker', 1, artifact={'id': 'out', 'relative_path': 'out'})
        self.assertEqual(self.repo.get_job(job['id'])['state'], 'running')
        with self.assertRaises(NotFound):
            self.repo.get_artifact('out')

    def test_input_revision_map_is_checked_atomically(self):
        self.domain()
        job = self.claim('merge', target='b')
        self.repo.upsert_artifact({'id': 'a', 'size': 99})
        with self.assertRaises(Conflict):
            self.repo.finish_job(job['id'], 'worker', 1, artifact={'id': 'out', 'relative_path': 'out', 'metadata': {'input_revisions': {'a': 1}}})

    def test_channels_intent_observation_and_idempotent_commands(self):
        channel = self.repo.upsert_channel('c', desired_mode='auto')
        self.repo.upsert_channel('c', desired_mode='paused')
        self.assertEqual(self.repo.get_channel('c')['desired_mode'], 'auto')
        channel = self.repo.set_desired_mode('c', 'paused', channel['revision'])
        with self.assertRaises(Conflict):
            self.repo.set_desired_mode('c', 'auto', 1)
        self.repo.upsert_broadcast('heuristic-b', 'c')
        channel = self.repo.observe_channel('c', 'recording', current_broadcast_id='heuristic-b')
        repeated = self.repo.observe_channel('c', 'recording', current_broadcast_id='heuristic-b', observed_at=1001)
        self.assertEqual(channel['revision'], repeated['revision'])
        command = self.repo.create_command('c', 'stop_current', idempotency_key='stop', broadcast_id='heuristic-b')
        self.assertTrue(command['created'])
        self.assertTrue(self.repo.is_suppressed('c', 'new-unknown-broadcast'))
        self.repo.observe_channel('c', 'idle', observed_at=1002)
        replay = self.repo.create_command('c', 'stop_current', idempotency_key='stop', broadcast_id='heuristic-b')
        self.assertEqual(command['id'], replay['id'])
        self.assertFalse(replay['created'])
        with self.assertRaises(Conflict):
            self.repo.create_command('c', 'stop_current', idempotency_key='different', broadcast_id='stale')
        self.assertFalse(self.repo.is_suppressed('another-channel', 'stale'))

    def test_provider_identity_survives_title_changes(self):
        self.repo.upsert_channel('c')
        first = self.repo.upsert_broadcast('one', 'c', platform='p', provider_live_id='provider', title='Old')
        second = self.repo.upsert_broadcast('two', 'c', platform='p', provider_live_id='provider', title='New')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(self.repo.list_broadcasts()['items'][0]['title'], 'New')

    def test_stable_cursor_and_full_counts(self):
        for number in range(207):
            self.repo.create_job('verify', str(number))
        ids, cursor = [], None
        while True:
            page = self.repo.list_jobs(limit=23, cursor=cursor)
            ids.extend(item['id'] for item in page['items'])
            cursor = page['next_cursor']
            if not cursor:
                break
        self.assertEqual(len(ids), 207)
        self.assertEqual(len(set(ids)), 207)
        self.assertEqual(self.repo.job_counts()['queued'], 207)
        with self.assertRaises(ValueError):
            self.repo.list_jobs(cursor='not-a-cursor')

    def test_backup_integrity_future_refusal_and_no_clobber(self):
        self.repo.create_job('verify', 'a')
        backup = self.root / 'backup.sqlite3'
        report = self.repo.backup(backup)
        self.assertEqual(report['sha256'], hashlib.sha256(backup.read_bytes()).hexdigest())
        with self.assertRaises(Conflict):
            self.repo.backup(backup)
        with sqlite3.connect(backup) as conn:
            conn.execute('PRAGMA user_version=999')
        conn.close()
        before = backup.read_bytes()
        with self.assertRaises(FutureSchema):
            V2Repository(backup).initialize()
        self.assertEqual(before, backup.read_bytes())
        self.assertFalse(Path(str(backup) + '-wal').exists())

    def test_disk_full_before_commit_rolls_back_job_and_idempotency_key(self):
        original = self.repo._connect
        class FailedCommit:
            def __init__(self, connection):
                self.connection = connection
            def __getattr__(self, name):
                return getattr(self.connection, name)
            def commit(self):
                raise sqlite3.OperationalError('database or disk is full')
        with mock.patch.object(self.repo, '_connect', side_effect=lambda: FailedCommit(original())):
            with self.assertRaises(sqlite3.OperationalError):
                self.repo.create_job('verify', 'a', idempotency_key='full')
        self.assertEqual(sum(self.repo.job_counts().values()), 0)
        self.assertIsNone(self.repo.lookup_job_request('verify', 'a', idempotency_key='full'))
        self.assertIsNotNone(self.repo.create_job('verify', 'a', idempotency_key='full'))

    def test_failed_artifact_commit_preserves_pending_publication(self):
        self.domain()
        job = self.claim('recover')
        self.repo.record_publication(job['id'], 'worker', 1, 'temporary', 'final')
        with mock.patch.object(self.repo, '_save_artifact', side_effect=sqlite3.OperationalError('database or disk is full')):
            with self.assertRaises(sqlite3.OperationalError):
                self.repo.finish_job(job['id'], 'worker', 1, artifact={'id': 'out', 'relative_path': 'out'})
        self.assertEqual(self.repo.get_job(job['id'])['state'], 'running')
        self.assertEqual(self.repo.list_publications()[0]['state'], 'pending')
        self.assertEqual(self.repo.get_artifact('a')['size'], 12)

    def test_integrity_and_foreign_keys(self):
        self.domain()
        self.claim()
        self.assertTrue(self.repo.integrity_check()['ok'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.upsert_artifact({'id': 'bad', 'broadcast_id': 'missing', 'relative_path': 'bad'})

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.media = self.root / 'media'
        self.media.mkdir()
        (self.media / 'first.ts').write_bytes(b'original-video')
        self.catalog = self.data / 'recordings.sqlite3'
        with sqlite3.connect(self.catalog) as conn:
            conn.executescript('''PRAGMA user_version=4;
              CREATE TABLE recordings(id INTEGER PRIMARY KEY,session_key TEXT,channel_id TEXT,channel_name TEXT,platform TEXT,title TEXT,broadcast_id TEXT,segment_index INTEGER,file_path TEXT,file_size INTEGER,status TEXT,started_at TEXT,ended_at TEXT,validation_status TEXT,validation_detail TEXT);
              CREATE TABLE notification_queue(id INTEGER PRIMARY KEY,status TEXT,delivery_json TEXT);
              CREATE TABLE archive_jobs(id INTEGER PRIMARY KEY,status TEXT);
            ''')
            conn.execute('INSERT INTO recordings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (1, 'session1', 'c', 'Channel', 'chzzk', 'Show', 'broadcast', 1, str(self.media / 'first.ts'), 14, 'completed', '2026-10-10', '2026-10-11', '', ''))
            conn.execute("INSERT INTO notification_queue VALUES (1,'sent','{\"attempts\":1}')")
            conn.execute("INSERT INTO archive_jobs VALUES (1,'completed')")
        (self.data / 'config.json').write_text(json.dumps({'unknownSetting': {'keep': 7}, 'password': 'secret-value'}))
        (self.data / 'channels.json').write_text(json.dumps([{'id': 'c', 'record_enabled': True, 'name': 'Channel'}]))
        (self.data / 'operations_jobs.json').write_text(json.dumps([{'id': 'done', 'kind': 'postprocess', 'status': 'done'}, {'id': 'active', 'kind': 'postprocess', 'status': 'running'}]))
        (self.data / 'recording_history.jsonl').write_text('{"event":"recording_stopped","id":"evt"}\n{broken\n{"event":"another"}\n')
        (self.data / 'cookie.json').write_text('{"secret":"cookie"}')

    def snapshots(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

    def test_dry_run_is_read_only_and_reports_bad_jsonl(self):
        before = self.snapshots()
        report = migrate(self.data, recording_root=self.media)
        self.assertTrue(report['ok'])
        self.assertTrue(report['dry_run'])
        self.assertEqual(report['invalid_rows'][0]['line'], 2)
        self.assertEqual(before, self.snapshots())
        self.assertNotIn('secret-value', json.dumps(report))

    def test_apply_requires_quiescence_and_original_image(self):
        before = self.snapshots()
        report = migrate(self.data, apply=True)
        self.assertFalse(report['ok'])
        self.assertEqual(before, self.snapshots())

    def test_backup_failure_does_not_start_import_or_mutate_sources(self):
        before = self.snapshots()
        with mock.patch('scripts.migrate_v2._sqlite_backup', side_effect=OSError('No space left on device')):
            report = migrate(self.data, recording_root=self.media, apply=True, stopped=True, image_id='sha256:old')
        self.assertFalse(report['ok'])
        self.assertEqual(report['phase'], 'failed')
        self.assertFalse((self.data / 'recorder_v2.sqlite3').exists())
        for name, content in before.items():
            self.assertEqual(content, (self.root / name).read_bytes())
        self.assertEqual(json.loads(Path(report['manifest']).read_text())['phase'], 'failed')

    def test_explicit_secret_backup_is_private_and_opt_in(self):
        report = migrate(self.data, recording_root=self.media, apply=True, stopped=True, image_id='sha256:old', include_secrets=True)
        self.assertTrue(report['ok'], report)
        directory = Path(report['manifest']).parent
        self.assertEqual((directory.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((directory / 'cookie.json').stat().st_mode & 0o777), 0o600)
        self.assertEqual((directory / 'cookie.json').read_bytes(), (self.data / 'cookie.json').read_bytes())
        self.assertEqual(json.loads((directory / 'config.json').read_text())['password'], 'secret-value')

    def test_additive_import_rerun_and_sanitized_backup(self):
        before = self.snapshots()
        report = migrate(self.data, recording_root=self.media, apply=True, stopped=True, image_id='sha256:old')
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['phase'], 'ready_for_opt_in')
        for name, content in before.items():
            self.assertEqual(content, (self.root / name).read_bytes())
        directory = Path(report['manifest']).parent
        self.assertFalse((directory / 'cookie.json').exists())
        config = json.loads((directory / 'config.json').read_text())
        self.assertEqual(config, {'unknownSetting': {'keep': 7}})
        repo = V2Repository(self.data / 'recorder_v2.sqlite3')
        self.assertEqual(repo.get_artifact(1)['relative_path'], 'first.ts')
        self.assertEqual(repo.get_artifact(1)['metadata']['status'], 'completed')
        self.assertEqual(repo.get_channel('c')['desired_mode'], 'auto')
        counts = repo.integrity_check()['counts']
        self.assertEqual(repo.job_counts()['succeeded'], 1)
        self.assertEqual(repo.job_counts()['interrupted'], 1)
        pending = repo.list_jobs(states=['interrupted'])['items'][0]
        with self.assertRaises(Conflict):
            repo.retry_job(pending['id'])
        again = migrate(self.data, recording_root=self.media, apply=True, stopped=True, image_id='sha256:old')
        self.assertTrue(again['ok'], again)
        self.assertEqual(counts, repo.integrity_check()['counts'])
        self.assertIsNone(repo.claim_job('worker'))

    def test_sync_preserves_v2_validation_and_updates_active_status(self):
        repo = V2Repository(self.data / 'sidecar.db')
        repo.initialize()
        report = repo.sync_legacy_catalog(self.catalog, self.media)
        self.assertEqual(report['imported'], 1)
        repo.upsert_artifact({'id': 'legacy-recording-1', 'validation': 'ok'})
        with sqlite3.connect(self.catalog) as conn:
            conn.execute("UPDATE recordings SET title='Changed',status='recording'")
        repo.sync_legacy_catalog(self.catalog, self.media)
        artifact = repo.get_artifact(1)
        self.assertEqual(artifact['validation'], 'ok')
        self.assertEqual(artifact['revision'], 1)
        self.assertEqual(artifact['metadata']['status'], 'recording')
        self.assertEqual(repo.sync_legacy_catalog(self.catalog, self.media)['skipped'], 1)

    def test_content_change_invalidates_validation_but_keeps_exact_path(self):
        repo = V2Repository(self.data / 'sidecar.db')
        repo.initialize()
        repo.sync_legacy_catalog(self.catalog, self.media)
        repo.upsert_artifact({'id': 'legacy-recording-1', 'validation': 'ok'})
        with sqlite3.connect(self.catalog) as conn:
            conn.execute('UPDATE recordings SET file_size=100')
        repo.sync_legacy_catalog(self.catalog, self.media)
        artifact = repo.get_artifact(1)
        self.assertEqual(artifact['revision'], 2)
        self.assertEqual(artifact['validation'], '')
        self.assertEqual(artifact['legacy_path'], str(self.media / 'first.ts'))
        self.assertEqual((self.media / 'first.ts').read_bytes(), b'original-video')

    def test_future_catalog_and_broken_json_refused_without_writes(self):
        with sqlite3.connect(self.catalog) as conn:
            conn.execute('PRAGMA user_version=99')
        before = self.snapshots()
        self.assertFalse(preflight(self.data)['ok'])
        self.assertEqual(before, self.snapshots())
        repo = V2Repository(self.data / 'sidecar.db')
        repo.initialize()
        with self.assertRaises(FutureSchema):
            repo.sync_legacy_catalog(self.catalog, self.media)
        (self.data / 'config.json').write_text('{broken')
        self.assertFalse(preflight(self.data)['ok'])

    def test_duplicate_path_alias_resolves_and_active_source_fails_closed(self):
        with sqlite3.connect(self.catalog) as conn:
            conn.execute("INSERT INTO recordings SELECT 2,'session2',channel_id,channel_name,platform,title,broadcast_id,2,file_path,file_size,'recording',started_at,ended_at,validation_status,validation_detail FROM recordings WHERE id=1")
        repo = V2Repository(self.data / 'sidecar.db')
        repo.initialize()
        report = repo.sync_legacy_catalog(self.catalog, self.media)
        self.assertEqual(report['imported'], 2)
        self.assertEqual(repo.get_artifact('2')['id'], 'legacy-recording-1')
        self.assertEqual(repo.get_artifact('legacy-recording-2')['id'], 'legacy-recording-1')
        self.assertEqual(repo.get_artifact('1')['metadata']['status'], 'recording')
        self.assertEqual(repo.get_artifact('1')['metadata']['legacy_recording_ids'], [1, 2])
        self.assertEqual(len(repo.list_artifacts()), 1)
        self.assertEqual(repo.sync_legacy_catalog(self.catalog, self.media)['skipped'], 2)
        self.assertEqual(repo.get_artifact('1')['metadata']['status'], 'recording')

    def test_outside_paths_are_preserved_but_unmapped(self):
        outside = str(self.root / 'outside.ts')
        with sqlite3.connect(self.catalog) as conn:
            conn.execute('UPDATE recordings SET file_path=?', (outside,))
        repo = V2Repository(self.data / 'sidecar.db')
        repo.initialize()
        repo.sync_legacy_catalog(self.catalog, self.media)
        self.assertEqual(repo.get_artifact(1)['storage_id'], 'legacy-unmapped')
        self.assertEqual(repo.get_artifact(1)['legacy_path'], outside)

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'file.ts').write_bytes(b'source')
        self.storage = StorageRoot('recordings', self.root)

    def test_path_traversal_absolute_and_symlinks_rejected(self):
        (self.root / 'alias.ts').symlink_to(self.root / 'file.ts')
        for path in ('../outside', '/etc/passwd', 'nested/../../outside', 'alias.ts', 'folder\\file'):
            with self.subTest(path=path), self.assertRaises(StorageError):
                resolve_storage_path(self.storage, path)
        self.assertEqual(resolve_storage_path(self.storage, 'file.ts'), self.root / 'file.ts')
        self.assertEqual(resolve_storage_path(self.storage, 'new.ts', must_exist=False), self.root / 'new.ts')

    def test_missing_marker_fail_closed_without_creating_root(self):
        missing = self.root / 'disconnected'
        report = preflight_storage(StorageRoot('nas', missing, marker='.identity', expected_marker='nas1'), probe_writes=True)
        self.assertFalse(report['ok'])
        self.assertFalse(missing.exists())
        report = preflight_storage(StorageRoot('nas', self.root, marker='.identity', expected_marker='nas1'), probe_writes=True)
        self.assertFalse(report['ok'])
        self.assertFalse((self.root / '.identity').exists())

    def test_read_only_preflight_and_no_clobber_probe(self):
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.assertTrue(preflight_storage(self.storage)['ok'])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})
        report = preflight_storage(self.storage, probe_writes=True)
        self.assertTrue(report['ok'], report)
        self.assertTrue(report['checks']['hardlink_publication'])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.root.iterdir()})

    def test_hardlink_failure_cleans_only_probe(self):
        with mock.patch('module.v2_storage.os.link', side_effect=OSError('not supported')):
            self.assertFalse(preflight_storage(self.storage, probe_writes=True)['ok'])
        self.assertEqual([path.name for path in self.root.iterdir()], ['file.ts'])
        self.assertEqual((self.root / 'file.ts').read_bytes(), b'source')

    def test_low_space_wrong_marker_and_remote_sqlite_blocked(self):
        (self.root / '.identity').write_text('NAS-A')
        self.assertFalse(preflight_storage(StorageRoot('nas', self.root, '.identity', 'NAS-B'))['ok'])
        self.assertFalse(preflight_storage(StorageRoot('nas', self.root, min_free_bytes=2**63))['ok'])
        with mock.patch('module.v2_storage.filesystem_info', return_value={'filesystem': 'nfs4'}):
            self.assertFalse(preflight_database_location(self.root)['ok'])

if __name__ == '__main__':
    unittest.main()
