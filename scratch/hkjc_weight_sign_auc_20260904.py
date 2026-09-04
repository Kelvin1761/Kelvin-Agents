#!/usr/bin/env python3
"""Power-adequate A/B: within-race AUC (ability vs top-3) + paired bootstrap by race.

193 race-level binary outcomes cannot resolve a 5%-weight leaf: a 1.5pp move on
`good` is three races. Within-race concordance uses every runner pair, and the
bootstrap is paired on the SAME races so the arms share all other noise.
"""
import os, sys, json, random, statistics as st
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/Antigravity-repo')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import matrix_mapper as mm, engine_core as ec
from hkjc_racing_engine.scoring import clip_score, parse_float

DIRS=[Path(l.rstrip('\n')) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
BASE={k:tuple(v) for k,v in mm.MATRIX_FORMULAS.items()}
_ow=ec.RacingEngine._weight_score

def flip():
    def f(self,_):
        w=parse_float(self._value("weight_carried") or self._value("weight")); t=self._text("weight_trend")
        if w is None: return 60,"負磅資料不足。","missing_neutral"
        s=54.0 if w<=120 else (70.0 if w>=132 else 64.0)
        if "轉輕" in t: s+=4.0
        if "轉重" in t: s-=4.0
        return clip_score(s),"",  "weight_carried"
    ec.RacingEngine._weight_score=f
def neutral():
    ec.RacingEngine._weight_score=lambda self,_:(60.0,"","weight_carried")
def reset():
    mm.MATRIX_FORMULAS.clear(); mm.MATRIX_FORMULAS.update({k:tuple(v) for k,v in BASE.items()})
    ec.RacingEngine._weight_score=_ow

def race_auc(race):
    ap=race["actual"]; top3={h for h,p in ap.items() if p<=3}
    pos=[s["ability"] for s in race["scored"] if s["hn"] in top3]
    neg=[s["ability"] for s in race["scored"] if s["hn"] in ap and s["hn"] not in top3]
    if not pos or not neg: return None
    c=sum((1.0 if a>b else 0.5 if a==b else 0.0) for a in pos for b in neg)
    return c/(len(pos)*len(neg))

def collect(setup):
    reset(); setup()
    out={}
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d)
        races,_=bt.rescore_meeting(md,include_legacy=False)
        for i,r in enumerate(races): out[(md.name,i)]=r
    return out

ROWS=pb.load_all_rows()
ARMS={"W0 baseline":lambda:None,"W2 weight neutral":neutral,"W3 weight flipped":flip}
data={k:collect(v) for k,v in ARMS.items()}
reset()
keys=sorted(set.intersection(*[set(d) for d in data.values()]))
auc={k:{q:race_auc(d[q]) for q in keys} for k,d in data.items()}
keys=[q for q in keys if all(auc[k][q] is not None for k in ARMS)]
print("paired races: %d"%len(keys))
for k in ARMS: print("  %-20s within-race AUC = %.4f"%(k,st.mean(auc[k][q] for q in keys)))
random.seed(20260904)
for cand in ("W2 weight neutral","W3 weight flipped"):
    d=[auc[cand][q]-auc["W0 baseline"][q] for q in keys]
    boots=[st.mean(random.choices(d,k=len(d))) for _ in range(4000)]
    boots.sort(); lo,hi=boots[100],boots[3900]
    moved=sum(1 for x in d if abs(x)>1e-9)
    print("\n%s − baseline: ΔAUC %+.4f  95%% CI [%+.4f, %+.4f]  (%d/%d races moved)"%(
        cand,st.mean(d),lo,hi,moved,len(d)))
    print("   verdict: %s"%("IMPROVES (CI all positive)" if lo>0 else
                            "WORSE (CI all negative)" if hi<0 else "CI spans zero — not resolvable"))
