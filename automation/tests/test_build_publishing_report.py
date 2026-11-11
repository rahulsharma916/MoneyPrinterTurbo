import json
import tempfile
import unittest
from pathlib import Path

from automation.build_publishing_report import build_report, write_report


class PublishingReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _manifest(self, name, channel, workflow, title=None):
        path = self.root / name
        path.write_text(json.dumps({
            "channel": channel,
            "channel_display_name": f"{channel.title()} Channel",
            "subject": "A test subject",
            "video_file": "/local/video.mp4",
            "youtube": {
                "title": title or "Test title",
                "privacy_status": "private",
                "made_for_kids": False,
                "contains_synthetic_media": True,
            },
            "workflow": workflow,
        }), encoding="utf-8")
        return path

    def test_groups_outcomes_separately_by_channel(self):
        devotional = self._manifest("devotional.publishing.json", "devotional", {
            "status": "approved",
            "approval": {"approved_by": "owner", "approved_at": "2026-11-11T10:00:00Z"},
            "execution_attempt": {
                "status": "completed",
                "started_at": "2026-11-11T10:01:00Z",
                "finished_at": "2026-11-11T10:02:00Z",
                "request_id": "request-1",
            },
        })
        motivation = self._manifest("motivation.publishing.json", "motivation", {
            "status": "pending_human_review",
            "approval": {},
        })
        report = build_report([devotional, motivation])
        self.assertEqual(report["total_packages"], 2)
        self.assertEqual(report["channels"]["devotional"]["completed_uploads"], 1)
        self.assertEqual(report["channels"]["motivation"]["pending_review"], 1)
        self.assertEqual(report["records"][0]["request_id"], "request-1")
        self.assertEqual(report["records"][0]["contains_synthetic_media"], True)

    def test_reports_unconfirmed_attempt_without_leaking_error_text(self):
        path = self._manifest("uncertain.publishing.json", "devotional", {
            "status": "approved",
            "approval": {},
            "execution_attempt": {
                "status": "outcome_unconfirmed",
                "request_id": "request-uncertain",
                "error": "private diagnostic that must not appear in report",
            },
        })
        report = build_report([path])
        record = report["records"][0]
        self.assertEqual(record["status"], "outcome_unconfirmed")
        self.assertTrue(record["has_error"])
        self.assertNotIn("error", record)
        self.assertEqual(report["channels"]["devotional"]["unconfirmed_uploads"], 1)

    def test_skips_invalid_or_unknown_channel_manifests(self):
        invalid = self.root / "invalid.publishing.json"
        invalid.write_text(json.dumps({"channel": "other", "workflow": {}, "youtube": {}}), encoding="utf-8")
        report = build_report([invalid])
        self.assertEqual(report["total_packages"], 0)
        self.assertEqual(len(report["warnings"]), 1)

    def test_deduplicates_same_manifest_path(self):
        path = self._manifest("one.publishing.json", "motivation", {"status": "pending_human_review"})
        report = build_report([path, path])
        self.assertEqual(report["total_packages"], 1)

    def test_writes_json_and_csv(self):
        path = self._manifest("one.publishing.json", "motivation", {"status": "pending_human_review"})
        report = build_report([path])
        json_out = self.root / "out" / "report.json"
        csv_out = self.root / "out" / "report.csv"
        write_report(report, json_out, csv_out)
        self.assertTrue(json_out.is_file())
        self.assertTrue(csv_out.is_file())
        self.assertIn("manifest_file", csv_out.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
