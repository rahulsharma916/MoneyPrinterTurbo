#!/usr/bin/env python3
"""Resolve one channel's Upload-Post credentials from environment variables.

Secrets are never written to files or printed. This validates local configuration
only; it does not contact Upload-Post or publish content.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping, Any

DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")


def load_channel_account(
    channel: str,
    *,
    config_path: Path = DEFAULT_CONFIG,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read channel configuration: {exc}") from exc
    channels = config.get("channels") if isinstance(config, dict) else None
    profile = channels.get(channel) if isinstance(channels, dict) else None
    if not isinstance(profile, dict) or profile.get("content_profile") != channel:
        raise ValueError(f"unknown or invalid channel: {channel}")
    publishing = profile.get("publishing")
    if not isinstance(publishing, dict):
        raise ValueError(f"{channel}: publishing configuration is missing")
    if publishing.get("upload_enabled") is not False:
        raise ValueError(f"{channel}: channel uploads must remain disabled during credential setup")
    key_name = publishing.get("upload_post_api_key_env")
    username_name = publishing.get("upload_post_account_env")
    for field, name in (("API key", key_name), ("account username", username_name)):
        if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
            raise ValueError(f"{channel}: invalid environment-variable name for {field}")
    if key_name == username_name:
        raise ValueError(f"{channel}: API key and username must use separate environment variables")
    source = os.environ if environ is None else environ
    api_key = source.get(key_name, "").strip()
    username = source.get(username_name, "").strip()
    missing = []
    if not api_key:
        missing.append(key_name)
    if not username:
        missing.append(username_name)
    if missing:
        raise ValueError(f"{channel}: missing required environment variable(s): {', '.join(missing)}")
    return {
        "upload_post_enabled": True,
        "upload_post_api_key": api_key,
        "upload_post_username": username,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=("devotional", "motivation"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        account = load_channel_account(args.channel, config_path=args.config)
    except ValueError as exc:
        print(f"Not ready: {exc}", file=sys.stderr)
        return 2
    # Intentionally report only readiness. Never print or serialize credentials.
    print(f"Ready: {args.channel} Upload-Post credentials are present in the environment.")
    print(f"Account username configured: {'yes' if bool(account['upload_post_username']) else 'no'}")
    print("Network verification: not performed. Uploads remain disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
