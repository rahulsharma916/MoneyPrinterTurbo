#!/usr/bin/env python3
"""Track evidence-backed production checkpoints and safely resume a channel run.

This utility never executes workflow commands, calls providers, or publishes.
A stage is complete only when a human reviewer records evidence files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
STATE_TYPE = "youtube_production_checkpoint_state"
VALID_STAGE_STATES = {"pending", "blocked", "completed", "failed"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _load_workflow(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    workflow = _read_json(path, "workflow runbook")
    if workflow.get("workflow_type") != "youtube_channel_production_runbook":
        raise ValueError("input must be a Phase 6 Step 9 youtube_channel_production_runbook")
    if workflow.get("channel") not in CHANNELS:
        raise ValueError("workflow channel must be devotional or motivation")
    stages = workflow.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("workflow must contain a non-empty stages list")
    seen: set[str] = set()
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("id"), str):
            raise ValueError("each workflow stage must have a string id")
        if stage["id"] in seen:
            raise ValueError(f"duplicate workflow stage id: {stage['id']}")
        seen.add(stage["id"])
        if stage.get("status") not in {"ready", "blocked"}:
            raise ValueError(f"stage {stage['id']} has an invalid readiness status")
    return workflow, stages, _sha256(path)


def _empty_state(workflow_path: Path, workflow: dict[str, Any],
                 stages: list[dict[str, Any]], workflow_hash: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state_type": STATE_TYPE,
        "channel": workflow["channel"],
        "subject": workflow.get("subject", ""),
        "workflow_file": str(workflow_path.resolve()),
        "workflow_sha256": workflow_hash,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "stages": {
            stage["id"]: {
                "name": stage.get("name", stage["id"]),
                "status": "pending" if stage["status"] == "ready" else "blocked",
                "evidence": [],
                "completed_at": None,
                "reviewed_by": None,
                "note": None,
                "failure": None,
            }
            for stage in stages
        },
        "guardrails": {
            "channel_isolation_enforced": True,
            "commands_executed_by_tracker": False,
            "provider_calls_enabled": False,
            "upload_authorized": False,
            "public_uploads_enabled": False,
            "scheduling_enabled": False,
        },
    }


def _load_state(state_path: Path) -> dict[str, Any]:
    state = _read_json(state_path, "checkpoint state")
    if state.get("state_type") != STATE_TYPE or state.get("schema_version") != 1:
        raise ValueError("unsupported checkpoint state schema")
    if state.get("channel") not in CHANNELS or not isinstance(state.get("stages"), dict):
        raise ValueError("invalid checkpoint state structure")
    return state


def _evidence_is_current(stage_record: dict[str, Any]) -> bool:
    evidence = stage_record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return False
        path = Path(item["path"])
        try:
            if not path.is_file() or _sha256(path) != item.get("sha256"):
                return False
        except OSError:
            return False
    return True


def initialize(workflow_path: Path, state_path: Path) -> dict[str, Any]:
    workflow, stages, workflow_hash = _load_workflow(workflow_path)
    if state_path.exists():
        raise ValueError(f"state file already exists; use sync or choose another path: {state_path}")
    state = _empty_state(workflow_path, workflow, stages, workflow_hash)
    _write_json_atomic(state_path, state)
    return state


def sync_state(workflow_path: Path, state_path: Path) -> dict[str, Any]:
    workflow, stages, workflow_hash = _load_workflow(workflow_path)
    state = _load_state(state_path)
    if state["channel"] != workflow["channel"]:
        raise ValueError("channel mismatch: refusing to sync state across channels")
    previous = state["stages"]
    updated: dict[str, Any] = {}
    prior_checkpoints_valid = True
    for stage in stages:
        stage_id = stage["id"]
        old = previous.get(stage_id)
        can_preserve = (
            prior_checkpoints_valid
            and stage["status"] == "ready"
            and isinstance(old, dict)
            and old.get("status") == "completed"
            and _evidence_is_current(old)
        )
        if can_preserve:
            updated[stage_id] = old
        else:
            updated[stage_id] = {
                "name": stage.get("name", stage_id),
                "status": "pending" if stage["status"] == "ready" else "blocked",
                "evidence": [],
                "completed_at": None,
                "reviewed_by": None,
                "note": None,
                "failure": None,
            }
            prior_checkpoints_valid = False
    state["stages"] = updated
    state["workflow_file"] = str(workflow_path.resolve())
    state["workflow_sha256"] = workflow_hash
    state["subject"] = workflow.get("subject", "")
    state["updated_at"] = _utc_now()
    _write_json_atomic(state_path, state)
    return state


def complete_stage(workflow_path: Path, state_path: Path, stage_id: str,
                   evidence_paths: list[Path], reviewed_by: str, note: str | None = None) -> dict[str, Any]:
    workflow, workflow_stages, workflow_hash = _load_workflow(workflow_path)
    state = _load_state(state_path)
    if state["channel"] != workflow["channel"]:
        raise ValueError("channel mismatch: refusing to complete a stage in another channel's state")
    if state.get("workflow_sha256") != workflow_hash:
        raise ValueError("workflow runbook changed; run the sync command before recording a checkpoint")
    if not reviewed_by.strip():
        raise ValueError("reviewed_by must identify the human reviewer")
    if not evidence_paths:
        raise ValueError("at least one --evidence file is required")
    plan_stage = next((item for item in workflow_stages if item["id"] == stage_id), None)
    if plan_stage is None:
        raise ValueError(f"unknown stage: {stage_id}")
    if plan_stage["status"] != "ready":
        raise ValueError(f"stage is blocked in the current runbook: {stage_id}")
    stage_ids = [item["id"] for item in workflow_stages]
    stage_index = stage_ids.index(stage_id)
    for prior_id in stage_ids[:stage_index]:
        prior = state["stages"].get(prior_id, {})
        if prior.get("status") != "completed" or not _evidence_is_current(prior):
            raise ValueError(f"cannot complete {stage_id}: earlier stage is incomplete or its evidence changed: {prior_id}")

    evidence: list[dict[str, str]] = []
    for raw_path in evidence_paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"evidence file does not exist: {path}")
        evidence.append({"path": str(path), "sha256": _sha256(path)})

    record = state["stages"][stage_id]
    record.update({
        "name": plan_stage.get("name", stage_id),
        "status": "completed",
        "evidence": evidence,
        "completed_at": _utc_now(),
        "reviewed_by": reviewed_by.strip(),
        "note": note,
        "failure": None,
    })
    state["updated_at"] = _utc_now()
    _write_json_atomic(state_path, state)
    return state


def fail_stage(state_path: Path, stage_id: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise ValueError("failure reason must not be empty")
    state = _load_state(state_path)
    if stage_id not in state["stages"]:
        raise ValueError(f"unknown stage: {stage_id}")
    record = state["stages"][stage_id]
    record.update({
        "status": "failed",
        "failure": {"reason": reason.strip(), "recorded_at": _utc_now()},
        "evidence": [],
        "completed_at": None,
        "reviewed_by": None,
    })
    state["updated_at"] = _utc_now()
    _write_json_atomic(state_path, state)
    return state


def reset_from(state_path: Path, stage_id: str) -> dict[str, Any]:
    state = _load_state(state_path)
    stage_ids = list(state["stages"])
    if stage_id not in state["stages"]:
        raise ValueError(f"unknown stage: {stage_id}")
    start = stage_ids.index(stage_id)
    for current_id in stage_ids[start:]:
        record = state["stages"][current_id]
        record.update({
            "status": "pending",
            "evidence": [],
            "completed_at": None,
            "reviewed_by": None,
            "note": None,
            "failure": None,
        })
    state["updated_at"] = _utc_now()
    _write_json_atomic(state_path, state)
    return state


def status_report(workflow_path: Path, state_path: Path) -> dict[str, Any]:
    workflow, workflow_stages, workflow_hash = _load_workflow(workflow_path)
    state = _load_state(state_path)
    if state["channel"] != workflow["channel"]:
        raise ValueError("channel mismatch between runbook and checkpoint state")
    records = state["stages"]
    report_stages: list[dict[str, Any]] = []
    resume_stage = None
    completed = 0
    prior_checkpoints_valid = True
    for stage in workflow_stages:
        record = records.get(stage["id"], {})
        current = record.get("status", "pending")
        evidence_valid = _evidence_is_current(record) if current == "completed" else None
        if current == "completed" and not evidence_valid:
            current = "stale_evidence"
        if not prior_checkpoints_valid and current == "completed":
            current = "blocked_by_prior_checkpoint"
        if current == "completed":
            completed += 1
        else:
            prior_checkpoints_valid = False
        if resume_stage is None and current != "completed":
            resume_stage = stage["id"]
        report_stages.append({
            "id": stage["id"],
            "name": stage.get("name", stage["id"]),
            "plan_readiness": stage["status"],
            "status": current,
            "evidence_valid": evidence_valid,
            "failure": record.get("failure"),
        })
    return {
        "channel": workflow["channel"],
        "subject": workflow.get("subject", ""),
        "completed_stages": completed,
        "total_stages": len(workflow_stages),
        "resume_from": resume_stage,
        "workflow_changed": state.get("workflow_sha256") != workflow_hash,
        "stages": report_stages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    init = sub.add_parser("init", help="create a new checkpoint state from a workflow runbook")
    init.add_argument("--workflow", required=True, type=Path)
    init.add_argument("--state", required=True, type=Path)

    sync = sub.add_parser("sync", help="refresh readiness while preserving valid completed evidence")
    sync.add_argument("--workflow", required=True, type=Path)
    sync.add_argument("--state", required=True, type=Path)

    show = sub.add_parser("status", help="show stage completion and safe resume point")
    show.add_argument("--workflow", required=True, type=Path)
    show.add_argument("--state", required=True, type=Path)

    complete = sub.add_parser("complete", help="record a human-reviewed stage with file evidence")
    complete.add_argument("--workflow", required=True, type=Path)
    complete.add_argument("--state", required=True, type=Path)
    complete.add_argument("--stage", required=True)
    complete.add_argument("--evidence", required=True, action="append", type=Path)
    complete.add_argument("--reviewed-by", required=True)
    complete.add_argument("--note")

    fail = sub.add_parser("fail", help="record a failed stage without retrying it")
    fail.add_argument("--state", required=True, type=Path)
    fail.add_argument("--stage", required=True)
    fail.add_argument("--reason", required=True)

    reset = sub.add_parser("reset", help="reset this and all downstream checkpoints")
    reset.add_argument("--state", required=True, type=Path)
    reset.add_argument("--stage", required=True)

    args = parser.parse_args()
    try:
        if args.action == "init":
            state = initialize(args.workflow, args.state)
            print(f"Checkpoint state initialized: {args.state}")
            print(f"Channel: {state['channel']}; stages: {len(state['stages'])}")
        elif args.action == "sync":
            state = sync_state(args.workflow, args.state)
            print(f"Checkpoint state synchronized: {args.state}")
            print(f"Channel: {state['channel']}; stages: {len(state['stages'])}")
        elif args.action == "status":
            report = status_report(args.workflow, args.state)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.action == "complete":
            state = complete_stage(args.workflow, args.state, args.stage, args.evidence,
                                   args.reviewed_by, args.note)
            print(f"Completed checkpoint recorded: {args.stage} ({state['channel']})")
        elif args.action == "fail":
            fail_stage(args.state, args.stage, args.reason)
            print(f"Failure recorded: {args.stage}")
        elif args.action == "reset":
            reset_from(args.state, args.stage)
            print(f"Reset {args.stage} and all downstream checkpoints")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Checkpoint operation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
