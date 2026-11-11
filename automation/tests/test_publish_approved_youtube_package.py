import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.publish_approved_youtube_package import publish_approved_package, validate_approved_package


class ApprovedYouTubePublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_config = Path(__file__).resolve().parents[1] / "channel_configs.json"
        self.config = self.root / "channels.json"
        self.config.write_text(source_config.read_text(encoding="utf-8"), encoding="utf-8")
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"video-fixture")
        self.manifest_path = self.root / "video.publishing.json"
        self.env = {
            "MPT_DEVOTIONAL_UPLOAD_POST_API_KEY": "test-secret",
            "MPT_DEVOTIONAL_UPLOAD_POST_USERNAME": "devotional-test-account",
        }
        self.manifest = {
            "channel": "devotional",
            "video_file": str(self.video),
            "publishing_account_env": "MPT_DEVOTIONAL_UPLOAD_POST_USERNAME",
            "youtube": {
                "title": "हनुमान जी की कथा",
                "description": "भक्ति और साहस की कथा।",
                "tags": ["हनुमान", "भक्ति"],
                "privacy_status": "private",
                "made_for_kids": False,
                "contains_synthetic_media": False,
            },
            "workflow": {
                "status": "approved",
                "upload_authorized": True,
                "checks": {
                    "video_played_and_reviewed": True,
                    "thumbnail_reviewed": True,
                    "title_description_tags_reviewed": True,
                    "copyright_and_music_rights_checked": True,
                    "audience_declaration_reviewed": True,
                    "synthetic_media_disclosure_reviewed": True,
                    "correct_channel_account_confirmed": True,
                },
                "approval": {
                    "approved_by": "channel-owner",
                    "approved_at": "2026-11-11T10:00:00+05:30",
                },
            },
        }
        self._save()

    def tearDown(self):
        self.temp.cleanup()

    def _save(self):
        self.manifest_path.write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    def test_dry_run_validates_without_network_or_manifest_mutation(self):
        before = self.manifest_path.read_text(encoding="utf-8")
        with patch("automation.publish_approved_youtube_package.UploadPostService") as service:
            result = publish_approved_package(
                self.manifest_path, "devotional", config_path=self.config,
                execute=False, environ=self.env,
            )
        service.assert_not_called()
        self.assertTrue(result["ready"])
        self.assertFalse(result["executed"])
        self.assertEqual(self.manifest_path.read_text(encoding="utf-8"), before)

    def test_execute_uses_one_shot_account_and_declared_synthetic_flag(self):
        service = patch("automation.publish_approved_youtube_package.UploadPostService").start()
        self.addCleanup(patch.stopall)
        service.return_value.upload_video.return_value = {
            "success": True, "request_id": "upload-123",
        }
        result = publish_approved_package(
            self.manifest_path, "devotional", config_path=self.config,
            execute=True, confirm_upload=True, environ=self.env,
        )
        account = service.call_args.kwargs["account"]
        self.assertTrue(account["upload_post_enabled"])
        self.assertEqual(account["upload_post_username"], "devotional-test-account")
        kwargs = service.return_value.upload_video.call_args.kwargs
        self.assertEqual(kwargs["platforms"], ["youtube"])
        self.assertIs(kwargs["youtube_extra"]["containsSyntheticMedia"], False)
        self.assertEqual(result["status"], "completed")
        saved = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["workflow"]["execution_attempt"]["request_id"], "upload-123")
        self.assertEqual(saved["workflow"]["execution_attempt"]["status"], "completed")

    def test_requires_both_execution_flags(self):
        with self.assertRaisesRegex(ValueError, "requires both"):
            publish_approved_package(
                self.manifest_path, "devotional", config_path=self.config,
                execute=True, confirm_upload=False, environ=self.env,
            )

    def test_rejects_incomplete_human_checklist(self):
        self.manifest["workflow"]["checks"]["correct_channel_account_confirmed"] = False
        self._save()
        with self.assertRaisesRegex(ValueError, "checklist incomplete"):
            validate_approved_package(
                self.manifest, self.manifest_path, "devotional", self.config,
            )

    def test_blocks_retry_after_an_attempt_is_recorded(self):
        self.manifest["workflow"]["execution_attempt"] = {
            "id": "existing", "status": "outcome_unconfirmed",
        }
        self._save()
        with self.assertRaisesRegex(ValueError, "already has an execution attempt"):
            publish_approved_package(
                self.manifest_path, "devotional", config_path=self.config,
                execute=False, environ=self.env,
            )

    def test_rejects_channel_mismatch(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_approved_package(
                self.manifest, self.manifest_path, "motivation", self.config,
            )


if __name__ == "__main__":
    unittest.main()
