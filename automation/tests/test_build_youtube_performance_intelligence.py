import json, tempfile, unittest
from pathlib import Path
from automation.build_youtube_performance_intelligence import aggregate, build_intelligence, build_channel_intelligence, load_report, markdown_report

def sample(channel="devotional"):
    return {"schema_version":1,"channel":channel,"channel_display_name":channel.title(),"verified_youtube_channel":{"channel_id":"UC123","title":channel.title()},"date_range":{"start":"2026-10-01","end":"2026-10-28"},"reports":{"daily":[{"day":"2026-10-01","creatorContentType":"VIDEO","views":100,"engagedViews":80,"estimatedMinutesWatched":500,"averageViewDuration":300,"averageViewPercentage":60,"subscribersGained":3,"subscribersLost":1,"likes":4,"comments":2,"shares":1},{"day":"2026-10-20","creatorContentType":"SHORTS","views":200,"engagedViews":150,"estimatedMinutesWatched":300,"averageViewDuration":90,"averageViewPercentage":45,"subscribersGained":2,"subscribersLost":1,"likes":5,"comments":2,"shares":3}],"top_videos":[{"video":"vid-a","views":100,"estimatedMinutesWatched":500,"averageViewDuration":300,"averageViewPercentage":60,"subscribersGained":3},{"video":"vid-b","views":200,"estimatedMinutesWatched":300,"averageViewDuration":90,"averageViewPercentage":45,"subscribersGained":2}],"traffic_sources":[{"insightTrafficSourceType":"YT_SEARCH","views":150,"estimatedMinutesWatched":600},{"insightTrafficSourceType":"SUGGESTED_VIDEO","views":150,"estimatedMinutesWatched":200}]}}
class Tests(unittest.TestCase):
    def test_aggregate(self):
        x=aggregate([{"views":100,"estimatedMinutesWatched":120,"likes":2,"comments":1,"shares":1,"subscribersGained":2,"subscribersLost":1}])
        self.assertEqual(x["watch_hours"],2); self.assertEqual(x["engagement_rate_pct"],4); self.assertEqual(x["net_subscribers"],1); self.assertEqual(x["subscriber_conversion_per_1000_views"],20)
    def test_content_types_and_totals(self):
        x=build_channel_intelligence(sample()); self.assertEqual(set(x["by_creator_content_type"]),{"VIDEO","SHORTS"}); self.assertEqual(x["overall"]["views"],300); self.assertEqual(x["overall"]["watch_hours"],13.33); self.assertEqual(x["top_videos_by_watch_time"][0]["video_id"],"vid-a")
    def test_two_channels_remain_separate(self):
        x=build_intelligence([sample("devotional"),sample("motivation")]); self.assertEqual(set(x["channels"]),{"devotional","motivation"}); self.assertIsNotNone(x["cross_channel_comparison"])
    def test_duplicate_channel_rejected(self):
        with self.assertRaisesRegex(ValueError,"at most one"): build_intelligence([sample(),sample()])
    def test_invalid_report_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bad.json"; p.write_text(json.dumps({"channel":"other"}),encoding="utf-8")
            with self.assertRaises(ValueError): load_report(p)
    def test_markdown_has_interpretation_limits(self):
        x=markdown_report(build_intelligence([sample()])); self.assertIn("Top videos by watch time",x); self.assertIn("official YouTube Partner Program",x)
    def test_empty_daily_data(self):
        x=sample(); x["reports"]["daily"]=[]; y=build_channel_intelligence(x); self.assertEqual(y["overall"]["views"],0); self.assertTrue(y["recommendations"])
if __name__=="__main__": unittest.main()
