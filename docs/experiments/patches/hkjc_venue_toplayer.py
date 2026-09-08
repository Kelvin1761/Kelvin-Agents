#!/usr/bin/env python3
"""兩個確認：
 (1) 控制咗綜合分之後，場地 delta 喺揀馬層仲有冇效（先解決『係咪只係綜合分嘅影子』）
 (2) 只喺 model top-4 出手嘅排名變體（效果集中喺頂，就唔好全場撒）"""
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
df=pd.read_csv('/tmp/hkjc_runner_ds.csv'); SD=df.t_dv.std()
RACES=[g for _,g in df.groupby("race")]
rows=[]
for g in RACES:
    o=g.sort_values(["ability","hn"],ascending=[False,True]).reset_index(drop=True)
    for i,r in o.iterrows():
        rows.append({"race":r.race,"rank":i+1,"placed":r.placed,"won":r.won,
                     "t_dv":r.t_dv/SD,"ability":r.ability,
                     "ab_z":(r.ability-g.ability.mean())/(g.ability.std() or 1)})
P=pd.DataFrame(rows)

def fit_ci(sub, cols, label):
    X=sub[cols].values; y=sub.placed.values
    f=lambda Xa,ya: LogisticRegression(max_iter=5000,C=1e6).fit(Xa,ya).coef_[0]
    b=f(X,y)
    races=sub.race.unique(); idx={r:np.where(sub.race.values==r)[0] for r in races}
    rng=np.random.default_rng(0); co=[]
    for _ in range(2000):
        s=np.concatenate([idx[r] for r in rng.choice(races,len(races),replace=True)])
        if len(np.unique(y[s]))<2: continue
        co.append(f(X[s],y[s]))
    co=np.array(co)
    i=cols.index("t_dv"); lo,hi=np.percentile(co[:,i],[2.5,97.5])
    p=y.mean()
    v="✅" if lo>0 else ("❌" if hi<0 else "➖ CI 跨零")
    print(f"  {label:<28} n={len(sub):>4}  t_dv 係數 {b[i]:+.3f} [{lo:+.3f},{hi:+.3f}] {v}"
          f"  ≈ 每 1 SD {100*b[i]*p*(1-p):+.1f}pp")

print("=== 1. 控制綜合分之後，場地 delta 仲有冇效")
for k,label in ((1,"頭1揀"),(2,"頭2揀"),(4,"頭4揀"),(99,"全場")):
    sub=P[P["rank"]<=k]
    fit_ci(sub,["t_dv"],f"{label}（唔控制）")
    fit_ci(sub,["ab_z","t_dv"],f"{label}（控制場內綜合分）")

print("\n=== 2. 只喺 model top-4 出手（效果集中喺頂）")
def pair_boot(f1,n=1000):
    per=[]
    for g in RACES:
        v0=g.ability.values; v1=f1(g); p=g.placed.values
        pos=np.where(p==1)[0]; neg=np.where(p==0)[0]
        c0=c1=t=0
        for i in pos:
            for j in neg:
                t+=1
                c0+= 1.0 if v0[i]>v0[j] else (0.5 if v0[i]==v0[j] else 0.0)
                c1+= 1.0 if v1[i]>v1[j] else (0.5 if v1[i]==v1[j] else 0.0)
        per.append((c0,c1,t))
    per=np.array(per,float); rng=np.random.default_rng(0); o=[]
    for _ in range(n):
        s=rng.integers(0,len(per),len(per)); w=per[s]; tot=w[:,2].sum()
        o.append(w[:,1].sum()/tot-w[:,0].sum()/tot)
    o=np.array(o)
    return per[:,0].sum()/per[:,2].sum(), per[:,1].sum()/per[:,2].sum(), o.mean(), np.percentile(o,2.5), np.percentile(o,97.5)
def top4_only(g,k):
    v=g.ability.values.astype(float).copy()
    order=np.argsort(-v)[:4]
    v[order]+= k*(g.t_dv.values[order]/SD)
    return v
for k in (0.25,0.5,1.0,2.0):
    b,c,m,lo,hi=pair_boot(lambda g,kk=k: top4_only(g,kk))
    v="✅" if lo>0 else ("❌" if hi<0 else "➖")
    print(f"  只郁 top-4，每 1 SD ±{k} 分: {b:.4f} → {c:.4f}  Δ {m:+.4f} [{lo:+.4f},{hi:+.4f}] {v}")
