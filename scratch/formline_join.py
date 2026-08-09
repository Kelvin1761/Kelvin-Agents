"""同一次評分同時攞 formline_score 同 valid —— 驗證「冇證據嗰批攞緊高分」。唯讀。"""
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
races=[]
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
        rows=[]
        for hn,h in horses.items():
            if not isinstance(h,dict): continue
            r=look.get(normalize_horse_name(get_true_horse_name(h)))
            if not r: continue
            hd=dict(h); hd.setdefault("horse_number",hn)
            eng=RacingEngine(hd,ctx,facts_section=(hd.get("_data") or {}).get("facts_section",""),
                             facts_path=str(md/"x.md"))
            sup,val = eng._formline_support_summary()
            nrows = len(eng._formline_rows() or [])
            fs = eng.analyze_horse().get("feature_scores",{}) or {}
            rows.append({"pos":int(r["pos"]),"valid":val,"support":sup,
                         "score":float(fs.get("formline_score") or 60.0),"n_rows":nrows})
        if len(rows)>=4: races.append({"field":len(rows),"rows":rows})
Path('scratch/formline_join.json').write_text(json.dumps(races))
rows=[h for rc in races for h in rc['rows']]
print(f"races {len(races)}  runners {len(rows)}\n")
print(f"{'cohort':28}{'n':>7}{'佔比':>8}{'分平均':>9}{'中位':>8}{'min':>7}{'max':>7}{'超額前三':>10}")
for nm,f in (("valid=0（冇對手線）",lambda h:h['valid']==0),
             ("valid>=1（有對手線）",lambda h:h['valid']>=1)):
    sub=[(rc,h) for rc in races for h in rc['rows'] if f(h)]
    if not sub: continue
    sc=[h['score'] for _,h in sub]
    exc=sum((1 if h['pos']<=3 else 0)-3.0/rc['field'] for rc,h in sub)/len(sub)
    print(f"{nm:28}{len(sub):>7}{100*len(sub)/len(rows):>7.1f}%{statistics.mean(sc):>9.2f}"
          f"{statistics.median(sc):>8.1f}{min(sc):>7.1f}{max(sc):>7.1f}{100*exc:>+9.1f}")
n70=sum(1 for h in rows if h['valid']==0 and h['score']>70)
print(f"\n冇對手線但攞到 >70 分：{n70} 匹（{100*n70/len(rows):.1f}% 全樣本）")
