#!/usr/bin/env python3
"""Q2 A/B：練馬師 × 場地（沙田／跑馬地）。Point-in-time，逐個賽日只用當日之前嘅行。

先量部件預算（§6）：現行「練馬師同程」完全熄咗，閘門睇唔睇到？
再試四個 arm。
"""
import os, sys, json
from pathlib import Path
import numpy as np, pandas as pd
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/CodexWork/wc-jt')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import engine_core as ec, matrix_mapper as mm, scoring as sc

DIRS=sorted([Path(l.strip()) for l in open('/tmp/hkjc_bt.lst') if l.strip()])
BASE_F={k:tuple(v) for k,v in mm.MATRIX_FORMULAS.items()}
_orig_ctx=ec.RacingEngine._apply_trainer_signal_context
_orig_tdist=ec.RacingEngine._trainer_distance_adjustment
_orig_label=ec.RacingEngine._feature_score_label
def _label(self,key):
    return "練馬師場地分" if key=="trainer_venue_score" else _orig_label(self,key)
ec.RacingEngine._feature_score_label=_label

BASE_PLACE=0.2437; EB_K=100.0
VENUE_DELTA={}          # (trainer, venue) -> edge delta（每個賽日重建）

def build_venue(sub):
    """練馬師場地 delta：EB shrink 過嘅『場地上名率超額』減『整體上名率超額』。"""
    d=sub.copy()
    d["Place"]=pd.to_numeric(d["Place"],errors="coerce").fillna(0.0)
    base=d.groupby("Venue").Place.mean().to_dict()     # 場地基準（馬匹數唔同）
    d["exp"]=d.Venue.map(base).fillna(BASE_PLACE)
    g=d.groupby("Trainer").agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
    overall={k:(r.obs-r.exp)/(r.n+EB_K) for k,r in g.iterrows()}
    gv=d.groupby(["Trainer","Venue"]).agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
    out={}
    for (t,v),r in gv.iterrows():
        out[(str(t).strip(),str(v).strip())]=((r.obs-r.exp)/(r.n+EB_K))-overall.get(t,0.0)
    return out

def _venue_key(self):
    return "沙田" if self._is_sha_tin_context() else "跑馬地"

def venue_delta(self):
    t=self._clean(self.horse_data.get("trainer"))
    return VENUE_DELTA.get((t,_venue_key(self)),0.0) if t else 0.0

def tiers(d):
    """離散版，門檻對齊現行『練馬師同程』嘅 ±2/±1/−1.5 幅度。"""
    if d>=0.020: return 2.0
    if d>=0.008: return 1.0
    if d<=-0.020: return -1.5
    return 0.0

def make(kind, g=1.0, drop_dist=False):
    def ctx(self, feature_scores):
        updated,note=_orig_ctx(self,feature_scores)
        d=venue_delta(self)
        adj = tiers(d) if kind=="tier" else g*d
        if kind=="leaf":
            updated["trainer_venue_score"]=sc.clip_score(60.0+g*d)
        else:
            updated["trainer_score"]=sc.clip_score(updated.get("trainer_score",60.0)+adj)
        return updated,note
    return ctx

MET=("gold","good_positional","gold_strict","min","champion")
def flags(race):
    ap=race["actual"]
    if not ap: return None
    best=min(ap.values()); winners={h for h,p in ap.items() if p==best}
    top3={h for h,p in ap.items() if p<=3}
    order=[s["hn"] for s in sorted(race["scored"],key=lambda x:(-x["ability"],x["hn"]))]
    picks=order[:4]; h3=sum(1 for x in picks[:3] if x in top3)
    return [float(len(top3)>0 and top3.issubset(set(picks))),
            float(len(picks)>=2 and picks[0] in top3 and picks[1] in top3),
            float(h3==3),float(h3>=2),float(bool(picks and picks[0] in winners))]

def reset():
    mm.MATRIX_FORMULAS.clear(); mm.MATRIX_FORMULAS.update({k:tuple(v) for k,v in BASE_F.items()})
    ec.RacingEngine._apply_trainer_signal_context=_orig_ctx
    ec.RacingEngine._trainer_distance_adjustment=_orig_tdist

def run(ctx=None, leaf_w=0.0, kill_dist=False):
    global VENUE_DELTA
    reset()
    if ctx is not None: ec.RacingEngine._apply_trainer_signal_context=ctx
    if kill_dist: ec.RacingEngine._trainer_distance_adjustment=lambda self,row: 0.0
    if leaf_w>0:
        mm.MATRIX_FORMULAS["trainer_signal"]=(("jockey_score",0.55*(1-leaf_w)),
                                              ("trainer_score",0.45*(1-leaf_w)),
                                              ("trainer_venue_score",leaf_w))
    races=[]
    for md in DIRS:
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d)
        VENUE_DELTA=build_venue(ROWS[ROWS["Date"]<d])
        r,_=bt.rescore_meeting(md,include_legacy=False); races.extend(r)
    reset()
    return np.array([f for f in (flags(x) for x in races) if f])

def paired(a,b,n=2000):
    rng=np.random.default_rng(0); N=len(a); o=[]
    for _ in range(n):
        s=rng.integers(0,N,N); o.append(b[s].mean(0)-a[s].mean(0))
    o=np.array(o); return o.mean(0),np.percentile(o,2.5,0),np.percentile(o,97.5,0)

ROWS=pb.load_all_rows()
base=run()
print("A0 baseline        "+" ".join(f"{m}={100*base[:,i].mean():5.2f}" for i,m in enumerate(MET)),flush=True)

print("\n§6 部件預算：熄咗現行『練馬師同程』（同一位置嘅可比部件）")
nod=run(kill_dist=True)
d,lo,hi=paired(base,nod)
for i,m in enumerate(MET[:3]):
    hw=(hi[i]-lo[i])/2*100
    print(f"  {m:<16} Δ {100*d[i]:+5.2f}pp  預算 {abs(100*d[i]):4.2f}pp vs 閘門半寬 {hw:4.2f}pp → {'✅ 睇得到' if abs(100*d[i])>hw else '❌ 閘門睇唔到'}")

ARMS=[("B1 場地離散 ±2/±1/−1.5", make("tier"), 0.0, False),
      ("B2 場地連續 ×44（幅度對齊）", make("cont", g=44.0), 0.0, False),
      ("B3 場地連續 ×88（雙倍）", make("cont", g=88.0), 0.0, False),
      ("B4 場地連續，同時熄同程", make("cont", g=44.0), 0.0, True),
      ("B5 場地做獨立 leaf w=0.1", make("leaf", g=440.0), 0.1, False)]
res={"A0":base}
for name,ctx,w,kd in ARMS:
    res[name]=run(ctx,w,kd)
    print(f"{name:<24} "+" ".join(f"{m}={100*res[name][:,i].mean():5.2f}" for i,m in enumerate(MET)),flush=True)
print("\n配對 race bootstrap vs A0")
for name,_,_,_ in ARMS:
    d,lo,hi=paired(base,res[name])
    parts=[]
    for i,m in enumerate(MET[:2]):
        v="✅" if lo[i]>0 else ("❌" if hi[i]<0 else "➖")
        parts.append(f"{m} {100*d[i]:+5.2f}pp [{100*lo[i]:+5.2f},{100*hi[i]:+5.2f}] {v}")
    print(f"  {name:<24} "+" | ".join(parts))
json.dump({k:[float(x) for x in v.mean(0)] for k,v in res.items()},open('/tmp/hkjc_venue_ab.json','w'),ensure_ascii=False,indent=1)
