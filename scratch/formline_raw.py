"""賽績線原材料嘅場內預測力 —— 重建之前要知有冇嘢可以榨。唯讀。"""
import json, sys
from pathlib import Path
S=Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')
sys.path.insert(0,str(S)); sys.path.insert(0,str(S))
from au_archive_calibrator import (ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows,
    detect_meeting_date, detect_meeting_track, get_true_horse_name, load_historical_results,
    normalize_horse_name, parse_int)
from au_auto_orchestrator import _build_field_summary
from au_racing_engine.engine_core import RacingEngine

results=load_historical_results(HISTORICAL_RESULTS_CSV)
out=[]
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
        rows=[]
        for hn,h in horses.items():
            if not isinstance(h,dict): continue
            r=look.get(normalize_horse_name(get_true_horse_name(h)))
            if not r: continue
            hd=dict(h); hd.setdefault("horse_number",hn)
            eng=RacingEngine(hd,ctx,facts_section=(hd.get("_data") or {}).get("facts_section",""),
                             facts_path=str(md/"x.md"))
            support, valid = eng._formline_support_summary()
            frows = eng._formline_rows() or []
            try: fw = eng._formline_future_wins()
            except Exception: fw = None
            try: hi, same, lo = eng._formline_followup_counts()
            except Exception: hi = same = lo = None
            rows.append({"pos":int(r["pos"]),
                         "support":support, "valid":valid,
                         "ratio":(support/valid) if valid else None,
                         "n_rows":len(frows),
                         "future_wins": (len(fw) if isinstance(fw,(list,tuple)) else fw),
                         "fu_higher":hi, "fu_same":same, "fu_lower":lo})
        if len(rows)>=4:
            out.append({"field":len(rows),"rows":rows})
Path('scratch/formline_raw.json').write_text(json.dumps(out))
print(f"races {len(out)}  runners {sum(len(r['rows']) for r in out)}")
