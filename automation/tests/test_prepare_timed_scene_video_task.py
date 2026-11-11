from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.prepare_timed_scene_video_task import (
    _load_approved_scenes,
    prepare_timed_video_task,
)


class TimedSceneVideoTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.image_root = self.root / "images"
        self.image_root.mkdir()
        self.image_one = self.image_root / "scene_001.png"
        self.image_two = self.image_root / "scene_002.png"
        self.image_one.write_bytes(b"image-one")
        self.image_two.write_bytes(b"image-two")
        self.audio = self.root / "narration.mp3"
        self.audio.write_bytes(b"audio")
        self.script = self.root / "script.txt"
        self.script.write_text("पहला दृश्य। दूसरा दृश्य।", encoding="utf-8")
        self.timeline_path = self.root / "scene_timeline.json"
        self._write_timeline()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_timeline(self, *, second_aligned=True, first_start=0.0):
        timeline = {
            "channel": "devotional",
            "subject": "हनुमान जी की कथा",
            "aligned_scene_count": 2 if second_aligned else 1,
            "scene_count": 2,
            "scenes": [
                {
                    "scene_number": 1,
                    "image_file": str(self.image_one),
                    "aligned": True,
                    "start_seconds": first_start,
                },
                {
                    "scene_number": 2,
                    "image_file": str(self.image_two),
                    "aligned": second_aligned,
                    "start_seconds": 3.0,
                },
            ],
        }
        self.timeline_path.write_text(
            json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
        )

    def test_loads_ordered_scenes_and_holds_first_from_zero(self):
        _, scenes = _load_approved_scenes(
            self.timeline_path, self.image_root, audio_duration=8.0
        )
        self.assertEqual([item[0] for item in scenes], [1, 2])
        self.assertAlmostEqual(scenes[0][2], 3.0)
        self.assertAlmostEqual(scenes[1][2], 8.0)

    def test_rejects_unaligned_scene(self):
        self._write_timeline(second_aligned=False)
        with self.assertRaisesRegex(ValueError, "all scenes must be aligned"):
            _load_approved_scenes(
                self.timeline_path, self.image_root, audio_duration=8.0
            )

    def test_rejects_image_outside_image_root(self):
        outside = self.root / "outside.png"
        outside.write_bytes(b"outside")
        timeline = json.loads(self.timeline_path.read_text(encoding="utf-8"))
        timeline["scenes"][0]["image_file"] = str(outside)
        self.timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inside --image-root"):
            _load_approved_scenes(
                self.timeline_path, self.image_root, audio_duration=8.0
            )

    def test_builds_manifest_with_timed_mp4s_and_custom_audio(self):
        local_videos = self.root / "local_videos"

        def render_mock(image_path, duration, image_motion):
            rendered = Path(image_path).with_name(
                Path(image_path).stem + ".rendered.mp4"
            )
            rendered.write_bytes(b"mp4")
            return str(rendered)

        with (
            patch("app.services.voice.get_audio_duration", return_value=8.0),
            patch("app.services.video.render_image_zoom_video", side_effect=render_mock),
        ):
            manifest = prepare_timed_video_task(
                self.timeline_path,
                self.image_root,
                self.audio,
                self.script,
                local_videos_dir=local_videos,
            )

        task = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(task["video_concat_mode"], "sequential")
        self.assertEqual(task["video_source"], "local")
        self.assertEqual(len(task["video_materials"]), 2)
        self.assertEqual(task["custom_audio_file"], "हनुमान-जी-की-कथा-devotional/narration.mp3")
        self.assertEqual(task["video_clip_duration"], 9)
        self.assertTrue((local_videos / task["video_materials"][0]["url"]).is_file())
        self.assertTrue((local_videos / task["video_materials"][1]["url"]).is_file())


if __name__ == "__main__":
    unittest.main()
