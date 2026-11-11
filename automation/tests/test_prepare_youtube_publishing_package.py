import json
import tempfile
import unittest
from pathlib import Path

from automation.prepare_youtube_publishing_package import build_package, load_channel


class PublishingPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets.json"
        self.video = self.root / "final.mp4"
        self.thumbnail = self.root / "thumb.png"
        self.video.write_bytes(b"video-placeholder")
        self.thumbnail.write_bytes(b"image-placeholder")
        self.assets.write_text(json.dumps({
            "channel": "devotional",
            "subject": "Hanuman story",
            "youtube": {
                "title": "हनुमान जी की प्रेरक कथा",
                "description": "एक भक्तिमय कथा।",
                "tags": ["हनुमान", "भक्ति"],
                "hashtags": ["#Bhakti", "#Hanuman"],
            },
        }, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_review_only_package(self):
        package = build_package(
            self.assets, self.video, "devotional",
            thumbnail_path=self.thumbnail,
            made_for_kids=False,
            contains_synthetic_media=True,
        )
        self.assertEqual(package["workflow"]["status"], "pending_human_review")
        self.assertFalse(package["workflow"]["upload_authorized"])
        self.assertFalse(package["workflow"]["upload_enabled_in_channel_config"])
        self.assertEqual(package["youtube"]["privacy_status"], "private")
        self.assertIs(package["youtube"]["made_for_kids"], False)
        self.assertIs(package["youtube"]["contains_synthetic_media"], True)
        self.assertEqual(package["thumbnail_file"], str(self.thumbnail.resolve()))
        self.assertTrue(all(value is False for value in package["workflow"]["checks"].values()))

    def test_requires_explicit_audience_review(self):
        with self.assertRaisesRegex(ValueError, "made_for_kids"):
            build_package(
                self.assets, self.video, "devotional",
                contains_synthetic_media=True,
            )

    def test_rejects_cross_channel_asset_package(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_package(
                self.assets, self.video, "motivation",
                made_for_kids=False, contains_synthetic_media=True,
            )

    def test_rejects_missing_video(self):
        with self.assertRaisesRegex(ValueError, "final video"):
            build_package(
                self.assets, self.root / "missing.mp4", "devotional",
                made_for_kids=False, contains_synthetic_media=True,
            )

    def test_rejects_oversized_title(self):
        data = json.loads(self.assets.read_text(encoding="utf-8"))
        data["youtube"]["title"] = "x" * 101
        self.assets.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "title"):
            build_package(
                self.assets, self.video, "devotional",
                made_for_kids=False, contains_synthetic_media=True,
            )

    def test_channel_uploads_must_remain_disabled(self):
        config = json.loads(Path(__file__).with_name("channel_configs.json").read_text(encoding="utf-8"))
        config["channels"]["devotional"]["publishing"]["upload_enabled"] = True
        altered = self.root / "channels.json"
        altered.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "uploads to remain disabled"):
            load_channel(altered, "devotional")


if __name__ == "__main__":
    unittest.main()
