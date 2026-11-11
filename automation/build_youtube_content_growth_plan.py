#!/usr/bin/env python3
"""Turn Phase 6 Step 6 analytics intelligence into channel-specific growth plans."""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
from typing import Any

CHANNELS=("devotional","motivation")
PILLARS={
 "devotional":[
  {"name":"Epic character stories","purpose":"Build narrative-led discovery around figures and turning points from Hindu epics.","ideas":["बर्बरीक की कथा: तीन बाणों का रहस्य और महाभारत में उनकी भूमिका","हनुमान जी के जीवन से साहस और सेवा की सीख","महाभारत का एक निर्णायक प्रसंग: निर्णय, धर्म और परिणाम"]},
  {"name":"Bhakti and meaning","purpose":"Create repeat viewing through devotional context and accessible explanations.","ideas":["हनुमान चालीसा की एक चौपाई का सरल अर्थ और जीवन में उपयोग","शिव भक्ति से जुड़ी एक परंपरा का अर्थ","भक्ति में विश्वास और धैर्य का महत्व"]},
  {"name":"Spiritual life lessons","purpose":"Connect traditional stories with practical everyday reflection.","ideas":["गीता की एक सीख: कठिन समय में मन को स्थिर कैसे रखें","रामायण से परिवार, मर्यादा और जिम्मेदारी की सीख","कथा से आज के जीवन के लिए एक व्यावहारिक संदेश"]}
 ],
 "motivation":[
  {"name":"Relatable life stories","purpose":"Earn attention through recognizable conflict, emotion and a clear payoff.","ideas":["एक असफलता जिसने सोच बदल दी: छोटी कहानी, बड़ा सबक","जब मेहनत का परिणाम देर से मिले तो क्या करें","एक साधारण व्यक्ति की आदत जिसने उसकी दिशा बदल दी"]},
  {"name":"Discipline and mindset","purpose":"Build a repeatable series viewers can return to.","ideas":["मोटिवेशन नहीं, सिस्टम: रोज़ के 20 मिनट कैसे बदल सकते हैं","टालमटोल तोड़ने के लिए एक छोटा नियम","अनुशासन बनाम मूड: मुश्किल दिनों में काम कैसे जारी रखें"]},
  {"name":"Hindi motivational shayari","purpose":"Create concise, shareable emotional moments with original writing.","ideas":["हार के बाद उठने पर मौलिक शायरी और 20 सेकंड की कहानी","खामोश मेहनत पर मौलिक शायरी","समय, आत्मसम्मान और धैर्य पर मौलिक शायरी"]}
 ]
}
def load_json(path:Path)->dict[str,Any]:
 try: data=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise ValueError(f"cannot read intelligence JSON: {exc}") from exc
 if not isinstance(data,dict) or data.get("report_type")!="rule_based_youtube_performance_intelligence" or not isinstance(data.get("channels"),dict): raise ValueError("input must be a Phase 6 Step 6 intelligence JSON file")
 return data

def load_catalog(path:Path|None)->dict[str,dict[str,dict[str,str]]]:
 result={}
 if path is None:return result
 try:
  with path.open("r",encoding="utf-8-sig",newline="") as handle:
   reader=csv.DictReader(handle)
   required={"channel","video_id","title","topic","format"}
   if not reader.fieldnames or not required.issubset(set(reader.fieldnames)): raise ValueError("catalog CSV requires channel,video_id,title,topic,format columns")
   for row in reader:
    channel=(row.get("channel") or "").strip(); video=(row.get("video_id") or "").strip()
    if channel not in CHANNELS or not video: raise ValueError("catalog rows need a supported channel and non-empty video_id")
    result.setdefault(channel,{})[video]={key:(row.get(key) or "").strip() for key in ("title","topic","format")}
 except OSError as exc: raise ValueError(f"cannot read catalog CSV: {exc}") from exc
 return result

def format_opportunity(by_type:dict[str,Any])->dict[str,Any]:
 candidates=[]
 for kind,metrics in by_type.items():
  views=float(metrics.get("views",0) or 0)
  if views<100: continue
  candidates.append({"format":kind,"views":views,"watch_hours_per_1000_views":round(float(metrics.get("watch_hours",0) or 0)*1000/views,2),"subscribers_per_1000_views":round(float(metrics.get("subscribersGained",0) or 0)*1000/views,2),"average_view_percentage":metrics.get("average_view_percentage_weighted",0)})
 if len(candidates)<2:
  return {"status":"insufficient_comparable_data","message":"Need at least two creator-content types with 100+ views each before making a format-mix recommendation.","formats":candidates}
 ranked=sorted(candidates,key=lambda x:(x["watch_hours_per_1000_views"],x["subscribers_per_1000_views"]),reverse=True)
 return {"status":"directional_comparison","message":"Use this as a test-priority signal, not proof of causation; exposure, audience intent and content mix may differ.","formats":ranked,"leading_format":ranked[0]["format"]}

