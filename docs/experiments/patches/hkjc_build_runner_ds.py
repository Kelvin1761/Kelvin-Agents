#!/usr/bin/env python3
"""砌一個 runner-level 資料集（193 場 / 2,438 匹），之後所有「擺邊度」嘅測試都
喺呢個資料集上面跑，唔使每次重新評分。PIT：先驗只用當日之前嘅行。"""
import os, sys, json
from pathlib import Path
import numpy as np, pandas as pd
os.environ.setdefault("PYTHONDONTWRITEBYTECODE","1")
R=Path('/Users/imac/CodexWork/wc-jt2')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts','.agents/scripts',
          '.agents/skills/shared_racing/scripts',
          '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'):
    sys.path.insert(0,str(R/p))
import pit_backtest as pb, rescore_backtest as bt
DIRS=sorted([Path(l.strip()) for l in open('/tmp/hkjc_bt.lst') if l.strip()])
BASE_PLACE=0.2437; EB_K=100.0

def build_venue(sub):
    d=sub.copy(); d["Place"]=pd.to_numeric(d["Place"],errors="coerce").fillna(0.0)
    base=d.groupby("Venue").Place.mean().to_dict(); d["exp"]=d.Venue.map(base).fillna(BASE_PLACE)
    g=d.groupby("Trainer").agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
    ov={k:(r.obs-r.exp)/(r.n+EB_K) for k,r in g.iterrows()}
    gv=d.groupby(["Trainer","Venue"]).agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
    delta={}; nstarts={}
    for (t,v),r in gv.iterrows():
        key=(str(t).strip(),str(v).strip())
        delta[key]=((r.obs-r.exp)/(r.n+EB_K))-ov.get(t,0.0); nstarts[key]=r.n
    return delta, nstarts

ROWS=pb.load_all_rows()
rows=[]
for md in DIRS:
    mdate=pb.meeting_date_from_dir(md)
    if not mdate: continue
    venue = "沙田" if "ShaTin" in md.name else "跑馬地"
    pb.inject_as_of(ROWS,mdate)
    VD,VN=build_venue(ROWS[ROWS["Date"]<mdate])
    try: rp=bt.find_results_json(md)
    except ValueError: continue
    if rp is None or bt.meeting_is_legacy_schema(md): continue
    actual=bt.load_results(rp)
    for lp in sorted(md.glob("Race_*_Logic.json"), key=bt.race_num_from_path):
        rn=bt.race_num_from_path(lp)
        if rn not in actual: continue
        logic=json.loads(lp.read_text(encoding="utf-8"))
        bt.resolve_meeting_context(logic, md)
        try: rescored=bt.rescore_logic(logic)
        except Exception: continue
        ap=actual[rn]
        if not ap: continue
        top3={h for h,p in ap.items() if p<=3}
        best=min(ap.values()); winners={h for h,p in ap.items() if p==best}
        for hn_text,h in rescored.get("horses",{}).items():
            try: hn=int(hn_text)
            except ValueError: continue
            auto=h.get("python_auto") or {}
            if "ability_score" not in auto: continue
            trainer=str(h.get("trainer") or (h.get("_data") or {}).get("trainer") or "").strip()
            jockey=str(h.get("jockey") or (h.get("_data") or {}).get("jockey") or "").strip()
            feats=auto.get("feature_scores") or {}
            ms=auto.get("matrix_scores") or {}
            rows.append({
              "meeting":md.name,"date":mdate,"venue":venue,"race":f"{md.name}|{rn}","hn":hn,
              "trainer":trainer,"jockey":jockey,
              "ability":float(auto["ability_score"]),
              "ability_raw":float(auto.get("ability_score_raw") or auto["ability_score"]),
              "trainer_signal":float(ms.get("trainer_signal",60.0)),
              "jockey_score":float(feats.get("jockey_score",60.0)),
              "trainer_score":float(feats.get("trainer_score",60.0)),
              "t_dv":float(VD.get((trainer,venue),0.0)),
              "t_dv_n":float(VN.get((trainer,venue),0.0)),
              "placed":int(hn in top3),"won":int(hn in winners),
            })
df=pd.DataFrame(rows)
df.to_csv('/tmp/hkjc_runner_ds.csv',index=False)
print(f"{len(df)} runner / {df.race.nunique()} 場 / {df.meeting.nunique()} 個場次")
print("練馬師名解析:", (df.trainer!="").mean()*100, "%")
print("場地 delta 非零:", (df.t_dv!=0).mean()*100, "%")
print(df[["ability","t_dv","t_dv_n"]].describe().round(4).to_string())
