"""兩個來源（Racenet profile vs 去年官方）會唔會造成系統性偏差。唯讀。"""
import json, sys, statistics
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
        horses=logic.get("horses",{})
        ctx=dict(ra); ctx["field_summary"]=_build_field_summary(horses)
        field=len([1 for h in horses.values() if isinstance(h,dict)])
        for hn,h in horses.items():
            if not isinstance(h,dict): continue
            r=look.get(normalize_horse_name(get_true_horse_name(h)))
            if not r: continue
            hd=dict(h); hd.setdefault("horse_number",hn)
            eng=RacingEngine(hd,ctx,facts_section=(hd.get("_data") or {}).get("facts_section",""),
                             facts_path=str(md/"x.md"))
            out={"pos":int(r["pos"]),"field":len(res)}
            for kind in ("jockey","trainer"):
                f=eng._unified_place_rate(kind); sc=eng._place_rate_score(kind)
                out[f"{kind}_src"]=f[2] if f else "none"
                out[f"{kind}_score"]=sc[0] if sc else None
                out[f"{kind}_runs"]=f[1] if f else 0
            rows.append(out)

print(f"n = {len(rows)}\n")
for kind in ("jockey","trainer"):
    print(f"===== {kind} =====")
    print(f"{'來源':10}{'n':>7}{'佔比':>8}{'平均分':>9}{'SD':>8}{'中位樣本':>10}{'前三率':>9}{'期望':>8}{'超額':>8}")
    for src in ("profile","ly","none"):
        sub=[r for r in rows if r[f"{kind}_src"]==src]
        if not sub: continue
        sc=[r[f"{kind}_score"] for r in sub if r[f"{kind}_score"] is not None]
        exp=sum(3.0/r["field"] for r in sub)/len(sub)
        act=sum(1 for r in sub if r["pos"]<=3)/len(sub)
        print(f"{src:10}{len(sub):>7}{100*len(sub)/len(rows):>7.1f}%"
              f"{(statistics.mean(sc) if sc else float('nan')):>9.2f}"
              f"{(statistics.pstdev(sc) if len(sc)>1 else 0):>8.2f}"
              f"{statistics.median([r[f'{kind}_runs'] for r in sub]):>10.0f}"
              f"{100*act:>8.1f}%{100*exp:>7.1f}%{100*(act-exp):>+8.1f}")
    print()
