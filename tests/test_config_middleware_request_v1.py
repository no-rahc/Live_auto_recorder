import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lar_app.web.middleware import SecurityMiddleware


class _AuditSink:
    def audit(self, event, detail, status="ok"):
        return None


class ConfigMiddlewareRequestTests(unittest.TestCase):
    def test_posted_form_is_replayed_with_preserved_secrets(self):
        app = FastAPI()

        @app.post("/config")
        async def receive_config(request: Request):
            form = await request.form()
            return {key: str(value) for key, value in form.multi_items()}

        app.add_middleware(SecurityMiddleware, operations=_AuditSink())
        payload = {
            "loginMode": "true",
            "fileManagerEnabled": "false",
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

        with (
            patch("lar_app.web.middleware.loadConfig", return_value={
                "loginMode": True,
                "fileManagerEnabled": False,
                "fileManagerMode": "whitelist",
                "fileManagerReadOnly": True,
                "trashEnabled": True,
                "discord_webhook_url": "stored-webhook",
            }),
            patch("lar_app.web.middleware.loadTelegram", return_value={
                "telegram_bot_token": "stored-token",
                "telegram_chat_id": "stored-chat",
            }),
            patch("lar_app.web.middleware.loadAccount", return_value=None),
        ):
            response = TestClient(app).post("/config", data=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["telegram_bot_token"], "stored-token")
        self.assertEqual(body["telegram_chat_id"], "stored-chat")
        self.assertEqual(body["discord_webhook_url"], "stored-webhook")


if __name__ == "__main__":
    unittest.main()
