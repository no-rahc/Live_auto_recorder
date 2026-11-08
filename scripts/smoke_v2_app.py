#!/usr/bin/env python3
"""Launch an isolated empty-channel app twice; never touches installation data."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='lar-v2-app-smoke-') as folder:
        root=Path(folder)
        for name in ('lar_app','module','templates'):
            shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('app_entry.py','live_auto_recorder.py','VERSION'):
            shutil.copy2(ROOT/name,root/name)
        data=root/'json';data.mkdir()
        (data/'channels.json').write_text('[]')
        (data/'config.json').write_text(json.dumps({'autoRecordingMode':False}))
        media=root/'media';media.mkdir();(media/'.lar-storage-id').write_text('isolated-smoke')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'LAR_V2_ENABLED':'true','LAR_DATA_DIR':str(data),'RECORDINGS_ROOT':str(media),'HOST':'127.0.0.1','PORT':str(port),'PYTHONDONTWRITEBYTECODE':'1','LAR_DISABLE_UPDATE_CHECK':'true'}
        for cycle in (1,2):
            log=root/f'server-{cycle}.log'
            with log.open('w') as output:
                process=subprocess.Popen([sys.executable,'app_entry.py'],cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    base=f'http://127.0.0.1:{port}'
                    deadline=time.monotonic()+30
                    while True:
                        if process.poll() is not None:raise RuntimeError('Server exited: '+log.read_text()[-6000:])
                        try:
                            with urlopen(base+'/healthz',timeout=1) as response:
                                assert response.status==200
                            break
                        except (URLError,TimeoutError):
                            if time.monotonic()>deadline:raise RuntimeError('Startup timed out: '+log.read_text()[-6000:])
                            time.sleep(.1)
                    for path in ('/readyz','/api/v2/channels','/api/v2/jobs','/api/v2/settings','/api/v2/status','/broadcasts','/jobs','/v2','/'):
                        with urlopen(base+path,timeout=5) as response:
                            payload=response.read().decode()
                            assert response.status==200,(path,response.status)
                            if path in {'/broadcasts','/jobs'}:assert '/static/library/' in payload and 'console.js' in payload
                            if path in {'/v2','/'}:assert 'page-index' in payload and '/static/v2/' not in payload
                            if path=='/api/v2/channels':assert json.loads(payload)['items']==[]
                    try:
                        urlopen(Request(base+'/api/v2/jobs',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://foreign.example'}),timeout=5)
                        raise AssertionError('Foreign origin accepted')
                    except HTTPError as exc:assert exc.code==403
                    print(f'cycle {cycle}: health/readiness/v2 API/UI/legacy UI/origin checks passed')
                finally:
                    process.send_signal(signal.SIGTERM)
                    try:process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait();raise
                if process.returncode not in (0,-signal.SIGTERM):raise RuntimeError(log.read_text()[-6000:])
                assert not (data/'v2-capture-active.json').exists(),'Clean shutdown retained capture block'
        print('Two full isolated startup/shutdown cycles passed; persistent DB reused.')
        # A real unclean process exit must leave a block, even with no channels.
        for crash_cycle in (True, False):
            with (root/'crash-cycle.log').open('w') as output:
                process=subprocess.Popen([sys.executable,'app_entry.py'],cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    deadline=time.monotonic()+30
                    while True:
                        try:
                            with urlopen(base+'/healthz',timeout=1):pass
                            break
                        except (URLError,TimeoutError):
                            if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Crash cycle startup failed')
                            time.sleep(.1)
                    if crash_cycle:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait(timeout=10)
                    else:
                        with urlopen(base+'/api/v2/status',timeout=5) as response:
                            status=json.load(response)
                        assert status['storage']['status']=='blocked'
                        assert 'CAPTURE_RECONCILIATION_REQUIRED' in status['storage']['message']
                        try:
                            urlopen(base+'/readyz',timeout=5)
                            raise AssertionError('Unclean capture state reported ready')
                        except HTTPError as exc:assert exc.code==503
                finally:
                    if process.poll() is None:
                        process.send_signal(signal.SIGTERM);process.wait(timeout=30)
        assert (data/'v2-capture-active.json').exists(),'Unresolved marker was incorrectly cleared'
        print('Real SIGKILL/restart remained fail-closed with a persistent reconciliation notice.')

if __name__=='__main__':main()
