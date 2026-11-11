from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from automation.track_youtube_production_checkpoints import (
    complete_stage,
    fail_stage,
    initialize,
    reset_from,
    status_report,
    sync_state,
)


class ProductionCheckpointTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workflow_path = self.root / "workflow.json"
        self.state_path = self.root / "state.json"
        self.script = self.root / "script.txt"
        self.script.write_text("final Hindi script", encoding="utf-8")
        self.evidence = []
        self.workflow = {
            "workflow_type": "youtube_channel_production_runbook",
            "channel": "devotional",
            "subject": "हनुमान जी",
            "stages": [
                {"id": "creative_brief", "name": "Creative brief", "status": "ready"},
                {"id": "scene_images", "name": "Scene images", "status": "ready"},
                {"id": "scene_timeline", "name": "Scene timeline", "status": "blocked"},
            ],
        }
        self._write_workflow()
        initialize(self.workflow_path, self.state_path)

    def tearDown(self):
        self.temp.cleanup()

    def _write_workflow(self):
        self.workflow_path.write_text(json.dumps(self.workflow), encoding="utf-8")

    def _evidence(self, name: str) -> Path:
        path = self.root / name
        path.write_text(f"evidence-{name}", encoding="utf-8")
        return path

    def _complete(self, stage: str, name: str):
        return complete_stage(
            self.workflow_path, self.state_path, stage, [self._evidence(name)],
            "human-reviewer", "reviewed",
        )

    def test_initialize_and_status_reports_first_resume_point(self):
        report = status_report(self.workflow_path, self.state_path)
        self.assertEqual(report["resume_from"], "creative_brief")
        self.assertEqual(report["completed_stages"], 0)
        self.assertEqual(report["stages"][2]["plan_readiness"], "blocked")

    def test_requires_previous_stage_and_evidence(self):
        with self.assertRaisesRegex(ValueError, "earlier stage"):
            self._complete("scene_images", "images.json")
        with self.assertRaisesRegex(ValueError, "at least one"):
            complete_stage(self.workflow_path, self.state_path, "creative_brief", [], "reviewer")

    def test_completion_requires_ready_stage_and_human_reviewer(self):
        self._complete("creative_brief", "assets.json")
        with self.assertRaisesRegex(ValueError, "blocked"):
            self._complete("scene_timeline", "timeline.json")
        with self.assertRaisesRegex(ValueError, "reviewed_by"):
            complete_stage(self.workflow_path, self.state_path, "scene_images",
                           [self._evidence("image-manifest.json")], " ")

    def test_evidence_change_is_detected(self):
        evidence = self._evidence("assets.json")
        complete_stage(self.workflow_path, self.state_path, "creative_brief",
                       [evidence], "reviewer")
        evidence.write_text("changed after review", encoding="utf-8")
        report = status_report(self.workflow_path, self.state_path)
        self.assertEqual(report["stages"][0]["status"], "stale_evidence")
        self.assertEqual(report["resume_from"], "creative_brief")

    def test_sync_preserves_valid_evidence_and_refreshes_blocked_stages(self):
        self._complete("creative_brief", "assets.json")
        self.workflow["stages"][1]["status"] = "blocked"
        self.workflow["stages"][2]["status"] = "ready"
        self._write_workflow()
        state = sync_state(self.workflow_path, self.state_path)
        self.assertEqual(state["stages"]["creative_brief"]["status"], "completed")
        self.assertEqual(state["stages"]["scene_images"]["status"], "blocked")
        self.assertEqual(state["stages"]["scene_timeline"]["status"], "pending")

    def test_failure_and_reset_clear_downstream_checkpoints(self):
        self._complete("creative_brief", "assets.json")
        fail_stage(self.state_path, "scene_images", "provider timeout")
        reset_from(self.state_path, "scene_images")
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["stages"]["scene_images"]["status"], "pending")
        self.assertEqual(state["stages"]["scene_timeline"]["status"], "blocked")
        self.assertEqual(state["stages"]["creative_brief"]["status"], "completed")

    def test_upstream_evidence_change_invalidates_downstream_on_sync(self):
        self.workflow["stages"][2]["status"] = "ready"
        self._write_workflow()
        sync_state(self.workflow_path, self.state_path)
        self._complete("creative_brief", "assets.json")
        self._complete("scene_images", "images.json")
        assets = self.root / "assets.json"
        assets.write_text("changed upstream asset", encoding="utf-8")
        state = sync_state(self.workflow_path, self.state_path)
        self.assertEqual(state["stages"]["creative_brief"]["status"], "pending")
        self.assertEqual(state["stages"]["scene_images"]["status"], "pending")
        self.assertEqual(state["stages"]["scene_timeline"]["status"], "pending")

    def test_channel_mismatch_prevents_cross_channel_state_use(self):
        self.workflow["channel"] = "motivation"
        self._write_workflow()
        with self.assertRaisesRegex(ValueError, "channel mismatch"):
            status_report(self.workflow_path, self.state_path)

    def test_workflow_change_requires_sync_before_completion(self):
        self.workflow["subject"] = "updated topic"
        self._write_workflow()
        with self.assertRaisesRegex(ValueError, "run the sync"):
            self._complete("creative_brief", "assets.json")


if __name__ == "__main__":
    unittest.main()
