#!/usr/bin/env python3
"""Create an evidence-backed, human-reviewed YouTube production optimization plan.

Consumes Phase 6 Step 6 performance intelligence and Step 11 production
intelligence. It emits recommendations only; it never edits calendars, invokes
providers, renders media, changes credentials, uploads or schedules videos.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
ACTIONS = ("test", "investigate", "maintain")


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_performance(path: Path) -> dict[str, Any]:
    data = read_json(path, "performance intelligence")
    if data.get("report_type") != "rule_based_youtube_performance_intelligence":
        raise ValueError("performance input must be a Phase 6 Step 6 intelligence report")
    if not isinstance(data.get("channels"), dict):
        raise ValueError("performance report is missing channels")
    return data


def load_production(path: Path) -> dict[str, Any]:
    data = read_json(path, "production intelligence")
    if data.get("report_type") != "youtube_production_intelligence":
        raise ValueError("production input must be a Phase 6 Step 11 intelligence report")
    if not isinstance(data.get("channels"), dict):
        raise ValueError("production report is missing channels")
    return data


def add(items: list[dict[str, Any]], priority: str, action: str, area: str,
        evidence: str, recommendation: str, success_metric: str,
        guardrail: str = "Run a controlled test; do not treat correlation as causation.") -> None:
    items.append({
        "priority": priority, "action": action, "area": area,
        "evidence": evidence, "recommendation": recommendation,
        "success_metric": success_metric, "guardrail": guardrail,
        "requires_human_approval": True,
    })


def build_channel_plan(channel: str, perf: dict[str, Any] | None,
                       prod: dict[str, Any] | None) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    metrics = (perf or {}).get("overall") or {}
    views = finite(metrics.get("views"))
    avg_pct = finite(metrics.get("average_view_percentage_weighted"))
    engagement = finite(metrics.get("engagement_rate_pct"))
    subscriber_rate = finite(metrics.get("subscriber_conversion_per_1000_views"))
    period = (perf or {}).get("date_range") or {}
    format_data = (perf or {}).get("by_creator_content_type") or {}
    prod_channel = (prod or {}).get("channels", {}).get(channel, {})
    quality = prod_channel.get("quality") or {}
    publishing = prod_channel.get("publishing") or {}
    format_opportunity = (perf or {}).get("format_opportunity") or {}

    if perf is None:
        add(actions, "P1", "investigate", "analytics",
            "No Step 6 performance report was supplied for this channel.",
            "Connect a verified read-only Analytics export and establish a baseline before changing the content mix.",
            "A complete, date-scoped baseline report.")
    elif views is None or views <= 0:
        add(actions, "P1", "investigate", "measurement",
            "The supplied reporting period contains no measurable views.",
            "Confirm channel identity, date range, report completeness and whether enough time has passed for Analytics processing.",
            "A valid report with non-zero activity or a documented reason for zero activity.")
    else:
        if avg_pct is not None and 0 < avg_pct < 30:
            add(actions, "P1", "test", "creative_retention",
                f"Weighted average view percentage is {avg_pct:.1f}% for {views:.0f} views.",
                "Test a stronger first 3–5 second promise, remove slow setup and bring the central story/payoff forward.",
                "Improvement in average view duration and average view percentage versus a comparable baseline.")
        elif avg_pct is not None and avg_pct >= 60:
            add(actions, "P2", "maintain", "creative_retention",
                f"Weighted average view percentage is {avg_pct:.1f}% for {views:.0f} views.",
                "Review the strongest-performing openings and narrative structures; test variations without copying scripts verbatim.",
                "Comparable or improved average view percentage and watch time.")
        elif avg_pct is not None:
            add(actions, "P2", "test", "creative_retention",
                f"Weighted average view percentage is {avg_pct:.1f}%.",
                "Run one controlled opening or pacing experiment; change one major creative variable at a time.",
                "Average view duration and average view percentage by format.")

        if engagement is not None and engagement < 2:
            add(actions, "P2", "test", "community_engagement",
                f"Interactions are {engagement:.2f}% of views.",
                "Test one natural, topic-specific viewer question or reflection prompt instead of a generic engagement request.",
                "Likes, comments and shares per view.")
        if subscriber_rate is not None and subscriber_rate < 1:
            add(actions, "P2", "test", "channel_conversion",
                f"Subscriber gains are {subscriber_rate:.2f} per 1,000 views.",
                "Clarify the recurring value proposition and give viewers a specific reason to return for the next episode.",
                "Subscribers gained per 1,000 views and returning viewers in Studio.")

        if isinstance(format_opportunity, dict) and format_opportunity.get("status") == "directional_comparison":
            lead = format_opportunity.get("leading_format")
            add(actions, "P2", "test", "format_mix",
                f"Step 7 identifies {lead} as the directional leading format using its own comparison filter.",
                f"Allocate a limited test slot to {lead}; retain a comparison slot for the alternate format and review after comparable exposure.",
                "Watch hours and subscriber gains per 1,000 views by creator content type.",
                "This is a directional signal, not causal proof; do not eliminate the alternate format.")
        elif format_data:
            add(actions, "P3", "investigate", "format_mix",
                "The available creator-content-type breakdown does not establish a reliable two-format comparison.",
                "Keep a balanced test mix until both formats have adequate comparable exposure.",
                "At least two creator-content types with sufficient comparable views.")

    q_total = int(quality.get("reports", 0) or 0)
    q_failed = int(quality.get("failed", 0) or 0)
    q_passed = int(quality.get("passed", 0) or 0)
    if q_failed:
        add(actions, "P1", "investigate", "technical_quality",
            f"{q_failed} of {q_total} attributed technical quality reports failed.",
            "Inspect failed video/audio stream, aspect-ratio and duration checks; correct and re-run validation before publishing.",
            "All intended final renders pass the technical validator.")
    elif q_total == 0 and prod is not None:
        add(actions, "P2", "investigate", "technical_quality",
            "No quality reports are attributed to this channel in the production report.",
            "Attach channel-specific final-render validation reports before treating production quality as verified.",
            "A technical quality report for each final render.")

    stale = int(prod_channel.get("stale_evidence_stages", 0) or 0)
    blocked = int(prod_channel.get("blocked_stages", 0) or 0)
    failed = int(prod_channel.get("failed_stages", 0) or 0)
    if stale or blocked or failed:
        add(actions, "P1", "investigate", "workflow_reliability",
            f"Production evidence: {stale} stale, {blocked} blocked and {failed} failed stages.",
            "Resolve stale evidence and the earliest blocked/failed stage first; revalidate downstream checkpoints before starting new production runs.",
            "No stale evidence and a reduced blocked/failed stage count.")

    cost_records = [r for r in ((prod or {}).get("costs") or {}).get("records", [])
                    if isinstance(r, dict) and r.get("channel") == channel]
    currencies = sorted({str(r.get("currency", "")).upper() for r in cost_records if r.get("currency")})
    cost_by_currency = {}
    for currency in currencies:
        cost_by_currency[currency] = sum(finite(r.get("amount")) or 0 for r in cost_records
                                         if str(r.get("currency", "")).upper() == currency)
    cost_efficiency = []
    if views is not None and views > 0:
        for currency, amount in cost_by_currency.items():
            cost_efficiency.append({
                "currency": currency,
                "reported_cost_per_1000_views": round(amount / views * 1000, 4),
                "basis": "user-supplied actual cost ledger divided by Analytics views",
            })
    if not cost_records:
        add(actions, "P3", "investigate", "unit_economics",
            "No actual cost ledger records were supplied for this channel; costs remain unknown.",
            "Record actual provider invoices or usage costs by channel, stage and currency before making cost-cutting decisions.",
            "Complete cost coverage for each production stage.",
            "Do not treat missing cost data as zero or infer provider rates.")
    else:
        add(actions, "P3", "investigate", "unit_economics",
            f"Actual cost records are available in {', '.join(currencies)}.",
            "Compare cost per 1,000 views only within the same currency and comparable reporting windows; use this as an efficiency indicator, not ROI.",
            "Cost per 1,000 views alongside watch time and subscriber conversion.",
            "Do not mix currencies or interpret cost per view as revenue or profitability.")

    if not actions:
        add(actions, "P3", "maintain", "measurement",
            "No actionable threshold or production issue was detected from supplied inputs.",
            "Maintain the current reviewed workflow and refresh the evidence after the next comparable reporting period.",
            "Stable or improving channel KPIs and production quality.")

    return {
        "channel": channel,
        "analytics_period": period,
        "baseline": {
            "views": views, "average_view_percentage": avg_pct,
            "engagement_rate_pct": engagement,
            "subscribers_per_1000_views": subscriber_rate,
            "quality_reports": q_total, "quality_passed": q_passed,
            "quality_failed": q_failed, "stale_evidence_stages": stale,
            "blocked_stages": blocked, "failed_stages": failed,
            "reported_cost_by_currency": cost_by_currency,
            "reported_cost_per_1000_views": cost_efficiency,
        },
        "actions": actions,
        "decision": "recommendations_only_human_review_required",
    }


def build_optimization_plan(performance: dict[str, Any], production: dict[str, Any]) -> dict[str, Any]:
    perf_channels = performance["channels"]
    prod_channels = production["channels"]
    plans = {}
    for channel in CHANNELS:
        perf = perf_channels.get(channel)
        prod = prod_channels.get(channel)
        if perf is not None and not isinstance(perf, dict):
            raise ValueError(f"{channel}: performance channel record must be an object")
        if prod is not None and not isinstance(prod, dict):
            raise ValueError(f"{channel}: production channel record must be an object")
        plans[channel] = build_channel_plan(channel, perf, prod)
    return {
        "schema_version": 1,
        "plan_type": "youtube_production_optimization_plan",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_reports": {
            "performance_report_type": performance.get("report_type"),
            "production_report_type": production.get("report_type"),
        },
        "channels": plans,
        "global_guardrails": [
            "Recommendations are deterministic decision support, not autonomous optimization.",
            "Devotional and motivation remain separate; never reuse audience assumptions or metadata across channels.",
            "No script, calendar, asset, budget, credential or publishing configuration is modified.",
            "No provider calls, rendering, uploads or scheduling are performed.",
            "Use comparable date ranges and sufficient exposure; do not infer causality from correlation.",
            "YouTube Studio remains the source of truth for retention curves, CTR, revenue and official YPP eligibility.",
        ],
    }


def write_outputs(plan: dict[str, Any], json_path: Path, md_path: Path, csv_path: Path) -> None:
    for path in (json_path, md_path, csv_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# YouTube Production Optimization Plan", ""]
    for channel, data in plan["channels"].items():
        lines += [f"## {channel.title()}", f"**Analytics period:** {data['analytics_period']}", "",
                  "| Priority | Area | Action | Evidence | Recommendation | Success metric |",
                  "|---|---|---|---|---|---|"]
        for item in data["actions"]:
            clean = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
            lines.append("| " + " | ".join(clean(item[key]) for key in
                         ("priority", "area", "action", "evidence", "recommendation", "success_metric")) + " |")
        lines.append("")
    lines += ["## Guardrails", ""] + [f"- {x}" for x in plan["global_guardrails"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    fields = ["channel", "priority", "action", "area", "evidence", "recommendation",
              "success_metric", "requires_human_approval"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for channel, data in plan["channels"].items():
            for item in data["actions"]:
                writer.writerow({"channel": channel, **{k: item[k] for k in fields[1:]}})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--performance", required=True, type=Path, help="Phase 6 Step 6 performance intelligence JSON")
    parser.add_argument("--production", required=True, type=Path, help="Phase 6 Step 11 production intelligence JSON")
    parser.add_argument("--output-json", type=Path, default=Path("optimization_plan.json"))
    parser.add_argument("--output-md", type=Path, default=Path("optimization_plan.md"))
    parser.add_argument("--output-csv", type=Path, default=Path("optimization_actions.csv"))
    args = parser.parse_args()
    try:
        plan = build_optimization_plan(load_performance(args.performance), load_production(args.production))
        write_outputs(plan, args.output_json, args.output_md, args.output_csv)
    except (OSError, ValueError) as exc:
        print(f"Optimization plan not generated: {exc}", file=sys.stderr)
        return 2
    print("Human-reviewed optimization plan generated.")
    for channel, data in plan["channels"].items():
        print(f"{channel}: {len(data['actions'])} recommended actions")
    print(f"JSON: {args.output_json}\nMarkdown: {args.output_md}\nCSV: {args.output_csv}")
    print("No production settings or publishing state were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
