import json
import tempfile
import unittest
from pathlib import Path

from automation.validate_channel_configs import validate


class ChannelConfigTests(unittest.TestCase):
    def load_config(self):
        path = Path(__file__).parents[1] / "channel_configs.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_default_channel_configs_are_valid_and_separate(self):
        data = self.load_config()
        self.assertEqual(validate(data), [])
        self.assertEqual(set(data["channels"]), {"devotional", "motivation"})
        self.assertNotEqual(
            data["channels"]["devotional"]["creative_direction"]["visual_style"],
            data["channels"]["motivation"]["creative_direction"]["visual_style"],
        )

    def test_uploads_must_remain_disabled_and_approval_required(self):
        data = self.load_config()
        data["channels"]["devotional"]["publishing"]["upload_enabled"] = True
        self.assertTrue(any("uploads must remain disabled" in e for e in validate(data)))

        data = self.load_config()
        data["channels"]["motivation"]["publishing"]["approval_required"] = False
        self.assertTrue(any("human approval must remain required" in e for e in validate(data)))

    def test_made_for_kids_requires_explicit_boolean_or_review_null(self):
        data = self.load_config()
        data["channels"]["devotional"]["publishing"]["made_for_kids"] = "false"
        self.assertTrue(any("made_for_kids" in e for e in validate(data)))


if __name__ == "__main__":
    unittest.main()
