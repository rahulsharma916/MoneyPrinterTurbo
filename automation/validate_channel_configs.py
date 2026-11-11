#!/usr/bin/env python3
"""Validate the independent channel configuration without publishing anything."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
EXPECTED_CHANNELS = {"devotional", "motivation"}
ASPECTS = {"9:16", "16:9", "1:1"}
PRIVACY = {"private", "unlisted", "public"}


def validate(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("version") != 1:
        return ["configuration must be an object with version: 1"]
    channels = data.get("channels")
    if not isinstance(channels, dict):
        return ["channels must be an object"]
    if set(channels) != EXPECTED_CHANNELS:
        errors.append("channels must contain exactly: devotional, motivation")

    for key in sorted(EXPECTED_CHANNELS & set(channels)):
        item = channels[key]
        if not isinstance(item, dict):
            errors.append(f"{key}: channel configuration must be an object")
            continue
        if item.get("content_profile") != key:
            errors.append(f"{key}: content_profile must match the channel key")
        if item.get("language") != "hi-IN":
            errors.append(f"{key}: language must be hi-IN for the current Hindi workflow")

        defaults = item.get("defaults")
        if not isinstance(defaults, dict):
            errors.append(f"{key}: defaults must be an object")
        else:
            if defaults.get("shorts_aspect") not in ASPECTS:
                errors.append(f"{key}: unsupported shorts_aspect")
            if defaults.get("long_form_aspect") not in ASPECTS:
                errors.append(f"{key}: unsupported long_form_aspect")
            for field in ("voice_rate", "voice_volume"):
                value = defaults.get(field)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    errors.append(f"{key}: {field} must be a non-negative number")

        creative = item.get("creative_direction")
        if not isinstance(creative, dict) or not all(
            isinstance(creative.get(field), str) and creative[field].strip()
            for field in ("visual_style", "thumbnail_direction", "music_direction")
        ):
            errors.append(f"{key}: visual, thumbnail and music directions are required")

        seo = item.get("seo")
        if not isinstance(seo, dict) or not isinstance(seo.get("hashtags"), list):
            errors.append(f"{key}: seo.hashtags must be a list")

        publishing = item.get("publishing")
        if not isinstance(publishing, dict):
            errors.append(f"{key}: publishing must be an object")
        else:
            if publishing.get("platform") != "youtube":
                errors.append(f"{key}: platform must be youtube")
            if publishing.get("upload_enabled") is not False:
                errors.append(f"{key}: uploads must remain disabled until explicitly configured")
            if publishing.get("approval_required") is not True:
                errors.append(f"{key}: human approval must remain required")
            if publishing.get("privacy_status") not in PRIVACY:
                errors.append(f"{key}: privacy_status must be private, unlisted or public")
            if publishing.get("made_for_kids") not in (True, False, None):
                errors.append(f"{key}: made_for_kids must be true, false or null (review required)")
            for field in ("upload_post_api_key_env", "upload_post_account_env"):
                env_name = publishing.get(field)
                if not isinstance(env_name, str) or not env_name.startswith("MPT_"):
                    errors.append(f"{key}: {field} must be an environment-variable name")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        data = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Error: cannot read channel configuration: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print("Valid: devotional and motivation channel configurations are separate.")
    print("Safety: publishing is disabled; human approval is required for both channels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
