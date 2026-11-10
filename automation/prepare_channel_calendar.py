#!/usr/bin/env python3
"""Apply a channel production defaults to a CSV calendar.

Prepares an enriched CSV for the existing batch-manifest tool. It does not
generate videos, thumbnails, SEO metadata, or publish content.
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
from typing import Any
DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
ASPECTS = {"9:16", "16:9", "1:1"}

def load_channel(config_path: Path, channel: str) -> dict[str, Any]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read channel configuration: {exc}") from exc
    channels = data.get("channels") if isinstance(data, dict) else None
    if not isinstance(channels, dict) or channel not in channels:
        raise ValueError(f"unknown channel {channel!r}; expected devotional or motivation")
    profile = channels[channel]
    if not isinstance(profile, dict) or profile.get("content_profile") != channel:
        raise ValueError(f"{channel}: invalid or mismatched content_profile")
    if not isinstance(profile.get("defaults"), dict) or not isinstance(profile.get("creative_direction"), dict):
        raise ValueError(f"{channel}: defaults and creative_direction are required")
    for key in ("visual_style", "thumbnail_direction", "music_direction"):
        if not isinstance(profile["creative_direction"].get(key), str) or not profile["creative_direction"][key].strip():
            raise ValueError(f"{channel}: creative_direction.{key} is required")
    return profile

def set_default(row: dict[str, str], field: str, value: Any) -> None:
    if value is None or (row.get(field) or "").strip():
        return
    row[field] = ("true" if value else "false") if isinstance(value, bool) else str(value)

def prepare_calendar(source: Path, destination: Path, channel: str, profile: dict[str, Any]) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        fields, rows = list(reader.fieldnames), list(reader)
    if not rows:
        raise ValueError("CSV contains no data rows")
    defaults = profile["defaults"]
    for row in rows:
        for field in ("video_language", "voice_name", "voice_rate", "voice_volume", "subtitle_enabled"):
            set_default(row, field, defaults.get(field))
        aspect = (row.get("video_aspect") or "").strip()
        if not aspect:
            set_default(row, "video_aspect", defaults.get("shorts_aspect", "9:16"))
        elif aspect not in ASPECTS:
            raise ValueError(f"unsupported video_aspect {aspect!r}; use {sorted(ASPECTS)}")
        existing = (row.get("custom_system_prompt") or "").strip()
        brief = (f"CHANNEL PRODUCTION CONTEXT ({channel.upper()}): "
                 f"{profile['creative_direction']['visual_style']}. "
                 "Write narration with concrete, scene-friendly details and a clear visual progression. "
                 "Do not invent facts, quotations, or attributions.")
        if brief not in existing:
            row["custom_system_prompt"] = f"{existing}\n\n{brief}".strip()
    for field in ("video_language", "voice_name", "voice_rate", "voice_volume", "subtitle_enabled", "video_aspect", "custom_system_prompt"):
        if field not in fields:
            fields.append(field)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    return len(rows)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--channel", required=True, choices=("devotional", "motivation"))
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        profile = load_channel(args.config, args.channel)
        output = args.output or args.csv_file.with_name(f"{args.csv_file.stem}.production.csv")
        count = prepare_calendar(args.csv_file, output, args.channel, profile)
        print(f"Prepared {count} {args.channel} task(s): {output}")
        print("Next: run content_calendar_to_batch.py on this prepared CSV.")
        print("This step does not generate or publish videos.")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 2

if __name__ == "__main__":
    raise SystemExit(main())