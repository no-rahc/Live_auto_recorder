from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lar_app.release import apply_release_info, load_release_info
from lar_app.server import ServerSettings
from lar_app.web.assets import all_asset_paths, inject_console_assets


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AppRuntimeStructureTests(unittest.TestCase):
    def test_entrypoint_stays_thin(self):
        source = (PROJECT_ROOT / "app_entry.py").read_text(encoding="utf-8")
        self.assertLessEqual(len(source.splitlines()), 30)
        self.assertNotIn("BaseHTTPMiddleware", source)
        self.assertNotIn("STYLESHEETS", source)
        self.assertIn("build_application", source)

    def test_asset_manifest_has_unique_paths(self):
        paths = all_asset_paths()
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(path.startswith("/static/") for path in paths))

    def test_asset_injection_is_idempotent_and_removes_title_version(self):
        html = "<html><head><title>Live Auto Recorder v1.1.15</title></head><body><main>ok</main></body></html>"
        injected = inject_console_assets(html, "v1.1.16")
        self.assertIn("<title>Live Auto Recorder</title>", injected)
        self.assertIn("/static/css/app-v3.css?v=v1.1.16", injected)
        self.assertIn("/static/js/app-ui-v3.js?v=v1.1.16", injected)
        self.assertEqual(inject_console_assets(injected, "v1.1.16"), injected)

    def test_asset_version_is_html_escaped(self):
        injected = inject_console_assets("<html><head></head><body></body></html>", 'v1.0" unsafe')
        self.assertIn("v1.0&quot; unsafe", injected)
        self.assertNotIn('v1.0" unsafe', injected)

    def test_release_info_uses_version_file_and_updates_templates(self):
        globals_map: dict[str, str] = {}
        core = SimpleNamespace(
            PROGRAM_NAME="Recorder Test",
            PROGRAM_VERSION="v0.0.1",
            templates=SimpleNamespace(env=SimpleNamespace(globals=globals_map)),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("v9.8.7\n", encoding="utf-8")
            release = load_release_info(core, root_dir=root)

        self.assertEqual(release.name, "Recorder Test")
        self.assertEqual(release.version, "v9.8.7")
        apply_release_info(core, release)
        self.assertEqual(core.PROGRAM_VERSION, "v9.8.7")
        self.assertEqual(globals_map["program_name"], "Recorder Test")
        self.assertEqual(globals_map["program_version"], "v9.8.7")

    def test_server_settings_validate_environment(self):
        settings = ServerSettings.from_env({
            "HOST": "127.0.0.1",
            "PORT": "8080",
            "LOG_LEVEL": "DEBUG",
        })
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.log_level, "debug")

        with self.assertRaisesRegex(ValueError, "PORT must be an integer"):
            ServerSettings.from_env({"PORT": "abc"})
        with self.assertRaisesRegex(ValueError, "between 1 and 65535"):
            ServerSettings.from_env({"PORT": "70000"})
        with self.assertRaisesRegex(ValueError, "LOG_LEVEL"):
            ServerSettings.from_env({"LOG_LEVEL": "verbose"})


if __name__ == "__main__":
    unittest.main()
