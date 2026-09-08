#!/usr/bin/env python3
"""Q1 A/B：騎練組合表示法。逐步拆開，每一步只郁一樣（feature-ablation）。

A0  baseline
A0b 空 leaf（常數 60，w=0.2）—— 純稀釋對照，量「加一個 leaf」本身嘅代價
A1  純去衰減：combo_adj ×1.980，仍然攤入 J/T（0.55²+0.45²=0.505 → 淨 ×1.0）
A2  獨立 leaf，幅度維持現行 0.505（w=0.101, k=5）—— 只換表示法
A3  獨立 leaf，全幅度（w=0.2, k=5）= A1+A2
A4  A3 + 連續化（EB shrink 上名率超額，SD 對齊離散版）
A5  A4 + 剷走 ≥40 仗門檻（EB shrink 本身處理細樣本）
"""
import os, sys, json, time
from pathlib import Path
import numpy as np
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/CodexWork/wc-jt')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import engine_core as ec, matrix_mapper as mm, scoring as sc

# 新 leaf 一定要有 label：`_feature_score_label` 用 `}[key]`（strict），
# 冇 label 嘅 leaf 會令每一場都 KeyError 而 rescore 靜靜回 0 場。
_orig_label = ec.RacingEngine._feature_score_label
def _label(self, key):
    if key == "jt_combo_score":
        return "騎練組合分"
    return _orig_label(self, key)
ec.RacingEngine._feature_score_label = _label

DIRS=[Path(l.strip()) for l in open('/tmp/hkjc_bt.lst') if l.strip()]
BASE_F={k:tuple(v) for k,v in mm.MATRIX_FORMULAS.items()}
_orig_combo=ec.RacingEngine._trainer_combo_adjustment
_orig_ctx=ec.RacingEngine._apply_trainer_signal_context
BASE_PLACE=0.2437        # 語料整體上名率（18,795 行實測）
EB_K=100.0
COMBO_G=None             # A4/A5 用，calibrate 之後填

def _combo_row(self):
    stack=self._trainer_signal_priors()
    j=self._clean(self.horse_data.get("jockey")); t=self._clean(self.horse_data.get("trainer"))
    row=self._jockey_trainer_prior()
    if row is None and j and t: row=stack.combo.get((j,t))
    return row

def _cont_edge(row, gate):
    if not row: return 0.0
    starts=float(row.get("starts",0) or 0)
    if starts<=0 or starts<gate: return 0.0
    places=float(row.get("places",0) or 0)
    return (places - starts*BASE_PLACE)/(starts+EB_K)

