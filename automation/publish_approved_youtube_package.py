#!/usr/bin/env python3
"""Execute one explicitly approved YouTube upload through the existing Upload-Post service.

Default mode validates the approval package and channel credentials without network access.
A real upload requires both --execute and --confirm-upload. The manifest is marked as
attempted before the network request so an interrupted/uncertain attempt cannot be retried
automatically and accidentally create a duplicate upload.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automation.validate_channel_upload_accounts import load_channel_account
from app.services.upload_post import UploadPostService

DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
REQUIRED_CHECKS = (
    "video_played_and_reviewed",
    "thumbnail_reviewed",
    "title_description_tags_reviewed",
    "copyright_and_music_rights_checked",
    "audience_declaration_reviewed",
    "synthetic_media_disclosure_reviewed",
    "correct_channel_account_confirmed",
)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read publishing manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("publishing manifest must be a JSON object")
    return data


def _write_manifest_atomic(path: Path, data: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def validate_approved_package(
    manifest: dict[str, Any],
    manifest_path: Path,
    channel: str,
    config_path: Path,
) -> tuple[dict[str, Any], Path]:
    if manifest.get("channel") != channel:
        raise ValueError("manifest channel does not match --channel")
    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("manifest workflow section is missing")
    if workflow.get("status") != "approved" or workflow.get("upload_authorized") is not True:
        raise ValueError("manifest is not explicitly approved; set status=approved and upload_authorized=true only after review")
    checks = workflow.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("approval checklist is missing")
    incomplete = [name for name in REQUIRED_CHECKS if checks.get(name) is not True]
    if incomplete:
        raise ValueError("approval checklist incomplete: " + ", ".join(incomplete))
    approval = workflow.get("approval")
    if not isinstance(approval, dict):
        raise ValueError("approval record is missing")
    if not isinstance(approval.get("approved_by"), str) or not approval["approved_by"].strip():
        raise ValueError("approval.approved_by must identify the human approver")
    if not isinstance(approval.get("approved_at"), str) or not approval["approved_at"].strip():
        raise ValueError("approval.approved_at must contain the approval timestamp")

    youtube = manifest.get("youtube")
    if not isinstance(youtube, dict):
        raise ValueError("YouTube metadata is missing")
    title = youtube.get("title")
    description = youtube.get("description")
    tags = youtube.get("tags")
    privacy = youtube.get("privacy_status")
    made_for_kids = youtube.get("made_for_kids")
    synthetic = youtube.get("contains_synthetic_media")
    if not isinstance(title, str) or not title.strip() or len(title) > 100:
        raise ValueError("YouTube title must contain 1-100 characters")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError("YouTube description must be a string of at most 5000 characters")
    if not isinstance(tags, list) or len(tags) > 15 or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise ValueError("YouTube tags must contain at most 15 non-empty strings")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("YouTube privacy_status must be private, unlisted or public")
    if not isinstance(made_for_kids, bool):
        raise ValueError("made_for_kids must be an explicit boolean")
    if not isinstance(synthetic, bool):
        raise ValueError("contains_synthetic_media must be an explicit boolean")

    video_value = manifest.get("video_file")
    if not isinstance(video_value, str) or not video_value.strip():
        raise ValueError("final video_file path is missing")
    video_path = Path(video_value).expanduser().resolve()
    if not video_path.is_file():
        raise ValueError(f"final video file does not exist: {video_path}")

    account = load_channel_account(channel, config_path=config_path, environ=environ)
    if manifest.get("publishing_account_env") != _channel_account_env(config_path, channel):
        raise ValueError("manifest publishing account does not match the selected channel configuration")
    if workflow.get("execution_attempt") is not None:
        raise ValueError("this manifest already has an execution attempt; reconcile its remote status before any manual recovery")
    return account, video_path


def _channel_account_env(config_path: Path, channel: str) -> str | None:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return config["channels"][channel]["publishing"]["upload_post_account_env"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return None


def publish_approved_package(
    manifest_path: Path,
    channel: str,
    *,
    config_path: Path = DEFAULT_CONFIG,
    execute: bool = False,
    confirm_upload: bool = False,
    environ=None,
) -> dict[str, Any]:
    manifest = _read_manifest(manifest_path)
    account, video_path = validate_approved_package(manifest, manifest_path, channel, config_path)
    if not execute:
        return {"ready": True, "executed": False, "channel": channel, "video_file": str(video_path)}
    if not confirm_upload:
        raise ValueError("real upload requires both --execute and --confirm-upload")

    # The channel config remains upload_enabled=false. Only this single, approved
    # invocation receives an enabled in-memory account snapshot.
    account["upload_post_enabled"] = True
    workflow = manifest["workflow"]
    attempt = {
        "id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "submitting",
    }
    workflow["execution_attempt"] = attempt
    _write_manifest_atomic(manifest_path, manifest)

    youtube = manifest["youtube"]
    service = UploadPostService(account=account)
    try:
        result = service.upload_video(
            video_path=str(video_path),
            title=youtube["title"],
            platforms=["youtube"],
            youtube_extra={
                "youtube_title": youtube["title"],
                "youtube_description": youtube["description"],
                "tags": youtube["tags"],
                "privacyStatus": youtube["privacy_status"],
                "selfDeclaredMadeForKids": youtube["made_for_kids"],
                "containsSyntheticMedia": youtube["contains_synthetic_media"],
            },
        )
    except Exception as exc:
        attempt.update({
            "status": "outcome_unconfirmed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
        })
        _write_manifest_atomic(manifest_path, manifest)
        raise

    if not isinstance(result, dict):
        result = {"success": False, "error": "Upload-Post returned an invalid response"}
    request_id = result.get("request_id")
    if result.get("success") is True:
        attempt["status"] = "completed"
    elif request_id or "unconfirmed" in str(result.get("error", "")).lower():
        attempt["status"] = "outcome_unconfirmed"
    else:
        attempt["status"] = "failed"
    attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
    if isinstance(request_id, str) and request_id:
        attempt["request_id"] = request_id
    if result.get("success") is not True:
        attempt["error"] = str(result.get("error") or result.get("message") or "Upload-Post reported failure")[:1000]
    _write_manifest_atomic(manifest_path, manifest)
    return {
        "ready": True,
        "executed": True,
        "channel": channel,
        "status": attempt["status"],
        "request_id": attempt.get("request_id"),
        "error": attempt.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=("devotional", "motivation"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true", help="perform the one approved YouTube upload")
    parser.add_argument("--confirm-upload", action="store_true", help="explicit confirmation required with --execute")
    args = parser.parse_args()
    if args.confirm_upload and not args.execute:
        parser.error("--confirm-upload can only be used together with --execute")
    try:
        result = publish_approved_package(
            args.manifest, args.channel, config_path=args.config,
            execute=args.execute, confirm_upload=args.confirm_upload,
        )
    except (OSError, ValueError) as exc:
        print(f"Not ready: {exc}", file=sys.stderr)
        return 2
    if not result["executed"]:
        print(f"Ready for explicit execution: {result['channel']} | {result['video_file']}")
        print("No network request was made. Use --execute --confirm-upload only after final review.")
        return 0
    print(f"Upload attempt status: {result['status']}")
    if result.get("request_id"):
        print(f"Upload-Post request ID: {result['request_id']}")
    if result.get("error"):
        print(f"Upload result: {result['error']}")
    if result["status"] == "outcome_unconfirmed":
        print("Do not retry. Check the request ID/status in Upload-Post before taking further action.")
        return 3
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
