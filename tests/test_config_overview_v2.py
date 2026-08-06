from pathlib import Path
import unittest

from lar_app.web.assets import BODY_SCRIPTS, STYLESHEETS, all_asset_paths


class ConfigOverviewAssetTests(unittest.TestCase):
    def test_overview_assets_are_registered_after_workspace_and_safety(self):
        paths = all_asset_paths()
        self.assertIn("/static/css/config-overview-v2.css", paths)
        self.assertIn("/static/js/config-overview-v2.js", paths)

        script_paths = [asset.path for asset in BODY_SCRIPTS]
        self.assertLess(
            script_paths.index("/static/js/config-workspace-v1.js"),
            script_paths.index("/static/js/config-safety-v1.js"),
        )
        self.assertLess(
            script_paths.index("/static/js/config-safety-v1.js"),
            script_paths.index("/static/js/config-overview-v2.js"),
        )

        style_paths = [asset.path for asset in STYLESHEETS]
        self.assertLess(
            style_paths.index("/static/css/config-safety-v1.css"),
            style_paths.index("/static/css/config-overview-v2.css"),
        )

    def test_overview_source_keeps_required_information_layers(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "templates/static/js/config-overview-v2.js").read_text(encoding="utf-8")
        stylesheet = (root / "templates/static/css/config-overview-v2.css").read_text(encoding="utf-8")

        for text in (
            "파일 관리",
            "접속 보안",
            "lar-tab-status",
            "lar-setting-switch",
            "lar-encoding-advanced",
            "lar-config-change-details",
            "lastTestLabel",
        ):
            self.assertIn(text, source)

        for selector in (
            ".lar-config-overview-line",
            ".lar-setting-switch",
            ".lar-encoding-advanced",
            ".lar-config-change-details",
        ):
            self.assertIn(selector, stylesheet)


if __name__ == "__main__":
    unittest.main()
