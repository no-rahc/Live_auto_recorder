import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from module import recording_catalog as catalog

class BroadcastFilterTests(unittest.TestCase):
    def test_filters_keep_all_segments_and_stable_order(self):
        with tempfile.TemporaryDirectory() as root, patch.object(catalog,'DB_PATH',Path(root)/'catalog.sqlite3'):
            catalog.init_catalog()
            with catalog._connect() as conn:
                for key,bid,start,status,platform in [('a','one',100,'completed','chzzk'),('b','one',200,'completed','chzzk'),('c','two',100,'recording','youtube')]:
                    conn.execute('INSERT INTO recordings(session_key,broadcast_id,started_epoch,status,platform) VALUES(?,?,?,?,?)',(key,bid,start,status,platform))
            result=catalog.list_broadcasts(started_from=90,started_to=150,platform='chzzk',status='completed')
            self.assertEqual(result['total'],1)
            self.assertEqual(result['items'][0]['segment_count'],2)
            self.assertEqual([r['broadcast_id'] for r in catalog.list_broadcasts()['items']],['two','one'])
            self.assertEqual(catalog.list_broadcasts(status='recording')['items'][0]['broadcast_id'],'two')
