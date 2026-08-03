#!/usr/bin/env python3
"""Isolated trainer-fill A/B using racenet finish positions (no Drive dependency).
ability(scale) = ab_off + (ab_on - ab_off) * scale, so magnitude tunes exactly."""
import json, re, sys
from pathlib import Path
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
from eval_metrics import race_metrics, summarize_races
def nn(s): return re.sub(r"[^a-z0-9]","",str(s or "").lower())
iso=json.loads(Path("/Users/imac/Antigravity-repo/scratch/au_trainer_isolated.json").read_text())
fin=json.loads(Path("/Users/imac/Antigravity-repo/scratch/au_finishes_map.json").read_text())
races=[]; affected=0; tot=0
for meeting,mrows in iso.items():
    fm=fin.get(meeting) or {}
    if not fm: continue
    d=re.match(r"(\d{4}-\d{2}-\d{2})",meeting)
    date=d.group(1) if d else "9999"
    for rno,rows in mrows.items():
        fr=fm.get(str(rno)) or {}
        if not fr: continue
        ent=[]
        for num,v in rows.items():
            f=fr.get(str(num))
            if not f: continue
            # sanity: names should match
            if f.get("name") and v.get("name") and nn(f["name"])!=nn(v["name"]): continue
            tot+=1; affected+= abs(v.get("delta",0))>0.05
            ent.append((int(num),float(v["ab_off"]),float(v["ab_on"]),int(f["pos"])))
        if len(ent)>=5 and sum(1 for _,_,_,p in ent if p<=3)>=3 and any(p==1 for _,_,_,p in ent):
            races.append((date,ent))
races.sort()
def ev(sub,scale):
    e=[]
    for _,ent in sub:
        pb={n:p for n,_,_,p in ent}; t3=[n for n,p in pb.items() if p<=3]
        order=[n for n,_,_,_ in sorted(ent,key=lambda x:(-(x[1]+(x[2]-x[1])*scale),x[0]))]
        e.append(race_metrics(order,t3,actual_pos=pb))
    return summarize_races(e)
def P(s):
    n=s["races"]; c=s["counts"]
    return (f"頭兩揀齊三甲 {c['good_positional']}場({100*c['good_positional']/n:.1f}%) | Top3中2隻 {c['good_any2']}場({100*c['good_any2']/n:.1f}%) | "
            f"捉到冠軍 {100*c['winner_in_top3']/n:.1f}% | 頭揀贏 {100*c['champion']/n:.1f}% | 全失 {s['hit_distribution']['0hit']}場")
print(f"=== 乾淨隔離 A/B（同一引擎，只切換練馬師填補）===")
print(f"可比對賽事: {len(races)} 場 | 受影響馬匹: {affected}/{tot} ({100*affected/max(1,tot):.0f}%)\n")
if not races: raise SystemExit("等賽果抽取完成")
print("全部賽事（幅度掃描）:")
for s in (0.0,0.25,0.5,0.75,1.0,1.5,2.0):
    print(f"  幅度 {s:<5}: {P(ev(races,s))}")
cut=int(len(races)*0.6); train,hold=races[:cut],races[cut:]
best=None
for s in (0.0,0.25,0.5,0.75,1.0,1.5,2.0):
    t=ev(train,s); k=(t["counts"]["good_positional"]+t["counts"]["good_any2"])/t["races"]
    if best is None or k>best[1]: best=(s,k)
print(f"\n=== 誠實 holdout（train {len(train)}場選幅度={best[0]}，holdout {len(hold)}場從未參與）===")
for lab,s in (("無填補",0.0),(f"train最佳({best[0]})",best[0]),("全填補(1.0)",1.0)):
    print(f"  {lab:<18}: {P(ev(hold,s))}")
