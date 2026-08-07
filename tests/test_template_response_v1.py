from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from lar_app.template_compat import install_template_response_compat


class TemplateResponseCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        install_template_response_compat()
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        (root / "index.html").write_text(
            "<!doctype html><title>{{ marker }}</title><h1>{{ marker }}</h1>",
            encoding="utf-8",
        )
        templates = Jinja2Templates(directory=str(root))
        app = FastAPI()

        @app.get("/legacy")
        async def legacy_page(request: Request):
            # Reproduces the calling convention that failed with Starlette 1.x
            # as: TypeError: unhashable type: 'dict'.
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "marker": "legacy-ok"},
            )

        @app.get("/legacy-status")
        async def legacy_status_page(request: Request):
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "marker": "legacy-status-ok"},
                201,
            )

        @app.get("/modern")
        async def modern_page(request: Request):
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={"request": request, "marker": "modern-ok"},
            )

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.tempdir.cleanup()

    def test_legacy_dashboard_style_call_renders_html(self) -> None:
        response = self.client.get("/legacy")
        self.assertEqual(response.status_code, 200)
        self.assertIn("legacy-ok", response.text)

    def test_legacy_positional_status_code_is_preserved(self) -> None:
        response = self.client.get("/legacy-status")
        self.assertEqual(response.status_code, 201)
        self.assertIn("legacy-status-ok", response.text)

    def test_modern_starlette_call_still_renders_html(self) -> None:
        response = self.client.get("/modern")
        self.assertEqual(response.status_code, 200)
        self.assertIn("modern-ok", response.text)


if __name__ == "__main__":
    unittest.main()
