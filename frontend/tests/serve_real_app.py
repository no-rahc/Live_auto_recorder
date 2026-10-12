"""Disposable full-app host for manual/automated browser integration checks.

Copies application code only. Does not read or mutate installation JSON, videos,
secrets, or existing databases. Synthetic sample files are generated with FFmpeg.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='lar-v2-browser-') as folder:
    root = Path(folder)
    for name in ('lar_app', 'module', 'templates'):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('app_entry.py', 'live_auto_recorder.py', 'VERSION'):
        shutil.copy2(ROOT / name, root / name)
    data, media = root / 'json', root / 'media'
    data.mkdir(); media.mkdir()
    (data / 'channels.json').write_text('[]')
    (data / 'config.json').write_text(json.dumps({'autoRecordingMode': False}))
    durable_enabled = os.getenv('UI_REAL_V2_ENABLED', 'true')
    if durable_enabled.lower() in {'1', 'true', 'yes', 'on'}:
        (media / '.lar-storage-id').write_text('disposable-browser-test')
    env = {**os.environ, 'LAR_V2_ENABLED': durable_enabled, 'LAR_DISABLE_UPDATE_CHECK': 'true', 'LAR_DATA_DIR': str(data), 'RECORDINGS_ROOT': str(media), 'HOST': '127.0.0.1', 'PORT': os.getenv('UI_REAL_PORT', '4175'), 'PYTHONDONTWRITEBYTECODE': '1'}
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc=size=128x72:rate=10', '-t', '1', '-c:v', 'mpeg2video', '-f', 'mpegts', '-n', str(media/'sample-1.ts')], check=True)
        shutil.copyfile(media/'sample-1.ts', media/'sample-2.ts')
        seed = '''
import os, sqlite3
from pathlib import Path
from module import recording_catalog as catalog
catalog.init_catalog()
root=Path(os.environ['RECORDINGS_ROOT'])
with sqlite3.connect(catalog.DB_PATH) as db:
 for i in (1,2):
  file=root/f'sample-{i}.ts'
  db.execute("INSERT INTO recordings(session_key,channel_id,channel_name,platform,title,filename,file_path,file_size,started_at,started_epoch,ended_at,ended_epoch,duration,status,broadcast_id,segment_index) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (f'test-session-{i}','test-channel','브라우저 테스트','chzzk','안전한 로컬 테스트 방송',file.name,str(file),file.stat().st_size,'2026-10-11T09:00:00Z',1791709200+i,'2026-10-11T09:00:01Z',1791709201+i,'00:00:01','completed','browser-test-broadcast',i))
'''
        subprocess.run([sys.executable, '-c', seed], cwd=root, env=env, check=True)
    process = subprocess.Popen([sys.executable, 'app_entry.py'], cwd=root, env=env)
    def stop(_signum, _frame):
        if process.poll() is None: process.terminate()
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    print(f'Disposable app: http://127.0.0.1:{env["PORT"]}/v2', flush=True)
    try:
        process.wait()
        if process.returncode: raise SystemExit(process.returncode)
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=20)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
