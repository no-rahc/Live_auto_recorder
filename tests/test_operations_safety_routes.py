"""Check API integration of merge admission and restore acknowledgements."""
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
import httpx

from module import operations_platform_v3, operations_v2
from module.recording_merge import MergeInProgressError


class OperationsSafetyRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_merge_is_conflict_without_false_failure_notification(self):
        app, runtime = FastAPI(), Mock()
        with patch.object(operations_platform_v3, 'PlatformRuntime', return_value=runtime):
            operations_platform_v3.install_platform_features(app, Mock(), Mock())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            with patch('module.recording_merge.merge_broadcast', side_effect=MergeInProgressError('busy')):
                response = await client.post('/api/v3/broadcasts/test/merge', json={})
        self.assertEqual(response.status_code, 409)
        runtime.enqueue_notification.assert_not_called()

    async def test_restore_passes_request_acknowledgement_and_checks_filename(self):
        app, runtime = FastAPI(), Mock()
        runtime.restore_backup.return_value = {'restored': ['config.json']}
        with patch.object(operations_v2, 'OperationsRuntime', return_value=runtime):
            operations_v2.install_operations(app, Mock())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/operations/backups/backup_test.zip/restore', json={'confirm': 'wrong'})
            self.assertEqual(response.status_code, 400)
            runtime.restore_backup.assert_not_called()
            response = await client.post('/api/operations/backups/backup_test.zip/restore', json={
                'confirm': 'backup_test.zip', 'danger_ack': '위험 설정 적용',
            })
        self.assertEqual(response.status_code, 200)
        runtime.restore_backup.assert_called_once_with('backup_test.zip', acknowledgement='위험 설정 적용')


if __name__ == '__main__':
    unittest.main()
