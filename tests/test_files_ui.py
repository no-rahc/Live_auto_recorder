"""Exercise file-manager request payloads with the existing JavaScript handler."""
from pathlib import Path
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for UI regression coverage")
class FilesUiTest(unittest.TestCase):
    def test_mkdir_sends_new_name_and_handles_cancel_and_error(self):
        source = (ROOT / "templates/static/js/app.js").read_text(encoding="utf-8")
        handler = source.split("  // 새 폴더\n", 1)[1].split("  // 경로 입력 후 Enter 이동", 1)[0]
        script = "const HANDLER = " + json.dumps(handler) + ";\n" + r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const calls = [], refreshes = [], alerts = [];
let click;
let name = '새 폴더';
let fail = false;
const context = {
  document: {getElementById: id => {
    assert.equal(id, 'btnMkdir');
    return {addEventListener: (event, callback) => {
      assert.equal(event, 'click'); click = callback;
    }};
  }},
  filesCurrentPath: '/recordings',
  prompt: () => name,
  apiPost: async (url, payload) => {
    if (fail) throw new Error('invalid name');
    calls.push({url, ...payload});
  },
  listAndRender: async path => refreshes.push(path),
  alert: message => alerts.push(message),
};
vm.createContext(context);
vm.runInContext(HANDLER, context);
(async () => {
  await click();
  assert.deepEqual(calls, [{url: '/api/files/mkdir', path: '/recordings', new_name: '새 폴더'}]);
  assert.deepEqual(refreshes, ['/recordings']);
  name = null;
  await click();
  assert.equal(calls.length, 1);
  assert.equal(refreshes.length, 1);
  name = '../outside'; fail = true;
  await click();
  assert.equal(refreshes.length, 1);
  assert.equal(alerts.length, 1);
  assert.ok(alerts[0].includes('invalid name'));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run(
            [shutil.which("node"), "-e", script], text=True, capture_output=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
