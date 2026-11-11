from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from automation.build_youtube_production_readiness_audit import audit_production


class ProductionReadinessAuditTests(unittest.TestCase):
    def _fixture(self, root: Path, channel: str = "devotional"):
        assets = root / "assets.json"
        image = root / "scene_001.png"
        image.write_bytes(b"png")
        assets.write_text(json.dumps({
            "channel": channel, "subject": "test",
            "scenes": [{"scene_number": 1, "narration_excerpt": "test"}],
        }), encoding="utf-8")
        image_manifest = root / "image_manifest.json"
        image_manifest.write_text(json.dumps({
            "channel": channel, "images": [{
                "scene_number": 1, "status": "generated", "image_file": str(image),
            }],
        }), encoding="utf-8")
        timeline = root / "scene_timeline.json"
        timeline.write_text(json.dumps({
            "channel": channel, "scene_count": 1, "aligned_scene_count": 1,
            "scenes": [{"scene_number": 1, "aligned": True, "image_file": str(image)}],
        }), encoding="utf-8")
        timed = root / "timed.jsonl"
        timed.write_text(json.dumps({
            "video_source": "local", "video_aspect": "16:9",
            "video_materials": [{"url": "scene.mp4"}],
        }) + "\n", encoding="utf-8")
        audio = root / "narration.mp3"
        audio.write_bytes(b"audio")
        video = root / "final.mp4"
        video.write_bytes(b"video")
        quality = root / "quality.json"
        quality.write_text(json.dumps({
            "status": "passed", "expected_aspect": "16:9",
            "video_stream_count": 1, "audio_stream_count": 1,
            "checks": {"video_stream": "passed", "audio_stream": "passed",
                       "aspect_ratio": "passed", "duration_window": "passed"},
            "video_file": str(video), "narration_file": str(audio),
        }), encoding="utf-8")
        publishing = root / "publishing.json"
        publishing.write_text(json.dumps({
            "channel": channel, "video_file": str(video),
            "youtube": {"privacy_status": "private", "made_for_kids": False,
                        "contains_synthetic_media": True},
            "workflow": {"status": "pending_human_review",
                         "upload_authorized": False,
                         "upload_enabled_in_channel_config": False},
        }), encoding="utf-8")
        config = root / "config.json"
        config.write_text(json.dumps({"channels": {channel: {
            "content_profile": channel,
            "publishing": {"upload_enabled": False, "approval_required": True},
        }}}), encoding="utf-8")
        return (assets, image_manifest, timeline, timed, audio, video, quality, publishing, config)

    def test_complete_artifact_set_is_ready_for_human_review_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = self._fixture(root)
            report = audit_production("devotional", "16:9", *paths)
            self.assertEqual(report["readiness"], "ready_for_human_review")
            self.assertFalse(report["authorization"]["upload_authorized"])
            self.assertFalse(report["authorization"]["public_uploads_enabled"])

    def test_channel_mismatch_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = self._fixture(root, "motivation")
            report = audit_production("devotional", "16:9", *paths)
            self.assertEqual(report["readiness"], "blocked")
            self.assertTrue(any(item["name"] == "assets_channel_matches"
                                for item in report["blockers"]))

    def test_failed_quality_gate_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = list(self._fixture(root))
            quality = json.loads(paths[6].read_text(encoding="utf-8"))
            quality["status"] = "failed"
            paths[6].write_text(json.dumps(quality), encoding="utf-8")
            report = audit_production("devotional", "16:9", *paths)
            self.assertEqual(report["readiness"], "blocked")
            self.assertTrue(any(item["name"] == "video_quality_gate_passed"
                                for item in report["blockers"]))

    def test_missing_artifacts_produce_blocked_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing = [root / f"missing_{i}" for i in range(9)]
            report = audit_production("devotional", "9:16", *missing)
            self.assertEqual(report["readiness"], "blocked")
            self.assertEqual(report["audit_state"], "missing_required_artifacts")

    def test_publishing_manifest_must_remain_unauthorized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = list(self._fixture(root))
            data = json.loads(paths[7].read_text(encoding="utf-8"))
            data["workflow"]["upload_authorized"] = True
            paths[7].write_text(json.dumps(data), encoding="utf-8")
            report = audit_production("devotional", "16:9", *paths)
            self.assertEqual(report["readiness"], "blocked")


if __name__ == "__main__":
    unittest.main()
