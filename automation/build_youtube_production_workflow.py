#!/usr/bin/env python3
"""Build a channel-isolated, human-gated production workflow plan.

This orchestrator plans the existing tools; it does not execute providers, render
videos, authorize uploads, or publish. Run each command only after its checkpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
ASPECTS = ("9:16", "16:9", "1:1")


def _path(value: str | Path | None) -> Path | None:
    return Path(value).expanduser().resolve() if value else None


def _exists(path: Path | None, label: str, errors: list[str]) -> str | None:
    if path is None:
        return None
    if not path.is_file():
        errors.append(f"{label} does not exist or is not a file: {path}")
        return str(path)
    return str(path)


def build_workflow(
    channel: str,
    subject: str,
    script_file: Path,
    output_dir: Path,
    *,
    aspect: str = "9:16",
    subtitles: Path | None = None,
    audio_file: Path | None = None,
    assets_file: Path | None = None,
    image_manifest: Path | None = None,
    image_root: Path | None = None,
    timeline_file: Path | None = None,
    final_video: Path | None = None,
    thumbnail: Path | None = None,
) -> dict[str, Any]:
    if channel not in CHANNELS:
        raise ValueError(f"unsupported channel: {channel}")
    if not subject.strip():
        raise ValueError("subject must not be empty")
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of {', '.join(ASPECTS)}")

    output = output_dir.expanduser().resolve()
    script = script_file.expanduser().resolve()
    errors: list[str] = []
    _exists(script, "script file", errors)
    assets = _path(assets_file) or output / f"{channel}.assets.json"
    manifest = _path(image_manifest) or output / "images" / "image_manifest.json"
    timeline = _path(timeline_file) or output / "scene_timeline.json"
    audio = _path(audio_file)
    srt = _path(subtitles)
    images = _path(image_root) or manifest.parent
    video = _path(final_video) or output / f"{channel}_final.mp4"
    thumb = _path(thumbnail)

    commands: list[dict[str, Any]] = [
        {
            "id": "creative_brief",
            "stage": "generate_content_assets",
            "command": ["python", "automation/generate_content_assets.py", "--channel", channel,
                        "--subject", subject, "--script-file", str(script), "--output", str(assets)],
            "requires": ["review_script_accuracy_and_channel_fit"],
            "provider_call": True,
        },
        {
            "id": "scene_images",
            "stage": "render_scene_images",
            "command": ["python", "automation/render_scene_images.py", str(assets),
                        "--output-dir", str(manifest.parent), "--include-thumbnail"],
            "execute_flag": "--execute",
            "requires": ["approve_scene_prompts_and_thumbnail_prompt"],
            "provider_call": True,
        },
    ]

    timeline_ready = bool(srt and audio and srt.is_file() and audio.is_file() and manifest.is_file())
    if timeline_ready:
        commands.append({
            "id": "scene_timeline",
            "stage": "build_scene_timeline",
            "command": ["python", "automation/build_scene_timeline.py", "--assets", str(assets),
                        "--image-manifest", str(manifest), "--subtitles", str(srt),
                        "--output", str(timeline)],
            "requires": ["confirm_srt_matches_final_narration_audio", "review_low_confidence_scene_matches"],
            "provider_call": False,
        })
    else:
        commands.append({
            "id": "scene_timeline",
            "stage": "build_scene_timeline",
            "command": None,
            "blocked_by": ["final narration SRT", "the same final narration audio", "executed image manifest"],
            "provider_call": False,
        })

    if timeline_ready and audio and srt:
        commands.append({
            "id": "timed_video_task",
            "stage": "prepare_timed_scene_video_task",
            "command": ["python", "automation/prepare_timed_scene_video_task.py",
                        "--timeline", str(timeline), "--image-root", str(images),
                        "--audio-file", str(audio), "--script-file", str(script),
                        "--aspect", aspect, "--output", str(output / f"{channel}_timed_video.jsonl")],
            "requires": ["approve_scene_timeline", "verify_audio_is_exact_srt_source"],
            "provider_call": False,
        })
    else:
        commands.append({
            "id": "timed_video_task",
            "stage": "prepare_timed_scene_video_task",
            "command": None,
            "blocked_by": ["approved scene_timeline.json", "final narration audio", "final script"],
            "provider_call": False,
        })

    commands.append({
        "id": "render_video",
        "stage": "moneyprinterturbo_cli",
        "command": ["python", "cli.py", "--batch-file", str(output / f"{channel}_timed_video.jsonl")],
        "requires": ["review task manifest", "confirm TTS/subtitle/music provider settings"],
        "provider_call": True,
    })
    commands.append({
        "id": "publishing_review",
        "stage": "prepare_youtube_publishing_package",
        "command": ["python", "automation/prepare_youtube_publishing_package.py",
                    "--channel", channel, "--assets", str(assets), "--video", str(video),
                    "--made-for-kids", "<review-and-set-yes-or-no>",
                    "--synthetic-media", "<review-and-set-yes-or-no>"],
        "requires": [
            "final video exists and has been watched end-to-end",
            "thumbnail, metadata, copyright, audience and synthetic-media declarations reviewed",
            "correct channel account confirmed",
        ],
        "upload_authorized": False,
    })

    for label, path in (("assets package", assets_file), ("image manifest", image_manifest),
                        ("subtitles", subtitles), ("audio file", audio_file),
                        ("scene timeline", timeline_file), ("final video", final_video)):
        if path:
            _exists(_path(path), label, errors)

    return {
        "schema_version": 1,
        "workflow_type": "youtube_channel_production_orchestration",
        "channel": channel,
        "subject": subject.strip(),
        "aspect": aspect,
        "output_dir": str(output),
        "status": "input_errors" if errors else "planned",
        "input_errors": errors,
        "commands": commands,
        "guardrails": {
            "channels_isolated": True,
            "provider_calls_opt_in": True,
            "human_review_required": True,
            "public_uploads_enabled": False,
            "upload_authorized": False,
            "scheduling_enabled": False,
        },
        "notes": [
            "This is a plan, not an execution record. Run commands individually after completing each checkpoint.",
            "The exact narration audio used to create the SRT must be passed to the timed scene task.",
            "The generated asset package is a creative/metadata brief; confirm it contains the YouTube metadata expected by the publishing-package step.",
            "No command in this plan uploads or schedules a video.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--aspect", choices=ASPECTS, default="9:16")
    parser.add_argument("--subtitles", type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--image-manifest", type=Path)
    parser.add_argument("--image-root", type=Path)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--thumbnail", type=Path)
    parser.add_argument("--output", type=Path, help="Workflow JSON output path")
    args = parser.parse_args()
    try:
        workflow = build_workflow(
            args.channel, args.subject, args.script, args.output_dir, aspect=args.aspect,
            subtitles=args.subtitles, audio_file=args.audio, assets_file=args.assets,
            image_manifest=args.image_manifest, image_root=args.image_root,
            timeline_file=args.timeline, final_video=args.video, thumbnail=args.thumbnail,
        )
        destination = args.output or args.output_dir / f"{args.channel}_workflow.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Workflow not created: {exc}", file=sys.stderr)
        return 2
    print(f"Workflow plan: {destination}")
    print(f"Channel: {args.channel}; status: {workflow['status']}")
    print(f"Stages: {len(workflow['commands'])}; provider calls are not executed by this planner.")
    print("Human review required; public upload and scheduling remain disabled.")
    return 0 if workflow["status"] == "planned" else 2


if __name__ == "__main__":
    raise SystemExit(main())
