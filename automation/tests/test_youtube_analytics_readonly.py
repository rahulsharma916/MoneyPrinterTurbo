import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from automation.youtube_analytics_readonly import build_output, default_date_range, load_channel_config, parse_date, rows_as_objects, validate_date_range

class YouTubeAnalyticsReadonlyTests(unittest.TestCase):
    def test_default_range_is_last_28_complete_days(self):
        self.assertEqual(default_date_range(date(2026, 11, 11)), ("2026-10-14", "2026-11-10"))
    def test_parse_date_rejects_invalid_format(self):
        with self.assertRaises(ValueError): parse_date("11/10/2026")
    def test_date_range_rejects_today_and_future(self):
        today = date.today().isoformat()
        with self.assertRaises(ValueError): validate_date_range(today, today)
    def test_date_range_rejects_reversed_dates(self):
        with self.assertRaises(ValueError): validate_date_range("2026-11-10", "2026-11-01")
    def test_rows_are_mapped_to_column_names(self):
        self.assertEqual(rows_as_objects({"columnHeaders":[{"name":"day"},{"name":"views"}],"rows":[["2026-11-01",123]]}), [{"day":"2026-11-01","views":123}])
    def test_load_channel_config_requires_channel_id(self):
        config={"channels":{"devotional":{"display_name":"Devotional","youtube_channel_id":"","analytics":{"oauth_client_secrets_env":"MPT_DEVOTIONAL_GOOGLE_OAUTH_CLIENT_SECRETS"}}}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"config.json"; path.write_text(json.dumps(config),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"channel ID"): load_channel_config("devotional",path)
    def test_load_channel_config_returns_no_secrets(self):
        config={"channels":{"motivation":{"display_name":"Motivation","youtube_channel_id":"UC1234567890123456789012","analytics":{"oauth_client_secrets_env":"MPT_MOTIVATION_GOOGLE_OAUTH_CLIENT_SECRETS"}}}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"config.json"; path.write_text(json.dumps(config),encoding="utf-8"); result=load_channel_config("motivation",path)
        self.assertEqual(result["channel_id"],"UC1234567890123456789012"); self.assertNotIn("client_secret",result)
    def test_output_marks_read_only_scope_and_limitations(self):
        result=build_output({"channel":"devotional","display_name":"Devotional"},{"channel_id":"UC123","title":"Devotional"},"2026-10-01","2026-10-31",{"daily":[],"top_videos":[],"traffic_sources":[]})
        self.assertIn("read-only",result["scope"]); self.assertTrue(any("impressions" in x.lower() for x in result["limitations"]))

if __name__ == "__main__": unittest.main()
