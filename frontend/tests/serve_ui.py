"""Render production Jinja templates and console assets with synthetic browser data.

This read-only loopback host does not start the recorder or read installation data.
Playwright supplies all API responses. The shell and asset injection are the real
production files, never a copied/mock dashboard. Run only where sockets are allowed.
"""
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
import os
import sys
import subprocess

from jinja2 import DictLoader, Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lar_app.web.assets import inject_console_assets

TEMPLATES = ROOT / 'templates'
VERSION = (ROOT / 'VERSION').read_text().strip()
environment = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(['html']))
BASELINE_REF = os.environ.get('UI_BASELINE_REF') or 'HEAD'
BASELINE_ASSETS = {'css/app.css', 'css/console.css', 'js/app.js', 'js/console.js', 'js/metrics.js'}


@lru_cache(maxsize=8)
def baseline_file(path: str) -> bytes:
    # Read only the original dashboard and its known console assets from the PR
    # base. No copied/mock shell and no connection to a running installation.
    if path != 'index.html' and path not in {'static/' + name for name in BASELINE_ASSETS}:
        raise ValueError('Not a baseline dashboard resource')
    return subprocess.run(['git', 'show', f'{BASELINE_REF}:templates/{path}'], cwd=ROOT, check=True, capture_output=True).stdout


def render_page(path: str, *, baseline: bool = False) -> str:
    template = 'index.html' if path == '/' else 'library.html' if path == '/jobs' or path == '/broadcasts' or path.startswith('/broadcasts/') else f'{path[1:]}.html'
    url_for = lambda name, path='': '/static/' + path if name == 'static' else '/' + name
    context = {
        'request': SimpleNamespace(session={}, url=SimpleNamespace(path=path), url_for=url_for),
        'url_for': url_for,
        'program_name': 'Live Auto Recorder', 'program_version': VERSION,
        'page_title': '작업 상태' if path == '/jobs' else '방송 보관함',
        'loginMode': False, 'config': {'loginMode': False, 'autoRecordingMode': False},
        'channels': [], 'account': {}, 'telegram': {}, 'error_message': '',
    }
    source = environment
    if baseline:
        if path != '/':
            raise ValueError('Baseline comparison is only for the preserved dashboard')
        source = Environment(loader=DictLoader({'index.html': baseline_file('index.html').decode('utf-8')}), autoescape=select_autoescape(['html']))
    html = inject_console_assets(source.get_template(template).render(**context), VERSION)
    return html.replace('/static/', '/__baseline/static/') if baseline else html


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(TEMPLATES), **kwargs)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path.startswith('/__baseline/static/'):
            asset = path.removeprefix('/__baseline/static/')
            if asset not in BASELINE_ASSETS:
                self.send_error(404)
                return
            body = baseline_file('static/' + asset)
            self.send_response(200)
            self.send_header('Content-Type', 'text/css' if asset.endswith('.css') else 'application/javascript')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in {'/', '/jobs', '/broadcasts', '/channels', '/config', '/recording', '/operations', '/cookies', '/files'} or path.startswith('/broadcasts/'):
            body = render_page(path, baseline=path == '/' and parse_qs(parsed.query).get('baseline') == ['1']).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, *_args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('UI_TEST_PORT', '4174'))), Handler).serve_forever()
