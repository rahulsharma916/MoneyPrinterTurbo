#!/usr/bin/env python3
"""Apply a reusable Hindi channel content profile to every row in a CSV calendar.

The utility enriches video_script_prompt while preserving existing columns and
user-written prompt text. It does not call an AI provider or publish content.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DEFAULT_PROFILES = Path(__file__).with_name("content_profiles.json")


def load_profile(profile_file: Path, profile_name: str) -> dict[str, str]:
    try:
        data = json.loads(profile_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read profile file: {exc}") from exc
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict) or profile_name not in profiles:
        choices = ", ".join(sorted(profiles)) if isinstance(profiles, dict) else "none"
        raise ValueError(f"unknown profile {profile_name!r}; available profiles: {choices}")
    profile = profiles[profile_name]
    if not isinstance(profile, dict) or not isinstance(profile.get("prompt"), str):
        raise ValueError(f"profile {profile_name!r} has no valid prompt")
    return profile


def apply_profile(source: Path, destination: Path, profile: dict[str, str]) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        fields = list(reader.fieldnames)
        if "video_script_prompt" not in fields:
            fields.append("video_script_prompt")
        rows = list(reader)

    if not rows:
        raise ValueError("CSV contains no data rows")

    prompt = profile["prompt"].strip()
    for row in rows:
        existing = (row.get("video_script_prompt") or "").strip()
        if prompt not in existing:
            row["video_script_prompt"] = f"{existing}\n\n{prompt}".strip()

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="Input content calendar CSV")
    parser.add_argument("--profile", required=True, help="devotional, mythology, motivation, or shayari")
    parser.add_argument("-o", "--output", type=Path, help="Output CSV path")
    parser.add_argument("--profiles-file", type=Path, default=DEFAULT_PROFILES)
    args = parser.parse_args()
    try:
        profile = load_profile(args.profiles_file, args.profile)
        output = args.output or args.csv_file.with_name(
            f"{args.csv_file.stem}.{args.profile}.csv"
        )
        count = apply_profile(args.csv_file, output, profile)
        print(f"Applied {args.profile!r} profile to {count} row(s): {output}")
        print("Next: run content_calendar_to_batch.py on this enriched CSV.")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
