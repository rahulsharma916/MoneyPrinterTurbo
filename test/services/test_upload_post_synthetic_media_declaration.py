import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from app.services.upload_post import UploadPostService


def _response(payload):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


class TestUploadPostSyntheticMediaDeclaration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.video = Path(self.temp.name) / "video.mp4"
        self.video.write_bytes(b"video fixture")
        self.service = UploadPostService({
            "upload_post_enabled": True,
            "upload_post_api_key": "test-api-key",
            "upload_post_username": "test-channel",
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_false_is_sent_to_youtube(self):
        with patch("app.services.upload_post.requests.post", return_value=_response({
            "success": True,
            "results": {"youtube": {"success": True}},
        })) as post:
            result = self.service.upload_video(
                str(self.video),
                "Test title",
                platforms=["youtube"],
                youtube_extra={
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": False,
                },
            )
        self.assertTrue(result["success"])
        data = dict(post.call_args.kwargs["data"])
        self.assertEqual(data["containsSyntheticMedia"], "false")

    def test_explicit_true_is_sent_to_youtube(self):
        with patch("app.services.upload_post.requests.post", return_value=_response({
            "success": True,
            "results": {"youtube": {"success": True}},
        })) as post:
            result = self.service.upload_video(
                str(self.video),
                "Test title",
                platforms=["youtube"],
                youtube_extra={
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": True,
                },
            )
        self.assertTrue(result["success"])
        data = dict(post.call_args.kwargs["data"])
        self.assertEqual(data["containsSyntheticMedia"], "true")

    def test_rejects_non_boolean_synthetic_media_value(self):
        with patch("app.services.upload_post.requests.post") as post:
            result = self.service.upload_video(
                str(self.video),
                "Test title",
                platforms=["youtube"],
                youtube_extra={
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": "false",
                },
            )
        self.assertFalse(result["success"])
        self.assertIn("must be a boolean", result["error"])
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
