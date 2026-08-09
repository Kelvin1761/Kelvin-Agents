#!/usr/bin/env python3
"""Measure (a) how well our pace_map_score aligns with ACTUAL settled position,
and (b) whether actual-position data would improve ranking (retrodictive)."""
import json, sys
from collections import defaultdict
from statistics import mean
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float
pos=json.load(open("/Users/imac/Antigravity-repo/scratch/au_positions_map.json"))
def band(p, field):
    if p is None or field<4: return None
    if p<=max(2,field*0.30): return "front"
    if p<=field*0.66: return "mid"
    return "back"
races=group_races(materialize_dataset())
matched=0; corr=[]; buck=defaultdict(lambda:[0,0])
for race in races:
    m=race[0]["meeting"]; rno=str(race[0]["race"])
    pm=(pos.get(m) or {}).get(rno) or {}
    if not pm: continue
    field=len(race); matched+=1
    for r in race:
        p=pm.get(str(int(r["horse_number"])))
        if not p: continue
        settled=p.get("settled") or p.get("p800")
        b=band(settled,field)
        if not b: continue
        pms=as_float(r.get("pace_map_score"),60)
        # does our pace_map_score correlate with being forward?
        buck[b][0]+=1; buck[b][1]+=pms
        corr.append((pms, settled))
print(f"races with position data: {matched}")
if buck:
    print("實際跑位 band vs 我哋 pace_map_score 平均:")
    for b in ("front","mid","back"):
        n,s=buck[b]
        if n: print(f"  {b:<6} n={n:<5} 平均 pace_map_score {s/n:.1f}")
if len(corr)>30:
    # spearman-ish: correlation between pace_map_score and settled pos
    xs=[c[0] for c in corr]; ys=[c[1] for c in corr]
    mx,my=mean(xs),mean(ys)
    num=sum((x-mx)*(y-my) for x,y in corr)
    den=(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**0.5
    print(f"\ncorrelation(pace_map_score, settled position) = {num/den if den else 0:+.3f}")
    print("  (負數 = 高分→前置，符合預期方向)")
