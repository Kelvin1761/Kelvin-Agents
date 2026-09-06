#!/usr/bin/env python3
"""改正：t_dv 幅度只有 ±0.08，sklearn 預設 L2（C=1.0）會將係數壓到接近零，
上一版嗰啲『CI 不跨零』其實係正則化假象。改用標準化 + 實質無罰則。"""
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
df=pd.read_csv('/tmp/hkjc_runner_ds.csv')
RACES=[g for _,g in df.groupby("race")]
def picks(k):
    out=[]
    for g in RACES:
        o=g.sort_values(["ability","hn"],ascending=[False,True])
        for rank,(_,r) in enumerate(o.head(k).iterrows(),1):
            out.append({"race":r.race,"rank":rank,"placed":r.placed,"won":r.won,"t_dv":r.t_dv})
    return pd.DataFrame(out)
SD=df.t_dv.std()
for k in (1,2,4):
    P=picks(k); X=((P[["t_dv"]].values)/SD); y=P.placed.values
    fit=lambda Xa,ya: LogisticRegression(max_iter=5000,C=1e6).fit(Xa,ya).coef_[0][0]
    b=fit(X,y)
    races=P.race.unique(); idx={r:np.where(P.race.values==r)[0] for r in races}
    rng=np.random.default_rng(0); co=[]
    for _ in range(2000):
        s=np.concatenate([idx[r] for r in rng.choice(races,len(races),replace=True)])
        if len(np.unique(y[s]))<2: continue
        co.append(fit(X[s],y[s]))
    co=np.array(co); lo,hi=np.percentile(co,[2.5,97.5])
    p=y.mean(); pp=100*b*p*(1-p)
    v="✅ 不跨零" if lo>0 else ("❌ 全負" if hi<0 else "➖ CI 跨零")
    print(f"頭{k}揀 (n={len(P)}): 標準化係數 {b:+.3f} [{lo:+.3f},{hi:+.3f}] {v}  ≈ 每 1 SD {pp:+.1f}pp")

print("\n重做置換檢定（1 SD 對比，唔用五分位量化）")
P=picks(1); y=P.placed.values; x=P.t_dv.values/SD
real=np.corrcoef(x,y)[0,1]
rng=np.random.default_rng(1)
null=np.array([np.corrcoef(rng.permutation(x),y)[0,1] for _ in range(5000)])
print(f"  真實 r = {real:+.4f}；置換 95% [{np.percentile(null,2.5):+.4f},{np.percentile(null,97.5):+.4f}]"
      f"  p = {(np.abs(null)>=abs(real)).mean():.3f} → {'✅ 顯著' if (np.abs(null)>=abs(real)).mean()<0.05 else '➖ 唔顯著'}")
