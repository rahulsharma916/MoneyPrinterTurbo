#!/usr/bin/env python3
"""Convert a UTF-8 CSV content calendar into a MoneyPrinterTurbo CLI batch manifest.

This utility only prepares and validates tasks. It does not generate videos or publish them.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

MAX_TASKS = 100
MAX_MANIFEST_BYTES = 1024 * 1024

STRING_FIELDS = {
    "video_subject", "video_script", "video_language", "voice_name",
    "bgm_type", "bgm_file", "video_script_prompt", "custom_system_prompt",
    "video_music_prompt", "sonilo_bgm_prompt", "subtitle_position",
    "font_name", "text_fore_color", "stroke_color", "video_source",
    "custom_audio_file", "video_fit_mode", "image_motion",
}
INTEGER_FIELDS = {
    "video_clip_duration", "video_count", "font_size", "paragraph_number",
    "n_threads",
}
FLOAT_FIELDS = {
    "video_clip_speed", "voice_volume", "voice_rate", "bgm_volume",
    "stroke_width", "custom_position",
}
BOOLEAN_FIELDS = {
    "match_materials_to_script", "subtitle_enabled", "rounded_subtitle_background",
}
JSON_FIELDS = {"text_background_color"}
LIST_FIELDS = {"video_terms"}
ALLOWED_FIELDS = (
    STRING_FIELDS | INTEGER_FIELDS | FLOAT_FIELDS | BOOLEAN_FIELDS
    | JSON_FIELDS | LIST_FIELDS
)
ASPECTS = {"9:16", "16:9", "1:1"}
FIT_MODES = {"cover", "contain"}
IMAGE_MOTIONS = {"static", "zoom"}
CONCAT_MODES = {"random", "sequential"}
TRANSITIONS = {"Shuffle", "FadeIn", "FadeOut", "SlideIn", "SlideOut", "ZoomIn", "ZoomOut", "none", ""}
ALLOWED_FIELDS |= {"video_aspect", "video_concat_mode", "video_transition_mode"}


def parse_bool(value: str, field: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"row {row_number}: {field} must be true/false, yes/no, or 1/0")


def parse_value(field: str, value: str, row_number: int) -> Any:
    value = value.strip()
    if field in INTEGER_FIELDS:
        try:
            result = int(value)
        except ValueError as exc:
            raise ValueError(f"row {row_number}: {field} must be an integer") from exc
        if field in {"video_clip_duration", "video_count", "font_size", "paragraph_number", "n_threads"} and result < 1:
            raise ValueError(f"row {row_number}: {field} must be at least 1")
        if field == "paragraph_number" and result > 10:
            raise ValueError(f"row {row_number}: paragraph_number must be at most 10")
        return result
    if field in FLOAT_FIELDS:
        try:
            result = float(value)
        except ValueError as exc:
            raise ValueError(f"row {row_number}: {field} must be a number") from exc
        if not (-1e12 < result < 1e12):
            raise ValueError(f"row {row_number}: {field} is outside the supported numeric range")
        if field in {"voice_volume", "voice_rate", "bgm_volume", "stroke_width"} and result < 0:
            raise ValueError(f"row {row_number}: {field} cannot be negative")
        if field == "custom_position" and not 0 <= result <= 100:
            raise ValueError(f"row {row_number}: custom_position must be between 0 and 100")
        return result
    if field in BOOLEAN_FIELDS:
        return parse_bool(value, field, row_number)
    if field in LIST_FIELDS:
        return [item.strip() for item in value.split(";") if item.strip()]
    if field in JSON_FIELDS:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"row {row_number}: {field} must contain valid JSON") from exc
        if not isinstance(parsed, (bool, str)):
            raise ValueError(f"row {row_number}: {field} must be a boolean or string")
        return parsed
    if field == "video_aspect" and value not in ASPECTS:
        raise ValueError(f"row {row_number}: video_aspect must be one of {sorted(ASPECTS)}")
    if field == "video_fit_mode" and value not in FIT_MODES:
        raise ValueError(f"row {row_number}: video_fit_mode must be one of {sorted(FIT_MODES)}")
    if field == "image_motion" and value not in IMAGE_MOTIONS:
        raise ValueError(f"row {row_number}: image_motion must be one of {sorted(IMAGE_MOTIONS)}")
    if field == "video_concat_mode" and value not in CONCAT_MODES:
        raise ValueError(f"row {row_number}: video_concat_mode must be one of {sorted(CONCAT_MODES)}")
    if field == "video_transition_mode" and value not in TRANSITIONS:
        raise ValueError(f"row {row_number}: unsupported video_transition_mode {value!r}")
    return value


def build_tasks(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        headers = [h.strip() for h in reader.fieldnames if h]
        unknown = sorted(set(headers) - ALLOWED_FIELDS)
        if unknown:
            raise ValueError("Unsupported CSV column(s): " + ", ".join(unknown))
        if len(headers) != len(set(headers)):
            raise ValueError("CSV contains duplicate column names")

        tasks: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, start=2):
            if not row or not any((value or "").strip() for value in row.values()):
                continue
            task: dict[str, Any] = {}
            for raw_field, raw_value in row.items():
                if raw_field is None:
                    continue
                field = raw_field.strip()
                value = (raw_value or "").strip()
                if not value:
                    continue
                task[field] = parse_value(field, value, row_number)
            if not task.get("video_subject") and not task.get("video_script"):
                raise ValueError(f"row {row_number}: provide video_subject or video_script")
            tasks.append(task)
            if len(tasks) > MAX_TASKS:
                raise ValueError(f"CSV exceeds the {MAX_TASKS}-task CLI batch limit")
    if not tasks:
        raise ValueError("CSV contains no video tasks")
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="Content calendar CSV")
    parser.add_argument("-o", "--output", type=Path, help="Output manifest path (default: <csv-name>.jsonl)")
    parser.add_argument("--format", choices=("jsonl", "json"), default="jsonl")
    parser.add_argument("--check", action="store_true", help="Validate only; do not write a manifest")
    args = parser.parse_args()

    try:
        tasks = build_tasks(args.csv_file)
        if args.format == "jsonl":
            payload = "".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks)
        else:
            payload = json.dumps(tasks, ensure_ascii=False, indent=2) + "\n"
        size = len(payload.encode("utf-8"))
        if size > MAX_MANIFEST_BYTES:
            raise ValueError(f"Generated manifest is {size} bytes; CLI limit is {MAX_MANIFEST_BYTES} bytes")
        if args.check:
            print(f"Valid: {len(tasks)} task(s), {size} bytes")
            return 0
        output = args.output or args.csv_file.with_suffix(".jsonl" if args.format == "jsonl" else ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"Created {output} ({len(tasks)} task(s), {size} bytes)")
        print("Generate videos with: python cli.py --batch-file " + str(output))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
