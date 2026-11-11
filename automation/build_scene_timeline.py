#!/usr/bin/env python3
"""Align generated scene excerpts to subtitle timestamps and write a scene timeline.

This creates a reviewable timing plan; it does not modify or render a video.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

MAX_SCENES = 30
SRT_BLOCK_RE = re.compile(
    r"(?m)^\s*(?:\d+\s*\n)?"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


def _seconds(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[^\W_]+", value, flags=re.UNICODE)]


def parse_srt(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read subtitle file: {exc}") from exc
    cues = []
    for match in SRT_BLOCK_RE.finditer(raw):
        text = " ".join(line.strip() for line in match.group(3).splitlines() if line.strip())
        words = _tokens(text)
        if not words:
            continue
        start, end = _seconds(match.group(1)), _seconds(match.group(2))
        if end <= start:
            raise ValueError("subtitle cue end must be after its start")
        cues.append({"start": start, "end": end, "text": text, "words": words})
    if not cues:
        raise ValueError("subtitle file contains no readable SRT cues")
    return cues


def _flatten_cues(cues: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    words: list[str] = []
    cue_indices: list[int] = []
    for cue_index, cue in enumerate(cues):
        words.extend(cue["words"])
        cue_indices.extend([cue_index] * len(cue["words"]))
    return words, cue_indices


def _best_match(
    target: list[str],
    transcript: list[str],
    cursor: int,
) -> tuple[int, int, float] | None:
    if not target:
        return None
    expected = len(target)
    low = max(1, int(expected * 0.65))
    high = max(low, int(expected * 1.4) + 2)
    best: tuple[int, int, float] | None = None
    # Keep matches monotonic: a later scene can never be assigned before an earlier one.
    for start in range(cursor, len(transcript)):
        for length in range(low, high + 1):
            end = start + length
            if end > len(transcript):
                continue
            score = difflib.SequenceMatcher(
                None, target, transcript[start:end], autojunk=False
            ).ratio()
            candidate = (start, end, score)
            if best is None or score > best[2] or (
                score == best[2] and start < best[0]
            ):
                best = candidate
            if score == 1.0:
                return candidate
    return best


def build_timeline(
    assets_path: Path,
    image_manifest_path: Path,
    subtitle_path: Path,
    *,
    min_score: float = 0.55,
) -> dict[str, Any]:
    if not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score must be between 0 and 1")
    try:
        assets = json.loads(assets_path.read_text(encoding="utf-8-sig"))
        image_manifest = json.loads(image_manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read scene or image manifest JSON: {exc}") from exc
    if not isinstance(assets, dict) or not isinstance(image_manifest, dict):
        raise ValueError("scene assets and image manifest must be JSON objects")
    scenes = assets.get("scenes")
    images = image_manifest.get("images")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise ValueError(f"asset package scenes must contain 1-{MAX_SCENES} entries")
    if image_manifest.get("execution") != "executed" or not isinstance(images, list):
        raise ValueError("an executed image manifest with an images list is required")

    image_by_number: dict[int, Path] = {}
    for item in images:
        if not isinstance(item, dict) or item.get("kind") != "scene":
            continue
        number = item.get("scene_number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ValueError("scene image entries require a positive integer scene_number")
        if item.get("status") not in {"generated", "skipped_existing"}:
            continue
        raw_file = item.get("file")
        if not isinstance(raw_file, str) or not raw_file.strip():
            continue
        candidate = Path(raw_file)
        if not candidate.is_absolute():
            candidate = image_manifest_path.parent / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(image_manifest_path.parent.resolve())
        except ValueError as exc:
            raise ValueError(f"scene image {number} is outside the image-manifest directory") from exc
        if not resolved.is_file():
            raise ValueError(f"scene image {number} does not exist: {resolved}")
        if number in image_by_number:
            raise ValueError(f"duplicate scene image number: {number}")
        image_by_number[number] = resolved

    cues = parse_srt(subtitle_path)
    transcript, cue_indices = _flatten_cues(cues)
    cursor = 0
    timeline = []
    for expected_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {expected_number} must be an object")
        number = scene.get("scene_number")
        if number != expected_number:
            raise ValueError("scene numbers must be consecutive and ordered starting at 1")
        excerpt = scene.get("narration_excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError(f"scene {number} has no narration_excerpt")
        image = image_by_number.get(number)
        if image is None:
            raise ValueError(f"no successfully rendered image found for scene {number}")
        match = _best_match(_tokens(excerpt), transcript, cursor)
        aligned = bool(match and match[2] >= min_score)
        if aligned:
            start_word, end_word, score = match
            first_cue = cues[cue_indices[start_word]]
            last_cue = cues[cue_indices[end_word - 1]]
            start_time, end_time = first_cue["start"], last_cue["end"]
            cursor = end_word
        else:
            score = match[2] if match else 0.0
            start_time = end_time = None
        timeline.append({
            "scene_number": number,
            "image_file": str(image),
            "narration_excerpt": excerpt,
            "aligned": aligned,
            "match_score": round(score, 4),
            "start_seconds": round(start_time, 3) if start_time is not None else None,
            "end_seconds": round(end_time, 3) if end_time is not None else None,
            "duration_seconds": round(end_time - start_time, 3) if aligned else None,
        })
    return {
        "channel": assets.get("channel", ""),
        "subject": assets.get("subject", ""),
        "subtitle_file": str(subtitle_path.resolve()),
        "alignment_method": "monotonic fuzzy token matching against SRT cue text",
        "minimum_match_score": min_score,
        "aligned_scene_count": sum(item["aligned"] for item in timeline),
        "scene_count": len(timeline),
        "scenes": timeline,
        "review_note": (
            "Approximate text alignment. Inspect every scene boundary, especially where "
            "speech recognition differs from the supplied script. This timeline is not "
            "automatically consumed by the video renderer."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--image-manifest", required=True, type=Path)
    parser.add_argument("--subtitles", required=True, type=Path, help="SRT generated from the final narration audio")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-score", type=float, default=0.55)
    args = parser.parse_args()
    try:
        timeline = build_timeline(
            args.assets, args.image_manifest, args.subtitles, min_score=args.min_score
        )
        output = args.output or args.image_manifest.with_name("scene_timeline.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Created {output}: {timeline['aligned_scene_count']}/{timeline['scene_count']} scenes aligned")
        print("Review scene_timeline.json before using timings; this utility does not render or alter a video.")
        return 0 if timeline["aligned_scene_count"] == timeline["scene_count"] else 1
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
