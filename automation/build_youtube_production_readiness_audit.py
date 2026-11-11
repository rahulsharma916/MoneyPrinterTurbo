#!/usr/bin/env python3
"""Audit production artifacts and issue a human-review readiness report.

This is a read-only gate. It never approves, uploads, publishes, or schedules.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
ASPECTS = ("9:16", "16:9", "1:1")
MAX_REPORT_BYTES = 512 * 1024


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _check_file(path: Path, label: str, checks: list[dict[str, str]]) -> bool:
    exists = path.is_file()
    checks.append({
        "name": label,
        "status": "passed" if exists else "blocked",
        "detail": str(path) if exists else f"file not found: {path}",
    })
    return exists


def audit_production(
    channel: str,
    expected_aspect: str,
    assets_path: Path,
    image_manifest_path: Path,
    timeline_path: Path,
    timed_manifest_path: Path,
    audio_path: Path,
    video_path: Path,
    quality_report_path: Path,
    publishing_manifest_path: Path,
    config_path: Path,
) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(CHANNELS)}")
    if expected_aspect not in ASPECTS:
        raise ValueError(f"expected_aspect must be one of: {', '.join(ASPECTS)}")

    paths = {
        "assets": assets_path.expanduser().resolve(),
        "image_manifest": image_manifest_path.expanduser().resolve(),
        "timeline": timeline_path.expanduser().resolve(),
        "timed_manifest": timed_manifest_path.expanduser().resolve(),
        "audio": audio_path.expanduser().resolve(),
        "video": video_path.expanduser().resolve(),
        "quality_report": quality_report_path.expanduser().resolve(),
        "publishing_manifest": publishing_manifest_path.expanduser().resolve(),
        "channel_config": config_path.expanduser().resolve(),
    }
    checks: list[dict[str, str]] = []
    for key, path in paths.items():
        _check_file(path, f"{key}_file_exists", checks)

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "passed" if passed else "blocked", "detail": detail})

    required = ("assets", "image_manifest", "timeline", "timed_manifest", "audio", "video",
                "quality_report", "publishing_manifest", "channel_config")
    if not all(paths[key].is_file() for key in required):
        return _report(channel, expected_aspect, paths, checks, "missing_required_artifacts")

    assets = _read_json(paths["assets"], "assets package")
    images = _read_json(paths["image_manifest"], "image manifest")
    timeline = _read_json(paths["timeline"], "scene timeline")
    quality = _read_json(paths["quality_report"], "video quality report")
    publishing = _read_json(paths["publishing_manifest"], "publishing package")
    config = _read_json(paths["channel_config"], "channel configuration")

    asset_channel = assets.get("channel")
    add("assets_channel_matches", asset_channel == channel, f"assets channel={asset_channel!r}; expected={channel!r}")
    add("image_manifest_channel_matches", images.get("channel") == channel,
        f"image manifest channel={images.get('channel')!r}; expected={channel!r}")
    add("timeline_channel_matches", timeline.get("channel") == channel,
        f"timeline channel={timeline.get('channel')!r}; expected={channel!r}")
    add("publishing_package_channel_matches", publishing.get("channel") == channel,
        f"publishing package channel={publishing.get('channel')!r}; expected={channel!r}")

    channel_data = config.get("channels", {}).get(channel) if isinstance(config.get("channels"), dict) else None
    publishing_config = channel_data.get("publishing") if isinstance(channel_data, dict) else None
    safe_config = (
        isinstance(channel_data, dict)
        and channel_data.get("content_profile") == channel
        and isinstance(publishing_config, dict)
        and publishing_config.get("upload_enabled") is False
        and publishing_config.get("approval_required") is True
    )
    add("channel_config_keeps_upload_disabled", safe_config,
        "upload_enabled must be false and approval_required must be true")

    scene_list = assets.get("scenes")
    image_entries = images.get("images")
    scene_count = len(scene_list) if isinstance(scene_list, list) else 0
    image_ready = (
        isinstance(image_entries, list)
        and len(image_entries) >= scene_count > 0
        and all(isinstance(item, dict) and item.get("status") in {"generated", "skipped_existing"}
                and isinstance(item.get("image_file"), str) and Path(item["image_file"]).is_file()
                for item in image_entries[:scene_count])
    )
    add("all_scene_images_exist", image_ready,
        f"asset scenes={scene_count}; image entries={len(image_entries) if isinstance(image_entries, list) else 0}")

    timeline_scenes = timeline.get("scenes")
    timeline_ready = (
        isinstance(timeline_scenes, list)
        and len(timeline_scenes) == scene_count
        and timeline.get("scene_count") == scene_count
        and timeline.get("aligned_scene_count") == scene_count
        and all(isinstance(scene, dict) and scene.get("aligned") is True
                and isinstance(scene.get("image_file"), str)
                and Path(scene["image_file"]).is_file()
                for scene in timeline_scenes)
    )
    add("all_timeline_scenes_aligned", timeline_ready,
        f"aligned={timeline.get('aligned_scene_count')!r}; scenes={timeline.get('scene_count')!r}")

    try:
        task_lines = [line for line in paths["timed_manifest"].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        task_objects = [json.loads(line) for line in task_lines]
        task_valid = (
            len(task_objects) == 1
            and isinstance(task_objects[0], dict)
            and task_objects[0].get("video_source") == "local"
            and task_objects[0].get("video_aspect") == expected_aspect
            and isinstance(task_objects[0].get("video_materials"), list)
            and len(task_objects[0]["video_materials"]) == scene_count
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        task_valid = False
    add("timed_task_manifest_valid", task_valid,
        f"expected one local task, aspect={expected_aspect}, material count={scene_count}")

    quality_ok = (
        quality.get("status") == "passed"
        and quality.get("expected_aspect") == expected_aspect
        and quality.get("video_stream_count", 0) >= 1
        and quality.get("audio_stream_count", 0) >= 1
        and isinstance(quality.get("checks"), dict)
        and all(quality["checks"].get(key) == "passed"
                for key in ("video_stream", "audio_stream", "aspect_ratio", "duration_window"))
    )
    reported_video = quality.get("video_file")
    reported_audio = quality.get("narration_file")
    quality_paths_match = (
        isinstance(reported_video, str) and Path(reported_video).resolve() == paths["video"]
        and isinstance(reported_audio, str) and Path(reported_audio).resolve() == paths["audio"]
    )
    add("video_quality_gate_passed", quality_ok and quality_paths_match,
        "FFprobe report must pass stream/aspect/duration checks and reference the supplied video/audio files")

    package_workflow = publishing.get("workflow")
    package_youtube = publishing.get("youtube")
    package_ok = (
        isinstance(package_workflow, dict)
        and package_workflow.get("status") == "pending_human_review"
        and package_workflow.get("upload_authorized") is False
        and package_workflow.get("upload_enabled_in_channel_config") is False
        and isinstance(package_youtube, dict)
        and package_youtube.get("privacy_status") in {"private", "unlisted", "public"}
        and isinstance(package_youtube.get("made_for_kids"), bool)
        and isinstance(package_youtube.get("contains_synthetic_media"), bool)
        and isinstance(publishing.get("video_file"), str)
        and Path(publishing["video_file"]).resolve() == paths["video"]
    )
    add("publishing_package_is_review_only", package_ok,
        "must match this channel/video, have explicit audience/disclosure booleans and remain unauthorized")

    return _report(channel, expected_aspect, paths, checks, "audited")


def _report(
    channel: str,
    expected_aspect: str,
    paths: dict[str, Path],
    checks: list[dict[str, str]],
    audit_state: str,
) -> dict[str, Any]:
    blockers = [item for item in checks if item["status"] != "passed"]
    return {
        "schema_version": 1,
        "report_type": "youtube_production_readiness_audit",
        "channel": channel,
        "expected_aspect": expected_aspect,
        "audit_state": audit_state,
        "readiness": "ready_for_human_review" if not blockers else "blocked",
        "passed_checks": len(checks) - len(blockers),
        "blocked_checks": len(blockers),
        "checks": checks,
        "blockers": blockers,
        "artifacts": {key: str(value) for key, value in paths.items()},
        "authorization": {
            "human_review_required": True,
            "upload_authorized": False,
            "public_uploads_enabled": False,
            "scheduling_enabled": False,
        },
        "limitations": [
            "A passed audit is technical readiness for human review, not approval to publish.",
            "FFprobe metadata checks do not establish visual quality, factual accuracy, cultural sensitivity, narration pronunciation, subtitle correctness, music rights or audience suitability.",
            "A human must watch the full video and complete every publishing checklist item.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument("--aspect", required=True, choices=ASPECTS)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--image-manifest", required=True, type=Path)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--timed-manifest", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--quality-report", required=True, type=Path,
                        help="JSON report created by validate_rendered_video.py --report")
    parser.add_argument("--publishing-manifest", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("channel_configs.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = audit_production(
            args.channel, args.aspect, args.assets, args.image_manifest, args.timeline,
            args.timed_manifest, args.audio, args.video, args.quality_report,
            args.publishing_manifest, args.config,
        )
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if len(encoded.encode("utf-8")) > MAX_REPORT_BYTES:
            raise ValueError("audit report exceeds 512 KiB")
        args.output.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output.expanduser().resolve().write_text(encoded, encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Readiness audit failed: {exc}", file=sys.stderr)
        return 2
    print(f"Readiness: {report['readiness']} | passed={report['passed_checks']} blocked={report['blocked_checks']}")
    print(f"Report: {args.output.expanduser().resolve()}")
    print("This audit does not authorize or perform publication.")
    return 0 if report["readiness"] == "ready_for_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
