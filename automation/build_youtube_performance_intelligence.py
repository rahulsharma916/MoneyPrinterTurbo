#!/usr/bin/env python3
"""Build local, rule-based YouTube performance intelligence from read-only exports."""
from __future__ import annotations
import argparse, json, math, sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CHANNELS = ("devotional", "motivation")
NUMERIC_METRICS = ("views","engagedViews","estimatedMinutesWatched","averageViewDuration","averageViewPercentage","subscribersGained","subscribersLost","likes","comments","shares")

def number(value: Any) -> float:
    try:
        result=float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError,ValueError): return 0.0

def rounded(value: float, digits: int=2) -> float: return round(value,digits)

def load_report(path: Path) -> dict[str,Any]:
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise ValueError(f"cannot read analytics report {path}: {exc}") from exc
    if not isinstance(value,dict) or not isinstance(value.get("reports"),dict): raise ValueError(f"{path}: expected a Phase 6 Step 5 analytics JSON report")
    if value.get("channel") not in CHANNELS: raise ValueError(f"{path}: unsupported or missing channel identity")
    dr=value.get("date_range")
    if not isinstance(dr,dict): raise ValueError(f"{path}: missing date_range")
    try: start,end=date.fromisoformat(dr["start"]),date.fromisoformat(dr["end"])
    except (KeyError,TypeError,ValueError) as exc: raise ValueError(f"{path}: invalid date range") from exc
    if start>end: raise ValueError(f"{path}: date range start is after end")
    return value

def aggregate(rows: list[dict[str,Any]]) -> dict[str,float]:
    totals={key:sum(number(row.get(key)) for row in rows) for key in NUMERIC_METRICS}
    views=totals["views"]; interactions=totals["likes"]+totals["comments"]+totals["shares"]
    totals["watch_hours"]=totals["estimatedMinutesWatched"]/60
    totals["net_subscribers"]=totals["subscribersGained"]-totals["subscribersLost"]
    totals["engagement_rate_pct"]=interactions/views*100 if views else 0
    totals["subscriber_conversion_per_1000_views"]=totals["subscribersGained"]/views*1000 if views else 0
    totals["average_view_duration_weighted_seconds"]=sum(number(r.get("averageViewDuration"))*number(r.get("views")) for r in rows)/views if views else 0
    totals["average_view_percentage_weighted"]=sum(number(r.get("averageViewPercentage"))*number(r.get("views")) for r in rows)/views if views else 0
    return {key:rounded(value) for key,value in totals.items()}

def _row_date(row: dict[str,Any]):
    try: return date.fromisoformat(str(row.get("day","")))
    except ValueError: return None

