"""Read-only static host used by browser tests; API is intercepted by Playwright."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[2] / 'templates'
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def do_GET(self):
        if self.path.split('?', 1)[0] == '/v2' or self.path.startswith('/v2/'):
            self.path = '/static/v2/index.html'
        return super().do_GET()
    def log_message(self, *_args):
        pass
ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('UI_TEST_PORT', '4174'))), Handler).serve_forever()
