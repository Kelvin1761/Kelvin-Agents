#!/usr/bin/env python3
"""§6 部件預算：將騎練組合訊號完全中性化，量呢個部件喺閘門上面嘅「總身家」。
部件預算 < 閘門 MDE → 呢把尺對呢個候選係非資訊性（UNRESOLVABLE，唔係 REJECT）。"""
import os, sys, json
from pathlib import Path
import numpy as np
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/CodexWork/wc-jt')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import engine_core as ec
DIRS=sorted([Path(l.strip()) for l in open('/tmp/hkjc_bt.lst') if l.strip()])
_orig=ec.RacingEngine._trainer_combo_adjustment
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
            float(h3==3), float(h3>=2), float(bool(picks and picks[0] in winners))]
def run(fn):
    ec.RacingEngine._trainer_combo_adjustment = fn
    races=[]
    for md in DIRS:
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d)
        r,_=bt.rescore_meeting(md,include_legacy=False); races.extend(r)
    ec.RacingEngine._trainer_combo_adjustment=_orig
    return np.array([f for f in (flags(r) for r in races) if f])
ROWS=pb.load_all_rows()
base=run(_orig); off=run(lambda self,row: 0.0)
rng=np.random.default_rng(0); N=len(base); o=[]
for _ in range(2000):
    s=rng.integers(0,N,N); o.append(off[s].mean(0)-base[s].mean(0))
o=np.array(o); d=o.mean(0); lo=np.percentile(o,2.5,0); hi=np.percentile(o,97.5,0)
print(f"n={N} 場")
for i,m in enumerate(MET):
    hw=(hi[i]-lo[i])/2*100
    print(f"  {m:<16} baseline {100*base[:,i].mean():5.2f}%  完全剷走組合 Δ {100*d[i]:+5.2f}pp  預算 |Δ|={abs(100*d[i]):4.2f}pp  閘門半寬 {hw:4.2f}pp  → {'✅ 睇得到' if abs(100*d[i])>hw else '❌ 閘門睇唔到'}")
json.dump({"base":base.mean(0).tolist(),"off":off.mean(0).tolist()},open('/tmp/hkjc_budget.json','w'))
