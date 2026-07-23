#!/usr/bin/env python3
"""AU Betfair full analysis: (1) ROI at BSP + morning price, (2) money-flow
feature retrodictive check. Joins on (race-date, horse) — near-unique across
AU on a given day, sidesteps the track-name alias problem.
"""
from __future__ import annotations
import csv, re, sys, random
from pathlib import Path
from collections import defaultdict
from statistics import mean, median

sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float
from au_archive_calibrator import normalize_horse_name

BSP_DIR = Path("/Users/imac/Antigravity-repo/scratch/betfair_bsp")
MONTHS = {m:i for i,m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],1)}
COMMISSION = 0.05

def norm_name(n): return re.sub(r"[^a-z0-9]","",re.sub(r"^\s*\d+\.?\s*","",str(n or "")).lower())
def ci(row,k): return row.get(k) or row.get(k.upper())

def hint_date(hint):
    m=re.search(r"\(AUS\)\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})",hint or "")
    if not m: return None
    mon=MONTHS.get(m.group(2)[:3].title())
    return f"{mon:02d}-{int(m.group(1)):02d}" if mon else None

def load(market):
    idx={}
    for fp in sorted(BSP_DIR.glob(f"dwbfpricesaus{market}*.csv")):
        for row in csv.DictReader(open(fp,encoding="utf-8-sig",errors="replace")):
            d=hint_date(ci(row,"menu_hint") or "")
            h=norm_name(ci(row,"selection_name") or "")
            if d and h: idx[(d,h)]=row
    return idx

def fnum(v):
    try: return float(v)
    except: return None

def main():
    win=load("win")
    print(f"loaded win BSP: {len(win)} selections")
    races=group_races(materialize_dataset())
    def gap(race):
        s=sorted((as_float(r["ability_score"],60) for r in race),reverse=True)
        return (s[0]-s[2]) if len(s)>=3 else 99.0

    # ---------- (1) ROI ----------
    bets=defaultdict(list)  # strat -> [(date, bsp, morn, won)]
    joined=tot=0
    mf_rows=[]  # money-flow: (date, drift, volrank, is_top3) per runner in joinable races
    for race in races:
        d=str(race[0]["date"])[5:]
        ranked=sorted(race,key=lambda r:(-as_float(r["ability_score"],60),int(r["horse_number"])))
        t="tight" if gap(race)<2 else ("medium" if gap(race)<5 else "clear")
        # money-flow: need field morning volumes for rank
        field=[]
        for r in race:
            tot+=1
            row=win.get((d,normalize_horse_name(str(r.get("horse_name") or ""))))
            if row: joined+=1
            field.append((r,row))
        vols=[(fnum(ci(rw,"morningtradedvol")) or 0) for _,rw in field if rw]
        for r,row in field:
            if not row: continue
            b=fnum(ci(row,"bsp")); mw=fnum(ci(row,"morningwap")); mv=fnum(ci(row,"morningtradedvol"))
            openp=fnum(ci(row,"ppmax"))  # proxy for early/open (widest pre-post)
            top3=int(r["actual_pos"])<=3
            if b and mw and mw>0:
                drift=b/mw
                volrank=(sum(1 for v in vols if v< (mv or 0))/max(1,len(vols)-1)) if mv is not None else None
                mf_rows.append((d, drift, volrank, top3, mw))
        for rank,r in enumerate(ranked[:2],1):
            row=win.get((d,normalize_horse_name(str(r.get("horse_name") or ""))))
            if not row: continue
            b=fnum(ci(row,"bsp")); mw=fnum(ci(row,"morningwap"))
            won=str(ci(row,"win_lose")).strip() in ("1","1.0")
            if b and mw:
                for lab in (f"{t} rank{rank}", f"ALL rank{rank}"):
                    bets[lab].append((str(race[0]["date"]),b,mw,won))
    print(f"join coverage: {100*joined/max(1,tot):.0f}% ({joined}/{tot} runners)\n")

    def roi(rows, price_idx):
        n=len(rows); w=sum(1 for x in rows if x[3])
        ret=sum((x[price_idx]-1)*(1-COMMISSION)+1 if x[3] else 0 for x in rows)
        return n,w,(ret/n-1 if n else 0)
    def boot(rows, price_idx, rng, it=2000):
        vals=[( (x[price_idx]-1)*(1-COMMISSION)+1 if x[3] else 0) for x in rows]
        if not vals: return (0,0)
        s=sorted(sum(rng.choices(vals,k=len(vals)))/len(vals)-1 for _ in range(it))
        return s[int(.025*it)],s[int(.975*it)]
    rng=random.Random(7)
    print(f"{'strategy':<14}{'bets':>5}{'strike':>7}{'ROI@BSP':>9}{'ROI@morn':>10}{'BSP 95%CI':>20}")
    for lab in ("tight rank1","clear rank1","medium rank1","ALL rank1","ALL rank2"):
        rows=bets[lab]
        if not rows: continue
        n,w,rb=roi(rows,1); _,_,rm=roi(rows,2); lo,hi=boot(rows,1,rng)
        print(f"{lab:<14}{n:>5}{100*w/n:>6.1f}%{100*rb:>+8.1f}%{100*rm:>+9.1f}%   [{100*lo:+.0f}%,{100*hi:+.0f}%]")

    # ---------- (2) money-flow retrodictive ----------
    print("\n--- money-flow retrodictive (does pre-race signal separate top-3?) ---")
    mf_rows=[x for x in mf_rows if x[2] is not None]
    dates=sorted({x[0] for x in mf_rows}); split=dates[len(dates)//2]
    for name,idx,hi_is_good in (("drift(BSP/morn)",1,None),("morning vol rank",2,True)):
        for half,lo,hiB in (("train","00-00",split),("valid",split,"99-99")):
            sub=[x for x in mf_rows if (x[0]<split if half=="train" else x[0]>=split)]
            hit=[x[idx] for x in sub if x[3]]; non=[x[idx] for x in sub if not x[3]]
            if hit and non:
                print(f"  {name:<18} {half:<6}: top3 mean {mean(hit):.3f}  non {mean(non):.3f}  Δ {mean(hit)-mean(non):+.3f}")

if __name__=="__main__":
    main()
