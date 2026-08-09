#!/usr/bin/env python3
"""Measure predicted-vs-actual running style using ONLY racenet + local data
(no Drive): for each horse we reconstruct the 'predicted' style from its OWN
recent settled positions (the same evidence our speed_map uses), then compare
to the actual settled position in the target race. This measures the ceiling of
settling-pattern prediction and how consistent horses actually are."""
import json, sys, re
from collections import defaultdict
from statistics import mean
pos=json.load(open("/Users/imac/Antigravity-repo/scratch/au_positions_map.json"))
l10=json.load(open("/Users/imac/Antigravity-repo/scratch/au_last10_map.json"))
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float

def band(p, field):
    if p is None or field<4: return None
    if p<=max(2,field*0.30): return "front"
    if p<=field*0.66: return "mid"
    return "back"

races=group_races(materialize_dataset())
# build per-horse history of actual settled bands from the extracted meetings (chronological)
hist=defaultdict(list)   # horse_name -> [(date, band)]
races_sorted=sorted(races,key=lambda r:str(r[0]["date"]))
for race in races_sorted:
    m=race[0]["meeting"]; rno=str(race[0]["race"]); pm=(pos.get(m) or {}).get(rno) or {}
    if not pm: continue
    field=len(race)
    for r in race:
        p=pm.get(str(int(r["horse_number"])))
        if not p: continue
        b=band(p.get("settled") or p.get("p800"), field)
        if b: hist[str(r.get("horse_name") or "").lower()].append((str(race[0]["date"]),b))

# now: for horses with >=2 prior observed runs, predict = modal prior band; compare to actual
conf=defaultdict(int); total=match=0
for race in races_sorted:
    m=race[0]["meeting"]; rno=str(race[0]["race"]); pm=(pos.get(m) or {}).get(rno) or {}
    if not pm: continue
    field=len(race); date=str(race[0]["date"])
    for r in race:
        nm=str(r.get("horse_name") or "").lower()
        p=pm.get(str(int(r["horse_number"])))
        if not p: continue
        actual=band(p.get("settled") or p.get("p800"), field)
        prior=[b for (d,b) in hist.get(nm,[]) if d<date]
        if not actual or len(prior)<2: continue
        pred=max(set(prior),key=prior.count)
        total+=1; match+= pred==actual; conf[(pred,actual)]+=1
print(f"horses with >=2 prior observed runs: {total}")
if total:
    print(f"跑法(前/中/後)預測準繩度 = {100*match/total:.1f}%  (隨機 ~33%, 常猜 back ~40%)")
    print("混淆 (預測→實際):")
    for pred in ("front","mid","back"):
        row={a:conf[(pred,a)] for a in ("front","mid","back")}; t=sum(row.values())
        if t: print(f"  預測{pred:<6}: "+"  ".join(f"{a}={100*row[a]/t:.0f}%" for a in ("front","mid","back"))+f"   (n={t})")
    # base rate of each actual band
    tot=defaultdict(int)
    for (p_,a),c in conf.items(): tot[a]+=c
    s=sum(tot.values())
    print("實際 band 基準率: "+"  ".join(f"{a}={100*tot[a]/s:.0f}%" for a in ("front","mid","back")))
