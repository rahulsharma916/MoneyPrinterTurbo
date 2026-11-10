import csv, unittest
from pathlib import Path
from automation.prepare_channel_calendar import load_channel, prepare_calendar
class PrepareChannelCalendarTests(unittest.TestCase):
    def setUp(self): self.config = Path(__file__).parents[1] / "channel_configs.json"
    def test_defaults_apply_and_explicit_values_win(self):
        profile = load_channel(self.config, "devotional")
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory)/"in.csv", Path(directory)/"out.csv"
            with source.open("w", encoding="utf-8", newline="") as f:
                w=csv.DictWriter(f, fieldnames=["video_subject","video_aspect","voice_name"]); w.writeheader()
                w.writerow({"video_subject":"हनुमान कथा","video_aspect":"","voice_name":""})
                w.writerow({"video_subject":"शिव कथा","video_aspect":"16:9","voice_name":"MyCustomHindiVoice"})
            self.assertEqual(prepare_calendar(source,dest,"devotional",profile),2)
            with dest.open("r",encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["video_aspect"],"9:16")
            self.assertEqual(rows[1]["video_aspect"],"16:9")
            self.assertEqual(rows[1]["voice_name"],"MyCustomHindiVoice")
            self.assertEqual(rows[0]["video_language"],"hi-IN")
            self.assertEqual(rows[0]["subtitle_enabled"],"true")
            self.assertIn("CHANNEL PRODUCTION CONTEXT (DEVOTIONAL)",rows[0]["custom_system_prompt"])
    def test_creative_contexts_are_distinct(self):
        d=load_channel(self.config,"devotional"); m=load_channel(self.config,"motivation")
        self.assertNotEqual(d["creative_direction"]["visual_style"],m["creative_direction"]["visual_style"])
    def test_unknown_channel_rejected(self):
        with self.assertRaises(ValueError): load_channel(self.config,"other")
if __name__ == "__main__": unittest.main()