def build_channel_plan(channel:str, data:dict[str,Any], catalog:dict[str,dict[str,str]])->dict[str,Any]:
 if channel not in CHANNELS: raise ValueError(f"unsupported channel: {channel}")
 overall=data.get("overall") or {}; by_type=data.get("by_creator_content_type") or {}
 if not isinstance(overall,dict) or not isinstance(by_type,dict): raise ValueError(f"{channel}: malformed Step 6 channel record")
 rec=list(data.get("recommendations") or [])
 ideas=[]
 for pillar in PILLARS[channel]:
  for idea in pillar["ideas"]:
   ideas.append({"pillar":pillar["name"],"working_topic":idea,"format_hypothesis":"Shorts discovery test; adapt into a long-form episode only when the story has sufficient depth.","editorial_guardrail":"Use accurate sources, original narration and relevant scene visuals; avoid unsupported claims."})
 enriched=[]
 for video in data.get("top_videos_by_watch_time") or []:
  vid=str(video.get("video_id") or "")
  row=catalog.get(vid)
  enriched.append({**video,"catalog_metadata":row or None})
 known=[v for v in enriched if v["catalog_metadata"] and v["catalog_metadata"].get("topic")]
 topic_note=("Top-video topics are linked from the supplied catalog by exact video ID." if known else "Topic-level winners cannot be inferred from video IDs alone. Add a reviewed catalog CSV to connect video IDs with titles and topics.")
 experiments=[
  {"priority":"P1","name":"Opening-hook test","hypothesis":"A clear promise or story conflict in the first 3–5 seconds may improve early viewing.","design":"Publish two comparable pieces in the same format and topic family with different opening structures; keep the rest of the execution as consistent as practical.","primary_measure":"Average view duration and average view percentage","guardrail":"Compare like-for-like format and similar exposure; do not treat one upload as conclusive."},
  {"priority":"P1","name":"Format-mix test","hypothesis":"The format with stronger watch hours and subscriber gains per 1,000 views may deserve more production slots.","design":"Use the creator-content-type comparison below; run a controlled follow-up with comparable subjects before reallocating the calendar.","primary_measure":"Watch hours per 1,000 views and subscribers gained per 1,000 views","guardrail":"Only interpret when at least two formats have 100+ views; this threshold is a planning filter, not a YouTube benchmark."},
  {"priority":"P2","name":"Series and return-viewer test","hypothesis":"A clearly named recurring series may give viewers a reason to return.","design":"Create three connected episodes with a consistent visual identity, title convention and end-of-video next-episode cue.","primary_measure":"Returning-viewer trend in YouTube Studio and subscriber gains","guardrail":"Returning viewers are not present in the current Step 5 export; review manually in Studio."},
  {"priority":"P2","name":"Packaging test","hypothesis":"A more specific promise in the title and thumbnail may improve qualified clicks.","design":"Prepare two title/thumbnail concepts before publishing and document the selected hypothesis; use YouTube Studio impression and CTR reporting when available.","primary_measure":"Impressions click-through rate","guardrail":"CTR is not included in the current Step 5/6 data; do not declare a winner without impression data."}
 ]
 return {"channel":channel,"display_name":data.get("channel_display_name",channel),"period":data.get("date_range",{}),"baseline_kpis":{"views":overall.get("views",0),"estimated_watch_hours":overall.get("watch_hours",0),"average_view_percentage":overall.get("average_view_percentage_weighted",0),"engagement_rate_pct":overall.get("engagement_rate_pct",0),"net_subscribers":overall.get("net_subscribers",0)},"format_opportunity":format_opportunity(by_type),"content_pillars":PILLARS[channel],"editorial_idea_bank":ideas,"top_video_metadata":enriched,"topic_analysis_status":topic_note,"experiments":experiments,"next_14_day_execution_framework":[{"window":"Days 1–3","action":"Review the top-video IDs and add verified titles/topics in the optional catalog; inspect the first 30 seconds and thumbnail manually."},{"window":"Days 4–7","action":"Publish one controlled opening-hook experiment and one story/subject test in the channel's established format."},{"window":"Days 8–11","action":"Publish a connected follow-up episode and a format-mix test if the Analytics data supports comparison."},{"window":"Days 12–14","action":"Review Studio results, record the winning creative hypothesis, and update the next two-week slate."}],"recommendations":rec,"decision_note":"This is a test plan, not a guaranteed growth forecast. Keep each channel's audience promise, assets, metadata and publishing workflow separate."}

