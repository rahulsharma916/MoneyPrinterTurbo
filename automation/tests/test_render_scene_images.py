import json
import tempfile
import unittest
from pathlib import Path

from automation.render_scene_images import load_package, render_package


def package():
    return {
        "channel": "devotional",
        "subject": "हनुमान कथा",
        "scenes": [
            {"image_prompt": "Temple at sunrise, cinematic illustration"},
            {"image_prompt": "Hanuman devotional scene, respectful illustration"},
        ],
        "thumbnail": {"image_prompt": "16:9 thumbnail with negative space"},
    }


class RenderSceneImagesTests(unittest.TestCase):
    def test_load_valid_package(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assets.json"
            path.write_text(json.dumps(package(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(len(load_package(path)["scenes"]), 2)

    def test_reject_missing_prompt(self):
        data = package()
        data["scenes"][0]["image_prompt"] = ""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assets.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_package(path)

    def test_dry_run_creates_plan_without_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            result = render_package(
                package(), Path(directory), max_scene_images=1,
                include_thumbnail=True, execute=False,
            )
            self.assertEqual(result["execution"], "dry_run")
            self.assertEqual([item["status"] for item in result["images"]], ["planned", "planned"])

    def test_scene_limit_selects_only_requested_count(self):
        with tempfile.TemporaryDirectory() as directory:
            result = render_package(
                package(), Path(directory), max_scene_images=1,
                include_thumbnail=False, execute=False,
            )
            self.assertEqual(len(result["images"]), 1)
            self.assertEqual(result["images"][0]["scene_number"], 1)


if __name__ == "__main__":
    unittest.main()
