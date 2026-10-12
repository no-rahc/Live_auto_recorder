"""Render production Jinja templates and console assets with synthetic browser data.

This read-only loopback host does not start the recorder or read installation data.
Playwright supplies all API responses. The shell and asset injection are the real
production files, never a copied/mock dashboard. Run only where sockets are allowed.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import os
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lar_app.web.assets import inject_console_assets

TEMPLATES = ROOT / 'templates'
VERSION = (ROOT / 'VERSION').read_text().strip()
environment = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(['html']))


def render_page(path: str) -> str:
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
    return inject_console_assets(environment.get_template(template).render(**context), VERSION)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(TEMPLATES), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in {'/', '/jobs', '/broadcasts', '/channels', '/config', '/recording', '/operations', '/cookies', '/files'} or path.startswith('/broadcasts/'):
            body = render_page(path).encode('utf-8')
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
