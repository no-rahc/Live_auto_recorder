from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lar_app.release import apply_release_info, load_release_info
from lar_app.security import enforce_local_mode, env_flag, secret_backups_allowed
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

    def test_legacy_core_never_installs_dependencies_at_import_time(self):
        source = (PROJECT_ROOT / "live_auto_recorder.py").read_text(encoding="utf-8")
        self.assertNotIn("install_missing_modules", source)
        self.assertNotIn('"-m", "pip", "install"', source)

    def test_asset_manifest_has_unique_paths(self):
        paths = all_asset_paths()
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(path.startswith("/static/") for path in paths))
        self.assertIn("/static/js/local-mode-v1.js", paths)
        self.assertIn("/static/css/ui-consolidated-v1.css", paths)
        self.assertNotIn("/static/css/local-mode-v1.css", paths)
        self.assertNotIn("/static/css/ui-refinement-final-v1.css", paths)
        self.assertNotIn("/static/js/sidebar-account-v1.js", paths)

    def test_asset_injection_is_idempotent_and_removes_title_version(self):
        html = "<html><head><title>Live Auto Recorder v1.1.15</title></head><body><main>ok</main></body></html>"
        injected = inject_console_assets(html, "v1.1.16")
        self.assertIn("<title>Live Auto Recorder</title>", injected)
        self.assertIn("/static/css/app-v3.css?v=v1.1.16", injected)
        self.assertIn("/static/css/ui-consolidated-v1.css?v=v1.1.16", injected)
        self.assertIn("/static/js/app-ui-v3.js?v=v1.1.16", injected)
        self.assertIn("/static/js/local-mode-v1.js?v=v1.1.16", injected)
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
        defaults = ServerSettings.from_env({})
        self.assertEqual(defaults.host, "127.0.0.1")
        self.assertEqual(defaults.port, 5000)

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

    def test_security_flags_are_strict(self):
        self.assertTrue(env_flag("FLAG", environ={"FLAG": "yes"}))
        self.assertFalse(env_flag("FLAG", True, environ={"FLAG": "off"}))
        self.assertTrue(env_flag("FLAG", True, environ={}))
        with self.assertRaisesRegex(ValueError, "FLAG must be one of"):
            env_flag("FLAG", environ={"FLAG": "sometimes"})

    def test_local_mode_forces_legacy_login_flag_off(self):
        saved: list[dict[str, bool]] = []
        app = SimpleNamespace(state=SimpleNamespace(config={"loginMode": True}))
        core = SimpleNamespace(saveConfig=lambda config: saved.append(dict(config)))

        changed = enforce_local_mode(app, core)
        self.assertTrue(changed)
        self.assertFalse(app.state.config["loginMode"])
        self.assertEqual(saved, [{"loginMode": False}])

        changed = enforce_local_mode(app, core)
        self.assertFalse(changed)
        self.assertEqual(len(saved), 1)

    def test_secret_backups_are_opt_in(self):
        self.assertFalse(secret_backups_allowed({}))
        self.assertTrue(secret_backups_allowed({"ALLOW_SECRET_BACKUPS": "true"}))


if __name__ == "__main__":
    unittest.main()
