import os
import sys
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from lar_app.bootstrap import _install_operations_lifespan

class V2LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_instance_lock_precedes_engine_and_releases_after_shutdown(self):
        events=[]
        app=FastAPI()
        @asynccontextmanager
        async def core_lifespan(app):
            events.append('engine-start')
            try: yield
            finally: events.append('engine-stop')
        app.router.lifespan_context=core_lifespan
        class Worker:
            def __init__(self,repo): pass
            def acquire_instance_lock(self): events.append('lock')
            async def start(self): events.append('worker-start')
            async def stop(self): events.append('worker-stop')
        operations=SimpleNamespace(start=AsyncMock(),stop=AsyncMock())
        platform=SimpleNamespace(start=AsyncMock(),stop=AsyncMock())
        with patch.dict(os.environ,{'LAR_V2_ENABLED':'1'}), patch.dict(sys.modules,{'module.v2_worker':SimpleNamespace(V2Worker=Worker)}), patch('lar_app.bootstrap.get_repository',return_value=Mock()), patch('module.v2_storage.preflight_database_location',return_value={'ok':True}), patch('module.v2_runtime.begin_capture_guard'), patch('module.v2_runtime.finish_capture_guard'), patch('module.v2_runtime.sync_catalog'), patch('module.v2_runtime.capture_storage_report',return_value={'ok':True}), patch('lar_app.bootstrap.enforce_local_mode'):
            _install_operations_lifespan(app,operations,platform,Mock())
            async with app.router.lifespan_context(app): events.append('yield')
        self.assertEqual(events,['lock','engine-start','worker-start','yield','engine-stop','worker-stop'])

    async def test_startup_failure_releases_instance_lock(self):
        events=[]
        app=FastAPI()
        @asynccontextmanager
        async def core_lifespan(app):
            raise RuntimeError('startup failed')
            yield
        app.router.lifespan_context=core_lifespan
        class Worker:
            def __init__(self,repo): pass
            def acquire_instance_lock(self): events.append('lock')
            async def stop(self): events.append('release')
        with patch.dict(os.environ,{'LAR_V2_ENABLED':'1'}), patch.dict(sys.modules,{'module.v2_worker':SimpleNamespace(V2Worker=Worker)}), patch('lar_app.bootstrap.get_repository',return_value=Mock()), patch('module.v2_storage.preflight_database_location',return_value={'ok':True}), patch('module.v2_runtime.begin_capture_guard'), patch('module.v2_runtime.finish_capture_guard'), patch('module.v2_runtime.sync_catalog'), patch('module.v2_runtime.capture_storage_report',return_value={'ok':True}):
            _install_operations_lifespan(app,Mock(),Mock(),Mock())
            with self.assertRaises(RuntimeError):
                async with app.router.lifespan_context(app): pass
        self.assertEqual(events,['lock','release'])

    async def test_default_lifespan_does_not_activate_durable_capture_or_storage(self):
        app = FastAPI()
        operations = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
        platform = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
        with (
            patch.dict(os.environ, {'LAR_V2_ENABLED': '0'}),
            patch('lar_app.bootstrap.get_repository', side_effect=AssertionError('must not open durable DB')),
            patch('module.v2_runtime.begin_capture_guard', side_effect=AssertionError('must not change capture policy')),
            patch('module.v2_runtime.finish_capture_guard', side_effect=AssertionError('must not touch capture marker')),
            patch('module.v2_runtime.sync_catalog', side_effect=AssertionError('must not migrate')),
            patch('module.v2_runtime.capture_storage_report', side_effect=AssertionError('must not probe storage')),
            patch('module.v2_storage.preflight_database_location', side_effect=AssertionError('must not initialize storage')),
            patch('lar_app.bootstrap.enforce_local_mode'),
        ):
            _install_operations_lifespan(app, operations, platform, Mock())
            async with app.router.lifespan_context(app):
                self.assertFalse(hasattr(app.state, 'v2_worker'))
            operations.start.assert_awaited_once()
            operations.stop.assert_awaited_once()
            platform.start.assert_awaited_once()
            platform.stop.assert_awaited_once()
