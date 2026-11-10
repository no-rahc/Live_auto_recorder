"""Opt-in host allowlisting must reject arbitrary private IPs."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from lar_app.web.v2_security import V2OriginMiddleware


class V2OriginAllowlistTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()
        app.add_middleware(V2OriginMiddleware)

        @app.get("/ok")
        async def ok():
            return {"ok": True}

        @app.post("/write")
        async def write():
            return {"ok": True}

        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")
        self.addAsyncCleanup(self.client.aclose)

    async def test_private_ip_not_automatically_trusted(self):
        with patch.dict(os.environ, {"LAR_V2_ENABLED": "true", "LAR_ALLOWED_HOSTS": "localhost,127.0.0.1,::1"}):
            denied = await self.client.get("/ok", headers={"Host": "192.168.20.33"})
            allowed = await self.client.get("/ok", headers={"Host": "localhost"})
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(allowed.status_code, 200)

    async def test_explicit_private_ip_allowed_but_cross_origin_blocked(self):
        with patch.dict(os.environ, {"LAR_V2_ENABLED": "true", "LAR_ALLOWED_HOSTS": "192.168.20.33"}):
            allowed = await self.client.get("/ok", headers={"Host": "192.168.20.33"})
            cross = await self.client.post(
                "/write",
                headers={"Host": "192.168.20.33", "Origin": "http://untrusted.example"},
            )
            same = await self.client.post(
                "/write",
                headers={"Host": "192.168.20.33", "Origin": "http://192.168.20.33"},
            )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(cross.status_code, 403)
        self.assertEqual(same.status_code, 200)

    async def test_default_disabled_mode_unchanged(self):
        with patch.dict(os.environ, {"LAR_V2_ENABLED": "false", "LAR_ALLOWED_HOSTS": "localhost"}):
            response = await self.client.get("/ok", headers={"Host": "192.168.20.33"})
        self.assertEqual(response.status_code, 200)
