from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from automation.build_youtube_production_readiness import build_report


class ProductionReadinessTests(unittest.TestCase):
    def make_manifest(self, root: Path, *, complete: bool) -> Path:
        channels = {}
        for name in ("devotional", "motivation"):
            (root / f"{name}-oauth.json").write_text("{}", encoding="utf-8")
            (root / f"{name}-token.json").write_text("{}", encoding="utf-8")
            (root / f"{name}-pilot.mp4").write_bytes(b"pilot")
            quality = {
                "status": "passed" if complete else "failed",
                "video_file": f"{name}-pilot.mp4",
            }
            (root / f"{name}-quality.json").write_text(json.dumps(quality), encoding="utf-8")
            channels[name] = {
                "channel_id": f"UC_{name}",
                "oauth_client_secrets_file": f"{name}-oauth.json",
                "oauth_token_file": f"{name}-token.json",
                "oauth_verified": complete,
                "channel_access_verified": complete,
                "upload_scope_verified": complete,
                "providers": {
                    key: {"name": f"{key}-provider", "configured": complete, "verified": complete}
                    for key in ("narration", "image", "video")
                },
                "pilot_video_file": f"{name}-pilot.mp4",
                "pilot_quality_report_file": f"{name}-quality.json",
                "upload_approved": False,
            }
        path = root / "manifest.json"
        path.write_text(json.dumps({
            "manifest_type": "youtube_production_readiness_manifest",
            "schema_version": 1,
            "public_uploads_enabled": False,
            "human_approval_required": True,
            "channels": channels,
        }), encoding="utf-8")
        return path

    def test_complete_evidence_is_only_ready_for_human_review(self):
        with tempfile.TemporaryDirectory() as temp:
            report = build_report(self.make_manifest(Path(temp), complete=True))
        self.assertEqual(report["overall_status"], "both_channels_ready_for_human_review")
        self.assertFalse(report["production_authorized"])
        self.assertFalse(report["public_uploads_enabled"])

    def test_missing_verification_and_failed_quality_block_both_channels(self):
        with tempfile.TemporaryDirectory() as temp:
            report = build_report(self.make_manifest(Path(temp), complete=False))
        self.assertEqual(report["overall_status"], "blocked")
        self.assertIn("oauth_authentication", report["channels"]["devotional"]["blockers"])
        self.assertIn("pilot_quality_report", report["channels"]["motivation"]["blockers"])

    def test_public_uploads_must_remain_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_manifest(Path(temp), complete=True)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["public_uploads_enabled"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            report = build_report(path)
        self.assertEqual(report["overall_status"], "blocked")
        self.assertFalse(report["production_authorized"])


if __name__ == "__main__":
    unittest.main()
