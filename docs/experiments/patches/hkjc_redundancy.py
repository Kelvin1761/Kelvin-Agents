#!/usr/bin/env python3
"""點解量得準嘅訊號落唔到排名？兩個可能：(a) 同現行分重複 (b) 正交但幅度太細。
喺 193 場真引擎語料上面直接量。"""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/CodexWork/wc-jt')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
from hkjc_racing_engine import engine_core as ec
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression

DIRS=sorted([Path(l.strip()) for l in open('/tmp/hkjc_bt.lst') if l.strip()])
BASE_PLACE=0.2437; EB_K=100.0; VENUE={}
_orig_ctx=ec.RacingEngine._apply_trainer_signal_context
_orig_combo=ec.RacingEngine._trainer_combo_adjustment
CAP=[]
def probe(self, fs):
    u,n=_orig_ctx(self,fs)
    t=self._clean(self.horse_data.get("trainer")); j=self._clean(self.horse_data.get("jockey"))
    v="沙田" if self._is_sha_tin_context() else "跑馬地"
    row=self._jockey_trainer_prior()
    if row is None and j and t:
        row=self._trainer_signal_priors().combo.get((j,t))
    starts=float((row or {}).get("starts",0) or 0); places=float((row or {}).get("places",0) or 0)
    CAP.append({"horse":self.horse_data.get("horse_no") or self.horse_data.get("hn"),
                "j":u.get("jockey_score",60.0),"t":u.get("trainer_score",60.0),
                "t_dv":VENUE.get((t,v),0.0),
                "c_edge":((places-starts*BASE_PLACE)/(starts+EB_K)) if starts>0 else 0.0})
    return u,n
def build_venue(sub):
    d=sub.copy(); d["Place"]=pd.to_numeric(d["Place"],errors="coerce").fillna(0.0)
    base=d.groupby("Venue").Place.mean().to_dict(); d["exp"]=d.Venue.map(base).fillna(BASE_PLACE)
    g=d.groupby("Trainer").agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
    ov={k:(r.obs-r.exp)/(r.n+EB_K) for k,r in g.iterrows()}
    gv=d.groupby(["Trainer","Venue"]).agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
    return {(str(t).strip(),str(v).strip()):((r.obs-r.exp)/(r.n+EB_K))-ov.get(t,0.0) for (t,v),r in gv.iterrows()}

ROWS=pb.load_all_rows()
ec.RacingEngine._apply_trainer_signal_context=probe
rows=[]
for md in DIRS:
    d=pb.meeting_date_from_dir(md)
    if not d: continue
    pb.inject_as_of(ROWS,d); VENUE=build_venue(ROWS[ROWS["Date"]<d])
    CAP.clear()
    races,_=bt.rescore_meeting(md,include_legacy=False)
    for race in races:
        ap=race["actual"]
        if not ap: continue
        top3={h for h,p in ap.items() if p<=3}
        for s in race["scored"]:
            rows.append({"ability":s["ability"],"hn":s["hn"],"placed":int(s["hn"] in top3),
                         "race":f"{md.name}|{id(race)}"})
    # 逐匹馬嘅 capture 同 scored 對唔返（rescore 內部另建 engine），改由 CAP 統計聚合
ec.RacingEngine._apply_trainer_signal_context=_orig_ctx
df=pd.DataFrame(rows)
cap=pd.DataFrame(CAP)   # 最後一個場次嘅逐匹馬特徵（做相關性用全語料版本喺下面）
print(f"runner 行 {len(df)}，場次 {df.race.nunique()}")
print(f"綜合分本身 place AUC = {roc_auc_score(df.placed, df.ability):.4f}")

# 全語料相關性：重跑一次，只收特徵（同一個 engine call 入面攞，所以逐匹馬對得返）
ALL=[]
def probe2(self, fs):
    u,n=_orig_ctx(self,fs)
    t=self._clean(self.horse_data.get("trainer")); j=self._clean(self.horse_data.get("jockey"))
    v="沙田" if self._is_sha_tin_context() else "跑馬地"
    row=self._jockey_trainer_prior()
    if row is None and j and t:
        row=self._trainer_signal_priors().combo.get((j,t))
    starts=float((row or {}).get("starts",0) or 0); places=float((row or {}).get("places",0) or 0)
    ALL.append({"j":u.get("jockey_score",60.0),"t":u.get("trainer_score",60.0),
                "t_dv":VENUE.get((t,v),0.0),
                "c_edge":((places-starts*BASE_PLACE)/(starts+EB_K)) if starts>0 else 0.0})
    return u,n
ec.RacingEngine._apply_trainer_signal_context=probe2
for md in DIRS:
    d=pb.meeting_date_from_dir(md)
    if not d: continue
    pb.inject_as_of(ROWS,d); VENUE=build_venue(ROWS[ROWS["Date"]<d])
    bt.rescore_meeting(md,include_legacy=False)
ec.RacingEngine._apply_trainer_signal_context=_orig_ctx
A=pd.DataFrame(ALL)
print(f"\n特徵行 {len(A)}")
print("相關性（同引擎現行分）：")
print(f"  練馬師場地 delta vs trainer_score  ρ = {A.t_dv.corr(A.t):+.4f}")
print(f"  練馬師場地 delta vs jockey_score   ρ = {A.t_dv.corr(A.j):+.4f}")
print(f"  組合超額     vs trainer_score  ρ = {A.c_edge.corr(A.t):+.4f}")
print(f"  組合超額     vs jockey_score   ρ = {A.c_edge.corr(A.j):+.4f}")
print(f"\n場地 delta 全距 {A.t_dv.min():+.4f} → {A.t_dv.max():+.4f}，SD {A.t_dv.std():.4f}")
print(f"換算成分數（×44）：全距 {44*A.t_dv.min():+.2f} → {44*A.t_dv.max():+.2f} 分，SD {44*A.t_dv.std():.2f}")
print(f"再乘 0.45（練馬師喺維度入面嘅份額）× 23.62%（維度權重）= 綜合分 SD {44*A.t_dv.std()*0.45*0.2362:.3f} 分")
print(f"對比：綜合分本身喺場內嘅 SD ≈ {df.groupby('race').ability.std().mean():.2f} 分")
