#!/usr/bin/env python3
"""Build privacy-conscious channel-wise reports from YouTube publishing manifests.

This is a local, read-only report builder. It does not contact YouTube or Upload-Post.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
VALID_STATUSES = {
    "pending_human_review",
    "approved",
    "submitting",
    "completed",
    "failed",
    "outcome_unconfirmed",
}
CSV_FIELDS = (
    "channel",
    "channel_display_name",
    "subject",
    "title",
    "status",
    "privacy_status",
    "made_for_kids",
    "contains_synthetic_media",
    "approved_by",
    "approved_at",
    "attempt_started_at",
    "attempt_finished_at",
    "request_id",
    "has_error",
    "video_file",
    "manifest_file",
)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def _status(workflow: dict[str, Any]) -> str:
    attempt = workflow.get("execution_attempt")
    if isinstance(attempt, dict):
        value = attempt.get("status")
        if value in {"submitting", "completed", "failed", "outcome_unconfirmed"}:
            return value
    value = workflow.get("status")
    if value in {"pending_human_review", "approved"}:
        return value
    return "unknown"


def _record(path: Path) -> dict[str, Any]:
    data = _read_manifest(path)
    channel = data.get("channel")
    if channel not in CHANNELS:
        raise ValueError("channel must be devotional or motivation")
    workflow = data.get("workflow")
    youtube = data.get("youtube")
    if not isinstance(workflow, dict) or not isinstance(youtube, dict):
        raise ValueError("workflow and youtube sections must be JSON objects")
    approval = workflow.get("approval")
    if not isinstance(approval, dict):
        approval = {}
    attempt = workflow.get("execution_attempt")
    if not isinstance(attempt, dict):
        attempt = {}
    status = _status(workflow)
    return {
        "channel": channel,
        "channel_display_name": str(data.get("channel_display_name") or channel),
        "subject": str(data.get("subject") or ""),
        "title": str(youtube.get("title") or ""),
        "status": status,
        "privacy_status": str(youtube.get("privacy_status") or ""),
        "made_for_kids": youtube.get("made_for_kids") if isinstance(youtube.get("made_for_kids"), bool) else "",
        "contains_synthetic_media": youtube.get("contains_synthetic_media") if isinstance(youtube.get("contains_synthetic_media"), bool) else "",
        "approved_by": str(approval.get("approved_by") or ""),
        "approved_at": str(approval.get("approved_at") or ""),
        "attempt_started_at": str(attempt.get("started_at") or ""),
        "attempt_finished_at": str(attempt.get("finished_at") or ""),
        "request_id": str(attempt.get("request_id") or ""),
        "has_error": bool(attempt.get("error")),
        "video_file": str(data.get("video_file") or ""),
        "manifest_file": str(path.resolve()),
    }


def build_report(paths: list[Path]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[Path] = set()
    for path in sorted(paths, key=lambda item: str(item)):
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            records.append(_record(resolved))
        except ValueError as exc:
            warnings.append(f"{resolved}: {exc}")

    grouped: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        grouped[record["channel"]][record["status"]] += 1

    channels: dict[str, Any] = {}
    for channel in CHANNELS:
        counts = grouped[channel]
        channels[channel] = {
            "total_packages": sum(counts.values()),
            "status_counts": {status: counts.get(status, 0) for status in sorted(VALID_STATUSES | {"unknown"})},
            "completed_uploads": counts.get("completed", 0),
            "failed_uploads": counts.get("failed", 0),
            "unconfirmed_uploads": counts.get("outcome_unconfirmed", 0),
            "pending_review": counts.get("pending_human_review", 0),
            "approved_not_submitted": counts.get("approved", 0),
        }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "local publishing-manifest outcomes only; not YouTube view or engagement analytics",
        "total_packages": len(records),
        "channels": channels,
        "records": records,
        "warnings": warnings,
    }


def write_report(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["records"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path, help="Folder containing *.publishing.json files; searched recursively")
    parser.add_argument("--output-json", type=Path, default=Path("publishing_report.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("publishing_report.csv"))
    args = parser.parse_args()
    if not args.input_dir.is_dir():
        print(f"Input directory does not exist: {args.input_dir}", file=sys.stderr)
        return 2
    paths = list(args.input_dir.rglob("*.publishing.json"))
    report = build_report(paths)
    try:
        write_report(report, args.output_json, args.output_csv)
    except OSError as exc:
        print(f"Could not write report: {exc}", file=sys.stderr)
        return 2
    print(f"Packages: {report['total_packages']}")
    for channel, summary in report["channels"].items():
        print(
            f"{channel}: completed={summary['completed_uploads']}, "
            f"failed={summary['failed_uploads']}, "
            f"unconfirmed={summary['unconfirmed_uploads']}, "
            f"pending_review={summary['pending_review']}, "
            f"approved_not_submitted={summary['approved_not_submitted']}"
        )
    print(f"JSON report: {args.output_json}")
    print(f"CSV report: {args.output_csv}")
    if report["warnings"]:
        print(f"Skipped invalid manifests: {len(report['warnings'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
