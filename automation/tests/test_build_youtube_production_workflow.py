from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from automation.build_youtube_production_workflow import build_workflow


class BuildYouTubeProductionWorkflowTests(unittest.TestCase):
    def test_channel_isolation_and_default_guardrails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "script.txt"
            script.write_text("नमूना narration", encoding="utf-8")
            result = build_workflow("devotional", "हनुमान जी", script, root / "out")
            self.assertEqual(result["channel"], "devotional")
            self.assertTrue(result["guardrails"]["channels_isolated"])
            self.assertFalse(result["guardrails"]["public_uploads_enabled"])
            self.assertFalse(result["guardrails"]["upload_authorized"])
            self.assertEqual(result["commands"][0]["command"][3], "devotional")

    def test_motivation_channel_is_not_mixed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "script.txt"
            script.write_text("एक प्रेरक कहानी", encoding="utf-8")
            result = build_workflow("motivation", "अनुशासन", script, root / "out")
            self.assertEqual(result["channel"], "motivation")
            self.assertIn("motivation.assets.json", result["commands"][0]["command"][-1])
            self.assertNotIn("devotional", result["commands"][0]["command"])

    def test_timeline_stays_blocked_without_exact_audio_and_srt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "script.txt"
            script.write_text("script", encoding="utf-8")
            result = build_workflow("devotional", "विषय", script, root / "out")
            timeline = next(item for item in result["commands"] if item["id"] == "scene_timeline")
            self.assertIsNone(timeline["command"])
            self.assertIn("final narration SRT", timeline["blocked_by"])

    def test_invalid_channel_and_aspect_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "script.txt"
            script.write_text("script", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_workflow("both", "विषय", script, root / "out")
            with self.assertRaises(ValueError):
                build_workflow("motivation", "विषय", script, root / "out", aspect="4:3")

    def test_missing_script_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_workflow("motivation", "विषय", root / "missing.txt", root / "out")
            self.assertEqual(result["status"], "input_errors")
            self.assertTrue(any("script file does not exist" in item for item in result["input_errors"]))


if __name__ == "__main__":
    unittest.main()