def build_plan(source:dict[str,Any],catalog:dict[str,dict[str,dict[str,str]]]|None=None)->dict[str,Any]:
 catalog=catalog or {}; channels={}
 for channel,data in source["channels"].items():
  if channel not in CHANNELS: continue
  channels[channel]=build_channel_plan(channel,data,catalog.get(channel,{}))
 if not channels: raise ValueError("no supported channel records found in Step 6 input")
 return {"schema_version":1,"plan_type":"youtube_content_intelligence_and_growth_plan","source":"Phase 6 Step 6 local analytics intelligence","channels":channels,"global_guardrails":["No guaranteed views, virality, subscribers or watch hours.","Do not merge devotional and motivation audiences or reuse channel-specific metadata across them.","Use YouTube Studio for CTR, retention curves, returning viewers and official monetization eligibility.","Validate religious/historical claims and rights to music, images and narration before publishing."]}

def markdown(plan:dict[str,Any])->str:
 lines=["# YouTube Content Intelligence & Growth Plan",""]
 for ch in plan["channels"].values():
  lines += [f"## {ch['display_name']} ({ch['channel']})",f"**Analytics period:** {ch['period'].get('start','?')} to {ch['period'].get('end','?')}","","### Baseline","","| KPI | Value |","|---|---:|",f"| Views | {ch['baseline_kpis']['views']:,.0f} |",f"| Estimated watch hours | {ch['baseline_kpis']['estimated_watch_hours']:,.2f} |",f"| Average view percentage | {ch['baseline_kpis']['average_view_percentage']:,.2f}% |",f"| Engagement rate | {ch['baseline_kpis']['engagement_rate_pct']:,.2f}% |",f"| Net subscribers | {ch['baseline_kpis']['net_subscribers']:,.0f} |","","### Format opportunity",ch["format_opportunity"]["message"],""]
  for f in ch["format_opportunity"]["formats"]: lines.append(f"- {f['format']}: {f['watch_hours_per_1000_views']} watch hours / 1,000 views; {f['subscribers_per_1000_views']} subscribers / 1,000 views")
  lines += ["","### Content pillars",""]
  for p in ch["content_pillars"]: lines.append(f"- **{p['name']}** — {p['purpose']}")
  lines += ["","### Editorial idea bank",""]+[f"- **{x['pillar']}:** {x['working_topic']}" for x in ch["editorial_idea_bank"]]
  lines += ["","### Experiments",""]+[f"- **{x['priority']} {x['name']}:** {x['hypothesis']} Design: {x['design']} Primary measure: {x['primary_measure']}." for x in ch["experiments"]]
  lines += ["","### Next 14 days",""]+[f"- **{x['window']}:** {x['action']}" for x in ch["next_14_day_execution_framework"]]
  lines += ["",ch["topic_analysis_status"],""]
 lines += ["## Guardrails",""]+[f"- {x}" for x in plan["global_guardrails"]]
 return "\n".join(lines)+"\n"

def main()->int:
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",required=True,type=Path); p.add_argument("--catalog-csv",type=Path); p.add_argument("--output-json",required=True,type=Path); p.add_argument("--output-md",type=Path); a=p.parse_args()
 try:
  source=load_json(a.input); catalog=load_catalog(a.catalog_csv); result=build_plan(source,catalog)
  out=a.output_json.expanduser().resolve(); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  if a.output_md:
   md=a.output_md.expanduser().resolve(); md.parent.mkdir(parents=True,exist_ok=True); md.write_text(markdown(result),encoding="utf-8")
  print(f"Growth plan saved: {out}")
  if a.output_md: print(f"Markdown plan saved: {a.output_md.expanduser().resolve()}")
  print("Channels planned: "+", ".join(result["channels"])); return 0
 except (ValueError,OSError) as exc: print(f"Growth plan not generated: {exc}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
