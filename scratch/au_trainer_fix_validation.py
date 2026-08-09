#!/usr/bin/env python3
"""Rescore the archive with the FIXED engine (empirical trainer fill) and
measure the honest performance impact vs the stored pre-fix scores."""
import json, re, sys
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine")
from wongchoi_paths import AU_RACING
from engine_core import RacingEngine
OUT=Path("/Users/imac/Antigravity-repo/scratch/au_trainer_fix_scores.json")
limit=int(sys.argv[1]) if len(sys.argv)>1 else 999
out=json.loads(OUT.read_text()) if OUT.exists() else {}
dirs=[d for d in sorted(AU_RACING.iterdir()) if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}\s",d.name)]
done=0
for d in dirs:
    if d.name in out: continue
    if done>=limit: break
    meeting={}
    for lp in sorted(d.glob("Race_*_Logic.json")):
        m=re.search(r"Race_(\d+)_Logic",lp.name)
        if not m or lp.stat().st_size<1000: continue
        try: data=json.loads(lp.read_text(encoding="utf-8"))
        except Exception: continue
        ctx=dict(data.get("race_analysis") or {})
        horses=data.get("horses") or {}
        ctx.setdefault("field_summary",{"count":len(horses)})
        rows={}
        for num,h in horses.items():
            old=(h.get("python_auto") or {}).get("ability_score")
            oldt=(h.get("python_auto") or {}).get("feature_scores",{}).get("trainer_score")
            hh=dict(h); hh.setdefault("horse_number",num)
            try:
                auto=RacingEngine(hh,ctx).analyze_horse()
            except Exception:
                continue
            rows[num]={"old_ability":old,"new_ability":auto["ability_score"],
                       "old_trainer":oldt,"new_trainer":auto["feature_scores"].get("trainer_score"),
                       "name":h.get("horse_name")}
        if rows: meeting[m.group(1)]=rows
    if meeting:
        out[d.name]=meeting; done+=1
        OUT.write_text(json.dumps(out),encoding="utf-8")
        print(f"[{done}] {d.name}: {sum(len(v) for v in meeting.values())} horses",flush=True)
print(f"DONE meetings={len(out)}")