def build_channel_intelligence(source: dict[str,Any]) -> dict[str,Any]:
    reports=source["reports"]; daily=reports.get("daily") or []; videos=reports.get("top_videos") or []; traffic=reports.get("traffic_sources") or []
    if not all(isinstance(x,dict) for x in daily+videos+traffic): raise ValueError(f"{source.get('channel')}: report rows must be objects")
    by_type={}
    for row in daily: by_type.setdefault(str(row.get("creatorContentType") or "UNSPECIFIED").upper(),[]).append(row)
    type_summary={key:aggregate(rows) for key,rows in sorted(by_type.items())}
    overall=aggregate(daily)
    start=date.fromisoformat(source["date_range"]["start"]); end=date.fromisoformat(source["date_range"]["end"])
    midpoint=start+timedelta(days=((end-start).days+1)//2)
    first_rows=[r for r in daily if _row_date(r) and _row_date(r)<midpoint]
    second_rows=[r for r in daily if _row_date(r) and _row_date(r)>=midpoint]
    first,second=aggregate(first_rows),aggregate(second_rows); trend={}
    for key in ("views","watch_hours","subscribersGained","engagement_rate_pct"):
        a,z=first[key],second[key]
        trend[key]={"first_period":a,"second_period":z,"change_pct":rounded((z-a)/a*100) if a else None}
    top=sorted(videos,key=lambda row:number(row.get("estimatedMinutesWatched")),reverse=True)[:10]
    top_videos=[{"video_id":str(row.get("video") or ""),"views":rounded(number(row.get("views"))),"watch_hours":rounded(number(row.get("estimatedMinutesWatched"))/60),"average_view_duration_seconds":rounded(number(row.get("averageViewDuration"))),"average_view_percentage":rounded(number(row.get("averageViewPercentage"))),"subscribers_gained":rounded(number(row.get("subscribersGained")))} for row in top]
    traffic_total=sum(number(row.get("views")) for row in traffic)
    traffic_mix=[{"source":str(row.get("insightTrafficSourceType") or "UNKNOWN"),"views":rounded(number(row.get("views"))),"watch_hours":rounded(number(row.get("estimatedMinutesWatched"))/60),"view_share_pct":rounded(number(row.get("views"))/traffic_total*100) if traffic_total else 0} for row in sorted(traffic,key=lambda row:number(row.get("views")),reverse=True)]
    rec=[]
    if overall["views"]==0: rec.append("No view activity is present in this export. Confirm the channel/date range and rerun after Analytics data has populated.")
    else:
        pct=overall["average_view_percentage_weighted"]
        if 0<pct<30: rec.append("Average view percentage is below 30%: test a faster opening hook, remove setup before the payoff, and review the first 30 seconds manually.")
        elif pct>=60: rec.append("Average view percentage is at least 60%: identify the strongest opening and story structure in top videos and test repeatable variations.")
        if overall["engagement_rate_pct"]<2: rec.append("Interactions are below 2% of views: test a specific, relevant viewer prompt rather than a generic like/subscribe request.")
        if overall["subscriber_conversion_per_1000_views"]<1: rec.append("Subscriber gains are below 1 per 1,000 views: strengthen the channel promise and give viewers a clear reason to return.")
        if len(top_videos)>=3: rec.append("Use the top-watch-time videos as the next editorial research set; compare subject, opening, duration and packaging manually.")
        if traffic_mix: rec.append(f"Review the leading traffic source ({traffic_mix[0]['source']}) and tailor distribution and metadata to that discovery path.")
    if not ({"SHORTS","VIDEO"} & set(type_summary)): rec.append("Creator content type is absent; do not infer Shorts-versus-long-form performance from these totals.")
    return {"channel":source["channel"],"channel_display_name":source.get("channel_display_name",source["channel"]),"verified_youtube_channel":source.get("verified_youtube_channel",{}),"date_range":source["date_range"],"overall":overall,"by_creator_content_type":type_summary,"period_comparison":{"split_date":midpoint.isoformat(),"first_period_rows":len(first_rows),"second_period_rows":len(second_rows),"metrics":trend},"top_videos_by_watch_time":top_videos,"traffic_sources":traffic_mix,"recommendations":rec}

def build_intelligence(sources: list[dict[str,Any]]) -> dict[str,Any]:
    channels=[build_channel_intelligence(source) for source in sources]; names=[x["channel"] for x in channels]
    if len(names)!=len(set(names)): raise ValueError("provide at most one report per channel")
    comparison=None
    if len(channels)==2:
        keys=("views","watch_hours","engagement_rate_pct","net_subscribers")
        comparison={"basis":"Each channel's own supplied date range; ranges may differ, so compare cautiously.","channels":{x["channel"]:{k:x["overall"][k] for k in keys} for x in channels}}
    return {"schema_version":1,"report_type":"rule_based_youtube_performance_intelligence","source":"local Phase 6 Step 5 read-only YouTube Analytics JSON exports","channels":{x["channel"]:x for x in channels},"cross_channel_comparison":comparison,"limitations":["Descriptive, rule-based analysis; no causal attribution or virality prediction.","The Step 5 export omits thumbnail impressions/CTR, retention curves, revenue and definitive Shorts eligibility classification.","Average view percentage is not a retention curve.","Estimated watch time is not the official YouTube Partner Program public-watch-hours counter; Shorts-feed watch time does not count toward the 4,000 public-watch-hours route.","Top-video rows contain IDs only; topic/title analysis needs separately validated metadata enrichment.","Period comparison splits the supplied range in half; interpret cautiously when activity or reporting coverage differs."]}

def markdown_report(result: dict[str,Any]) -> str:
    lines=["# YouTube Performance Intelligence",""]
    for ch in result["channels"].values():
        m=ch["overall"]; lines += [f"## {ch['channel_display_name']} ({ch['channel']})",f"**Period:** {ch['date_range']['start']} to {ch['date_range']['end']}","","| KPI | Result |","|---|---:|",f"| Views | {m['views']:,.0f} |",f"| Estimated watch hours | {m['watch_hours']:,.2f} |",f"| Weighted average view duration (seconds) | {m['average_view_duration_weighted_seconds']:,.2f} |",f"| Weighted average view percentage | {m['average_view_percentage_weighted']:,.2f}% |",f"| Engagement rate | {m['engagement_rate_pct']:,.2f}% |",f"| Net subscribers | {m['net_subscribers']:,.0f} |","","### Creator content type","","| Type | Views | Watch hours | Avg view % |","|---|---:|---:|---:|"]
        for kind,v in ch["by_creator_content_type"].items(): lines.append(f"| {kind} | {v['views']:,.0f} | {v['watch_hours']:,.2f} | {v['average_view_percentage_weighted']:,.2f}% |")
        lines += ["","### Recommendations",""]+[f"- {x}" for x in ch["recommendations"]]+["","### Top videos by watch time","","| Video ID | Views | Watch hours | Avg view % |","|---|---:|---:|---:|"]
        lines += [f"| {v['video_id']} | {v['views']:,.0f} | {v['watch_hours']:,.2f} | {v['average_view_percentage']:,.2f}% |" for v in ch["top_videos_by_watch_time"]]+[""]
    if result["cross_channel_comparison"]:
        lines += ["## Cross-channel comparison","","| Channel | Views | Watch hours | Engagement | Net subscribers |","|---|---:|---:|---:|---:|"]
        for name,m in result["cross_channel_comparison"]["channels"].items(): lines.append(f"| {name} | {m['views']:,.0f} | {m['watch_hours']:,.2f} | {m['engagement_rate_pct']:,.2f}% | {m['net_subscribers']:,.0f} |")
        lines += ["",result["cross_channel_comparison"]["basis"],""]
    lines += ["## Interpretation limits",""]+[f"- {x}" for x in result["limitations"]]
    return "\n".join(lines)+"\n"

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",action="append",required=True,type=Path,help="Step 5 JSON export; repeat for the second channel"); p.add_argument("--output-json",type=Path,required=True); p.add_argument("--output-md",type=Path); a=p.parse_args()
    try:
        if len(a.input)>2: raise ValueError("provide one or two channel exports")
        result=build_intelligence([load_report(x) for x in a.input])
        out=a.output_json.expanduser().resolve(); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        if a.output_md:
            md=a.output_md.expanduser().resolve(); md.parent.mkdir(parents=True,exist_ok=True); md.write_text(markdown_report(result),encoding="utf-8")
        print(f"Performance intelligence saved: {out}")
        if a.output_md: print(f"Markdown report saved: {a.output_md.expanduser().resolve()}")
        print("Channels analyzed: "+", ".join(result["channels"])); return 0
    except (ValueError,OSError) as exc: print(f"Performance intelligence not generated: {exc}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
