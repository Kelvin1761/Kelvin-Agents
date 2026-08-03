#!/usr/bin/env python3
"""CLEAN isolated A/B of the trainer empirical fill.

Previous validation was CONFOUNDED: it compared stored archive scores (older
engine era) against a fresh rescore with today's engine, so it measured the fill
PLUS every other change since. This version scores each horse ONCE with today's
engine, then recomputes ability with the trainer_score set to (a) the empirical
value and (b) neutral 60 — an exact counterfactual with everything else identical.
Magnitudes are swept so we can tune rather than discard.
"""
import csv, json, re, sys
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine")
from wongchoi_paths import AU_RACING
from engine_core import RacingEngine
from matrix_mapper import map_features_to_matrix_scores
from scoring import MATRIX_WEIGHTS
OUT=Path("/Users/imac/Antigravity-repo/scratch/au_trainer_isolated.json")

def ability_from(features, wet_feat):
    mx=map_features_to_matrix_scores(features)
    return round(sum(mx[k]*MATRIX_WEIGHTS[k] for k in MATRIX_WEIGHTS)+wet_feat,4)

def main():
    out=json.loads(OUT.read_text()) if OUT.exists() else {}
    dirs=[d for d in sorted(AU_RACING.iterdir()) if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}\s",d.name)]
    for d in dirs:
        if d.name in out: continue
        meeting={}
        for lp in sorted(d.glob("Race_*_Logic.json")):
            m=re.search(r"Race_(\d+)_Logic",lp.name)
            if not m or lp.stat().st_size<1000: continue
            try: data=json.loads(lp.read_text(encoding="utf-8"))
            except Exception: continue
            ctx=dict(data.get("race_analysis") or {}); horses=data.get("horses") or {}
            ctx.setdefault("field_summary",{"count":len(horses)})
            rows={}
            for num,h in horses.items():
                hh=dict(h); hh.setdefault("horse_number",num)
                try:
                    eng=RacingEngine(hh,ctx); auto=eng.analyze_horse()
                except Exception: continue
                fs=dict(auto["feature_scores"]); wet=auto.get("wet_form_feature",0.0)
                t_emp=fs.get("trainer_score",60.0)
                # counterfactual: what was the trainer score WITHOUT the fill?
                tly=(h.get("_data") or {}).get("trainer_ly") or {}
                emp=eng._trainer_empirical_base(tly)
                listed = eng._trainer_rating_profile(eng._clean_identity(h.get("trainer"))) is not None
                delta = 0.0 if (listed or emp is None) else emp[0]
                fs_off=dict(fs); fs_off["trainer_score"]=max(0.0,min(100.0,t_emp-delta))
                rows[num]={"name":h.get("horse_name"),
                           "ab_on":ability_from(fs,wet),
                           "ab_off":ability_from(fs_off,wet),
                           "delta":round(delta,3)}
            if rows: meeting[m.group(1)]=rows
        if meeting:
            out[d.name]=meeting; OUT.write_text(json.dumps(out),encoding="utf-8")
            print(f"[{len(out)}] {d.name}",flush=True)
    print(f"DONE meetings={len(out)}")

if __name__=="__main__": main()
