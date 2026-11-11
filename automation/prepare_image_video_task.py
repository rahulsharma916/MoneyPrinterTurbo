#!/usr/bin/env python3
"""Prepare a local-image MoneyPrinterTurbo task from a rendered scene manifest.

Copies approved scene PNGs into storage/local_videos and writes a one-task JSONL
manifest. It prepares inputs only; the normal CLI still performs video rendering.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SCENE_IMAGES = 12
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_VIDEOS_DIR = REPOSITORY_ROOT / "storage" / "local_videos"


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return (stem or "scene-video")[:80]


def collect_scene_images(image_manifest_path: Path) -> list[tuple[int, Path]]:
    manifest = _read_json(image_manifest_path, "image manifest")
    if manifest.get("execution") != "executed":
        raise ValueError("image manifest must come from an executed image-rendering run")
    entries = manifest.get("images")
    if not isinstance(entries, list):
        raise ValueError("image manifest images must be a list")

    scenes: list[tuple[int, Path]] = []
    seen: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") != "scene":
            continue
        number = entry.get("scene_number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ValueError("each scene image must have a positive integer scene_number")
        if number in seen:
            raise ValueError(f"duplicate scene_number in image manifest: {number}")
        seen.add(number)
        if entry.get("status") not in {"generated", "skipped_existing"}:
            continue
        raw_path = entry.get("file")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"scene {number} has no image file path")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = image_manifest_path.parent / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(image_manifest_path.parent.resolve())
        except ValueError as exc:
            raise ValueError(f"scene {number} image must be inside the image-manifest directory") from exc
        if not resolved.is_file():
            raise ValueError(f"scene {number} image does not exist: {resolved}")
        scenes.append((number, resolved))

    scenes.sort(key=lambda item: item[0])
    if not scenes:
        raise ValueError("no successfully generated scene images were found")
    if len(scenes) > MAX_SCENE_IMAGES:
        raise ValueError(f"image manifest contains more than {MAX_SCENE_IMAGES} scene images")
    return scenes


def prepare_video_task(
    asset_package_path: Path,
    image_manifest_path: Path,
    script_path: Path,
    *,
    aspect: str = "9:16",
    clip_duration: int = 5,
    output_manifest: Path | None = None,
    local_videos_dir: Path = LOCAL_VIDEOS_DIR,
) -> Path:
    if aspect not in {"9:16", "16:9", "1:1"}:
        raise ValueError("aspect must be one of 9:16, 16:9, or 1:1")
    if not isinstance(clip_duration, int) or isinstance(clip_duration, bool) or not 1 <= clip_duration <= 60:
        raise ValueError("clip_duration must be an integer between 1 and 60 seconds")

    assets = _read_json(asset_package_path, "asset package")
    subject = assets.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("asset package subject is required")
    script = script_path.read_text(encoding="utf-8-sig").strip()
    if not script:
        raise ValueError("script file is empty")

    scenes = collect_scene_images(image_manifest_path)
    channel = str(assets.get("channel") or "unassigned")
    folder_name = _safe_stem(f"{asset_package_path.stem}-{channel}")
    image_folder = local_videos_dir / folder_name
    image_folder.mkdir(parents=True, exist_ok=True)

    material_entries = []
    for number, source in scenes:
        filename = f"scene_{number:03d}{source.suffix.lower()}"
        destination = image_folder / filename
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        material_entries.append({
            "provider": "local",
            "url": f"{folder_name}/{filename}",
            "duration": 0,
        })

    task = {
        "video_subject": subject.strip(),
        "video_script": script,
        "video_source": "local",
        "video_materials": material_entries,
        "video_aspect": aspect,
        "video_concat_mode": "sequential",
        "image_motion": "zoom",
        "video_clip_duration": clip_duration,
        "video_fit_mode": "cover",
        "subtitle_enabled": True,
    }
    payload = json.dumps(task, ensure_ascii=False) + "\n"
    if len(payload.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("generated video task exceeds the CLI 1 MiB manifest limit")

    destination = output_manifest or (local_videos_dir / f"{folder_name}.video.jsonl")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, type=Path, help="Phase 5 scene/SEO asset JSON")
    parser.add_argument("--image-manifest", required=True, type=Path, help="Executed render_scene_images image_manifest.json")
    parser.add_argument("--script-file", required=True, type=Path, help="Original narration script")
    parser.add_argument("--aspect", choices=("9:16", "16:9", "1:1"), default="9:16")
    parser.add_argument("--clip-duration", type=int, default=5, help="Seconds per still-image clip (1-60)")
    parser.add_argument("--output", type=Path, help="Output JSONL path (default: storage/local_videos/<package>.video.jsonl)")
    args = parser.parse_args()
    try:
        output = prepare_video_task(
            args.assets, args.image_manifest, args.script_file,
            aspect=args.aspect, clip_duration=args.clip_duration,
            output_manifest=args.output,
        )
        print(f"Prepared local-image video task: {output}")
        print("Next: python cli.py --batch-file " + str(output))
        print("Images are ordered by scene number; the existing engine applies slow zoom and subtitles.")
        print("Review the rendered video before publishing. This step does not upload or schedule.")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
