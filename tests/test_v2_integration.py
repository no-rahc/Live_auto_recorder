"""HTTP-to-SQLite-to-worker regression tests with isolated media fixtures."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from lar_app.routers.v2 import install_v2_routes
from module import recording_catalog as catalog
from module.v2_repository import V2Repository
from module.v2_storage import StorageRoot
from module.v2_worker import V2Worker

class V2IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.media=self.root/'media';self.media.mkdir()
        self.path=self.media/'capture.ts';self.path.write_bytes(b'original fixture bytes')
        self.catalog_path=self.root/'legacy.sqlite3'
        self.catalog_patch=patch.object(catalog,'DB_PATH',self.catalog_path);self.catalog_patch.start();self.addCleanup(self.catalog_patch.stop)
        catalog.init_catalog()
        with catalog._connect() as conn:
            conn.execute("INSERT INTO recordings(session_key,broadcast_id,channel_id,channel_name,platform,filename,file_path,file_size,status,started_epoch) VALUES(?,?,?,?,?,?,?,?,?,?)",('session','broadcast','channel','Channel','chzzk',self.path.name,str(self.path),self.path.stat().st_size,'completed',100))
        self.repo=V2Repository(self.root/'v2.sqlite3');self.repo.initialize()
        def sync():return self.repo.sync_legacy_catalog(self.catalog_path,recording_root=self.media)
        sync()
        self.patches=[patch.dict(os.environ,{'LAR_V2_ENABLED':'1'}),patch('lar_app.routers.v2.get_repository',return_value=self.repo),patch('lar_app.routers.v2.sync_catalog',side_effect=sync)]
        for context in self.patches:context.start();self.addCleanup(context.stop)
        app=FastAPI();install_v2_routes(app,SimpleNamespace(requireLogin=lambda:True))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost');self.addAsyncCleanup(self.client.aclose)

    async def test_verify_accept_execute_poll_and_idempotent_replay(self):
        artifact=self.repo.get_artifact('1')
        body={'kind':'verify','target_id':artifact['id'],'input_revision':artifact['revision']}
        first=await self.client.post('/api/v2/jobs',json=body,headers={'Idempotency-Key':'request-1'})
        self.assertEqual(first.status_code,202,first.text);job_id=first.json()['job_id']
        worker=V2Worker(self.repo,storages={'recordings':StorageRoot('recordings',self.media)})
        with patch.object(worker,'_probe',return_value={'duration':1,'streams':[{'codec_type':'video'}]}):
            self.assertTrue(worker.run_once(kinds=('verify',)))
        result=(await self.client.get('/api/v2/jobs/'+job_id)).json()
        self.assertEqual(result['state'],'succeeded');self.assertEqual(len(result['attempt_history']),1)
        repeat=await self.client.post('/api/v2/jobs',json=body,headers={'Idempotency-Key':'request-1'})
        self.assertEqual(repeat.status_code,202,repeat.text);self.assertEqual(repeat.json()['job_id'],job_id)
        conflict=await self.client.post('/api/v2/jobs',json={**body,'options':{'suffix':'.mkv'}},headers={'Idempotency-Key':'request-1'})
        self.assertEqual(conflict.status_code,409)
        self.assertEqual(self.path.read_bytes(),b'original fixture bytes')

    async def test_imported_active_input_is_rejected(self):
        with catalog._connect() as conn:conn.execute("UPDATE recordings SET status='recording'")
        response=await self.client.post('/api/v2/jobs',json={'kind':'verify','target_id':'1','input_revision':1},headers={'Idempotency-Key':'active'})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.repo.list_jobs()['items'],[])

    async def test_broadcast_detail_exposes_normalized_relationships(self):
        response=await self.client.get('/api/v2/broadcasts/broadcast')
        self.assertEqual(response.status_code,200,response.text)
        detail=response.json()
        self.assertEqual(detail['artifacts'][0]['id'],'legacy-recording-1')
        self.assertEqual(len(detail['sessions']),1)
        self.assertEqual(detail['segments'][0]['sequence'],1)
