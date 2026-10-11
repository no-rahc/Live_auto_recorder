"""Retained legacy controls must not bypass v2 original-preserving execution."""
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch
from module import live_recorder, recording_merge, recording_verify
from module.operations_health import HealthJobsMixin
from module.operations_backup import BackupStatsMixin
from fastapi import HTTPException

class LegacyV2SafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.flag=patch.dict(os.environ,{'LAR_V2_ENABLED':'true'});self.flag.start();self.addCleanup(self.flag.stop)

    async def test_legacy_verify_routes_to_durable_job_without_repair(self):
        with patch('module.v2_runtime.enqueue_legacy_job',return_value={'status':'queued'}) as enqueue,patch.object(recording_verify,'_repair') as repair:
            result=recording_verify.verify_recording(1,attempt_repair=True)
        enqueue.assert_called_once_with('verify','1');repair.assert_not_called();self.assertEqual(result['status'],'queued')

    async def test_legacy_merge_cannot_delete_sources(self):
        with patch('module.v2_runtime.enqueue_legacy_job',return_value={'status':'queued'}) as enqueue,patch.object(recording_merge,'_merge_broadcast') as merge:
            result=recording_merge.merge_broadcast('broadcast',delete_segments=True)
        enqueue.assert_called_once_with('merge','broadcast');merge.assert_not_called();self.assertEqual(result['status'],'queued')

    async def test_detached_batches_and_legacy_postprocess_are_disabled(self):
        with patch.object(live_recorder,'batchEncodeSegments',new=AsyncMock()) as batch,patch.object(live_recorder,'copyStream',new=AsyncMock()) as copy:
            self.assertFalse(await live_recorder.queueBatchPattern('channel','/old/pattern_%03d.ts'))
            self.assertFalse(await live_recorder.queueBatchLast('channel'))
            await live_recorder.handlePostProcessing('/source.ts','channel','Channel',{'deleteAfterPostProcessing':True})
        batch.assert_not_awaited();copy.assert_not_awaited()

    async def test_short_recording_cleanup_and_live_restore_do_not_run(self):
        owner=Mock()
        await HealthJobsMixin._delete_short_recording(owner,'channel','/source.ts')
        owner.settings.get.assert_not_called()
        with self.assertRaises(HTTPException) as caught:BackupStatsMixin.restore_backup(owner,'backup.zip')
        self.assertEqual(caught.exception.status_code,409)
        owner.backup_path.assert_not_called()

    async def test_offline_smoke_suppresses_network_update_checks(self):
        from module.operations_maintenance import MaintenanceOpsMixin
        owner=Mock()
        with patch.dict(os.environ,{'LAR_DISABLE_UPDATE_CHECK':'true'}),patch('module.operations_maintenance.requests.get') as get:
            result=MaintenanceOpsMixin.version_status(owner,True)
        self.assertEqual(result['status'],'disabled')
        get.assert_not_called()

    async def test_legacy_retention_cannot_remove_referenced_media(self):
        from module.operations_common import OperationsBase
        owner=Mock()
        with self.assertRaises(HTTPException) as caught:OperationsBase.run_cleanup(owner,{'confirm':True})
        self.assertEqual(caught.exception.status_code,409)
        owner.cleanup_candidates.assert_not_called()
