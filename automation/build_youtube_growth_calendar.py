#!/usr/bin/env python3
"""Generate a dated 14-day editorial calendar and MoneyPrinterTurbo-ready CSV."""
from __future__ import annotations
import argparse, csv, json, sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CHANNELS=("devotional","motivation")
MIXES={"balanced":("SHORTS","VIDEO"),"shorts-heavy":("SHORTS","SHORTS","VIDEO"),"long-form-heavy":("SHORTS","VIDEO","VIDEO")}

def load_plan(path:Path)->dict[str,Any]:
 try: value=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise ValueError(f"cannot read growth plan: {exc}") from exc
 if not isinstance(value,dict) or value.get("plan_type")!="youtube_content_intelligence_and_growth_plan" or not isinstance(value.get("channels"),dict): raise ValueError("input must be a Phase 6 Step 7 growth plan JSON")
 return value

def format_sequence(channel_data:dict[str,Any],count:int,mode:str)->list[str]:
 if mode=="data-led":
  opportunity=channel_data.get("format_opportunity") or {}
  if opportunity.get("status")=="directional_comparison" and opportunity.get("leading_format") in {"SHORTS","VIDEO"}:
   lead=opportunity["leading_format"]; other="VIDEO" if lead=="SHORTS" else "SHORTS"
   pattern=(lead,lead,other)
  else: pattern=MIXES["balanced"]
 else: pattern=MIXES[mode]
 return [pattern[i%len(pattern)] for i in range(count)]

def schedule_dates(start:date,count:int)->list[date]:
 if count<1 or count>28: raise ValueError("calendar must contain 1-28 posts over 14 days")
 if count==1:return [start]
 return [start+timedelta(days=round(i*13/(count-1))) for i in range(count)]

def build_calendar(channel:str,channel_data:dict[str,Any],start:date,posts_per_week:int,format_mix:str)->tuple[list[dict[str,str]],list[dict[str,str]]]:
 if channel not in CHANNELS: raise ValueError(f"unsupported channel: {channel}")
 if not 1<=posts_per_week<=14: raise ValueError("posts_per_week must be between 1 and 14")
 pillars=channel_data.get("content_pillars") or []; ideas=channel_data.get("editorial_idea_bank") or []
 if not pillars or not ideas: raise ValueError(f"{channel}: growth plan has no content pillars or editorial ideas")
 count=min(posts_per_week*2,28); dates=schedule_dates(start,count); formats=format_sequence(channel_data,count,format_mix)
 editorial=[]; production=[]
 for index,(publish_date,fmt) in enumerate(zip(dates,formats)):
  idea=ideas[index%len(ideas)]; pillar=idea.get("pillar","General")
  topic=str(idea.get("working_topic") or "").strip()
  if not topic: raise ValueError(f"{channel}: editorial idea {index+1} has no topic")
  aspect="9:16" if fmt=="SHORTS" else "16:9"
  duration="4" if fmt=="SHORTS" else "5"
  hook="पहले 3 सेकंड में स्पष्ट सवाल या चौंकाने वाला संदर्भ दें" if channel=="devotional" else "पहले 3 सेकंड में relatable problem और स्पष्ट promise दें"
  prompt=(f"भाषा: स्वाभाविक हिंदी (hi-IN)। विषय: {topic}. "
   f"फॉर्मेट: {'YouTube Shorts' if fmt=='SHORTS' else 'YouTube long-form'}. "
   f"एक मजबूत शुरुआती hook दें ({hook}); फिर स्पष्ट कहानी/व्याख्या, भावनात्मक लेकिन तथ्यपरक progression, "
   "और अंत में एक उपयोगी takeaway दें। अनावश्यक repetition न करें। "
   "किसी शास्त्र, ऐतिहासिक घटना, व्यक्ति या उद्धरण के बारे में अप्रमाणित तथ्य/उद्धरण न गढ़ें। "
   "केवल मूल narration लिखें; visual directions को narration में न पढ़ें।")
  editorial.append({"publish_date":publish_date.isoformat(),"channel":channel,"content_format":fmt,"pillar":pillar,"video_subject":topic,"video_aspect":aspect,"production_status":"planned","human_review_required":"yes"})
  production.append({"video_subject":topic,"video_script_prompt":prompt,"video_aspect":aspect,"video_language":"hi-IN","video_clip_duration":duration,"video_count":"1","bgm_type":"random","subtitle_enabled":"true","video_source":"pexels"})
 return editorial,production

def write_csv(path:Path,rows:list[dict[str,str]])->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 if not rows: raise ValueError("refusing to write an empty calendar")
 with path.open("w",encoding="utf-8-sig",newline="") as handle:
  writer=csv.DictWriter(handle,fieldnames=list(rows[0]),extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)

def main()->int:
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",required=True,type=Path); p.add_argument("--channel",required=True,choices=CHANNELS); p.add_argument("--start-date",required=True,help="First calendar date (YYYY-MM-DD)"); p.add_argument("--posts-per-week",type=int,default=5); p.add_argument("--format-mix",choices=("data-led","balanced","shorts-heavy","long-form-heavy"),default="data-led"); p.add_argument("--output-dir",required=True,type=Path); a=p.parse_args()
 try:
  plan=load_plan(a.input); data=plan["channels"].get(a.channel)
  if not isinstance(data,dict): raise ValueError(f"growth plan does not contain {a.channel}")
  try: start=date.fromisoformat(a.start_date)
  except ValueError as exc: raise ValueError("--start-date must use YYYY-MM-DD") from exc
  editorial,production=build_calendar(a.channel,data,start,a.posts_per_week,a.format_mix)
  out=a.output_dir.expanduser().resolve(); write_csv(out/f"{a.channel}_editorial_calendar.csv",editorial); write_csv(out/f"{a.channel}_production.csv",production)
  print(f"Created {len(editorial)} scheduled editorial slots for {a.channel}: {out}")
  print(f"Editorial calendar: {out/f'{a.channel}_editorial_calendar.csv'}")
  print(f"Production CSV: {out/f'{a.channel}_production.csv'}")
  print("Next: apply_content_profile.py, prepare_channel_calendar.py, then content_calendar_to_batch.py --check.")
  print("No scripts, media, uploads or scheduled publications were created.")
  return 0
 except (OSError,ValueError) as exc: print(f"Calendar not generated: {exc}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
