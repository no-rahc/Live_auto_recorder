import unittest

from lar_app.web.middleware import (
    _apply_secret_actions,
    _validate_dangerous_config,
    mask_config_secrets,
)


class ConfigSafetyMiddlewareTests(unittest.TestCase):
    def test_config_html_never_contains_stored_secrets(self):
        html = """
        <input type="text" id="telegram_bot_token" name="telegram_bot_token" value="telegram-secret">
        <input id="telegram_chat_id" name="telegram_chat_id" value="123456789">
        <input type="text" id="discord_webhook_url" name="discord_webhook_url" value="https://discord.example/secret">
        """

        masked = mask_config_secrets(html)

        self.assertNotIn("telegram-secret", masked)
        self.assertNotIn("123456789", masked)
        self.assertNotIn("discord.example/secret", masked)
        self.assertEqual(masked.count('data-stored-secret="true"'), 3)
        self.assertEqual(masked.count('type="password"'), 3)

    def test_secret_actions_preserve_replace_and_clear(self):
        pairs = [
            ("telegram_bot_token", ""),
            ("telegram_bot_token_action", "keep"),
            ("telegram_chat_id", "new-chat"),
            ("telegram_chat_id_action", "replace"),
            ("discord_webhook_url", "ignored"),
            ("discord_webhook_url_action", "clear"),
        ]

        _apply_secret_actions(
            pairs,
            {"discord_webhook_url": "stored-webhook"},
            {"telegram_bot_token": "stored-token", "telegram_chat_id": "stored-chat"},
        )
        result = dict(pairs)

        self.assertEqual(result["telegram_bot_token"], "stored-token")
        self.assertEqual(result["telegram_chat_id"], "new-chat")
        self.assertEqual(result["discord_webhook_url"], "")

    def test_risky_file_manager_transition_requires_acknowledgement(self):
        current = {
            "loginMode": False,
            "fileManagerEnabled": False,
            "fileManagerMode": "whitelist",
            "fileManagerReadOnly": True,
            "trashEnabled": True,
        }
        risky = [
            ("loginMode", "false"),
            ("fileManagerEnabled", "true"),
            ("fileManagerMode", "blacklist"),
            ("fileManagerReadOnly", "false"),
            ("trashEnabled", "false"),
        ]

        self.assertIn(
            "위험한 파일 관리자",
            _validate_dangerous_config(risky, current) or "",
        )
        risky.append(("danger_ack", "위험 설정 적용"))
        self.assertIsNone(_validate_dangerous_config(risky, current))


if __name__ == "__main__":
    unittest.main()
