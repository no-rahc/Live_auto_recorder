"""All settings entry points share typed normalization and danger checks."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
import httpx

from lar_app.config_validation import ConfigValidationError, DANGER_ACK, normalize_config_update
from lar_app.routers.config import install_config_routes

SAFE = {'fileManagerEnabled': True, 'fileManagerMode': 'whitelist',
        'fileManagerReadOnly': True, 'trashEnabled': True, 'fileManagerRoots': ['/recordings'],
        'recheckInterval': 60, 'plugin_type': 'basic'}


class ConfigValidationTest(unittest.TestCase):
    def test_strict_boolean_normalization(self):
        value = normalize_config_update(SAFE, {'autoRecordingMode': 'false', 'enableTray': 'on'})
        self.assertIs(value['autoRecordingMode'], False)
        self.assertIs(value['enableTray'], True)
        for bad in ['sometimes', [], {}, 2, None]:
            with self.subTest(bad=bad), self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, {'trashEnabled': bad})

    def test_invalid_types_ranges_and_enums(self):
        for updates in [[], None, {'recheckInterval': 0}, {'port': 65536}, {'video_quality': True},
                        {'splitOverlapSec': '1.5'}, {'plugin_type': 'other'},
                        {'fileManagerMode': 'other'}, {'fileManagerRoots': {}},
                        {'fileManagerRoots': [1]}, {'filenamePattern': []}]:
            with self.subTest(updates=updates), self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, updates)

    def test_dangerous_transitions_cannot_use_embedded_confirmation(self):
        for update in [{'fileManagerReadOnly': False}, {'trashEnabled': 'off'},
                       {'fileManagerMode': 'blacklist'}, {'fileManagerRoots': ['/tmp']}]:
            with self.subTest(update=update), self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, dict(update, danger_ack=DANGER_ACK))
            result = normalize_config_update(SAFE, update, acknowledgement=DANGER_ACK)
            self.assertNotIn('danger_ack', result)

    def test_protected_roots_cannot_be_allowed_even_with_ack(self):
        import tempfile
        from pathlib import Path
        for root in ['/', '/etc', '/etc/ssl', '/usr/local', 'C:\\', 'C:\\Windows', 'C:\\Program Files\\app']:
            with self.subTest(root=root), self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, {'fileManagerRoots': [root]}, acknowledgement=DANGER_ACK)
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / 'alias'
            alias.symlink_to('/etc', target_is_directory=True)
            with self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, {'fileManagerRoots': [str(alias)]}, acknowledgement=DANGER_ACK)
            with self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, {'fileManagerRoots': [str(Path(directory) / 'missing')]}, acknowledgement=DANGER_ACK)
            result = normalize_config_update(SAFE, {'fileManagerRoots': [directory]}, acknowledgement=DANGER_ACK)
            self.assertEqual(result['fileManagerRoots'], [directory])

    def test_windows_junction_resolves_before_protected_root_check(self):
        with patch('lar_app.config_validation.os.name', 'nt'), patch(
            'lar_app.config_validation.os.path.realpath', return_value='C:\\Windows'
        ) as resolved:
            with self.assertRaises(ConfigValidationError):
                normalize_config_update(SAFE, {'fileManagerRoots': ['C:\\Users\\me\\safe-link']}, acknowledgement=DANGER_ACK)
            resolved.assert_called_once_with('C:\\Users\\me\\safe-link')

    def test_partial_updates_dependencies_and_no_mutation(self):
        current = dict(SAFE, discord_webhook_url='secret', extension_setting={'x': 1})
        before = deepcopy(current)
        result = normalize_config_update(current, {'timemachine_time_shift': '90',
                         'splitOverlapSec': 15, 'autoStopInterval': 30,
                         'minimizeToTrayOnClose': 'true'})
        self.assertEqual(result['timemachine_time_shift'], 10)
        self.assertEqual(result['splitOverlapSec'], 0)
        self.assertEqual(result['autoStopInterval'], 0)
        self.assertFalse(result['minimizeToTrayOnClose'])
        self.assertEqual(result['discord_webhook_url'], 'secret')
        self.assertEqual(current, before)

    def test_unchanged_risky_config_does_not_require_reapproval(self):
        risky = dict(SAFE, fileManagerMode='blacklist', trashEnabled=False)
        result = normalize_config_update(risky, {'recheckInterval': '120'})
        self.assertEqual(result['recheckInterval'], 120)


class ConfigRoutesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.current = dict(SAFE)
        self.saved = Mock(side_effect=lambda value: value)
        self.telegram_saved = Mock()
        async def login():
            return True
        core = SimpleNamespace(loadConfig=lambda: deepcopy(self.current), saveConfig=self.saved,
            loadAccount=lambda: {}, loadTelegram=lambda: {}, saveTelegram=self.telegram_saved,
            toBool=bool, _normalizeAllowedRoots=lambda roots: roots, templates=Mock(),
            PROGRAM_VERSION='test', requireLogin=login, logger=Mock())
        self.app = FastAPI()
        install_config_routes(self.app, core)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def test_json_and_form_reject_danger_before_any_write(self):
        for path, kwargs in [('/api/save_config', {'json': {'fileManagerReadOnly': 'false'}}),
                             ('/config', {'data': {'fileManagerReadOnly': 'false'}})]:
            response = await self.client.post(path, **kwargs)
            self.assertEqual(response.status_code, 400, response.text)
        self.saved.assert_not_called()
        self.telegram_saved.assert_not_called()

    async def test_json_and_form_have_same_normalization(self):
        update = {'recheckInterval': '120', 'autoRecordingMode': 'false',
                  'fileManagerReadOnly': 'false', 'danger_ack': DANGER_ACK}
        for path, kwargs in [('/api/save_config', {'json': update}), ('/config', {'data': update})]:
            response = await self.client.post(path, **kwargs)
            self.assertIn(response.status_code, (200, 303), response.text)
            value = self.saved.call_args.args[0]
            self.assertEqual(value['recheckInterval'], 120)
            self.assertIs(value['autoRecordingMode'], False)
            self.assertIs(value['fileManagerReadOnly'], False)
            self.assertNotIn('danger_ack', value)

    async def test_malformed_json_setting_rejected(self):
        response = await self.client.post('/api/save_config', json={'recheckInterval': []})
        self.assertEqual(response.status_code, 400)
        self.saved.assert_not_called()


class LegacyConfigImportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Compile only the two handlers to avoid legacy module startup side effects.
        import ast
        from datetime import datetime
        from pathlib import Path
        from fastapi import Depends, Request
        from fastapi.responses import JSONResponse
        async def requireLogin():
            return True
        self.app = FastAPI()
        self.saved = Mock()
        self.channels_saved = Mock()
        self.telegram_saved = Mock()
        self.current = dict(SAFE, discord_webhook_url='stored-webhook')
        self.telegram = {'telegram_bot_token': 'stored-token', 'telegram_chat_id': 'stored-chat'}
        namespace = dict(Request=Request, Any=object, Depends=Depends, requireLogin=requireLogin,
            JSONResponse=JSONResponse, json=json, datetime=datetime,
            loadConfig=lambda: deepcopy(self.current), saveConfig=self.saved,
            loadChannels=lambda: [], saveChannels=self.channels_saved,
            loadTelegram=lambda: dict(self.telegram), saveTelegram=self.telegram_saved)
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'live_auto_recorder.py').read_text())
        handlers = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name in {'api_config_import', 'api_config_export'}]
        for node in handlers:
            node.decorator_list = []
        exec(compile(ast.Module(body=handlers, type_ignores=[]), '<legacy-config>', 'exec'), namespace)
        self.app.post('/api/config_import')(namespace['api_config_import'])
        self.app.get('/api/config_export')(namespace['api_config_export'])
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def test_embedded_ack_is_not_authority_for_import(self):
        response = await self.client.post('/api/config_import', json={
            'danger_ack': DANGER_ACK, 'config': {'fileManagerReadOnly': False, 'danger_ack': DANGER_ACK}})
        self.assertEqual(response.status_code, 400, response.text)
        self.saved.assert_not_called()

    async def test_import_explicit_header_and_sanitized_secret_preservation(self):
        from urllib.parse import quote
        response = await self.client.post('/api/config_import', headers={'X-Config-Danger-Ack': quote(DANGER_ACK)},
            json={'config': {'fileManagerReadOnly': False}, 'telegram': {}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.saved.call_args.args[0]['discord_webhook_url'], 'stored-webhook')
        self.telegram_saved.assert_called_once_with(self.telegram)

    async def test_invalid_import_shapes_do_not_write_any_settings(self):
        for extra in [{'channels': [{}]}, {'channels': [{'id': 'x'}, {'id': 'x'}]},
                      {'telegram': {'telegram_bot_token': []}}, {'config': []}]:
            response = await self.client.post('/api/config_import', json={'config': {}, **extra})
            self.assertEqual(response.status_code, 400, response.text)
        self.saved.assert_not_called()
        self.channels_saved.assert_not_called()
        self.telegram_saved.assert_not_called()

    async def test_legacy_export_is_sanitized_even_when_query_requests_secrets(self):
        response = await self.client.get('/api/config_export?include_secrets=true')
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIs(result['include_secrets'], False)
        self.assertNotIn('discord_webhook_url', result['config'])
        self.assertEqual(result['telegram'], {})
        self.assertNotIn('stored-token', response.text)


class ConfigUiTest(unittest.TestCase):
    def test_backup_restore_confirmation_is_reactive_and_cancelable(self):
        import shutil
        import subprocess
        from pathlib import Path
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for UI regression coverage')
        source = (Path(__file__).resolve().parents[1] / 'templates/static/js/console.js').read_text()
        handler = source.split('const restoreBackup = ', 1)[1].split('// End restore result reporting.', 1)[0]
        handler = 'const restoreBackup = ' + handler
        script = 'const HANDLER = ' + json.dumps(handler) + ';\n' + r'''
const assert = require('node:assert/strict');
const execute = new Function('request', 'prompt', 'name', 'notice', 'return (async () => {' + HANDLER + '})();');
const run = (request, prompt, name, notice = () => {}) => execute(request, prompt, name, notice);
(async () => {
  for (const choice of ['위험 설정 적용', null]) {
    const calls = [];
    let prompts = 0;
    await run(async (url, options) => {
      calls.push(JSON.parse(options.body));
      if (calls.length === 1) throw new Error('확인 문구 위험 설정 적용');
    }, () => { prompts++; return choice; }, 'backup_test.zip');
    assert.equal(prompts, 1);
    assert.equal(calls[0].danger_ack, '');
    assert.equal(calls.length, choice ? 2 : 1);
    if (choice) assert.equal(calls[1].danger_ack, choice);
  }
  let prompts = 0;
  await assert.rejects(run(async () => {throw new Error('invalid archive');},
    () => { prompts++; return '위험 설정 적용'; }, 'backup_test.zip'), /invalid archive/);
  assert.equal(prompts, 0);
  for (const omitted of [[], ['config.json', 'telegram.json']]) {
    const notices = [];
    await run(async () => ({pre_restore_backup: {omitted_files: omitted, omission_reason: 'invalid JSON'}}),
      () => { throw new Error('unexpected confirmation'); }, 'backup_test.zip',
      (message, tone) => notices.push({message, tone}));
    assert.equal(notices.length, 1);
    assert.equal(notices[0].tone, omitted.length ? 'warning' : 'success');
    for (const filename of omitted) assert.ok(notices[0].message.includes(filename));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run([node, '-e', script], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
