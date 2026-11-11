from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from automation.build_youtube_production_optimization import (
    build_optimization_plan, write_outputs,
)


class ProductionOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def sources(self):
        performance = {
            "report_type": "rule_based_youtube_performance_intelligence",
            "channels": {
                "devotional": {
                    "date_range": {"start": "2026-10-01", "end": "2026-10-28"},
                    "overall": {"views": 1200, "average_view_percentage_weighted": 24,
                                "engagement_rate_pct": 1.2,
                                "subscriber_conversion_per_1000_views": 0.5},
                    "by_creator_content_type": {"SHORTS": {"views": 1200}},
                    "format_opportunity": {"status": "directional_comparison",
                                           "leading_format": "SHORTS"},
                },
                "motivation": {
                    "date_range": {"start": "2026-10-01", "end": "2026-10-28"},
                    "overall": {"views": 800, "average_view_percentage_weighted": 65,
                                "engagement_rate_pct": 3,
                                "subscriber_conversion_per_1000_views": 2},
                    "by_creator_content_type": {},
                    "format_opportunity": {"status": "insufficient_comparable_data"},
                },
            },
        }
        production = {
            "report_type": "youtube_production_intelligence",
            "channels": {
                "devotional": {"quality": {"reports": 2, "passed": 1, "failed": 1},
                               "stale_evidence_stages": 1, "blocked_stages": 2,
                               "failed_stages": 0},
                "motivation": {"quality": {"reports": 0, "passed": 0, "failed": 0},
                               "stale_evidence_stages": 0, "blocked_stages": 0,
                               "failed_stages": 0},
            },
            "costs": {"records": [
                {"channel": "devotional", "amount": 10, "currency": "INR"},
                {"channel": "motivation", "amount": 2, "currency": "USD"},
            ]},
        }
        return performance, production

    def test_channel_specific_recommendations_and_cost_currency(self):
        performance, production = self.sources()
        plan = build_optimization_plan(performance, production)
        devotional = plan["channels"]["devotional"]
        motivation = plan["channels"]["motivation"]
        areas = {item["area"] for item in devotional["actions"]}
        self.assertIn("creative_retention", areas)
        self.assertIn("technical_quality", areas)
        self.assertIn("workflow_reliability", areas)
        self.assertEqual(devotional["baseline"]["reported_cost_per_1000_views"][0]["currency"], "INR")
        self.assertIn("maintain", {item["action"] for item in motivation["actions"]})
        self.assertNotEqual(devotional["actions"], motivation["actions"])

    def test_missing_channel_data_is_explicit_and_safe(self):
        performance, production = self.sources()
        del performance["channels"]["motivation"]
        plan = build_optimization_plan(performance, production)
        self.assertTrue(plan["channels"]["motivation"]["actions"])
        self.assertIn("analytics", {x["area"] for x in plan["channels"]["motivation"]["actions"]})

    def test_outputs_json_markdown_csv(self):
        performance, production = self.sources()
        plan = build_optimization_plan(performance, production)
        json_path = self.root / "out" / "plan.json"
        md_path = self.root / "out" / "plan.md"
        csv_path = self.root / "out" / "actions.csv"
        write_outputs(plan, json_path, md_path, csv_path)
        self.assertTrue(json_path.is_file())
        self.assertIn("YouTube Production Optimization Plan", md_path.read_text())
        self.assertIn("requires_human_approval", csv_path.read_text(encoding="utf-8-sig"))

    def test_no_cost_ledger_means_no_cost_cutting_claim(self):
        performance, production = self.sources()
        production["costs"] = {"records": []}
        plan = build_optimization_plan(performance, production)
        devotional = plan["channels"]["devotional"]
        unit = [x for x in devotional["actions"] if x["area"] == "unit_economics"]
        self.assertEqual(len(unit), 1)
        self.assertIn("unknown", unit[0]["evidence"].lower())


if __name__ == "__main__":
    unittest.main()
