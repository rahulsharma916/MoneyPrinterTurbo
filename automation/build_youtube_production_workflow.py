#!/usr/bin/env python3
"""Create a channel-isolated, checkpointed YouTube production runbook.

This tool plans commands only. It never calls AI/image providers, renders media,
authorizes publication, uploads, or schedules videos.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
ASPECTS = ("9:16", "16:9", "1:1")


def _resolved(value: str | Path | None, default: Path | None = None) -> Path | None:
    if value is None:
        return default.resolve() if default is not None else None
    return Path(value).expanduser().resolve()


def _stage(
    stage_id: str,
    name: str,
    command: list[str] | None,
    prerequisites: list[str],
    *,
    blocked_by: list[str] | None = None,
    execute_command: list[str] | None = None,
    provider_call: bool = False,
    human_checkpoint: bool = True,
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "name": name,
        "status": "ready" if command is not None else "blocked",
        "command": command,
        "execute_command": execute_command,
        "blocked_by": blocked_by or [],
        "prerequisites": prerequisites,
        "provider_call": provider_call,
        "human_checkpoint": human_checkpoint,
    }


def build_workflow(
    channel: str,
    subject: str,
    script_file: Path,
    output_dir: Path,
    *,
    aspect: str = "9:16",
    assets_file: Path | None = None,
    image_manifest: Path | None = None,
    subtitles: Path | None = None,
    audio_file: Path | None = None,
    image_root: Path | None = None,
    timeline_file: Path | None = None,
    timed_manifest: Path | None = None,
    final_video: Path | None = None,
    thumbnail: Path | None = None,
) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(CHANNELS)}")
    if not subject.strip():
        raise ValueError("subject must not be empty")
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of: {', '.join(ASPECTS)}")

    out = output_dir.expanduser().resolve()
    script = script_file.expanduser().resolve()
    assets = _resolved(assets_file, out / f"{channel}.assets.json")
    images_manifest = _resolved(image_manifest, out / "images" / "image_manifest.json")
    srt = _resolved(subtitles)
    audio = _resolved(audio_file)
    images = _resolved(image_root, images_manifest.parent)
    timeline = _resolved(timeline_file, out / "scene_timeline.json")
    timed = _resolved(timed_manifest, out / f"{channel}_timed_video.jsonl")
    video = _resolved(final_video, out / f"{channel}_final.mp4")
    thumb = _resolved(thumbnail)

    input_errors: list[str] = []
    for label, path in (("script", script),):
        if not path.is_file():
            input_errors.append(f"{label} file not found: {path}")

    assets_ready = assets.is_file()
    image_manifest_ready = images_manifest.is_file()
    srt_ready = srt is not None and srt.is_file()
    audio_ready = audio is not None and audio.is_file()
    timeline_ready = timeline.is_file()
    timed_ready = timed.is_file()
    video_ready = video.is_file()

    brief_cmd = [
        "python", "automation/generate_content_assets.py",
        "--channel", channel, "--subject", subject,
        "--script-file", str(script), "--output", str(assets),
    ]
    stages: list[dict[str, Any]] = [
        _stage(
            "creative_brief", "Generate scene, thumbnail and YouTube metadata brief",
            brief_cmd if script.is_file() else None,
            ["final Hindi narration script exists", "configured LLM provider is available"],
            blocked_by=[] if script.is_file() else ["final narration script"],
            provider_call=True,
        )
    ]

    dry_run_cmd = [
        "python", "automation/render_scene_images.py", str(assets),
        "--output-dir", str(images_manifest.parent), "--include-thumbnail",
    ]
    execute_cmd = dry_run_cmd + ["--execute"]
    stages.append(_stage(
        "scene_images", "Review and render scene images",
        dry_run_cmd if assets_ready else None,
        ["creative brief exists", "scene prompts and thumbnail prompt reviewed"],
        blocked_by=[] if assets_ready else ["generated and reviewed assets JSON"],
        execute_command=execute_cmd if assets_ready else None,
        provider_call=True,
    ))

    timeline_cmd = None
    timeline_blockers = []
    if not assets_ready:
        timeline_blockers.append("assets JSON")
    if not image_manifest_ready:
        timeline_blockers.append("executed image_manifest.json")
    if not srt_ready:
        timeline_blockers.append("final narration SRT")
    if not audio_ready:
        timeline_blockers.append("exact final narration audio used to create the SRT")
    if not timeline_blockers:
        timeline_cmd = [
            "python", "automation/build_scene_timeline.py",
            "--assets", str(assets), "--image-manifest", str(images_manifest),
            "--subtitles", str(srt), "--output", str(timeline),
        ]
    stages.append(_stage(
        "scene_timeline", "Align scene excerpts to final narration subtitles",
        timeline_cmd,
        ["SRT and audio are from the same final narration", "review all low-confidence matches"],
        blocked_by=timeline_blockers,
    ))

    timed_cmd = None
    timed_blockers = []
    if not timeline_ready:
        timed_blockers.append("approved scene_timeline.json")
    if not audio_ready:
        timed_blockers.append("final narration audio")
    if not script.is_file():
        timed_blockers.append("final narration script")
    if not timed_blockers:
        timed_cmd = [
            "python", "automation/prepare_timed_scene_video_task.py",
            "--timeline", str(timeline), "--image-root", str(images),
            "--audio-file", str(audio), "--script-file", str(script),
            "--aspect", aspect, "--output", str(timed),
        ]
    stages.append(_stage(
        "timed_video_task", "Prepare narration-timed video render task",
        timed_cmd,
        ["scene timeline approved", "image paths verified", "aspect ratio confirmed"],
        blocked_by=timed_blockers,
    ))

    render_cmd = (
        ["python", "cli.py", "--batch-file", str(timed)]
        if timed_ready else None
    )
    stages.append(_stage(
        "render_video", "Render final video with MoneyPrinterTurbo",
        render_cmd,
        ["timed task manifest reviewed", "TTS, subtitle and music settings verified"],
        blocked_by=[] if timed_ready else ["generated timed video JSONL manifest"],
        provider_call=True,
    ))

    publish_cmd = None
    publish_blockers = []
    if not assets_ready:
        publish_blockers.append("assets JSON with YouTube metadata")
    if not video_ready:
        publish_blockers.append("final rendered MP4")
    if not publish_blockers:
        publish_cmd = [
            "python", "automation/prepare_youtube_publishing_package.py",
            "--channel", channel, "--assets", str(assets), "--video", str(video),
        ]
        if thumb:
            publish_cmd.extend(["--thumbnail", str(thumb)])
        publish_cmd.extend([
            "--made-for-kids", "<review-and-set-yes-or-no>",
            "--synthetic-media", "<review-and-set-yes-or-no>",
        ])
    stages.append(_stage(
        "publishing_review", "Prepare human-review-only YouTube publishing package",
        publish_cmd,
        [
            "watch the final video end-to-end",
            "review thumbnail, title, description, tags and hashtags",
            "check music/image rights and synthetic-media disclosure",
            "confirm audience declaration and correct channel account",
        ],
        blocked_by=publish_blockers,
    ))

    return {
        "schema_version": 1,
        "workflow_type": "youtube_channel_production_runbook",
        "channel": channel,
        "subject": subject.strip(),
        "aspect": aspect,
        "output_dir": str(out),
        "status": "input_errors" if input_errors else "planned",
        "input_errors": input_errors,
        "paths": {
            "script": str(script), "assets": str(assets),
            "image_manifest": str(images_manifest), "subtitles": str(srt) if srt else None,
            "audio": str(audio) if audio else None, "image_root": str(images),
            "timeline": str(timeline), "timed_manifest": str(timed),
            "final_video": str(video), "thumbnail": str(thumb) if thumb else None,
        },
        "stages": stages,
        "guardrails": {
            "devotional_and_motivation_are_separate": True,
            "provider_execution_is_opt_in": True,
            "human_review_required": True,
            "upload_enabled": False,
            "upload_authorized": False,
            "public_uploads_enabled": False,
            "scheduling_enabled": False,
        },
        "important_notes": [
            "This file is a runbook, not an execution log; no commands were run by this planner.",
            "Run stages individually and regenerate the runbook after each output is created.",
            "The audio supplied to the timed scene task must be the exact audio used to create the SRT.",
            "The publishing package is review-only; upload remains a separate explicitly approved action.",
            "Review every generated asset for factual accuracy, cultural sensitivity, licensing and visual quality.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--aspect", choices=ASPECTS, default="9:16")
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--image-manifest", type=Path)
    parser.add_argument("--subtitles", type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--image-root", type=Path)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--timed-manifest", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--thumbnail", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        workflow = build_workflow(
            args.channel, args.subject, args.script, args.output_dir,
            aspect=args.aspect, assets_file=args.assets,
            image_manifest=args.image_manifest, subtitles=args.subtitles,
            audio_file=args.audio, image_root=args.image_root,
            timeline_file=args.timeline, timed_manifest=args.timed_manifest,
            final_video=args.video, thumbnail=args.thumbnail,
        )
        destination = (args.output.expanduser().resolve() if args.output
                       else args.output_dir.expanduser().resolve() / f"{args.channel}_workflow.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        print(f"Workflow plan not created: {exc}", file=sys.stderr)
        return 2

    ready = sum(stage["status"] == "ready" for stage in workflow["stages"])
    print(f"Workflow plan: {destination}")
    print(f"Channel: {args.channel}; ready stages: {ready}/{len(workflow['stages'])}")
    print("No provider calls, rendering, uploads or scheduling were executed.")
    print("Human approval remains mandatory; public uploads remain disabled.")
    return 0 if workflow["status"] == "planned" else 2


if __name__ == "__main__":
    raise SystemExit(main())
