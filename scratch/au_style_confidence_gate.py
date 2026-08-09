#!/usr/bin/env python3
"""Test: confidence-weighted running-style input (trust 'front', discount 'mid').

From extracted actual settling history we derive, per horse, a leak-free
style signal usable BEFORE the race:
  front_evidence = share of prior runs settled in the front band
  (only prior runs, strictly earlier dates → no leakage)

Hypothesis (from measured accuracy): front-runner evidence is 71% reliable and
front position is an advantage on many AU tracks, while mid-pack evidence is
noise. So add a small bonus scaled by front_evidence (confidence-weighted),
and NOT a generic style label.

Gate: honest holdout (tune nothing / fixed grid) + walk-forward folds, all races.
"""
import json, sys
from collections import defaultdict
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float, date_folds, metrics_for_races

pos=json.load(open("/Users/imac/Antigravity-repo/scratch/au_positions_map.json"))
def band(p, field):
    if p is None or field<4: return None
    if p<=max(2,field*0.30): return "front"
    if p<=field*0.66: return "mid"
    return "back"

races=sorted(group_races(materialize_dataset()),key=lambda r:str(r[0]["date"]))
# build chronological per-horse settled-band history from extracted positions
hist=defaultdict(list)  # name -> [(date, band)]
for race in races:
    pm=(pos.get(race[0]["meeting"]) or {}).get(str(race[0]["race"])) or {}
    if not pm: continue
    field=len(race)
    for r in race:
        p=pm.get(str(int(r["horse_number"])))
        if not p: continue
        b=band(p.get("settled") or p.get("p800"), field)
        if b: hist[str(r.get("horse_name") or "").lower()].append((str(race[0]["date"]),b))

def front_evidence(name, date, min_runs=2):
    prior=[b for (d,b) in hist.get(name,[]) if d<date]
    if len(prior)<min_runs: return None
    return sum(1 for b in prior if b=="front")/len(prior)

def scored(subset, bonus, mode):
    out=[]
    for race in subset:
        date=str(race[0]["date"]); rows=[]
        for r in race:
            ab=as_float(r["ability_score"],60)
            fe=front_evidence(str(r.get("horse_name") or "").lower(), date)
            if bonus>0 and fe is not None:
                if mode=="front_only":
                    ab += bonus*fe                    # confidence-weighted front bonus
                elif mode=="front_minus_mid":
                    prior=[b for (d,b) in hist.get(str(r.get("horse_name") or "").lower(),[]) if d<date]
                    mid=sum(1 for b in prior if b=="mid")/max(1,len(prior))
                    ab += bonus*(fe-0.5*mid)          # trust front, discount mid
            rows.append({**r,"_score":ab})
        out.append(rows)
    return out

def P(m):
    n=m["races"]
    return (f"頭兩揀齊三甲 {m['good_positional']}場({100*m['good_positional']/n:.1f}%) | "
            f"Top3中2隻 {m['good']}場({100*m['good']/n:.1f}%) | 捉到冠軍 {100*m['winner_in_top3']:.1f}% | "
            f"頭揀贏 {100*m['top1_win']:.1f}% | 全失 {m['miss']}場")

folds=date_folds(races); valid=[r for _t,v in folds for r in v]
cov=sum(1 for race in valid for r in race if front_evidence(str(r.get("horse_name") or "").lower(),str(race[0]["date"])) is not None)
tot=sum(len(r) for r in valid)
print(f"驗證窗 {len(valid)} 場；有跑位歷史(>=2場)嘅馬: {cov}/{tot} ({100*cov/max(1,tot):.0f}%)")
base=metrics_for_races(scored(valid,0,"none"))
print("現狀              :",P(base))
for mode in ("front_only","front_minus_mid"):
    for bonus in (1.0,2.0,3.5):
        nw=sum(metrics_for_races(scored(v,bonus,mode))["top3_precision"]>=metrics_for_races(scored(v,0,"none"))["top3_precision"] for _t,v in folds)
        c=metrics_for_races(scored(valid,bonus,mode))
        gp=c['good_positional']-base['good_positional']; g2=c['good']-base['good']
        print(f"{mode} +{bonus:<4}: {P(c)} | Δ頭兩揀 {gp:+d}場 Δ中2隻 {g2:+d}場 fold非差 {nw}/5")
