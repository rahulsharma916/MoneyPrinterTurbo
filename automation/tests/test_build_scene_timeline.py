from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from automation.build_scene_timeline import build_timeline, parse_srt


class BuildSceneTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.images = self.root / "images"
        self.images.mkdir()
        self.image1 = self.images / "scene_001.png"
        self.image2 = self.images / "scene_002.png"
        self.image1.write_bytes(b"image-1")
        self.image2.write_bytes(b"image-2")
        self.assets = self.root / "assets.json"
        self.assets.write_text(json.dumps({
            "channel": "devotional",
            "subject": "Hanuman story",
            "scenes": [
                {"scene_number": 1, "narration_excerpt": "Hanuman crossed the mighty ocean"},
                {"scene_number": 2, "narration_excerpt": "He reached Lanka and found Sita"},
            ],
        }), encoding="utf-8")
        self.manifest = self.images / "image_manifest.json"
        self.manifest.write_text(json.dumps({
            "execution": "executed",
            "images": [
                {"kind": "scene", "scene_number": 1, "status": "generated", "file": str(self.image1)},
                {"kind": "scene", "scene_number": 2, "status": "generated", "file": str(self.image2)},
                {"kind": "thumbnail", "scene_number": None, "status": "generated", "file": str(self.images / "thumb.png")},
            ],
        }), encoding="utf-8")
        self.srt = self.root / "narration.srt"
        self.srt.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\nHanuman crossed the mighty ocean.\n\n"
            "2\n00:00:03,000 --> 00:00:06,000\nHe reached Lanka and found Sita.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_aligns_scene_excerpts_monotonically(self):
        result = build_timeline(self.assets, self.manifest, self.srt)
        self.assertEqual(result["aligned_scene_count"], 2)
        self.assertEqual(result["scenes"][0]["start_seconds"], 0.0)
        self.assertEqual(result["scenes"][0]["end_seconds"], 3.0)
        self.assertEqual(result["scenes"][1]["start_seconds"], 3.0)
        self.assertEqual(result["scenes"][1]["end_seconds"], 6.0)

    def test_marks_unmatched_excerpt_for_review(self):
        data = json.loads(self.assets.read_text(encoding="utf-8"))
        data["scenes"][1]["narration_excerpt"] = "unrelated words not spoken anywhere"
        self.assets.write_text(json.dumps(data), encoding="utf-8")
        result = build_timeline(self.assets, self.manifest, self.srt, min_score=0.8)
        self.assertFalse(result["scenes"][1]["aligned"])
        self.assertIsNone(result["scenes"][1]["start_seconds"])

    def test_rejects_dry_run_manifest(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["execution"] = "dry_run"
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "executed"):
            build_timeline(self.assets, self.manifest, self.srt)

    def test_rejects_scene_image_outside_manifest_directory(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["images"][0]["file"] = str(self.root / "outside.png")
        (self.root / "outside.png").write_bytes(b"outside")
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside"):
            build_timeline(self.assets, self.manifest, self.srt)

    def test_rejects_invalid_srt(self):
        self.srt.write_text("not an srt", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no readable"):
            parse_srt(self.srt)


if __name__ == "__main__":
    unittest.main()
