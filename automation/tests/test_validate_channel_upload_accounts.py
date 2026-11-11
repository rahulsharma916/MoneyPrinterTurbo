import json
import tempfile
import unittest
from pathlib import Path

from automation.validate_channel_upload_accounts import load_channel_account


class ChannelUploadAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "channels.json"
        self.config.write_text(
            (Path(__file__).resolve().parents[1] / "channel_configs.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_resolves_devotional_credentials_without_mutating_config(self):
        values = {
            "MPT_DEVOTIONAL_UPLOAD_POST_API_KEY": "secret-a",
            "MPT_DEVOTIONAL_UPLOAD_POST_USERNAME": "devotional-account",
        }
        account = load_channel_account("devotional", config_path=self.config, environ=values)
        self.assertEqual(account, {
            "upload_post_enabled": True,
            "upload_post_api_key": "secret-a",
            "upload_post_username": "devotional-account",
        })
        saved = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertFalse(saved["channels"]["devotional"]["publishing"]["upload_enabled"])

    def test_motivation_uses_independent_environment_variables(self):
        values = {
            "MPT_MOTIVATION_UPLOAD_POST_API_KEY": "secret-b",
            "MPT_MOTIVATION_UPLOAD_POST_USERNAME": "motivation-account",
        }
        account = load_channel_account("motivation", config_path=self.config, environ=values)
        self.assertEqual(account["upload_post_username"], "motivation-account")
        self.assertEqual(account["upload_post_api_key"], "secret-b")

    def test_missing_secret_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing required"):
            load_channel_account("devotional", config_path=self.config, environ={})

    def test_rejects_same_env_name_for_key_and_username(self):
        data = json.loads(self.config.read_text(encoding="utf-8"))
        publishing = data["channels"]["devotional"]["publishing"]
        publishing["upload_post_account_env"] = publishing["upload_post_api_key_env"]
        self.config.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "separate environment variables"):
            load_channel_account("devotional", config_path=self.config, environ={})

    def test_refuses_when_channel_upload_is_enabled(self):
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["channels"]["devotional"]["publishing"]["upload_enabled"] = True
        self.config.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must remain disabled"):
            load_channel_account("devotional", config_path=self.config, environ={})


if __name__ == "__main__":
    unittest.main()
