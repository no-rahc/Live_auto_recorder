"""The recording library joins the existing console without taking over its root."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from lar_app.routers.v2 import install_v2_routes
from lar_app.web.middleware import ConsoleAssetsMiddleware
from lar_app.web.v2_security import V2OriginMiddleware


class LibraryRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'library.html').write_text(
            '<html><head><title>{{ page_title }}</title></head>'
            '<body data-login="{{ loginMode }}"><div id="root"></div>'
            '<span>{{ program_version }}</span><span>{{ request.url.path }}</span>'
            '<script type="module" src="/static/library/library.js"></script></body></html>',
            encoding='utf-8',
        )
        self.login = Mock()
        async def require_login(request: Request):
            self.login()
            if request.headers.get('x-deny-login'):
                raise HTTPException(401, 'Login required')
            return True
        self.core = SimpleNamespace(
            requireLogin=require_login, templates=Jinja2Templates(directory=str(root)),
            PROGRAM_VERSION='1.13.0', PROGRAM_NAME='Recorder',
        )
        self.app = FastAPI()
        @self.app.get('/')
        async def old_dashboard(login=Depends(require_login)):
            return HTMLResponse('<html><head><title>v1 dashboard</title></head><body>Existing recording controls</body></html>')
        self.original_root = next(route for route in self.app.routes if getattr(route, 'path', None) == '/')
        install_v2_routes(self.app, self.core, root_dir=root)
        self.app.add_middleware(ConsoleAssetsMiddleware, release_version='1.13.0')
        self.app.add_middleware(V2OriginMiddleware)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://localhost')
        self.addAsyncCleanup(self.client.aclose)
        env = patch.dict(os.environ, {'LAR_V2_ENABLED': '0'})
        env.start()
        self.addCleanup(env.stop)

    async def test_root_preserves_existing_endpoint_with_or_without_stale_v2_build(self):
        for built in (False, True):
            if built:
                folder = Path(self.temp.name) / 'templates/static/v2'
                folder.mkdir(parents=True)
                (folder / 'index.html').write_text('Obsolete v2 dashboard')
            response = await self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Existing recording controls', response.text)
            self.assertIn('/static/js/console.js?v=1.13.0', response.text)
            self.assertNotIn('Obsolete v2 dashboard', response.text)
            self.assertNotIn('location', response.headers)
            self.assertIs(next(route for route in self.app.routes if getattr(route, 'path', None) == '/'), self.original_root)
        self.assertEqual((await self.client.get('/legacy')).status_code, 404)

    async def test_library_pages_render_core_template_and_console_exactly_once(self):
        for enabled in ('0', '1'):
            with patch.dict(os.environ, {'LAR_V2_ENABLED': enabled}):
                for path, title in (('/broadcasts', '방송 보관함'), ('/broadcasts/example', '방송 보관함'), ('/jobs', '작업 상태')):
                    with self.subTest(enabled=enabled, path=path):
                        response = await self.client.get(path)
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertIn(f'<title>{title}</title>', response.text)
                        self.assertIn('data-login="False"', response.text)
                        self.assertIn('1.13.0', response.text)
                        self.assertIn(path, response.text)
                        self.assertEqual(response.text.count('/static/js/console.js?'), 1)
                        self.assertEqual(response.text.count('/static/css/console.css?'), 1)
                        self.assertIn('/static/library/library.js', response.text)
                        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.login.call_count, 6)

    async def test_aliases_keep_query_strings_and_stay_on_direct_local_routes(self):
        aliases = {
            '/v2': '/', '/v2/channels': '/channels', '/v2/settings': '/config',
            '/v2/broadcasts': '/broadcasts', '/v2/broadcasts/example': '/broadcasts/example',
            '/v2/jobs': '/jobs',
            '/v2/broadcasts/a%20b%3Fnext%3Dhttps%3A%2F%2Fevil.example': None,
        }
        query = '?query=%EB%B0%A9%EC%86%A1&state=failed&state=blocked&next=https%3A%2F%2Fevil.example'
        for source, target in aliases.items():
            response = await self.client.get(source + query)
            if target is None:
                self.assertEqual(response.status_code, 404)
                continue
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers['location'], target + query)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertFalse(urlsplit(response.headers['location']).netloc)
        response = await self.client.get('/v2/broadcasts/a%20b%3Fnext%3Devil.example')
        self.assertEqual(response.headers['location'], '/broadcasts/a%20b%3Fnext%3Devil.example')
        for path in ('/v2/unknown', '/v2//evil.example', '/v2/broadcasts/%2E%2E', '/v2/broadcasts/%2F%2Fevil.example'):
            self.assertEqual((await self.client.get(path)).status_code, 404)
        # Slash normalization may take one hop but must preserve bookmarks.
        response = await self.client.get('/v2/broadcasts/' + query, follow_redirects=True)
        self.assertEqual(response.url.path, '/broadcasts')
        self.assertEqual(response.url.query.decode(), query[1:])

    async def test_new_pages_aliases_and_api_all_require_login(self):
        for enabled in ('0', '1'):
            with patch.dict(os.environ, {'LAR_V2_ENABLED': enabled}):
                for path in ('/broadcasts', '/broadcasts/example', '/jobs', '/v2', '/v2/broadcasts/example', '/api/v2/jobs'):
                    response = await self.client.get(path, headers={'x-deny-login': 'yes'})
                    self.assertEqual(response.status_code, 401, path)
                response = await self.client.post('/api/v2/jobs', headers={'x-deny-login': 'yes'})
                self.assertEqual(response.status_code, 401)


class DisabledLibraryApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.state.channels_lock = asyncio.Lock()
        self.app.state.channels = [
            {'id': 'z', 'name': 'Recording', 'record_enabled': False},
            {'id': 'a', 'name': 'Watching', 'record_enabled': True},
            {'id': 'b', 'name': 'Idle', 'record_enabled': True},
        ]
        self.app.state.fsm = SimpleNamespace(getState=lambda cid: 'WATCHING' if cid == 'a' else 'IDLE')
        core = SimpleNamespace(requireLogin=lambda: True, toBool=bool, recorder_manager=SimpleNamespace(
            get_status_recording=lambda cid: cid == 'z', get_status_reserved=lambda cid: False,
        ))
        self.app.state.v2_channels = SimpleNamespace(patch_mode=AsyncMock(), command=AsyncMock())
        install_v2_routes(self.app, core)
        self.app.add_middleware(V2OriginMiddleware)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://localhost')
        self.addAsyncCleanup(self.client.aclose)
        for context in (
            patch.dict(os.environ, {'LAR_V2_ENABLED': '0'}),
            patch('lar_app.routers.v2.get_repository', side_effect=AssertionError('Durable DB must stay unopened')),
            patch('lar_app.routers.v2.sync_catalog', side_effect=AssertionError('No durable migration')),
            patch('module.v2_runtime.capture_storage_report', side_effect=AssertionError('No storage marker probe')),
        ):
            context.start()
            self.addCleanup(context.stop)

    async def test_channels_observe_legacy_states_and_paginate_without_changing_intent(self):
        first = (await self.client.get('/api/v2/channels?limit=2')).json()
        self.assertEqual([row['id'] for row in first['items']], ['a', 'b'])
        self.assertEqual(first['next_cursor'], '2')
        self.assertEqual([row['actual_state'] for row in first['items']], ['watching', 'idle'])
        last = (await self.client.get('/api/v2/channels?limit=2&cursor=2')).json()
        self.assertIsNone(last['next_cursor'])
        self.assertEqual(last['items'][0]['desired_mode'], 'paused')
        self.assertEqual(last['items'][0]['actual_state'], 'recording')
        self.assertFalse(last['items'][0]['controls_available'])
        status = (await self.client.get('/api/v2/status')).json()
        self.assertEqual(status['channels'], {'total': 3, 'recording': 1, 'watching': 1, 'attention': 0})

    async def test_catalog_list_filters_and_detail_never_claim_durable_validation(self):
        secret = '/private/token=secret'
        source = {
            'broadcast_id': 'b', 'title': 'Broadcast', 'platform': 'chzzk', 'status': 'completed',
            'file_size': 42, 'merged_path': secret, 'merge_error': secret, 'failure_detail': secret,
            'merge': {'output_path': secret},
            'segments': [{'id': 1, 'filename': secret + '/recording.ts', 'file_path': secret,
                          'source_url': secret, 'error': secret, 'file_size': 42, 'segment_index': 1}],
        }
        with patch('lar_app.routers.v2.catalog.list_broadcasts', return_value={'total': 2, 'items': [source]}) as listing:
            response = await self.client.get('/api/v2/broadcasts?limit=1&query=example&channel_id=one&platform=chzzk&status=completed&date_from=2026-10-01&date_to=2026-10-02')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['next_cursor'], '1')
        self.assertNotIn(secret, response.text)
        self.assertEqual(response.json()['items'][0]['total_size'], 42)
        kwargs = listing.call_args.kwargs
        self.assertEqual((kwargs['query'], kwargs['channel_id'], kwargs['platform'], kwargs['status']), ('example', 'one', 'chzzk', 'completed'))
        self.assertEqual(kwargs['started_to'] - kwargs['started_from'], 2 * 86400)
        with patch('lar_app.routers.v2.catalog.get_broadcast', return_value=source):
            response = await self.client.get('/api/v2/broadcasts/b')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.text)
        data = response.json()
        self.assertFalse(data['jobs_available'])
        self.assertEqual(data['jobs'], [])
        self.assertEqual(data['sessions'], [])
        self.assertEqual(data['segments'][0]['sequence'], 1)
        self.assertIsNone(data['segments'][0]['gap_before'])
        self.assertEqual(data['artifacts'][0]['relative_path'], 'recording.ts')
        self.assertIsNone(data['artifacts'][0]['exists'])
        self.assertFalse(data['artifacts'][0]['controls_available'])
        self.assertNotIn('validation', data['artifacts'][0])
        with patch('lar_app.routers.v2.catalog.get_broadcast', return_value=None):
            response = await self.client.get('/api/v2/broadcasts/missing')
        self.assertEqual(response.status_code, 404)

    async def test_every_durable_mutation_is_rejected_while_disabled(self):
        cases = (
            ('PATCH', '/api/v2/channels/one', {'desired_mode': 'paused', 'expected_revision': 1}),
            ('POST', '/api/v2/channels/one/commands', {'kind': 'start_once'}),
            ('POST', '/api/v2/jobs', {'kind': 'verify', 'target_id': '1'}),
            ('POST', '/api/v2/jobs/old/cancel', {}),
            ('POST', '/api/v2/jobs/old/retry', {}),
        )
        for method, url, body in cases:
            response = await self.client.request(method, url, json=body, headers={'Idempotency-Key': 'example'})
            self.assertEqual(response.status_code, 409, url)
            self.assertEqual(response.json()['code'], 'REQUEST_REJECTED')
        self.app.state.v2_channels.patch_mode.assert_not_awaited()
        self.app.state.v2_channels.command.assert_not_awaited()


class LibraryFetchOwnershipTests(unittest.TestCase):
    def test_library_feedback_is_not_overwritten_by_console_toasts(self):
        import json
        import subprocess
        source = (Path(__file__).resolve().parents[1] / 'templates/static/js/console.js').read_text()
        function = 'function installFetchFeedback() {' + source.split('  function installFetchFeedback() {', 1)[1].split('  function confirmDialog()', 1)[0]
        script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const toasts = [];
let next;
const context = {window: {}, Request, nativeFetch: async () => await next, toast: (...args) => toasts.push(args), feedbackMessage: () => 'done'};
vm.createContext(context);
vm.runInContext(FUNCTION, context);
context.installFetchFeedback();
(async () => {
  for (const path of ['/api/v2/jobs', 'http://localhost/api/v2/jobs/job-1/retry']) {
    next = {ok:true, status:202};
    await context.window.fetch(path, {method:'POST'});
    assert.equal(toasts.length,0,'job acceptance must not emit generic completion');
  }
  next = {ok:false,status:503};
  await context.window.fetch('/api/v2/broadcasts');
  assert.equal(toasts.length,0,'island handles read failure');
  next = Promise.reject(Object.assign(new Error('aborted'), {name:'AbortError'}));
  await assert.rejects(context.window.fetch('/api/v2/broadcasts?query=next'));
  assert.equal(toasts.length,0,'filter cancellation must not report lost connection');
  next = {ok:true,status:200};
  await context.window.fetch('/api/config', {method:'POST'});
  assert.equal(toasts.length,1,'existing console feedback must remain');
})().catch(error => {console.error(error); process.exitCode=1;});
""".replace('FUNCTION', json.dumps(function))
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
