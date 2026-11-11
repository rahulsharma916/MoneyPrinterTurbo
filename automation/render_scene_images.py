#!/usr/bin/env python3
"""Render selected scene and thumbnail prompts from a Phase 5 asset JSON package.

Image generation is opt-in via --execute. Calls are sequential and bounded.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, UnidentifiedImageError

from app.services import codex_image

MAX_PACKAGE_BYTES = 2 * 1024 * 1024
MAX_PROMPT_CHARS = 8000
MAX_SCENE_IMAGES = 12


def load_package(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("asset package exceeds the 2 MiB safety limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read asset package: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("asset package must be a JSON object")
    scenes = data.get("scenes")
    thumbnail = data.get("thumbnail")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 30:
        raise ValueError("asset package must contain 1-30 scenes")
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {index} must be an object")
        prompt = scene.get("image_prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"scene {index} has a missing or oversized image_prompt")
    if not isinstance(thumbnail, dict):
        raise ValueError("asset package is missing thumbnail")
    prompt = thumbnail.get("image_prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("thumbnail has a missing or oversized image_prompt")
    return data


def save_png(image_bytes: bytes, destination: Path) -> tuple[int, int]:
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("image provider returned no image bytes")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temp_path.write_bytes(image_bytes)
        with Image.open(temp_path) as image:
            image.verify()
        with Image.open(temp_path) as image:
            if image.format != "PNG":
                raise ValueError("image provider returned a non-PNG image")
            dimensions = image.size
        temp_path.replace(destination)
        return dimensions
    except (OSError, UnidentifiedImageError) as exc:
        temp_path.unlink(missing_ok=True)
        raise ValueError("generated image could not be validated as PNG") from exc
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def render_package(
    package: dict[str, Any],
    output_dir: Path,
    *,
    max_scene_images: int,
    include_thumbnail: bool,
    execute: bool,
) -> dict[str, Any]:
    scenes = package["scenes"][:max_scene_images]
    jobs = [
        (f"scene_{index:03d}.png", scene["image_prompt"], "scene", index)
        for index, scene in enumerate(scenes, 1)
    ]
    if include_thumbnail:
        jobs.append(("thumbnail.png", package["thumbnail"]["image_prompt"], "thumbnail", None))

    manifest: dict[str, Any] = {
        "channel": package.get("channel", ""),
        "subject": package.get("subject", ""),
        "execution": "executed" if execute else "dry_run",
        "images": [],
    }
    context = codex_image.capture_context() if execute else None
    for filename, prompt, kind, scene_number in jobs:
        destination = output_dir / filename
        entry = {"file": str(destination), "kind": kind, "scene_number": scene_number}
        if destination.exists():
            entry["status"] = "skipped_existing"
        elif not execute:
            entry["status"] = "planned"
            entry["prompt_preview"] = prompt[:240]
        else:
            # One request at a time; do not retry ambiguous image calls.
            try:
                image_bytes = codex_image.generate_image(prompt, context)
                width, height = save_png(image_bytes, destination)
                entry.update({"status": "generated", "width": width, "height": height})
            except codex_image.CodexImageError as exc:
                entry.update({"status": "failed", "error": str(exc)})
                manifest["images"].append(entry)
                break  # Do not retry an ambiguous or potentially billable image request.
        manifest["images"].append(entry)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_package", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-scene-images", type=int, default=3)
    parser.add_argument("--include-thumbnail", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Actually call the configured Codex image provider")
    args = parser.parse_args()
    try:
        if not 1 <= args.max_scene_images <= MAX_SCENE_IMAGES:
            raise ValueError(f"--max-scene-images must be between 1 and {MAX_SCENE_IMAGES}")
        package = load_package(args.asset_package)
        channel = package.get("channel") or "unassigned"
        output_dir = args.output_dir or args.asset_package.parent / f"{args.asset_package.stem}.images"
        if args.execute:
            # Validate authorization and model configuration before starting any image jobs.
            codex_image.capture_context()
        manifest = render_package(
            package,
            output_dir,
            max_scene_images=args.max_scene_images,
            include_thumbnail=args.include_thumbnail,
            execute=args.execute,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "image_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generated = sum(item["status"] == "generated" for item in manifest["images"])
        planned = sum(item["status"] == "planned" for item in manifest["images"])
        skipped = sum(item["status"] == "skipped_existing" for item in manifest["images"])
        print(f"Channel: {channel}; generated: {generated}; planned: {planned}; skipped: {skipped}")
        print(f"Manifest: {manifest_path}")
        if not args.execute:
            print("Dry run only. Add --execute to call the configured image provider.")
        if any(item["status"] == "failed" for item in manifest["images"]):
            print("Rendering stopped after a provider error; inspect the manifest before retrying.", file=sys.stderr)
            return 2
        return 0
    except (OSError, UnicodeError, ValueError, codex_image.CodexImageError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
