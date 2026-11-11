from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from automation.build_youtube_production_workflow import build_workflow


class BuildYouTubeProductionWorkflowTests(unittest.TestCase):
    def _script(self, root: Path) -> Path:
        path = root / "narration.txt"
        path.write_text("यह एक नमूना हिंदी narration है।", encoding="utf-8")
        return path

    def test_devotional_runbook_is_isolated_and_upload_is_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_workflow("devotional", "हनुमान जी", self._script(root), root / "out")
            self.assertEqual(result["channel"], "devotional")
            self.assertIn("devotional.assets.json", result["paths"]["assets"])
            self.assertTrue(result["guardrails"]["devotional_and_motivation_are_separate"])
            self.assertFalse(result["guardrails"]["upload_enabled"])
            self.assertFalse(result["guardrails"]["upload_authorized"])
            self.assertFalse(result["guardrails"]["public_uploads_enabled"])

    def test_motivation_channel_uses_separate_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_workflow("motivation", "अनुशासन", self._script(root), root / "out")
            self.assertEqual(result["channel"], "motivation")
            self.assertIn("motivation.assets.json", result["paths"]["assets"])
            self.assertNotIn("devotional", result["paths"]["assets"])

    def test_downstream_stages_block_until_required_artifacts_exist(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_workflow("devotional", "विषय", self._script(root), root / "out")
            stages = {stage["id"]: stage for stage in result["stages"]}
            self.assertEqual(stages["creative_brief"]["status"], "ready")
            self.assertEqual(stages["scene_images"]["status"], "blocked")
            self.assertIn("executed image_manifest.json", stages["scene_timeline"]["blocked_by"])
            self.assertIn("approved scene_timeline.json", stages["timed_video_task"]["blocked_by"])
            self.assertIn("final rendered MP4", stages["publishing_review"]["blocked_by"])

    def test_timeline_ready_only_with_all_exact_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self._script(root)
            out = root / "out"
            out.mkdir()
            (out / "devotional.assets.json").write_text("{}", encoding="utf-8")
            (out / "images").mkdir()
            (out / "images" / "image_manifest.json").write_text("{}", encoding="utf-8")
            srt = root / "final.srt"
            audio = root / "final.mp3"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nनमस्ते\n", encoding="utf-8")
            audio.write_bytes(b"audio")
            result = build_workflow("devotional", "विषय", script, out, subtitles=srt, audio_file=audio)
            stages = {stage["id"]: stage for stage in result["stages"]}
            self.assertEqual(stages["scene_timeline"]["status"], "ready")
            self.assertEqual(stages["timed_video_task"]["status"], "blocked")

    def test_invalid_channel_and_aspect_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self._script(root)
            with self.assertRaises(ValueError):
                build_workflow("both", "विषय", script, root / "out")
            with self.assertRaises(ValueError):
                build_workflow("motivation", "विषय", script, root / "out", aspect="4:3")

    def test_missing_script_is_reported_without_claiming_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = build_workflow("motivation", "विषय", root / "missing.txt", root / "out")
            self.assertEqual(result["status"], "input_errors")
            self.assertEqual(result["stages"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
