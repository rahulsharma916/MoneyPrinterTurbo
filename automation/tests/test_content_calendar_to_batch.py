import csv
import tempfile
import unittest
from pathlib import Path

from automation.content_calendar_to_batch import build_tasks


class ContentCalendarTests(unittest.TestCase):
    def write_csv(self, directory: str, headers: list[str], rows: list[list[str]]) -> Path:
        path = Path(directory) / "calendar.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def test_parses_hindi_subject_and_types(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                ["video_subject", "video_aspect", "video_clip_duration", "subtitle_enabled", "video_terms"],
                [["हनुमान जी की सीख", "9:16", "4", "true", "भक्ति;हनुमान"]],
            )
            tasks = build_tasks(path)
            self.assertEqual(tasks[0]["video_subject"], "हनुमान जी की सीख")
            self.assertEqual(tasks[0]["video_clip_duration"], 4)
            self.assertIs(tasks[0]["subtitle_enabled"], True)
            self.assertEqual(tasks[0]["video_terms"], ["भक्ति", "हनुमान"])

    def test_requires_subject_or_script(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, ["video_language"], [["hi-IN"]])
            with self.assertRaisesRegex(ValueError, "video_subject or video_script"):
                build_tasks(path)

    def test_rejects_unknown_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, ["video_subject", "vide_aspect"], [["Topic", "9:16"]])
            with self.assertRaisesRegex(ValueError, "Unsupported CSV column"):
                build_tasks(path)

    def test_rejects_invalid_aspect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, ["video_subject", "video_aspect"], [["Topic", "vertical"]])
            with self.assertRaisesRegex(ValueError, "video_aspect"):
                build_tasks(path)


if __name__ == "__main__":
    unittest.main()
