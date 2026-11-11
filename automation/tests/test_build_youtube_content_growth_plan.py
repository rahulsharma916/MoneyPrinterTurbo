import csv, json, tempfile, unittest
from pathlib import Path
from automation.build_youtube_content_growth_plan import build_plan, build_channel_plan, format_opportunity, load_catalog, load_json, markdown

def step6():
 return {"report_type":"rule_based_youtube_performance_intelligence","channels":{"devotional":{"channel":"devotional","channel_display_name":"Devotional","date_range":{"start":"2026-10-01","end":"2026-10-28"},"overall":{"views":500,"watch_hours":20,"average_view_percentage_weighted":55,"engagement_rate_pct":3,"net_subscribers":8},"by_creator_content_type":{"SHORTS":{"views":300,"watch_hours":5,"subscribersGained":4,"average_view_percentage_weighted":45},"VIDEO":{"views":200,"watch_hours":15,"subscribersGained":4,"average_view_percentage_weighted":65}},"top_videos_by_watch_time":[{"video_id":"v1","views":100,"watch_hours":8}],"recommendations":["Improve opening"]},"motivation":{"channel":"motivation","channel_display_name":"Motivation","date_range":{"start":"2026-10-01","end":"2026-10-28"},"overall":{"views":100,"watch_hours":2,"average_view_percentage_weighted":25,"engagement_rate_pct":1,"net_subscribers":1},"by_creator_content_type":{},"top_videos_by_watch_time":[],"recommendations":[]}}}

class Tests(unittest.TestCase):
 def test_two_channels_get_separate_pillars_and_plan(self):
  p=build_plan(step6()); self.assertEqual(set(p["channels"]),{"devotional","motivation"}); self.assertNotEqual(p["channels"]["devotional"]["content_pillars"][0]["name"],p["channels"]["motivation"]["content_pillars"][0]["name"])
 def test_format_opportunity_requires_minimum_observations(self):
  x=format_opportunity({"SHORTS":{"views":99,"watch_hours":1},"VIDEO":{"views":200,"watch_hours":3}}); self.assertEqual(x["status"],"insufficient_comparable_data")
 def test_format_opportunity_ranks_observed_types(self):
  x=format_opportunity({"SHORTS":{"views":300,"watch_hours":5,"subscribersGained":4},"VIDEO":{"views":200,"watch_hours":15,"subscribersGained":4}}); self.assertEqual(x["leading_format"],"VIDEO")
 def test_catalog_enriches_exact_video_id(self):
  p=build_plan(step6(),{"devotional":{"v1":{"title":"Example","topic":"Hanuman","format":"VIDEO"}}}); self.assertEqual(p["channels"]["devotional"]["top_video_metadata"][0]["catalog_metadata"]["topic"],"Hanuman")
 def test_catalog_csv_validation(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/"catalog.csv"
   f.write_text("channel,video_id,title,topic,format\ndevotional,v1,Title,Hanuman,VIDEO\n",encoding="utf-8")
   self.assertEqual(load_catalog(f)["devotional"]["v1"]["topic"],"Hanuman")
 def test_invalid_step6_file(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/"bad.json"; f.write_text(json.dumps({"channels":{}}),encoding="utf-8")
   with self.assertRaises(ValueError): load_json(f)
 def test_markdown_contains_guardrails(self):
  self.assertIn("No guaranteed views",markdown(build_plan(step6())))
if __name__=="__main__": unittest.main()
