#!/usr/bin/env python3
"""Audit local evidence for a controlled, two-channel YouTube production pilot.

This is a read-only preflight. It never reads secret contents, calls providers,
renders media, schedules jobs, or uploads videos.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
PROVIDERS = ("narration", "image", "video")


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def is_true(value: Any) -> bool:
    return value is True


def resolve(base: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def check_file(base: Path, value: Any, label: str, checks: list[dict[str, str]]) -> bool:
    path = resolve(base, value)
    if path is None or not path.is_file():
        checks.append({"status": "blocked", "check": label,
                       "detail": "Required file is missing or not configured."})
        return False
    checks.append({"status": "passed", "check": label,
                   "detail": f"File exists: {path.name}"})
    return True


def channel_audit(channel: str, record: Any, base: Path) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    if not isinstance(record, dict):
        record = {}

    channel_id = record.get("channel_id")
    channel_id_ok = isinstance(channel_id, str) and bool(channel_id.strip()) and not channel_id.lower().startswith("your_")
    checks.append({
        "status": "passed" if channel_id_ok else "blocked",
        "check": "channel_identity",
        "detail": "Channel ID supplied." if channel_id_ok else "A real channel ID is required.",
    })

    for field, label in (
        ("oauth_client_secrets_file", "oauth_client_file"),
        ("oauth_token_file", "oauth_token_file"),
    ):
        check_file(base, record.get(field), label, checks)

    for field, label in (
        ("oauth_verified", "oauth_authentication"),
        ("channel_access_verified", "channel_access"),
        ("upload_scope_verified", "youtube_upload_scope"),
    ):
        ok = is_true(record.get(field))
        checks.append({
            "status": "passed" if ok else "blocked",
            "check": label,
            "detail": "Verified by operator." if ok else "Operator verification is required; do not infer from file presence.",
        })

    providers = record.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    for provider in PROVIDERS:
        item = providers.get(provider)
        ok = isinstance(item, dict) and bool(str(item.get("name") or "").strip()) and is_true(item.get("configured")) and is_true(item.get("verified"))
        checks.append({
            "status": "passed" if ok else "blocked",
            "check": f"{provider}_provider",
            "detail": f"{item.get('name')} configured and verified." if ok else f"Configure and verify the {provider} provider.",
        })

    video_ok = check_file(base, record.get("pilot_video_file"), "pilot_video_file", checks)
    quality_path = resolve(base, record.get("pilot_quality_report_file"))
    quality_ok = False
    if quality_path is None or not quality_path.is_file():
        checks.append({"status": "blocked", "check": "pilot_quality_report",
                       "detail": "A final-render quality report is required."})
    else:
        try:
            quality = read_json(quality_path, "pilot quality report")
            report_video = resolve(quality_path.parent, quality.get("video_file"))
            expected_video = resolve(base, record.get("pilot_video_file"))
            quality_ok = (
                quality.get("status") == "passed"
                and report_video is not None
                and expected_video is not None
                and report_video == expected_video
            )
            checks.append({
                "status": "passed" if quality_ok else "blocked",
                "check": "pilot_quality_report",
                "detail": "Quality report passed and references the configured pilot video."
                if quality_ok else "Quality report must have status=passed and reference this exact pilot video.",
            })
        except ValueError as exc:
            checks.append({"status": "blocked", "check": "pilot_quality_report", "detail": str(exc)})

    checks.append({
        "status": "passed" if record.get("upload_approved") is False else "blocked",
        "check": "human_upload_approval_guard",
        "detail": "No upload approval is pre-authorized." if record.get("upload_approved") is False
        else "Set upload_approved to false; this preflight cannot authorize publishing.",
    })

    blockers = [item["check"] for item in checks if item["status"] != "passed"]
    return {
        "channel": channel,
        "status": "pilot_ready_for_human_review" if not blockers else "blocked",
        "channel_id_configured": channel_id_ok,
        "pilot_video_present": video_ok,
        "pilot_quality_passed": quality_ok,
        "checks": checks,
        "blockers": blockers,
    }


def build_report(manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path, "readiness manifest")
    if manifest.get("manifest_type") != "youtube_production_readiness_manifest" or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest type or schema_version; expected version 1.")
    base = manifest_path.resolve().parent
    channel_records = manifest.get("channels")
    if not isinstance(channel_records, dict):
        channel_records = {}

    channels = {name: channel_audit(name, channel_records.get(name), base) for name in CHANNELS}
    global_checks = []
    safe = manifest.get("public_uploads_enabled") is False
    global_checks.append({
        "status": "passed" if safe else "blocked",
        "check": "public_uploads_disabled",
        "detail": "Public uploads remain disabled." if safe else "Set public_uploads_enabled to false.",
    })
    approval = manifest.get("human_approval_required") is True
    global_checks.append({
        "status": "passed" if approval else "blocked",
        "check": "human_approval_required",
        "detail": "Human approval is mandatory." if approval else "Set human_approval_required to true.",
    })

    ready = all(c["status"] == "pilot_ready_for_human_review" for c in channels.values()) and all(
        c["status"] == "passed" for c in global_checks
    )
    return {
        "report_type": "youtube_production_readiness_audit",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "both_channels_ready_for_human_review" if ready else "blocked",
        "production_authorized": False,
        "public_uploads_enabled": False,
        "global_checks": global_checks,
        "channels": channels,
        "next_action": (
            "Review both pilot videos and approve any upload separately in the publishing workflow."
            if ready else "Resolve every blocker, rerun this audit, then review pilot videos manually."
        ),
        "limitations": [
            "This report verifies local evidence and operator attestations; it does not independently authenticate Google or provider accounts.",
            "It never reads secret contents, invokes providers, renders media, schedules jobs or uploads videos.",
            "A readiness pass is not publishing approval or a production go-live authorization.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# YouTube Production Readiness Audit",
        "",
        f"**Overall status:** {report['overall_status']}",
        f"**Production authorized:** {str(report['production_authorized']).lower()}",
        f"**Public uploads enabled:** {str(report['public_uploads_enabled']).lower()}",
        "",
        "## Global safeguards",
        "",
    ]
    for item in report["global_checks"]:
        lines.append(f"- [{'x' if item['status'] == 'passed' else ' '}] {item['check']}: {item['detail']}")
    for channel, result in report["channels"].items():
        lines.extend(["", f"## {channel.title()}", "", f"**Status:** {result['status']}", ""])
        for item in result["checks"]:
            lines.append(f"- [{'x' if item['status'] == 'passed' else ' '}] {item['check']}: {item['detail']}")
    lines.extend(["", "## Next action", "", report["next_action"], "", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-json", type=Path, default=Path("storage/reports/production_readiness.json"))
    parser.add_argument("--output-md", type=Path, default=Path("storage/reports/production_readiness.md"))
    args = parser.parse_args()
    try:
        report = build_report(args.manifest)
        for path, content in (
            (args.output_json, json.dumps(report, indent=2, ensure_ascii=False) + "\n"),
            (args.output_md, render_markdown(report)),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Overall status: {report['overall_status']}")
    print(f"JSON report: {args.output_json}")
    print(f"Markdown report: {args.output_md}")
    return 0 if report["overall_status"] == "both_channels_ready_for_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
