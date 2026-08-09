#!/usr/bin/env python3
"""Honest gate: does the trainer empirical fill improve analysis performance?
Compares stored pre-fix ability vs rescored post-fix ability on the SAME races,
using real results. All races available. Split-half stability included."""
import csv, json, re, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,"/Users/imac/Antigravity-repo")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0,"/Users/imac/Antigravity-repo/.agents/skills/shared_racing")
from wongchoi_paths import AU_RACING
from au_archive_calibrator import normalize_horse_name
from eval_metrics import race_metrics, summarize_races
scores=json.loads(Path("/Users/imac/Antigravity-repo/scratch/au_trainer_fix_scores.json").read_text())
# results
res={}
with open(AU_RACING/"AU_Historical_Raw_Race_Results.csv",encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        try: pos=int(str(row.get("Pos") or "").strip())
        except ValueError: continue
        res.setdefault((row["Date"].strip(),row["Track"].strip().lower(),row["Race"].strip()),{})[normalize_horse_name(row["Horse"])]=pos
def meta(name):
    m=re.match(r"(\d{4}-\d{2}-\d{2})\s+(.*?)(?:\s+Race\s|$)",name)
    return (m.group(1),m.group(2).lower()) if m else (None,None)
old_e=[]; new_e=[]; dates=[]
trainer_changed=0; total_h=0
for meeting,mrows in scores.items():
    date,track=meta(meeting)
    if not date: continue
    for rno,rows in mrows.items():
        pos=res.get((date,track,rno))
        if not pos or 1 not in pos.values(): continue
        entries=[]
        for num,v in rows.items():
            p=pos.get(normalize_horse_name(str(v.get("name") or "")))
            if p is None: continue
            total_h+=1
            if v.get("old_trainer") is not None and abs(float(v["old_trainer"])-60)<1e-9 and v.get("new_trainer") and abs(float(v["new_trainer"])-60)>0.05:
                trainer_changed+=1
            entries.append((int(num),float(v["old_ability"] or 60),float(v["new_ability"] or 60),p))
        if len(entries)<5 or sum(1 for _,_,_,p in entries if p<=3)<3: continue
        pos_by={n:p for n,_,_,p in entries}
        top3=[n for n,p in pos_by.items() if p<=3]
        oldr=[n for n,_,_,_ in sorted(entries,key=lambda e:(-e[1],e[0]))]
        newr=[n for n,_,_,_ in sorted(entries,key=lambda e:(-e[2],e[0]))]
        old_e.append(race_metrics(oldr,top3,actual_pos=pos_by))
        new_e.append(race_metrics(newr,top3,actual_pos=pos_by))
        dates.append(date)
def P(s):
    n=s["races"]; c=s["counts"]
    return (f"頭兩揀齊三甲 {c['good_positional']}場({100*c['good_positional']/n:.1f}%) | Top3中2隻 {c['good_any2']}場({100*c['good_any2']/n:.1f}%) | "
            f"捉到冠軍 {100*c['winner_in_top3']/n:.1f}% | 頭揀贏 {100*c['champion']/n:.1f}% | 全失 {s['hit_distribution']['0hit']}場")
o,nw=summarize_races(old_e),summarize_races(new_e)
print(f"=== 練馬師修復驗證：{o['races']} 場（全部可比對賽事）===")
print(f"影響面: {trainer_changed}/{total_h} 匹馬由 default 60 變實證分 ({100*trainer_changed/max(1,total_h):.0f}%)")
print("修復前:",P(o))
print("修復後:",P(nw))
gp=nw['counts']['good_positional']-o['counts']['good_positional']; g2=nw['counts']['good_any2']-o['counts']['good_any2']
print(f"Δ 頭兩揀 {gp:+d}場  Δ Top3中2隻 {g2:+d}場  Δ捉冠軍 {100*(nw['counts']['winner_in_top3']-o['counts']['winner_in_top3'])/o['races']:+.1f}pp  Δ頭揀贏 {100*(nw['counts']['champion']-o['counts']['champion'])/o['races']:+.1f}pp")
# split-half
idx=sorted(range(len(dates)),key=lambda i:dates[i]); h=len(idx)//2
for lab,sl in (("前半",idx[:h]),("後半",idx[h:])):
    oo=summarize_races([old_e[i] for i in sl]); nn2=summarize_races([new_e[i] for i in sl])
    print(f"  {lab}: Δ頭兩揀 {nn2['counts']['good_positional']-oo['counts']['good_positional']:+d}場  Δ中2隻 {nn2['counts']['good_any2']-oo['counts']['good_any2']:+d}場")
