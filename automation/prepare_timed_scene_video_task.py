#!/usr/bin/env python3
"""Prepare a narration-timed, local-video task from an approved scene timeline.

Each still is rendered to a clip whose duration ends at the next scene's narration
start. The final scene holds through the narration tail and a small render margin.
The normal MoneyPrinterTurbo CLI then concatenates these clips in scene order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_VIDEOS_DIR = REPOSITORY_ROOT / "storage" / "local_videos"
MAX_SCENES = 30
MAX_MANIFEST_BYTES = 1024 * 1024
TAIL_MARGIN_SECONDS = 3.0
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{(cleaned or 'timed-scenes')[:60]}-{digest}"


def _finite_seconds(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return number


def _load_approved_scenes(
    timeline_path: Path, image_root: Path, audio_duration: float
) -> tuple[dict[str, Any], list[tuple[int, Path, float]]]:
    timeline = _read_json(timeline_path, "scene timeline")
    scenes = timeline.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise ValueError(f"timeline must contain 1-{MAX_SCENES} scenes")
    if timeline.get("aligned_scene_count") != len(scenes):
        raise ValueError("all scenes must be aligned before timed rendering")
    root = image_root.resolve()
    starts: list[tuple[int, Path, float]] = []
    previous_start = -1.0
    for expected, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict) or scene.get("scene_number") != expected:
            raise ValueError("scene numbers must be consecutive and ordered from 1")
        if scene.get("aligned") is not True:
            raise ValueError(f"scene {expected} is not aligned; review the timeline first")
        start = _finite_seconds(scene.get("start_seconds"), f"scene {expected} start_seconds")
        if start <= previous_start:
            raise ValueError("scene start times must be strictly increasing")
        if start >= audio_duration:
            raise ValueError(f"scene {expected} starts after the narration ends")
        raw_image = scene.get("image_file")
        if not isinstance(raw_image, str) or not raw_image.strip():
            raise ValueError(f"scene {expected} has no image_file")
        image_path = Path(raw_image).resolve()
        try:
            image_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"scene {expected} image must be inside --image-root") from exc
        if not image_path.is_file():
            raise ValueError(f"scene {expected} image does not exist: {image_path}")
        starts.append((expected, image_path, start))
        previous_start = start

    # Scene 1 is held from t=0. Each later scene starts at its aligned narration
    # timestamp; the final still holds to the audio end plus a small safety margin.
    timed: list[tuple[int, Path, float]] = []
    for index, (number, image_path, start) in enumerate(starts):
        end = (
            starts[index + 1][2]
            if index + 1 < len(starts)
            else audio_duration + TAIL_MARGIN_SECONDS
        )
        effective_start = 0.0 if index == 0 else start
        duration = end - effective_start
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"scene {number} has an invalid playback duration")
        timed.append((number, image_path, duration))
    return timeline, timed


def prepare_timed_video_task(
    timeline_path: Path,
    image_root: Path,
    audio_path: Path,
    script_path: Path,
    *,
    aspect: str = "9:16",
    image_motion: str = "zoom",
    video_language: str = "hi-IN",
    local_videos_dir: Path = LOCAL_VIDEOS_DIR,
    output_manifest: Path | None = None,
) -> Path:
    if aspect not in {"9:16", "16:9", "1:1"}:
        raise ValueError("aspect must be one of 9:16, 16:9, or 1:1")
    if image_motion not in {"zoom", "static"}:
        raise ValueError("image-motion must be zoom or static")
    audio_path = audio_path.resolve()
    if not audio_path.is_file() or audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError("audio file must exist and use a supported audio extension")
    script = script_path.read_text(encoding="utf-8-sig").strip()
    if not script:
        raise ValueError("script file is empty")

    # Imports are delayed so validation-only users and unit tests do not load
    # MoviePy/FFmpeg until actual preparation is requested.
    from app.services import video, voice

    audio_duration = float(voice.get_audio_duration(str(audio_path)))
    if not math.isfinite(audio_duration) or audio_duration <= 0:
        raise ValueError("could not determine a valid narration audio duration")
    timeline, scenes = _load_approved_scenes(timeline_path, image_root, audio_duration)

    subject = str(timeline.get("subject") or "Untitled video").strip()
    channel = str(timeline.get("channel") or "unassigned").strip()
    folder_name = _safe_stem(f"{subject}-{channel}")
    work_dir = local_videos_dir / folder_name
    work_dir.mkdir(parents=True, exist_ok=True)

    audio_copy = work_dir / f"narration{audio_path.suffix.lower()}"
    if audio_path.resolve() != audio_copy.resolve():
        shutil.copy2(audio_path, audio_copy)

    material_entries = []
    durations = []
    for number, source_image, duration in scenes:
        image_copy = work_dir / f"scene_{number:03d}{source_image.suffix.lower()}"
        if source_image.resolve() != image_copy.resolve():
            shutil.copy2(source_image, image_copy)
        rendered = Path(video.render_image_zoom_video(
            str(image_copy), duration, image_motion=image_motion
        ))
        if not rendered.is_file():
            raise ValueError(f"scene {number} renderer did not create an MP4 clip")
        clip_name = f"timed_scene_{number:03d}.mp4"
        clip_copy = work_dir / clip_name
        if rendered.resolve() != clip_copy.resolve():
            shutil.copy2(rendered, clip_copy)
        material_entries.append({
            "provider": "local",
            "url": f"{folder_name}/{clip_name}",
            "duration": 0,
        })
        durations.append(duration)

    task = {
        "video_subject": subject,
        "video_script": script,
        "video_source": "local",
        "video_materials": material_entries,
        "custom_audio_file": f"{folder_name}/{audio_copy.name}",
        "voice_name": "no-voice",
        "video_language": video_language,
        "video_aspect": aspect,
        "video_concat_mode": "sequential",
        "video_clip_duration": math.ceil(max(durations)) + 1,
        "image_motion": "static",
        "video_fit_mode": "cover",
        "subtitle_enabled": True,
        "bgm_type": "",
        "bgm_volume": 0,
    }
    payload = json.dumps(task, ensure_ascii=False) + "\n"
    if len(payload.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("generated video task exceeds the CLI 1 MiB manifest limit")

    destination = output_manifest or (local_videos_dir / f"{folder_name}.timed.video.jsonl")
    try:
        if destination.resolve().parent != local_videos_dir.resolve():
            raise ValueError("output manifest must be directly inside storage/local_videos so relative inputs resolve safely")
    except (OSError, ValueError) as exc:
        raise ValueError("output manifest must be directly inside storage/local_videos so relative inputs resolve safely") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", required=True, type=Path, help="approved scene_timeline.json")
    parser.add_argument("--image-root", required=True, type=Path, help="directory containing the approved scene PNGs")
    parser.add_argument("--audio-file", required=True, type=Path, help="the exact narration audio used to create the SRT")
    parser.add_argument("--script-file", required=True, type=Path, help="complete narration script")
    parser.add_argument("--aspect", choices=("9:16", "16:9", "1:1"), default="9:16")
    parser.add_argument("--image-motion", choices=("zoom", "static"), default="zoom")
    parser.add_argument("--video-language", default="hi-IN")
    parser.add_argument("--output", type=Path, help="output JSONL manifest")
    args = parser.parse_args()
    try:
        output = prepare_timed_video_task(
            args.timeline, args.image_root, args.audio_file, args.script_file,
            aspect=args.aspect, image_motion=args.image_motion,
            video_language=args.video_language, output_manifest=args.output,
        )
        print(f"Prepared narration-timed video task: {output}")
        print("Next: python cli.py --batch-file " + str(output))
        print("The final scene is held through the narration tail; inspect the MP4 before publishing.")
        print("No upload or scheduling is performed by this preparation step.")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
