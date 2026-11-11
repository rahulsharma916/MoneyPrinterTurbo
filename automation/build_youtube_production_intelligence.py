#!/usr/bin/env python3
"""Build evidence-backed production performance, cost and quality intelligence.

Consumes local checkpoint states and optional FFprobe quality reports, publishing
outcome reports, and an explicitly supplied cost ledger. It does not call APIs,
probe media, infer provider prices, or mutate production state.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
CSV_FIELDS = (
    "channel", "subject", "completed_stages", "total_stages",
    "failed_stages", "blocked_stages", "stale_evidence_stages",
    "evidence_files", "evidence_bytes", "quality_reports",
    "quality_passed", "quality_failed", "publishing_packages",
    "completed_uploads", "failed_uploads", "unconfirmed_uploads",
    "reported_cost", "cost_currency",
)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return data


def _safe_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _checkpoint_summary(path: Path) -> dict[str, Any]:
    state = _read_json(path, "checkpoint state")
    if state.get("state_type") != "youtube_production_checkpoint_state" or state.get("schema_version") != 1:
        raise ValueError("unsupported checkpoint state schema")
    channel = state.get("channel")
    stages = state.get("stages")
    if channel not in CHANNELS or not isinstance(stages, dict):
        raise ValueError("checkpoint state has invalid channel or stages")
    counts: Counter[str] = Counter()
    evidence_files = 0
    evidence_bytes = 0
    stale = 0
    for record in stages.values():
        if not isinstance(record, dict):
            continue
        status = record.get("status", "pending")
        counts[status] += 1
        if status == "completed":
            valid = True
            evidence = record.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                valid = False
            for item in evidence if isinstance(evidence, list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    valid = False
                    continue
                file_path = Path(item["path"])
                try:
                    if not file_path.is_file():
                        valid = False
                    else:
                        evidence_files += 1
                        evidence_bytes += file_path.stat().st_size
                except OSError:
                    valid = False
            if not valid:
                stale += 1
    return {
        "channel": channel,
        "subject": str(state.get("subject") or ""),
        "state_file": str(path.resolve()),
        "stage_counts": dict(counts),
        "total_stages": len(stages),
        "completed_stages": counts["completed"] - stale,
        "failed_stages": counts["failed"],
        "blocked_stages": counts["blocked"],
        "pending_stages": counts["pending"],
        "stale_evidence_stages": stale,
        "evidence_files": evidence_files,
        "evidence_bytes": evidence_bytes,
        "updated_at": str(state.get("updated_at") or ""),
    }


def _quality_record(path: Path) -> dict[str, Any]:
    data = _read_json(path, "video quality report")
    status = data.get("status")
    if status not in {"passed", "failed"}:
        # The validator normally emits JSON only on success. A manually prepared
        # failure report may use failed; unknown schemas are not counted as passes.
        status = "unknown"
    return {
        "report_file": str(path.resolve()),
        "status": status,
        "video_file": str(data.get("video_file") or ""),
        "narration_file": str(data.get("narration_file") or ""),
        "video_duration_seconds": data.get("video_duration_seconds"),
        "narration_duration_seconds": data.get("narration_duration_seconds"),
        "duration_delta_seconds": data.get("duration_delta_seconds"),
        "actual_aspect": data.get("actual_aspect"),
        "expected_aspect": data.get("expected_aspect"),
        "checks": data.get("checks") if isinstance(data.get("checks"), dict) else {},
        "limitations": data.get("limitations") if isinstance(data.get("limitations"), list) else [],
    }


def _publishing_summary(path: Path) -> dict[str, Any]:
    data = _read_json(path, "publishing outcome report")
    channels = data.get("channels")
    if not isinstance(channels, dict):
        raise ValueError("publishing report must contain a channels object")
    result: dict[str, Any] = {"report_file": str(path.resolve()), "channels": {}}
    for channel in CHANNELS:
        summary = channels.get(channel, {})
        if not isinstance(summary, dict):
            summary = {}
        result["channels"][channel] = {
            "total_packages": _safe_int(summary.get("total_packages")),
            "completed_uploads": _safe_int(summary.get("completed_uploads")),
            "failed_uploads": _safe_int(summary.get("failed_uploads")),
            "unconfirmed_uploads": _safe_int(summary.get("unconfirmed_uploads")),
            "pending_review": _safe_int(summary.get("pending_review")),
        }
    return result


def _cost_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"provided": False, "records": [], "totals_by_channel_currency": {},
                "note": "No cost ledger supplied; costs are unknown, not zero."}
    data = _read_json(path, "cost ledger")
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("cost ledger must contain a records array")
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"amount": 0.0, "records": 0})
    normalized = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"cost record {index} must be an object")
        channel = item.get("channel")
        currency = item.get("currency")
        amount = item.get("amount")
        provider = item.get("provider")
        if channel not in CHANNELS:
            raise ValueError(f"cost record {index}: channel must be devotional or motivation")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError(f"cost record {index}: currency is required")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError(f"cost record {index}: provider is required")
        if (isinstance(amount, bool) or not isinstance(amount, (int, float))
                or not math.isfinite(amount) or amount < 0):
            raise ValueError(f"cost record {index}: amount must be a finite non-negative number")
        stage = str(item.get("stage") or "unspecified")
        key = f"{channel}:{currency.upper()}"
        totals[key]["amount"] += float(amount)
        totals[key]["records"] += 1
        normalized.append({
            "channel": channel, "stage": stage, "provider": provider.strip(),
            "amount": float(amount), "currency": currency.upper(),
            "source": str(item.get("source") or "user-supplied"),
            "recorded_at": str(item.get("recorded_at") or ""),
        })
    return {"provided": True, "records": normalized,
            "totals_by_channel_currency": dict(totals),
            "note": "Costs are reported only from supplied ledger records; no provider rates are inferred."}


def build_intelligence(
    checkpoint_paths: list[Path],
    quality_paths: list[Path] | None = None,
    publishing_path: Path | None = None,
    cost_ledger_path: Path | None = None,
) -> dict[str, Any]:
    checkpoints = [_checkpoint_summary(path) for path in checkpoint_paths]
    channels: dict[str, Any] = {}
    for channel in CHANNELS:
        items = [item for item in checkpoints if item["channel"] == channel]
        channels[channel] = {
            "workflow_count": len(items),
            "total_stages": sum(item["total_stages"] for item in items),
            "completed_stages": sum(item["completed_stages"] for item in items),
            "failed_stages": sum(item["failed_stages"] for item in items),
            "blocked_stages": sum(item["blocked_stages"] for item in items),
            "pending_stages": sum(item["pending_stages"] for item in items),
            "stale_evidence_stages": sum(item["stale_evidence_stages"] for item in items),
            "evidence_files": sum(item["evidence_files"] for item in items),
            "evidence_bytes": sum(item["evidence_bytes"] for item in items),
            "workflows": items,
        }
    quality = [_quality_record(path) for path in (quality_paths or [])]
    quality_by_channel = {channel: {"reports": 0, "passed": 0, "failed": 0, "unknown": 0}
                          for channel in CHANNELS}
    # Quality reports do not inherently identify a channel. Attribute only when
    # their video path contains an explicit channel path segment.
    for item in quality:
        parts = Path(item["video_file"]).parts
        channel = next((part for part in parts if part in CHANNELS), None)
        if channel:
            quality_by_channel[channel]["reports"] += 1
            quality_by_channel[channel][item["status"]] += 1
    for channel in CHANNELS:
        channels[channel]["quality"] = quality_by_channel[channel]
    publishing = _publishing_summary(publishing_path) if publishing_path else None
    if publishing:
        for channel in CHANNELS:
            channels[channel]["publishing"] = publishing["channels"][channel]
    return {
        "schema_version": 1,
        "report_type": "youtube_production_intelligence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "local checkpoint evidence, supplied quality reports, supplied publishing report and optional supplied cost ledger",
        "channels": channels,
        "checkpoint_workflows": checkpoints,
        "quality_reports": quality,
        "publishing_report": publishing,
        "costs": _cost_summary(cost_ledger_path),
        "interpretation_limits": [
            "No costs are inferred; without a supplied ledger, cost is unknown, not zero.",
            "Quality reports cover technical stream, aspect and duration checks only; they do not score creative quality, Hindi pronunciation, subtitle readability or narrative synchronization.",
            "A quality report is assigned to a channel only when its video path contains a devotional or motivation path segment.",
            "Publishing outcomes are local package outcomes, not YouTube views, watch time, revenue or monetization eligibility.",
            "Evidence byte totals are file sizes, not cloud storage billing estimates.",
        ],
    }


def write_outputs(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for channel in CHANNELS:
            item = report["channels"][channel]
            pub = item.get("publishing", {})
            cost_items = [row for row in report["costs"]["records"] if row["channel"] == channel]
            currencies = sorted({row["currency"] for row in cost_items})
            # Never combine unlike currencies into a misleading total.
            for currency in currencies or [""]:
                amount = sum(row["amount"] for row in cost_items if row["currency"] == currency)
                writer.writerow({
                    "channel": channel,
                    "subject": "; ".join(w["subject"] for w in item["workflows"] if w["subject"]),
                    "completed_stages": item["completed_stages"],
                    "total_stages": item["total_stages"],
                    "failed_stages": item["failed_stages"],
                    "blocked_stages": item["blocked_stages"],
                    "stale_evidence_stages": item["stale_evidence_stages"],
                    "evidence_files": item["evidence_files"],
                    "evidence_bytes": item["evidence_bytes"],
                    "quality_reports": item["quality"]["reports"],
                    "quality_passed": item["quality"]["passed"],
                    "quality_failed": item["quality"]["failed"],
                    "publishing_packages": pub.get("total_packages", ""),
                    "completed_uploads": pub.get("completed_uploads", ""),
                    "failed_uploads": pub.get("failed_uploads", ""),
                    "unconfirmed_uploads": pub.get("unconfirmed_uploads", ""),
                    "reported_cost": amount if currency else "",
                    "cost_currency": currency,
                })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="append", required=True, type=Path,
                        help="checkpoint state JSON; repeat for multiple workflows/channels")
    parser.add_argument("--quality-report", action="append", type=Path, default=[],
                        help="technical video quality JSON report; repeat as needed")
    parser.add_argument("--publishing-report", type=Path)
    parser.add_argument("--cost-ledger", type=Path,
                        help="optional JSON ledger of actual user-supplied costs")
    parser.add_argument("--output-json", type=Path, default=Path("production_intelligence.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("production_intelligence.csv"))
    args = parser.parse_args()
    try:
        report = build_intelligence(args.checkpoint, args.quality_report,
                                    args.publishing_report, args.cost_ledger)
        write_outputs(report, args.output_json, args.output_csv)
    except (OSError, ValueError) as exc:
        print(f"Production intelligence failed: {exc}", file=sys.stderr)
        return 2
    print("Production intelligence generated.")
    for channel in CHANNELS:
        item = report["channels"][channel]
        print(f"{channel}: workflows={item['workflow_count']}, completed={item['completed_stages']}/{item['total_stages']}, "
              f"failed={item['failed_stages']}, stale_evidence={item['stale_evidence_stages']}, "
              f"quality_passed={item['quality']['passed']}, quality_failed={item['quality']['failed']}")
    print(f"JSON: {args.output_json}")
    print(f"CSV: {args.output_csv}")
    if not report["costs"]["provided"]:
        print("Cost: unknown (no cost ledger supplied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
