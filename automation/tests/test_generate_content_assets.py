import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.generate_content_assets import (
    build_prompt,
    generate_package,
    load_channel,
    parse_asset_package,
)

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "channel_configs.json"


def valid_payload():
    return {
        "scenes": [{
            "scene_number": 1,
            "narration_excerpt": "एक छोटा अंश",
            "visual_description": "मंदिर के प्रांगण में दीपक",
            "image_prompt": "Cinematic respectful temple courtyard at dawn, oil lamp, detailed illustration",
            "stock_search_terms": ["temple lamp", "sunrise prayer"],
            "motion_direction": "Slow cinematic push-in",
        }],
        "thumbnail": {
            "headline_hindi": "भक्ति की शक्ति",
            "concept": "One illuminated diya as focal point",
            "image_prompt": "16:9 cinematic devotional thumbnail, diya on right, negative space left",
        },
        "youtube": {
            "title": "भक्ति की शक्ति | प्रेरक कथा",
            "description": "कथा का सार और दर्शकों के लिए आमंत्रण।",
            "tags": ["भक्ति", "हिंदी कथा"],
            "hashtags": ["#Bhakti", "#HindiKatha"],
        },
    }


class ContentAssetPackageTests(unittest.TestCase):
    def test_channel_prompts_remain_distinct(self):
        devotional = load_channel(CONFIG, "devotional")
        motivation = load_channel(CONFIG, "motivation")
        d_prompt = build_prompt("हनुमान कथा", "जय हनुमान", "devotional", devotional)
        m_prompt = build_prompt("अनुशासन", "हर दिन अभ्यास करो", "motivation", motivation)
        self.assertIn("culturally respectful", d_prompt.lower())
        self.assertIn("relatable", m_prompt.lower())
        self.assertNotEqual(d_prompt, m_prompt)

    def test_valid_package_is_parsed_and_bounded(self):
        payload = valid_payload()
        payload["youtube"]["tags"] = [f"tag-{i}" for i in range(20)]
        result = parse_asset_package(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(len(result["youtube"]["tags"]), 15)
        self.assertEqual(result["youtube"]["title"], payload["youtube"]["title"])

    def test_invalid_scene_is_rejected(self):
        payload = valid_payload()
        payload["scenes"][0].pop("image_prompt")
        with self.assertRaises(ValueError):
            parse_asset_package(json.dumps(payload, ensure_ascii=False))

    def test_scene_count_is_bounded(self):
        payload = valid_payload()
        payload["scenes"] = payload["scenes"] * 31
        with self.assertRaises(ValueError):
            parse_asset_package(json.dumps(payload, ensure_ascii=False))

    def test_generation_adds_channel_context(self):
        profile = load_channel(CONFIG, "devotional")
        with patch("automation.generate_content_assets._generate_response", return_value=json.dumps(valid_payload(), ensure_ascii=False)):
            result = generate_package("हनुमान कथा", "जय हनुमान", "devotional", profile)
        self.assertEqual(result["channel"], "devotional")
        self.assertEqual(result["language"], "hi-IN")
        self.assertIn("does not render images", result["generation_note"])


if __name__ == "__main__":
    unittest.main()
