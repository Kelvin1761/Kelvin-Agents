#!/usr/bin/env python3
"""A/B 馬匹健康/新鮮感：剷走負磅分，同修體重變幅嘅方向。

實測（16,959 個有上仗體重嘅 runner-start）：
  長休 >75 日：回來重咗(>+5lb) − 輕咗(<-5lb) 上名率 **+7.9pp, CI [+2.1,+13.7]**
  短休 ≤75 日：同一個對比           −0.6pp, CI [-2.5,+1.2]（跨零＝冇訊號）
  長休 >75 日 − 正常間隔 21-75 日     −3.7pp, CI [-6.4,-1.0]（長休罰分係啱嘅）
  急放 ≤20 日 − 正常間隔             −1.3pp, CI 跨零（急放調整冇支持）
即係：**長休罰分要留，體重變幅罰分喺短休冇訊號、喺長休方向反**。
"""
import os, sys, json, re
from pathlib import Path
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/CodexWork/wc-health')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import matrix_mapper as mm, engine_core as ec
from hkjc_racing_engine import scoring as sc

DIRS=[Path(l.rstrip('\n')) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
BASE_F={k:tuple(v) for k,v in mm.MATRIX_FORMULAS.items()}
BASE_W=dict(sc.HORSE_HEALTH_CONTEXT_WEIGHTS)
_orig_ctx=ec.RacingEngine._candidate_health_risk_score

def drop_weight_leaf():
    """負磅分場內 AUC 0.4630（弱過擲毫）；Kelvin 亦指出佢既唔係健康亦唔係新鮮感。"""
    mm.MATRIX_FORMULAS["horse_health"]=(("risk_score",1.00),)

def bodyweight_inert():
    """短休嘅體重變幅冇訊號（CI 跨零）→ 熄咗四個變幅項。"""
    for k in ("weight_micro_bonus","weight_sharp_change_pen","weight_drop_pen","weight_gain_pen"):
        sc.HORSE_HEALTH_CONTEXT_WEIGHTS[k]=0.0

def bodyweight_conditioned():
    """長休回來重咗係好事（+7.9pp, CI 不跨零）；短休冇訊號。
    所以：短休 → 冇調整；長休 → 重咗加分、輕咗扣分。"""
    for k in ("weight_micro_bonus","weight_sharp_change_pen","weight_drop_pen","weight_gain_pen"):
        sc.HORSE_HEALTH_CONTEXT_WEIGHTS[k]=0.0
    def ctx(self):
        score,note=_orig_ctx(self)
        days=self._days_since_last()
        seq=[int(x) for x in re.findall(r"\d{3,4}", self._text("weight_trend"))]
        if days is not None and days > 75 and len(seq) >= 2:
            delta=seq[0]-seq[1]          # 今仗 − 上仗
            if delta > 5:
                score=sc.clip_score(score+3.0)
                note+="長休後回來體重增加，實測係正面訊號（+7.9pp）。"
            elif delta < -5:
                score=sc.clip_score(score-3.0)
                note+="長休後回來體重下降，實測係負面訊號。"
        return score,note
    ec.RacingEngine._candidate_health_risk_score=ctx

def reset():
    mm.MATRIX_FORMULAS.clear(); mm.MATRIX_FORMULAS.update({k:tuple(v) for k,v in BASE_F.items()})
    sc.HORSE_HEALTH_CONTEXT_WEIGHTS.clear(); sc.HORSE_HEALTH_CONTEXT_WEIGHTS.update(BASE_W)
    ec.RacingEngine._candidate_health_risk_score=_orig_ctx

ARMS=[("H0 baseline",           []),
      ("H1 剷走負磅分",            [drop_weight_leaf]),
      ("H2 體重變幅熄咗",           [bodyweight_inert]),
      ("H3 體重變幅按長休條件化",       [bodyweight_conditioned]),
      ("H4 H1+H3",             [drop_weight_leaf,bodyweight_conditioned])]
ROWS=pb.load_all_rows(); out={}
for name,setups in ARMS:
    reset()
    for s in setups: s()
    races=[]
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d)
        r,_=bt.rescore_meeting(md,include_legacy=False); races.extend(r)
    agg=bt.evaluate(races); n=agg['races'] or 1
    out[name]={m:round(100*agg[m]/n,2) for m in bt.METRICS}
    print('%-22s races=%3d  '%(name,agg['races'])+'  '.join('%s=%5.2f'%(m,100*agg[m]/n) for m in bt.METRICS),flush=True)
reset(); json.dump(out,open('/tmp/ab_health.json','w'),indent=1)
