import unittest

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lar_app.web.middleware import SecurityMiddleware


class _AuditSink:
    def audit(self, event, detail, status="ok"):
        return None


class ConfigMiddlewareRequestTests(unittest.TestCase):
    def test_posted_form_passes_through_without_private_request_rewrite(self):
        app = FastAPI()

        @app.post("/config")
        async def receive_config(request: Request):
            form = await request.form()
            return {key: str(value) for key, value in form.multi_items()}

        app.add_middleware(SecurityMiddleware, operations=_AuditSink())
        payload = {
            "loginMode": "true",
            "fileManagerEnabled": "true",
            "fileManagerMode": "whitelist",
            "fileManagerReadOnly": "true",
            "trashEnabled": "true",
            "telegram_bot_token": "",
            "telegram_bot_token_action": "keep",
            "telegram_chat_id": "",
            "telegram_chat_id_action": "keep",
            "discord_webhook_url": "",
            "discord_webhook_url_action": "keep",
        }
        response = TestClient(app).post("/config", data=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["loginMode"], "true")
        self.assertEqual(body["fileManagerEnabled"], "true")
        self.assertEqual(body["telegram_bot_token"], "")
        self.assertEqual(body["telegram_chat_id"], "")
        self.assertEqual(body["discord_webhook_url"], "")

    def test_legacy_auth_routes_redirect_to_dashboard(self):
        app = FastAPI()

        @app.get("/")
        async def root():
            return {"status": "ok"}

        @app.get("/login")
        async def login():
            return {"legacy": True}

        app.add_middleware(SecurityMiddleware, operations=_AuditSink())
        response = TestClient(app, follow_redirects=False).get("/login")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/")


if __name__ == "__main__":
    unittest.main()
