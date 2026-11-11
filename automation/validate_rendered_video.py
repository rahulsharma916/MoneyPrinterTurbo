#!/usr/bin/env python3
"""Validate a rendered MP4's streams, dimensions, and duration against its narration."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_REPORT_BYTES = 256 * 1024


def probe_media(path: Path, ffprobe: str = "ffprobe") -> dict[str, Any]:
    executable = shutil.which(ffprobe)
    if not executable:
        raise ValueError(f"ffprobe executable not found: {ffprobe}")
    if not path.is_file():
        raise ValueError(f"media file does not exist: {path}")
    command = [
        executable,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height,duration",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=60
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ValueError(f"ffprobe failed for {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"ffprobe returned invalid metadata for {path}")
    return payload


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def evaluate_video_metadata(
    video_metadata: dict[str, Any],
    audio_metadata: dict[str, Any],
    *,
    expected_aspect: str,
    min_duration: float,
    max_duration: float,
    aspect_tolerance: float = 0.02,
) -> dict[str, Any]:
    if expected_aspect not in {"9:16", "16:9", "1:1"}:
        raise ValueError("expected_aspect must be 9:16, 16:9, or 1:1")
    video_streams = [
        item for item in video_metadata.get("streams", [])
        if isinstance(item, dict) and item.get("codec_type") == "video"
    ]
    audio_streams = [
        item for item in video_metadata.get("streams", [])
        if isinstance(item, dict) and item.get("codec_type") == "audio"
    ]
    if not video_streams:
        raise ValueError("rendered file has no video stream")
    if not audio_streams:
        raise ValueError("rendered file has no audio stream")

    stream = video_streams[0]
    width = stream.get("width")
    height = stream.get("height")
    if (
        isinstance(width, bool) or not isinstance(width, int) or width <= 0
        or isinstance(height, bool) or not isinstance(height, int) or height <= 0
    ):
        raise ValueError("rendered video has invalid frame dimensions")
    actual_aspect = width / height
    expected_width, expected_height = map(int, expected_aspect.split(":"))
    target_aspect = expected_width / expected_height
    aspect_error = abs(actual_aspect - target_aspect) / target_aspect
    if aspect_error > aspect_tolerance:
        raise ValueError(
            f"aspect mismatch: expected {expected_aspect}, got {width}x{height}"
        )

    format_data = video_metadata.get("format")
    if not isinstance(format_data, dict):
        raise ValueError("rendered file has no container format metadata")
    video_duration = _positive_number(format_data.get("duration"), "video duration")
    audio_format = audio_metadata.get("format")
    if not isinstance(audio_format, dict):
        raise ValueError("narration file has no container format metadata")
    audio_duration = _positive_number(audio_format.get("duration"), "narration duration")

    if video_duration < min_duration:
        raise ValueError(
            f"video is shorter than narration tolerance: {video_duration:.2f}s "
            f"(minimum {min_duration:.2f}s)"
        )
    if video_duration > max_duration:
        raise ValueError(
            f"video exceeds narration duration limit: {video_duration:.2f}s "
            f"(maximum {max_duration:.2f}s)"
        )

    return {
        "status": "passed",
        "video_duration_seconds": round(video_duration, 3),
        "narration_duration_seconds": round(audio_duration, 3),
        "duration_delta_seconds": round(video_duration - audio_duration, 3),
        "width": width,
        "height": height,
        "actual_aspect": round(actual_aspect, 6),
        "expected_aspect": expected_aspect,
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "checks": {
            "video_stream": "passed",
            "audio_stream": "passed",
            "aspect_ratio": "passed",
            "duration_window": "passed",
        },
        "limitations": [
            "This checks container metadata and stream presence, not visual correctness, narration synchronization, or audible quality.",
            "It cannot verify whether subtitles are burned into the picture.",
        ],
    }


def validate_video(
    video_path: Path,
    audio_path: Path,
    *,
    expected_aspect: str = "9:16",
    min_audio_coverage: float = 0.995,
    max_extra_seconds: float = 8.0,
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    if not 0 <= min_audio_coverage <= 1:
        raise ValueError("min_audio_coverage must be between 0 and 1")
    if not math.isfinite(max_extra_seconds) or max_extra_seconds < 0:
        raise ValueError("max_extra_seconds must be finite and non-negative")
    video_metadata = probe_media(video_path, ffprobe)
    audio_metadata = probe_media(audio_path, ffprobe)
    audio_format = audio_metadata.get("format")
    if not isinstance(audio_format, dict):
        raise ValueError("narration file has no container format metadata")
    audio_duration = _positive_number(audio_format.get("duration"), "narration duration")
    min_duration = audio_duration * min_audio_coverage
    max_duration = audio_duration + max_extra_seconds
    report = evaluate_video_metadata(
        video_metadata,
        audio_metadata,
        expected_aspect=expected_aspect,
        min_duration=min_duration,
        max_duration=max_duration,
    )
    report["video_file"] = str(video_path)
    report["narration_file"] = str(audio_path)
    report["duration_policy"] = {
        "minimum_audio_coverage": min_audio_coverage,
        "maximum_extra_seconds": max_extra_seconds,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-file", required=True, type=Path)
    parser.add_argument("--audio-file", required=True, type=Path)
    parser.add_argument("--aspect", choices=("9:16", "16:9", "1:1"), default="9:16")
    parser.add_argument("--min-audio-coverage", type=float, default=0.995)
    parser.add_argument("--max-extra-seconds", type=float, default=8.0)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--report", type=Path, help="optional JSON report destination")
    args = parser.parse_args()
    try:
        report = validate_video(
            args.video_file,
            args.audio_file,
            expected_aspect=args.aspect,
            min_audio_coverage=args.min_audio_coverage,
            max_extra_seconds=args.max_extra_seconds,
            ffprobe=args.ffprobe,
        )
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if len(serialized.encode("utf-8")) > MAX_REPORT_BYTES:
            raise ValueError("quality report exceeds the 256 KiB limit")
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(serialized, encoding="utf-8")
        print(serialized, end="")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Quality gate failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
