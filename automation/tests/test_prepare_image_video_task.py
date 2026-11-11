from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from automation.prepare_image_video_task import collect_scene_images, prepare_video_task


class PrepareImageVideoTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.images = self.root / "assets.images"
        self.images.mkdir()
        self.scene1 = self.images / "scene_001.png"
        self.scene2 = self.images / "scene_002.png"
        self.scene1.write_bytes(b"png-placeholder-1")
        self.scene2.write_bytes(b"png-placeholder-2")
        self.assets = self.root / "story.assets.json"
        self.assets.write_text(json.dumps({"channel": "devotional", "subject": "Hanuman story"}), encoding="utf-8")
        self.script = self.root / "story.txt"
        self.script.write_text("First narration. Second narration.", encoding="utf-8")
        self.manifest = self.images / "image_manifest.json"
        self.manifest.write_text(json.dumps({
            "execution": "executed",
            "images": [
                {"file": str(self.scene2), "kind": "scene", "scene_number": 2, "status": "generated"},
                {"file": str(self.images / "thumbnail.png"), "kind": "thumbnail", "scene_number": None, "status": "generated"},
                {"file": str(self.scene1), "kind": "scene", "scene_number": 1, "status": "generated"},
            ],
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_collects_images_in_scene_order_and_ignores_thumbnail(self):
        scenes = collect_scene_images(self.manifest)
        self.assertEqual([number for number, _ in scenes], [1, 2])

    def test_dry_run_manifest_uses_local_sequential_images(self):
        local_dir = self.root / "local_videos"
        output = prepare_video_task(
            self.assets, self.manifest, self.script,
            local_videos_dir=local_dir,
        )
        task = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(task["video_source"], "local")
        self.assertEqual(task["video_concat_mode"], "sequential")
        self.assertEqual(task["image_motion"], "zoom")
        self.assertEqual(len(task["video_materials"]), 2)
        self.assertTrue((local_dir / task["video_materials"][0]["url"]).is_file())

    def test_rejects_dry_run_image_manifest(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["execution"] = "dry_run"
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "executed"):
            collect_scene_images(self.manifest)

    def test_rejects_path_outside_manifest_directory(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["images"][0]["file"] = str(self.root / "outside.png")
        (self.root / "outside.png").write_bytes(b"not allowed")
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inside"):
            collect_scene_images(self.manifest)

    def test_rejects_invalid_aspect_and_clip_duration(self):
        with self.assertRaisesRegex(ValueError, "aspect"):
            prepare_video_task(self.assets, self.manifest, self.script, aspect="4:3", local_videos_dir=self.root / "out")
        with self.assertRaisesRegex(ValueError, "clip_duration"):
            prepare_video_task(self.assets, self.manifest, self.script, clip_duration=0, local_videos_dir=self.root / "out")


if __name__ == "__main__":
    unittest.main()
