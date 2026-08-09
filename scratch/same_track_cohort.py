"""同場零上名罰分：按出賽次數分組，睇實測值唔值咁重嘅罰。唯讀。

現行階梯（TRACK_MICRO_WEIGHTS）：
    同場有上名        → +min(9, places*5.0 + wins*2.4)
    同場 >=2 戰零上名 → **−8.81**
    同場  1 戰零上名  → −0.81
1 戰同 2 戰之間跳 10 倍，而且 3 戰、10 戰都係同一個 −8.81（完全唔理樣本量）。
同一個檔案入面「going」嗰組階梯 2026-07-11 就係因為同類非單調問題被修過。
"""
import json, sys
from pathlib import Path
S=Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')
sys.path.insert(0,str(S)); sys.path.insert(0,str(S/'racing_engine'))
from au_archive_calibrator import (ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows,
    detect_meeting_date, detect_meeting_track, get_true_horse_name, load_historical_results,
    normalize_horse_name, parse_int)
from au_auto_orchestrator import _build_field_summary
from engine_core import RacingEngine

results=load_historical_results(HISTORICAL_RESULTS_CSV)
rows=[]
for md in sorted(p for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
    lf=sorted(md.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1],999))
    if not lf: continue
    date=detect_meeting_date(md)
    track=detect_meeting_track(md, json.loads(lf[0].read_text(encoding="utf-8")))
    if not date or not track: continue
    for lp in lf:
        logic=json.loads(lp.read_text(encoding="utf-8"))
        ra=logic.get("race_analysis",{})
        rno=parse_int(ra.get("race_number")) or parse_int(lp.stem.split("_")[1])
        res=choose_track_rows(results.get((date,rno),[]), track)
        if not res: continue
        look={normalize_horse_name(r["horse_slug"]):r for r in res}
        horses=logic.get("horses",{}); ctx=dict(ra)
        ctx["field_summary"]=_build_field_summary(horses)
        for hn,h in horses.items():
            if not isinstance(h,dict): continue
            r=look.get(normalize_horse_name(get_true_horse_name(h)))
            if not r: continue
            hd=dict(h); hd.setdefault("horse_number",hn)
            eng=RacingEngine(hd,ctx,facts_section=(hd.get("_data") or {}).get("facts_section",""),
                             facts_path=str(md/"x.md"))
            st=eng._same_track_stats()
            rows.append({"pos":int(r["pos"]),"field":len(res),
                         "starts":int(st.get("starts") or 0),"places":int(st.get("places") or 0)})
Path('scratch/same_track_cohort.json').write_text(json.dumps(rows))
print(f"n = {len(rows)}\n")
def show(pred, label):
    sub=[r for r in rows if pred(r)]
    if not sub: return
    exp=sum(3.0/r["field"] for r in sub)/len(sub)
    act=sum(1 for r in sub if r["pos"]<=3)/len(sub)
    print(f"{label:34}{len(sub):>7}{100*len(sub)/len(rows):>7.1f}%"
          f"{100*act:>10.1f}%{100*exp:>8.1f}%{100*(act-exp):>+8.1f}")
print(f"{'同場往績':34}{'n':>7}{'佔比':>8}{'實際前三%':>11}{'期望%':>8}{'超額':>8}")
show(lambda r: r["starts"]==0, "0 戰（冇同場紀錄，唔扣分）")
show(lambda r: r["starts"]==1 and r["places"]==0, "1 戰零上名（現扣 −0.81）")
show(lambda r: r["starts"]==2 and r["places"]==0, "2 戰零上名（現扣 −8.81）")
show(lambda r: r["starts"]==3 and r["places"]==0, "3 戰零上名（現扣 −8.81）")
show(lambda r: 4<=r["starts"]<=5 and r["places"]==0, "4–5 戰零上名（現扣 −8.81）")
show(lambda r: r["starts"]>=6 and r["places"]==0, ">=6 戰零上名（現扣 −8.81）")
show(lambda r: r["places"]>0, "同場曾上名（加分）")
