import csv
import json
import tempfile
import unittest
from pathlib import Path

from automation.apply_content_profile import apply_profile, load_profile


class ContentProfileTests(unittest.TestCase):
    def test_applies_profile_and_preserves_existing_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "calendar.csv"
            destination = root / "enriched.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["video_subject", "video_script_prompt"])
                writer.writeheader()
                writer.writerow({"video_subject": "हनुमान कथा", "video_script_prompt": "Keep it under 60 seconds."})
            profile = {"prompt": "Write respectful Hindi narration."}
            count = apply_profile(source, destination, profile)
            self.assertEqual(count, 1)
            with destination.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertIn("Keep it under 60 seconds.", row["video_script_prompt"])
            self.assertIn("Write respectful Hindi narration.", row["video_script_prompt"])

    def test_profile_catalog_has_four_profiles(self):
        catalog = Path(__file__).parents[1] / "content_profiles.json"
        data = json.loads(catalog.read_text(encoding="utf-8"))
        self.assertEqual(set(data["profiles"]), {"devotional", "mythology", "motivation", "shayari"})
        for profile in data["profiles"].values():
            self.assertTrue(profile["prompt"].strip())


if __name__ == "__main__":
    unittest.main()
