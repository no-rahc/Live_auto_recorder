import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from module import v2_runtime

class CaptureGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.repo=SimpleNamespace(db_path=self.root/'v2.sqlite3')
        self.state=patch.multiple(v2_runtime,_capture_dirty_path=None,_capture_reconciliation_required=False,_capture_processes=[],_capture_tracking_uncertain=False)
        self.state.start();self.addCleanup(self.state.stop)

    def test_clean_shutdown_clears_marker(self):
        v2_runtime.begin_capture_guard(self.repo)
        self.assertTrue((self.root/'v2-capture-active.json').exists())
        v2_runtime.finish_capture_guard(shutdown_confirmed=True)
        self.assertFalse((self.root/'v2-capture-active.json').exists())

    def test_unclean_shutdown_remains_blocked_across_restart(self):
        v2_runtime.begin_capture_guard(self.repo)
        v2_runtime.finish_capture_guard(shutdown_confirmed=False)
        v2_runtime.begin_capture_guard(self.repo)
        self.assertFalse(v2_runtime.capture_storage_report()['ok'])
        v2_runtime.finish_capture_guard(shutdown_confirmed=True)
        self.assertTrue((self.root/'v2-capture-active.json').exists())

    def test_surviving_or_uncertain_capture_prevents_clean_marker(self):
        v2_runtime.begin_capture_guard(self.repo)
        v2_runtime._capture_processes.append({'pid':123})
        for result in (False,None):
            with patch('module.v2_worker.process_confirmed_absent',return_value=result):
                v2_runtime.finish_capture_guard(shutdown_confirmed=True)
                self.assertTrue((self.root/'v2-capture-active.json').exists())

    def test_missing_storage_marker_is_fail_closed(self):
        with patch.dict(os.environ,{'RECORDINGS_ROOT':str(self.root),'LAR_V2_RECORDINGS_MARKER':''}):
            self.assertFalse(v2_runtime.capture_storage_report()['ok'])
            (self.root/'.lar-storage-id').write_text('fixture')
            self.assertTrue(v2_runtime.capture_storage_report()['ok'])

    def test_database_preflight_before_any_sqlite_initialization(self):
        candidate=Mock(db_path=self.root/'v2.sqlite3')
        with patch.dict(os.environ,{'LAR_V2_ENABLED':'1'}),patch.object(v2_runtime,'_repository',None),patch('module.v2_repository.V2Repository',return_value=candidate),patch('module.v2_storage.preflight_database_location',return_value={'ok':False}):
            with self.assertRaises(RuntimeError):v2_runtime.get_repository()
            candidate.initialize.assert_not_called()
