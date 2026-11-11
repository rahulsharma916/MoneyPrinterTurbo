import csv, json, tempfile, unittest
from datetime import date
from pathlib import Path
from automation.build_youtube_growth_calendar import build_calendar, format_sequence, load_plan, schedule_dates, write_csv
from automation.content_calendar_to_batch import build_tasks

def channel(name="devotional",lead="VIDEO"):
 return {"content_pillars":[{"name":"Pillar"}],"editorial_idea_bank":[{"pillar":"Pillar","working_topic":f"Topic {i}"} for i in range(8)],"format_opportunity":{"status":"directional_comparison","leading_format":lead}}

def plan():
 return {"plan_type":"youtube_content_intelligence_and_growth_plan","channels":{"devotional":channel(),"motivation":channel("motivation","SHORTS")}}

class Tests(unittest.TestCase):
 def test_schedule_spans_fourteen_days(self):
  dates=schedule_dates(date(2026,11,12),10); self.assertEqual(dates[0],date(2026,11,12)); self.assertEqual(dates[-1],date(2026,11,25)); self.assertEqual(len(dates),10)
 def test_data_led_format_uses_observed_leader(self):
  self.assertEqual(format_sequence(channel(lead="VIDEO"),3,"data-led"),["VIDEO","VIDEO","SHORTS"])
 def test_data_led_falls_back_to_balanced(self):
  d=channel(); d["format_opportunity"]={"status":"insufficient_comparable_data"}
  self.assertEqual(format_sequence(d,4,"data-led"),["SHORTS","VIDEO","SHORTS","VIDEO"])
 def test_channel_and_format_are_isolated(self):
  e,p=build_calendar("devotional",channel(lead="VIDEO"),date(2026,11,12),3,"data-led")
  self.assertEqual(len(e),6); self.assertTrue(all(x["channel"]=="devotional" for x in e)); self.assertEqual(e[0]["video_aspect"],"16:9")
 def test_shorts_map_to_vertical_and_long_form_to_wide(self):
  e,p=build_calendar("motivation",channel("motivation","SHORTS"),date(2026,11,12),2,"data-led")
  self.assertEqual(e[0]["video_aspect"],"9:16"); self.assertEqual(e[2]["video_aspect"],"16:9")
 def test_production_csv_is_batch_converter_compatible(self):
  with tempfile.TemporaryDirectory() as d:
   e,p=build_calendar("devotional",channel(),date(2026,11,12),2,"balanced"); path=Path(d)/"production.csv"; write_csv(path,p)
   tasks=build_tasks(path); self.assertEqual(len(tasks),4); self.assertEqual(tasks[0]["video_language"],"hi-IN")
 def test_rejects_empty_ideas_and_bad_cadence(self):
  d=channel(); d["editorial_idea_bank"]=[]
  with self.assertRaises(ValueError): build_calendar("devotional",d,date.today(),2,"balanced")
  with self.assertRaises(ValueError): build_calendar("devotional",channel(),date.today(),0,"balanced")
 def test_load_plan_validation(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"plan.json"; path.write_text(json.dumps(plan()),encoding="utf-8"); self.assertIn("devotional",load_plan(path)["channels"])
if __name__=="__main__": unittest.main()
