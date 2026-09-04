#!/usr/bin/env python3
"""A/B: give 級數優勢 a real in-race class signal (official rating).

Blends into _class_score itself so no new MATRIX_FORMULAS key is introduced
(a key absent from feature_scores silently reads 60 — see
matrix_mapper._component_score — which would fake a null result)."""
import os, sys, json, statistics as st
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/Antigravity-repo')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb
import rescore_backtest as bt
from hkjc_racing_engine import matrix_mapper as mm
from hkjc_racing_engine import engine_core as ec
from hkjc_racing_engine.scoring import clip_score, parse_float

DIRS=[Path(l.rstrip('\n')) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
BASE={k:tuple(v) for k,v in mm.MATRIX_FORMULAS.items()}
_ow=ec.RacingEngine._weight_score
_oc=ec.RacingEngine._class_score
_orig_rescore=bt.rescore_logic
CFG={}

def _inject(logic,**kw):
    ctx=logic.setdefault("race_analysis",{})
    ctx["field_ratings"]={str(n):float((h.get("_data") or {}).get("current_rating"))
        for n,h in (logic.get("horses") or {}).items()
        if isinstance(h,dict) and isinstance((h.get("_data") or {}).get("current_rating"),(int,float))}
    return _orig_rescore(logic,**kw)
bt.rescore_logic=_inject

COV={"hit":0,"miss":0}
def rating_score(self):
    field=[v for v in ((self.race_context or {}).get("field_ratings") or {}).values()]
    mine=parse_float((self.horse_data.get("_data") or {}).get("current_rating"))
    if mine is None or len(field)<2:
        COV["miss"]+=1; return None
    COV["hit"]+=1
    if CFG.get("mode")=="linear":
        return clip_score(60.0+CFG["k"]*(mine-st.mean(field)))
    below=sum(1 for v in field if v<mine)+0.5*sum(1 for v in field if v==mine)
    return clip_score(45.0+30.0*(below/len(field)))

def make_class(w_rating):
    def f(self,_features):
        cs,note,src=_oc(self,_features)
        rs=rating_score(self)
        if rs is None: return cs,note,src
        blended=(1.0-w_rating)*cs+w_rating*rs
        return blended,f"{note}；場內官方評分 {rs:.0f} 分（權重 {w_rating:.0%}）","career_context+rating"
    return f

def flip_weight():
    def f(self,_features):
        w=parse_float(self._value("weight_carried") or self._value("weight"))
        t=self._text("weight_trend")
        if w is None: return 60,"負磅資料不足，負磅分60分。","missing_neutral"
        s=54.0 if w<=120 else (70.0 if w>=132 else 64.0)
        if "轉輕" in t: s+=4.0
        if "轉重" in t: s-=4.0
        return clip_score(s),f"今仗負磅{w:.0f}磅，負磅分{clip_score(s):.0f}分。","weight_carried"
    ec.RacingEngine._weight_score=f

def reset():
    mm.MATRIX_FORMULAS.clear(); mm.MATRIX_FORMULAS.update({k:tuple(v) for k,v in BASE.items()})
    ec.RacingEngine._weight_score=_ow; ec.RacingEngine._class_score=_oc
    CFG.clear(); CFG.update({"mode":"percentile","k":1.0})

def A_base(): pass
def A_pct(w,nodouble=False,flip=False):
    def go():
        ec.RacingEngine._class_score=make_class(w)
        if nodouble: mm.MATRIX_FORMULAS["class_advantage"]=(("class_score",1.00),)
        if flip: flip_weight()
    return go
def A_lin(w,k):
    def go():
        CFG.update({"mode":"linear","k":k}); ec.RacingEngine._class_score=make_class(w)
    return go

ARMS=[
 ("W0 baseline",                A_base),
 ("R1 rating 25% (pct)",        A_pct(0.25)),
 ("R2 rating 50% (pct)",        A_pct(0.50)),
 ("R3 rating 100% (pct)",       A_pct(1.00)),
 ("R4 rating 50% linear k=1.0", A_lin(0.50,1.0)),
 ("R5 rating 50% linear k=0.6", A_lin(0.50,0.6)),
 ("R6 R2 + no double-count",    A_pct(0.50,nodouble=True)),
 ("R7 R2 + weight flipped",     A_pct(0.50,flip=True)),
 ("R8 R3 + no double-count",    A_pct(1.00,nodouble=True)),
]

rows=pb.load_all_rows(); out={}
for name,setup in ARMS:
    reset(); COV.update({"hit":0,"miss":0}); setup()
    races=[]
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(rows,d)
        r,_=bt.rescore_meeting(md,include_legacy=False); races.extend(r)
    agg=bt.evaluate(races); n=agg["races"] or 1
    cov=100*COV["hit"]/max(1,COV["hit"]+COV["miss"])
    out[name]={m:round(100*agg[m]/n,2) for m in bt.METRICS}|{"races":agg["races"],"rating_cov":round(cov,1)}
    print("%-30s races=%3d cov=%4.1f%%  "%(name,agg["races"],cov)+"  ".join("%s=%5.2f"%(m,100*agg[m]/n) for m in bt.METRICS),flush=True)
reset(); json.dump(out,open('/tmp/ab_class.json','w'),indent=1)
