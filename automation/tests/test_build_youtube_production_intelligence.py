from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from automation.build_youtube_production_intelligence import build_intelligence, write_outputs


class ProductionIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _checkpoint(self, channel: str, filename: str) -> Path:
        evidence = self.root / channel / "evidence.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text('{"ok": true}', encoding="utf-8")
        state = {
            "schema_version": 1,
            "state_type": "youtube_production_checkpoint_state",
            "channel": channel,
            "subject": "test topic",
            "updated_at": "2026-11-11T00:00:00+00:00",
            "stages": {
                "brief": {"status": "completed", "evidence": [
                    {"path": str(evidence), "sha256": __import__("hashlib").sha256(evidence.read_bytes()).hexdigest()}
                ]},
                "images": {"status": "failed", "evidence": []},
                "render": {"status": "blocked", "evidence": []},
            },
        }
        path = self.root / filename
        path.write_text(json.dumps(state), encoding="utf-8")
        return path

    def test_channel_separation_and_unknown_cost_not_zero(self):
        devotional = self._checkpoint("devotional", "devotional.state.json")
        motivation = self._checkpoint("motivation", "motivation.state.json")
        report = build_intelligence([devotional, motivation])
        self.assertEqual(report["channels"]["devotional"]["workflow_count"], 1)
        self.assertEqual(report["channels"]["motivation"]["workflow_count"], 1)
        self.assertEqual(report["channels"]["devotional"]["completed_stages"], 1)
        self.assertFalse(report["costs"]["provided"])
        self.assertIn("unknown, not zero", report["costs"]["note"])

    def test_changed_evidence_is_not_counted_as_completed(self):
        state = self._checkpoint("devotional", "state.json")
        evidence = self.root / "devotional" / "evidence.json"
        evidence.write_text("changed", encoding="utf-8")
        report = build_intelligence([state])
        self.assertEqual(report["channels"]["devotional"]["completed_stages"], 0)
        self.assertEqual(report["channels"]["devotional"]["stale_evidence_stages"], 1)

    def test_cost_ledger_aggregates_only_matching_currency(self):
        state = self._checkpoint("devotional", "state.json")
        ledger = self.root / "costs.json"
        ledger.write_text(json.dumps({"records": [
            {"channel": "devotional", "provider": "image-provider", "stage": "images", "amount": 12.5, "currency": "INR"},
            {"channel": "devotional", "provider": "llm", "stage": "brief", "amount": 2.5, "currency": "INR"},
            {"channel": "motivation", "provider": "tts", "stage": "narration", "amount": 1, "currency": "USD"},
        ]}), encoding="utf-8")
        report = build_intelligence([state], cost_ledger_path=ledger)
        totals = report["costs"]["totals_by_channel_currency"]
        self.assertEqual(totals["devotional:INR"]["amount"], 15.0)
        self.assertEqual(totals["motivation:USD"]["amount"], 1.0)

    def test_quality_report_is_counted_only_with_explicit_channel_path(self):
        state = self._checkpoint("devotional", "state.json")
        quality = self.root / "quality.json"
        quality.write_text(json.dumps({
            "status": "passed",
            "video_file": "/media/devotional/final.mp4",
            "video_duration_seconds": 120,
            "narration_duration_seconds": 119,
            "actual_aspect": 1.777,
            "expected_aspect": 1.777,
            "checks": {"video_stream": "passed"},
        }), encoding="utf-8")
        report = build_intelligence([state], quality_paths=[quality])
        self.assertEqual(report["channels"]["devotional"]["quality"]["passed"], 1)
        self.assertEqual(report["channels"]["motivation"]["quality"]["reports"], 0)

    def test_publishing_report_and_csv_outputs(self):
        state = self._checkpoint("devotional", "state.json")
        pub = self.root / "publishing.json"
        pub.write_text(json.dumps({"channels": {
            "devotional": {"total_packages": 3, "completed_uploads": 2, "failed_uploads": 1},
            "motivation": {"total_packages": 1, "completed_uploads": 1},
        }}), encoding="utf-8")
        report = build_intelligence([state], publishing_path=pub)
        self.assertEqual(report["channels"]["devotional"]["publishing"]["completed_uploads"], 2)
        json_out, csv_out = self.root / "out" / "report.json", self.root / "out" / "report.csv"
        write_outputs(report, json_out, csv_out)
        self.assertTrue(json_out.is_file())
        self.assertTrue(csv_out.is_file())

    def test_non_finite_cost_amount_is_rejected(self):
        state = self._checkpoint("devotional", "state.json")
        ledger = self.root / "bad-costs.json"
        ledger.write_text('{"records":[{"channel":"devotional","provider":"x","amount":NaN,"currency":"INR"}]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "finite non-negative"):
            build_intelligence([state], cost_ledger_path=ledger)

    def test_invalid_channel_in_cost_ledger_is_rejected(self):
        state = self._checkpoint("devotional", "state.json")
        ledger = self.root / "bad-costs.json"
        ledger.write_text(json.dumps({"records": [
            {"channel": "both", "provider": "x", "amount": 5, "currency": "INR"}
        ]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "channel must be devotional"):
            build_intelligence([state], cost_ledger_path=ledger)


if __name__ == "__main__":
    unittest.main()
