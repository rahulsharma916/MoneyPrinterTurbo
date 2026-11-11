#!/usr/bin/env python3
"""Generate a channel-aware scene and YouTube publishing brief from a script.

This creates structured prompts and metadata only. It does not render images,
create thumbnails, generate video, or publish to YouTube.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.services.llm import _generate_response, _strip_code_fence

DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
MAX_SUBJECT_CHARS = 500
MAX_SCRIPT_CHARS = 12000
MAX_SCENES = 30


def load_channel(config_path: Path, channel: str) -> dict[str, Any]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read channel configuration: {exc}") from exc
    channels = data.get("channels") if isinstance(data, dict) else None
    profile = channels.get(channel) if isinstance(channels, dict) else None
    if not isinstance(profile, dict) or profile.get("content_profile") != channel:
        raise ValueError(f"unknown or invalid channel {channel!r}")
    creative = profile.get("creative_direction")
    seo = profile.get("seo")
    if not isinstance(creative, dict) or not isinstance(seo, dict):
        raise ValueError(f"{channel}: creative_direction and seo configuration are required")
    for key in ("visual_style", "thumbnail_direction", "music_direction"):
        if not isinstance(creative.get(key), str) or not creative[key].strip():
            raise ValueError(f"{channel}: creative_direction.{key} is required")
    return profile


def build_prompt(subject: str, script: str, channel: str, profile: dict[str, Any]) -> str:
    creative = profile["creative_direction"]
    seo = profile["seo"]
    language = str(seo.get("title_language") or "Hindi")
    hashtags = seo.get("hashtags", [])
    if not isinstance(hashtags, list) or not all(isinstance(tag, str) for tag in hashtags):
        raise ValueError("channel SEO hashtags must be a list of strings")
    return f"""You are a YouTube story producer and metadata strategist.
Return exactly one valid JSON object. Do not use markdown fences or commentary.

CHANNEL: {channel}
CONTENT SUBJECT: {subject}
OUTPUT LANGUAGE: {language}
VISUAL STYLE: {creative["visual_style"]}
THUMBNAIL DIRECTION: {creative["thumbnail_direction"]}
CHANNEL HASHTAG SEEDS: {json.dumps(hashtags, ensure_ascii=False)}

SOURCE SCRIPT:
{script}

Create this exact JSON structure:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "narration_excerpt": "short exact excerpt from the supplied script",
      "visual_description": "specific scene composition, setting, subject, action, lighting and camera framing",
      "image_prompt": "detailed standalone image-generation prompt; no text, captions, logos or watermark",
      "stock_search_terms": ["2-4 concise English search phrases"],
      "motion_direction": "subtle camera or subject movement suitable for a video scene"
    }}
  ],
  "thumbnail": {{
    "headline_hindi": "short readable Hindi headline, ideally 2-5 words",
    "concept": "one clear focal idea and composition",
    "image_prompt": "standalone 16:9 thumbnail image prompt; reserve clean negative space for separately typeset headline; no generated text, logos or watermark"
  }},
  "youtube": {{
    "title": "compelling accurate title in the output language, no false claims",
    "description": "useful description with opening hook, concise summary, natural keywords and a clear subscribe/comment CTA",
    "tags": ["relevant YouTube search tags without #"],
    "hashtags": ["relevant hashtags beginning with #"]
  }}
}}

Rules:
- Create 5 to 12 chronological scenes for a short script; use more for a long script, never exceed {MAX_SCENES}.
- Scene narration excerpts must be grounded in the supplied script and follow its order.
- Visuals must match each scene, not generic filler. Preserve cultural and religious respect for devotional content.
- Do not invent scripture quotations, historical facts, character details, or attributions.
- Motivational visuals should be grounded and relatable, not promise guaranteed success or wealth.
- Thumbnail headline must not misrepresent the story.
- Keep title under 100 characters, description under 5000 characters, tags to 15 items, hashtags to 5 items.
- Return valid JSON only.
""".strip()


def parse_asset_package(response: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip_code_fence(response))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("model response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("asset package must be a JSON object")
    scenes = data.get("scenes")
    thumbnail = data.get("thumbnail")
    youtube = data.get("youtube")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise ValueError(f"scenes must contain between 1 and {MAX_SCENES} items")
    required_scene_fields = (
        "scene_number", "narration_excerpt", "visual_description",
        "image_prompt", "stock_search_terms", "motion_direction",
    )
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict) or any(not scene.get(key) for key in required_scene_fields):
            raise ValueError(f"scene {index} is missing required fields")
        if not isinstance(scene["stock_search_terms"], list) or not all(
            isinstance(term, str) and term.strip() for term in scene["stock_search_terms"]
        ):
            raise ValueError(f"scene {index}: stock_search_terms must be a list of strings")
    if not isinstance(thumbnail, dict) or any(
        not isinstance(thumbnail.get(key), str) or not thumbnail[key].strip()
        for key in ("headline_hindi", "concept", "image_prompt")
    ):
        raise ValueError("thumbnail is missing required fields")
    if not isinstance(youtube, dict):
        raise ValueError("youtube metadata is missing")
    for key in ("title", "description"):
        if not isinstance(youtube.get(key), str) or not youtube[key].strip():
            raise ValueError(f"youtube.{key} is required")
    for key in ("tags", "hashtags"):
        values = youtube.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(f"youtube.{key} must be a list of strings")
    youtube["title"] = youtube["title"][:100]
    youtube["description"] = youtube["description"][:5000]
    youtube["tags"] = youtube["tags"][:15]
    youtube["hashtags"] = youtube["hashtags"][:5]
    return {"scenes": scenes, "thumbnail": thumbnail, "youtube": youtube}


def generate_package(subject: str, script: str, channel: str, profile: dict[str, Any]) -> dict[str, Any]:
    subject = (subject or "").strip()
    script = (script or "").strip()
    if not subject or len(subject) > MAX_SUBJECT_CHARS:
        raise ValueError(f"subject must contain 1-{MAX_SUBJECT_CHARS} characters")
    if not script or len(script) > MAX_SCRIPT_CHARS:
        raise ValueError(f"script must contain 1-{MAX_SCRIPT_CHARS} characters")
    prompt = build_prompt(subject, script, channel, profile)
    response = _generate_response(prompt)
    if not isinstance(response, str) or response.startswith("Error: "):
        raise ValueError("configured LLM provider could not generate the asset package")
    package = parse_asset_package(response)
    package["channel"] = channel
    package["subject"] = subject
    package["language"] = profile.get("language", "hi-IN")
    package["generation_note"] = (
        "Prompts and metadata only. Images, thumbnail rendering, video generation, "
        "and publishing require separate execution and review."
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", required=True, choices=("devotional", "motivation"))
    parser.add_argument("--subject", required=True)
    parser.add_argument("--script-file", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        profile = load_channel(args.config, args.channel)
        script = args.script_file.read_text(encoding="utf-8-sig")
        package = generate_package(args.subject, script, args.channel, profile)
        output = args.output or args.script_file.with_name(
            f"{args.script_file.stem}.{args.channel}.assets.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Created {output}: {len(package['scenes'])} scene(s) and YouTube metadata")
        print("Review all scene prompts, thumbnail concept, title and description before use.")
        print("This command does not render images, generate video, or publish.")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