def make_ctx(*, leaf_w=0.0, leaf_k=5.0, adj_scale=1.0, continuous=False, gate=40.0, empty_leaf=False):
    """回傳一個 patched _apply_trainer_signal_context。"""
    def ctx(self, feature_scores):
        updated, note = _orig_ctx(self, feature_scores)
        if empty_leaf:
            updated["jt_combo_score"]=60.0
            return updated, note
        if leaf_w<=0 and adj_scale==1.0 and not continuous:
            return updated, note
        row=_combo_row(self)
        if continuous:
            adj = COMBO_G * _cont_edge(row, gate)
        else:
            adj = _orig_combo(self, row) if row else 0.0
        if leaf_w>0:
            # 由 J/T 抽返組合貢獻，改為擺入獨立 leaf
            base = _orig_combo(self, row) if row else 0.0
            js=base*sc.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_jockey_share"]
            ts=base*sc.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_trainer_share"]
            updated["jockey_score"]=sc.clip_score(updated.get("jockey_score",60.0)-js)
            updated["trainer_score"]=sc.clip_score(updated.get("trainer_score",60.0)-ts)
            updated["jt_combo_score"]=sc.clip_score(60.0+leaf_k*adj)
        else:
            base = _orig_combo(self, row) if row else 0.0
            extra=(adj-base)*adj_scale if continuous else base*(adj_scale-1.0)
            updated["jockey_score"]=sc.clip_score(updated.get("jockey_score",60.0)
                                                  +extra*sc.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_jockey_share"])
            updated["trainer_score"]=sc.clip_score(updated.get("trainer_score",60.0)
                                                  +extra*sc.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_trainer_share"])
        return updated, note
    return ctx

def set_formula(w):
    if w<=0:
        mm.MATRIX_FORMULAS["trainer_signal"]=BASE_F["trainer_signal"]
    else:
        mm.MATRIX_FORMULAS["trainer_signal"]=(("jockey_score",0.55*(1-w)),
                                              ("trainer_score",0.45*(1-w)),
                                              ("jt_combo_score",w))

def reset():
    mm.MATRIX_FORMULAS.clear(); mm.MATRIX_FORMULAS.update({k:tuple(v) for k,v in BASE_F.items()})
    ec.RacingEngine._apply_trainer_signal_context=_orig_ctx

# ── metrics ──────────────────────────────────────────────────────────────────
def race_flags(race):
    ap=race["actual"]
    if not ap: return None
    best=min(ap.values()); winners={h for h,p in ap.items() if p==best}
    top3={h for h,p in ap.items() if p<=3}
    order=[s["hn"] for s in sorted(race["scored"],key=lambda x:(-x["ability"],x["hn"]))]
    picks=order[:4]
    return {
        # canonical gold（合約）：實際前三全部喺 model Top 4
        "gold": float(len(top3)>0 and top3.issubset(set(picks))),
        "good_positional": float(len(picks)>=2 and picks[0] in top3 and picks[1] in top3),
        "gold_strict": float(sum(1 for x in picks[:3] if x in top3)==3),
        "min": float(sum(1 for x in picks[:3] if x in top3)>=2),
        "champion": float(bool(picks and picks[0] in winners)),
    }
MET=("gold","good_positional","gold_strict","min","champion")

def run(name, ctx=None, w=0.0):
    reset()
    if ctx is not None: ec.RacingEngine._apply_trainer_signal_context=ctx
    set_formula(w)
    races=[]
    for md in sorted(DIRS):
        d=pb.meeting_date_from_dir(md)
        if not d: continue
        pb.inject_as_of(ROWS,d)
        r,_=bt.rescore_meeting(md,include_legacy=False); races.extend(r)
    reset()
    flags=[f for f in (race_flags(r) for r in races) if f]
    return np.array([[f[m] for m in MET] for f in flags])

def paired(a,b,n=2000):
    rng=np.random.default_rng(0); N=len(a); out=[]
    for _ in range(n):
        s=rng.integers(0,N,N); out.append(b[s].mean(0)-a[s].mean(0))
    o=np.array(out)
    return o.mean(0), np.percentile(o,2.5,axis=0), np.percentile(o,97.5,axis=0)

t=time.time(); ROWS=pb.load_all_rows(); print("rows %.1fs"%(time.time()-t),flush=True)

# ── calibrate COMBO_G：令連續版同離散版喺同一語料上有同一個 SD（幅度對齊）───────
reset()
disc=[]; cont=[]
_probe={}
def probe_ctx(self, feature_scores):
    updated,note=_orig_ctx(self,feature_scores)
    row=_combo_row(self)
    disc.append(_orig_combo(self,row) if row else 0.0)
    cont.append(_cont_edge(row,40.0))
    return updated,note
ec.RacingEngine._apply_trainer_signal_context=probe_ctx
for md in sorted(DIRS):
    d=pb.meeting_date_from_dir(md)
    if not d: continue
    pb.inject_as_of(ROWS,d); bt.rescore_meeting(md,include_legacy=False)
reset()
disc=np.array(disc); cont=np.array(cont)
COMBO_G=float(disc.std()/cont.std()) if cont.std()>0 else 0.0
print(f"calibrate: n={len(disc)} runner；離散 SD {disc.std():.3f}，連續 edge SD {cont.std():.5f} → COMBO_G {COMBO_G:.2f}",flush=True)
print(f"           非零離散調整覆蓋 {np.mean(disc!=0)*100:.1f}%，連續非零 {np.mean(cont!=0)*100:.1f}%",flush=True)

ARMS=[
 ("A0  baseline", None, 0.0),
 ("A0b 空 leaf（純稀釋對照）", make_ctx(empty_leaf=True), 0.2),
 ("A1  純去衰減 ×1.980", make_ctx(adj_scale=1/0.505), 0.0),
 ("A2  獨立 leaf・幅度不變", make_ctx(leaf_w=0.101, leaf_k=5.0), 0.101),
 ("A3  獨立 leaf・全幅度", make_ctx(leaf_w=0.2, leaf_k=5.0), 0.2),
 ("A4  A3+連續化", make_ctx(leaf_w=0.2, leaf_k=5.0, continuous=True, gate=40.0), 0.2),
 ("A5  A4+剷走≥40門檻", make_ctx(leaf_w=0.2, leaf_k=5.0, continuous=True, gate=0.0), 0.2),
]
res={}
for name,ctx,w in ARMS:
    t=time.time(); res[name]=run(name,ctx,w)
    print(f"{name:<24} n={len(res[name])} "+" ".join(f"{m}={100*res[name][:,i].mean():5.2f}" for i,m in enumerate(MET))+f"  ({time.time()-t:.0f}s)",flush=True)

base=res["A0  baseline"]
print("\n配對 race bootstrap（2000 次，vs A0）")
for name,_,_ in ARMS[1:]:
    d,lo,hi=paired(base,res[name])
    parts=[]
    for i,m in enumerate(MET[:2]):
        v="✅" if lo[i]>0 else ("❌" if hi[i]<0 else "➖")
        parts.append(f"{m} {100*d[i]:+5.2f}pp [{100*lo[i]:+5.2f},{100*hi[i]:+5.2f}] {v}")
    print(f"  {name:<24} "+" | ".join(parts))
print("\n§6 閘門 MDE（193 場，95% CI 半寬）")
d,lo,hi=paired(base,base)
for i,m in enumerate(MET[:2]):
    hw=100*(np.percentile([np.random.default_rng(s).choice(base[:,i],len(base)).mean() for s in range(2000)],97.5)
            -np.percentile([np.random.default_rng(s).choice(base[:,i],len(base)).mean() for s in range(2000)],2.5))/2
    print(f"  {m}: baseline {100*base[:,i].mean():.2f}%  半寬 ≈ {hw:.2f}pp")
np.save('/tmp/hkjc_combo_arms.npy', np.array([res[n] for n,_,_ in ARMS]))
json.dump({n:{m:float(100*res[n][:,i].mean()) for i,m in enumerate(MET)} for n,_,_ in ARMS},
          open('/tmp/hkjc_combo_ab.json','w'),indent=1,ensure_ascii=False)
