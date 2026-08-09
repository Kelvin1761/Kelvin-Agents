#!/usr/bin/env python3
"""Isolated A/B result + magnitude tuning with honest holdout.
ab_on/ab_off differ ONLY by the trainer fill, so scaling the delta lets us tune
magnitude exactly: ability(scale) = ab_off + (ab_on - ab_off) * scale."""
import csv, json, re, sys
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
from wongchoi_paths import AU_RACING
from au_archive_calibrator import normalize_horse_name
from eval_metrics import race_metrics, summarize_races
iso=json.loads(Path("/Users/imac/Antigravity-repo/scratch/au_trainer_isolated.json").read_text())
# rebuild/load the labelled cache (carries actual_pos per horse)
from au_cached_walkforward_ml import materialize_dataset
res={}
for row in materialize_dataset():
    try: pos=int(str(row.get("actual_pos") or "").strip())
    except (ValueError, TypeError): continue
    res.setdefault((row["meeting"],str(row["race"])),{})[normalize_horse_name(str(row["horse_name"]))]=pos
def meta(n):
    m=re.match(r"(\d{4}-\d{2}-\d{2})\s+(.*?)(?:\s+Race\s|$)",n); return (m.group(1),m.group(2).lower()) if m else (None,None)
races=[]; affected=0; tot=0
def mdate(n):
    m=re.match(r"(\d{4}-\d{2}-\d{2})",n); return m.group(1) if m else "9999"
for meeting,mrows in iso.items():
    for rno,rows in mrows.items():
        pos=res.get((meeting,str(rno)))
        if not pos or 1 not in pos.values(): continue
        ent=[]
        for num,v in rows.items():
            p=pos.get(normalize_horse_name(str(v.get("name") or "")))
            if p is None: continue
            tot+=1; affected+= abs(v.get("delta",0))>0.05
            ent.append((int(num),float(v["ab_off"]),float(v["ab_on"]),p))
        if len(ent)>=5 and sum(1 for _,_,_,p in ent if p<=3)>=3: races.append((mdate(meeting),ent))
races.sort()
def ev(subset,scale):
    e=[]
    for _,ent in subset:
        pb={n:p for n,_,_,p in ent}; t3=[n for n,p in pb.items() if p<=3]
        order=[n for n,_,_,_ in sorted(ent,key=lambda x:(-(x[1]+(x[2]-x[1])*scale),x[0]))]
        e.append(race_metrics(order,t3,actual_pos=pb))
    return summarize_races(e)
def P(s):
    n=s["races"]; c=s["counts"]
    return (f"頭兩揀齊三甲 {c['good_positional']}場({100*c['good_positional']/n:.1f}%) | Top3中2隻 {c['good_any2']}場 | "
            f"捉到冠軍 {100*c['winner_in_top3']/n:.1f}% | 頭揀贏 {100*c['champion']/n:.1f}% | 全失 {s['hit_distribution']['0hit']}場")
print(f"=== 乾淨隔離 A/B：{len(races)} 場，只切換練馬師填補 ===")
print(f"受影響: {affected}/{tot} 匹馬 ({100*affected/max(1,tot):.0f}%)\n")
print("全部賽事（幅度掃描）:")
for s in (0.0,0.25,0.5,0.75,1.0,1.5):
    print(f"  幅度 {s:<5}: {P(ev(races,s))}")
cut=int(len(races)*0.6); train,hold=races[:cut],races[cut:]
best=None
for s in (0.0,0.25,0.5,0.75,1.0,1.5):
    t=ev(train,s); k=(t["counts"]["good_positional"]+t["counts"]["good_any2"])/t["races"]
    if best is None or k>best[1]: best=(s,k)
print(f"\n=== 誠實 holdout（train 選幅度={best[0]}，holdout {len(hold)} 場從未參與）===")
print(f"  幅度 0 (無填補): {P(ev(hold,0.0))}")
print(f"  幅度 {best[0]} (train最佳): {P(ev(hold,best[0]))}")
print(f"  幅度 1.0 (全填補): {P(ev(hold,1.0))}")
