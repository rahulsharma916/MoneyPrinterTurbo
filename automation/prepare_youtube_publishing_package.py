#!/usr/bin/env python3
"""Create a review-only YouTube publishing package; never uploads or schedules."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
MAX_MANIFEST_BYTES = 256 * 1024


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _required_file(path: Path, label: str) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist or is not a file: {path}")
    return str(resolved)


def load_channel(config_path: Path, channel: str) -> dict[str, Any]:
    data = _read_json(config_path, "channel configuration")
    channels = data.get("channels")
    profile = channels.get(channel) if isinstance(channels, dict) else None
    if not isinstance(profile, dict) or profile.get("content_profile") != channel:
        raise ValueError(f"unknown or invalid channel: {channel}")
    publishing = profile.get("publishing")
    if not isinstance(publishing, dict):
        raise ValueError(f"{channel}: publishing configuration is missing")
    if publishing.get("platform") != "youtube":
        raise ValueError(f"{channel}: publishing platform must be youtube")
    if publishing.get("upload_enabled") is not False:
        raise ValueError(f"{channel}: this preparation tool requires uploads to remain disabled")
    if publishing.get("approval_required") is not True:
        raise ValueError(f"{channel}: human approval must remain required")
    if publishing.get("privacy_status") not in {"private", "unlisted", "public"}:
        raise ValueError(f"{channel}: invalid privacy status")
    return profile


def build_package(
    assets_path: Path,
    video_path: Path,
    channel: str,
    *,
    thumbnail_path: Path | None = None,
    config_path: Path = DEFAULT_CONFIG,
    made_for_kids: bool | None = None,
    contains_synthetic_media: bool | None = None,
) -> dict[str, Any]:
    if made_for_kids is None:
        raise ValueError("made_for_kids must be explicitly reviewed as true or false")
    if contains_synthetic_media is None:
        raise ValueError("contains_synthetic_media must be explicitly reviewed as true or false")
    profile = load_channel(config_path, channel)
    assets = _read_json(assets_path, "content asset package")
    if assets.get("channel") != channel:
        raise ValueError("asset package channel does not match the selected publishing channel")
    youtube = assets.get("youtube")
    if not isinstance(youtube, dict):
        raise ValueError("asset package is missing YouTube metadata")
    title = youtube.get("title")
    description = youtube.get("description")
    tags = youtube.get("tags")
    hashtags = youtube.get("hashtags")
    if not isinstance(title, str) or not title.strip() or len(title) > 100:
        raise ValueError("YouTube title must contain 1-100 characters")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError("YouTube description must be a string of at most 5000 characters")
    if not isinstance(tags, list) or len(tags) > 15 or not all(
        isinstance(item, str) and item.strip() for item in tags
    ):
        raise ValueError("YouTube tags must be a list of at most 15 non-empty strings")
    if not isinstance(hashtags, list) or len(hashtags) > 5 or not all(
        isinstance(item, str) and item.strip().startswith("#") for item in hashtags
    ):
        raise ValueError("YouTube hashtags must be a list of at most 5 #hashtags")

    video = _required_file(video_path, "final video")
    thumbnail = _required_file(thumbnail_path, "thumbnail") if thumbnail_path else None
    publishing = profile["publishing"]
    manifest = {
        "schema_version": 1,
        "channel": channel,
        "channel_display_name": profile.get("display_name", channel),
        "subject": str(assets.get("subject") or "").strip(),
        "assets_package": str(assets_path.expanduser().resolve()),
        "video_file": video,
        "thumbnail_file": thumbnail,
        "youtube": {
            "title": title.strip(),
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "privacy_status": publishing["privacy_status"],
            "made_for_kids": made_for_kids,
            "contains_synthetic_media": contains_synthetic_media,
        },
        "publishing_account_env": publishing.get("upload_post_account_env"),
        "workflow": {
            "status": "pending_human_review",
            "upload_enabled_in_channel_config": False,
            "upload_authorized": False,
            "schedule_at": None,
            "checks": {
                "video_played_and_reviewed": False,
                "thumbnail_reviewed": False,
                "title_description_tags_reviewed": False,
                "copyright_and_music_rights_checked": False,
                "audience_declaration_reviewed": False,
                "synthetic_media_disclosure_reviewed": False,
                "correct_channel_account_confirmed": False,
            },
            "approval": {
                "approved_by": None,
                "approved_at": None,
                "notes": None,
            },
        },
        "safety_note": (
            "Review package only. This utility does not upload, schedule, change channel "
            "configuration, read credentials, or authorize publication."
        ),
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=("devotional", "motivation"))
    parser.add_argument("--assets", required=True, type=Path, help="Generated *_assets.json package")
    parser.add_argument("--video", required=True, type=Path, help="Final rendered MP4")
    parser.add_argument("--thumbnail", type=Path, help="Optional final thumbnail image")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--made-for-kids", required=True, choices=("yes", "no"))
    parser.add_argument("--synthetic-media", required=True, choices=("yes", "no"))
    parser.add_argument("--output", type=Path, help="Output JSON path; defaults beside the video")
    args = parser.parse_args()
    try:
        manifest = build_package(
            args.assets, args.video, args.channel,
            thumbnail_path=args.thumbnail, config_path=args.config,
            made_for_kids=args.made_for_kids == "yes",
            contains_synthetic_media=args.synthetic_media == "yes",
        )
        output = args.output or args.video.with_suffix(".publishing.json")
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if len(encoded.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise ValueError("publishing package exceeds the 256 KiB safety limit")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Review package created: {output}")
    print("Status: pending_human_review; upload_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
