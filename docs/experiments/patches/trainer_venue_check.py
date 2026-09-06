"""Q2 深一層：練馬師場地 delta 係咪只係『練馬師同程』嘅影子？
（trainer_distance 已經入咗現行引擎，跑馬地／沙田距離分佈唔同）"""
import pandas as pd, numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
ROOT=Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database/comprehensive_stats")
m=pd.read_csv(ROOT/"all_race_results_master.csv"); m=m[m.Rank!=99].copy().sort_values("Date").reset_index(drop=True)
base=m.groupby("Venue").Place.mean(); m["exp"]=m.Venue.map(base); K=100.0
dates=sorted(m.Date.unique()); start=[i for i,d in enumerate(dates) if d>="2025-09-01"][0]
rows=[]
for d in dates[start:]:
    hist=m[m.Date<d]; today=m[m.Date==d]
    if len(hist)<3000: continue
    def edg(keys):
        g=hist.groupby(keys).agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
        return ((g.obs-g.exp)/(g.n+K)).to_dict(), g.n.to_dict()
    jo,_=edg(["Jockey"]); to,_=edg(["Trainer"])
    tv,tvn=edg(["Trainer","Venue"]); td,_=edg(["Trainer","Distance"])
    ttr,_=edg(["Trainer","Track"])
    for _,r in today.iterrows():
        t_all=to.get(r.Trainer,0.0)
        rows.append({"Place":r.Place,"race":f"{d}|{r.RaceNo}","Venue":r.Venue,
            "j":jo.get(r.Jockey,0.0),"t":t_all,
            "t_dv":tv.get((r.Trainer,r.Venue),0.0)-t_all,
            "t_dd":td.get((r.Trainer,r.Distance),0.0)-t_all,
            "t_dt":ttr.get((r.Trainer,r.Track),0.0)-t_all,
            "n_tv":tvn.get((r.Trainer,r.Venue),0)})
df=pd.DataFrame(rows); y=df.Place.values
def fit(c): return LogisticRegression(max_iter=1000).fit(df[c],y).predict_proba(df[c])[:,1]
def bs(p0,p1,n=400):
    races=df.race.unique(); idx={r:np.where(df.race.values==r)[0] for r in races}
    rng=np.random.default_rng(0); o=[]
    for _ in range(n):
        s=np.concatenate([idx[r] for r in rng.choice(races,len(races),replace=True)])
        o.append(roc_auc_score(y[s],p1[s])-roc_auc_score(y[s],p0[s]))
    return np.mean(o),np.percentile(o,2.5),np.percentile(o,97.5)
tests=[(["j","t"],["t_dd"],"練馬師同程 delta（現行已有）"),
       (["j","t"],["t_dv"],"練馬師場地 delta"),
       (["j","t","t_dd"],["t_dv"],"場地 delta 加喺同程 delta 之上"),
       (["j","t","t_dv"],["t_dd"],"同程 delta 加喺場地 delta 之上"),
       (["j","t"],["t_dt"],"練馬師跑道 delta（草地/全天候）"),
       (["j","t","t_dv"],["t_dt"],"跑道 delta 加喺場地 delta 之上")]
for b,a,label in tests:
    mean,lo,hi=bs(fit(b),fit(b+a))
    v="✅ 顯著" if lo>0 else ("❌ 顯著負" if hi<0 else "➖ CI 跨零")
    print(f"  {label:<28} Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {v}")
print(f"\n練馬師×場地 有記錄覆蓋: {(df.n_tv>0).mean()*100:.1f}% / ≥50 仗 {(df.n_tv>=50).mean()*100:.1f}% / ≥100 仗 {(df.n_tv>=100).mean()*100:.1f}%")
print("t_dv 分佈 (上名率超額，場地相對自己整體):")
print(df.t_dv.describe([.05,.25,.5,.75,.95]).round(4).to_string())
