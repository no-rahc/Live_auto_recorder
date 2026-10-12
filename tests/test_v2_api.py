"""v2 compatibility, API contracts, and request-origin boundaries."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI
from lar_app.routers.v2 import install_v2_routes
from lar_app.web.v2_security import V2OriginMiddleware

class V2ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'LAR_V2_ENABLED': '1'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.app = FastAPI()
        self.service = SimpleNamespace(list_channels=Mock(return_value=[{'id':'one','name':'One','platform':'chzzk','desired_mode':'auto','actual_state':'watching','revision':1}]), patch_mode=AsyncMock(return_value={'id':'one','desired_mode':'paused','actual_state':'recording','revision':2}), command=AsyncMock(return_value={'id':'cmd1','state':'accepted'}), get_command=Mock(return_value={'id':'cmd1','state':'accepted'}))
        self.app.state.v2_channels = self.service
        self.core = SimpleNamespace(requireLogin=lambda: True)
        install_v2_routes(self.app, self.core)
        self.app.add_middleware(V2OriginMiddleware)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://localhost')
        self.addAsyncCleanup(self.client.aclose)

    async def test_default_ui_reads_legacy_without_durable_repository(self):
        self.app.state.channels_lock = asyncio.Lock()
        self.app.state.channels = [{'id': 'one', 'name': 'One', 'platform': 'chzzk', 'record_enabled': True, 'token': 'secret'}]
        self.app.state.fsm = SimpleNamespace(getState=lambda cid: 'WATCHING')
        self.core.recorder_manager = SimpleNamespace(get_status_recording=lambda cid: False, get_status_reserved=lambda cid: True)
        self.core.toBool = bool
        with patch.dict(os.environ, {'LAR_V2_ENABLED': '0'}), patch('lar_app.routers.v2.get_repository', side_effect=AssertionError('must not open durable DB')), patch('lar_app.routers.v2.sync_catalog', side_effect=AssertionError('must not migrate')):
            response = await self.client.get('/api/v2/channels')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['items'][0]['actual_state'], 'watching')
            self.assertFalse(response.json()['items'][0]['controls_available'])
            self.assertNotIn('secret', response.text)
            status = (await self.client.get('/api/v2/status')).json()
            self.assertEqual(status['channels']['watching'], 1)
            self.assertFalse(status['features']['durable_jobs'])
            self.assertEqual(status['storage']['status'], 'unknown')
            self.assertNotIn('worker', status)
            self.assertFalse((await self.client.get('/api/v2/jobs')).json()['available'])
            self.assertFalse((await self.client.get('/api/v2/settings')).json()['features']['durable_jobs'])
            self.assertEqual((await self.client.get('/api/v2/jobs/old')).status_code, 404)
            self.assertEqual((await self.client.get('/api/v2/commands/old')).status_code, 404)
            response = await self.client.post('/api/v2/channels/one/commands', json={'kind': 'start_once'}, headers={'Idempotency-Key': 'key'})
            self.assertEqual(response.status_code, 409)
            self.service.command.assert_not_awaited()
            source = {'broadcast_id': 'b', 'title': 'Broadcast', 'merge': {'output_path': '/private'}, 'segments': [{'id': 1, 'filename': 'recording.ts', 'file_path': '/private/path', 'file_size': 42}]}
            with patch('lar_app.routers.v2.catalog.get_broadcast', return_value=source):
                detail = await self.client.get('/api/v2/broadcasts/b')
            self.assertEqual(detail.status_code, 200)
            self.assertNotIn('/private', detail.text)
            self.assertFalse(detail.json()['jobs_available'])
            self.assertEqual(detail.json()['artifacts'][0]['size'], 42)
            self.assertIsNone(detail.json()['artifacts'][0]['exists'])

    async def test_root_defaults_v2_and_preserves_legacy_with_missing_build_fallback(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'LAR_V2_ENABLED': '0'}):
            app = FastAPI()
            @app.get('/')
            async def old_dashboard():
                return {'screen': 'legacy'}
            install_v2_routes(app, self.core, root_dir=Path(root))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
                self.assertEqual((await client.get('/')).headers['location'], '/legacy')
                target = Path(root) / 'templates/static/v2'
                target.mkdir(parents=True)
                (target / 'index.html').write_text('<html>v2 screen</html>')
                for _ in range(2):
                    response = await client.get('/')
                    self.assertEqual(response.headers['location'], '/v2')
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertEqual((await client.get('/legacy')).json()['screen'], 'legacy')
                    self.assertIn('v2 screen', (await client.get('/v2/channels')).text)

    async def test_channels_separate_intent_actual_and_have_envelope(self):
        result = (await self.client.get('/api/v2/channels')).json()
        self.assertEqual(result['items'][0]['desired_mode'], 'auto')
        self.assertEqual(result['items'][0]['actual_state'], 'watching')
        self.assertIsNone(result['next_cursor'])

    async def test_patch_does_not_claim_actual_stop(self):
        result = await self.client.patch('/api/v2/channels/one', json={'desired_mode':'paused','expected_revision':1})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['actual_state'], 'recording')
        self.service.patch_mode.assert_awaited_once_with('one','paused',1)

    async def test_commands_require_idempotency(self):
        response = await self.client.post('/api/v2/channels/one/commands',json={'kind':'start_once'})
        self.assertEqual(response.status_code,422)
        self.service.command.assert_not_awaited()
        response = await self.client.post('/api/v2/channels/one/commands',json={'kind':'start_once'},headers={'Idempotency-Key':'key'})
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.json()['status_url'],'/api/v2/commands/cmd1')

    async def test_stale_cross_origin_rejected_before_control(self):
        for headers in ({'Origin':'http://evil.example'}, {'Origin':'null'}, {'Sec-Fetch-Site':'cross-site'}):
            response=await self.client.patch('/api/v2/channels/one',json={'desired_mode':'paused','expected_revision':1},headers=headers)
            self.assertEqual(response.status_code,403)
        self.service.patch_mode.assert_not_awaited()

    async def test_same_origin_and_nonbrowser_allowed(self):
        response=await self.client.patch('/api/v2/channels/one',json={'desired_mode':'paused','expected_revision':1},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,200)

    async def test_dns_rebinding_host_rejected(self):
        response=await self.client.get('/api/v2/channels',headers={'Host':'attacker.example'})
        self.assertEqual(response.status_code,400)
        self.service.list_channels.assert_not_called()

    async def test_unknown_job_target_and_live_input_rejected(self):
        from module.v2_repository import NotFound
        repo = Mock()
        repo.lookup_job_request.return_value = None
        with patch('lar_app.routers.v2.sync_catalog'), patch('lar_app.routers.v2.get_repository', return_value=repo):
            repo.get_artifact.side_effect = NotFound('Unknown artifact')
            response=await self.client.post('/api/v2/jobs',json={'kind':'verify','target_id':'1'},headers={'Idempotency-Key':'a'})
            self.assertEqual(response.status_code,404)
            repo.get_artifact.side_effect = None
            repo.get_artifact.return_value = {'id':'1','status':'recording','revision':1}
            response=await self.client.post('/api/v2/jobs',json={'kind':'verify','target_id':'1'},headers={'Idempotency-Key':'a'})
            self.assertEqual(response.status_code,409)
            repo.create_job.assert_not_called()

    async def test_input_revision_and_unsafe_options_rejected(self):
        repo = Mock()
        repo.lookup_job_request.return_value = None
        repo.get_artifact.return_value = {'id':'legacy-recording-1','revision':2}
        with patch('lar_app.routers.v2.sync_catalog'), patch('lar_app.routers.v2.get_repository',return_value=repo):
            response=await self.client.post('/api/v2/jobs',json={'kind':'verify','target_id':'1','input_revision':1},headers={'Idempotency-Key':'a'})
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['code'],'INPUT_CHANGED')
            response=await self.client.post('/api/v2/jobs',json={'kind':'verify','target_id':'1','options':{'delete_originals':True}},headers={'Idempotency-Key':'a'})
            self.assertEqual(response.status_code,422)
            repo.create_job.assert_not_called()

    async def test_status_does_not_expose_internal_exception_or_storage_details(self):
        secret = 'Traceback: OSError /private/cookies/token=private-secret'
        self.app.state.v2_worker = SimpleNamespace(snapshot=lambda: {
            'ready': False, 'running': 1, 'reconciled': True,
            'error': secret, 'storages': {'recordings': {'errors': [secret]}}})
        repo = Mock()
        repo.list_jobs.return_value = {'items': []}
        repo.job_counts.return_value = {'blocked': 1}
        report = {'ok': False, 'errors': [secret], 'checks': {'free_bytes': 42}}
        with patch('lar_app.routers.v2.get_repository', return_value=repo), patch('module.v2_runtime.capture_storage_report', return_value=report):
            response = await self.client.get('/api/v2/status')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('private', response.text)
        self.assertNotIn('Traceback', response.text)
        self.assertNotIn('storages', response.json()['worker'])
        self.assertEqual(response.json()['worker']['running'], 1)
        self.assertEqual(response.json()['storage']['status'], 'blocked')
        self.assertEqual(response.json()['storage']['free_bytes'], 42)

    async def test_settings_have_no_secret_values(self):
        result=(await self.client.get('/api/v2/settings')).json()
        self.assertTrue(result['storage']['originals_preserved'])
        self.assertNotIn('cookies',str(result))

    async def test_ui_returns_only_v2_assets(self):
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'templates/static/v2';target.mkdir(parents=True)
            (target/'index.html').write_text('<html><script src="/static/v2/app.js"></script></html>')
            app=FastAPI();install_v2_routes(app,self.core,root_dir=Path(root))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
                response=await client.get('/v2/broadcasts/test')
            self.assertEqual(response.status_code,200)
            self.assertNotIn('console.js',response.text)
            self.assertEqual(response.headers['cache-control'],'no-store')

    async def test_legacy_dashboard_keeps_console_assets_and_storage_warning(self):
        from fastapi.responses import HTMLResponse
        from lar_app.web.middleware import ConsoleAssetsMiddleware
        app = FastAPI()
        @app.get('/')
        async def old_dashboard():
            return HTMLResponse('<html><head><title>Dashboard</title></head><body>Legacy</body></html>')
        install_v2_routes(app, self.core)
        app.add_middleware(ConsoleAssetsMiddleware, release_version='test')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
            legacy = await client.get('/legacy')
            self.assertEqual(legacy.status_code, 200)
            self.assertIn('console.js', legacy.text)
        console = (Path(__file__).resolve().parents[1] / 'templates/static/js/console.js').read_text()
        self.assertIn('["/", "/legacy", "/recording"].includes(path)', console)
