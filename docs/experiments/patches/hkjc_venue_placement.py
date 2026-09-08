#!/usr/bin/env python3
"""Q2「擺邊度最好」：喺 2,438 匹 runner 上面用**場內配對**做高功效篩選。
gold/good 喺 193 場只有 ~2pp 解析度；場內配對用 27,000+ 對，功效高一個數量級。"""
import numpy as np, pandas as pd, itertools
df=pd.read_csv('/tmp/hkjc_runner_ds.csv')
RACES=[g for _,g in df.groupby("race")]

def pairs(col_getter, subset=None):
    """回傳 (concordant, total)：場內每一對『上名 vs 唔上名』，分高嗰個係咪上名嗰個。"""
    c=t=0
    for g in RACES:
        v=col_getter(g); p=g.placed.values
        if subset is not None:
            m=subset(g)
            v=v[m]; p=p[m]
        pos=np.where(p==1)[0]; neg=np.where(p==0)[0]
        for i in pos:
            for j in neg:
                d=v[i]-v[j]
                t+=1; c+= 1.0 if d>0 else (0.5 if d==0 else 0.0)
    return c,t

def pair_auc(col_getter, subset=None):
    c,t=pairs(col_getter,subset); return c/t if t else float('nan'), t

def boot_pair_delta(f0,f1,n=1000,subset=None):
    """配對 bootstrap：按場次重抽，量兩個排序嘅場內配對 AUC 之差。"""
    per=[]
    for g in RACES:
        v0=f0(g); v1=f1(g); p=g.placed.values
        if subset is not None:
            m=subset(g); v0,v1,p=v0[m],v1[m],p[m]
        pos=np.where(p==1)[0]; neg=np.where(p==0)[0]
        c0=c1=t=0
        for i in pos:
            for j in neg:
                t+=1
                d0=v0[i]-v0[j]; d1=v1[i]-v1[j]
                c0+= 1.0 if d0>0 else (0.5 if d0==0 else 0.0)
                c1+= 1.0 if d1>0 else (0.5 if d1==0 else 0.0)
        per.append((c0,c1,t))
    per=np.array(per,dtype=float)
    rng=np.random.default_rng(0); out=[]
    for _ in range(n):
        s=rng.integers(0,len(per),len(per)); w=per[s]
        tot=w[:,2].sum()
        out.append(w[:,1].sum()/tot - w[:,0].sum()/tot)
    o=np.array(out)
    base=per[:,0].sum()/per[:,2].sum(); cand=per[:,1].sum()/per[:,2].sum()
    return base,cand,o.mean(),np.percentile(o,2.5),np.percentile(o,97.5)

A=lambda g: g.ability.values
D=lambda g: g.t_dv.values

print("=== 1. 場地 delta 自己有冇場內排序力")
a,t=pair_auc(D); print(f"  場地 delta 單獨：場內配對 AUC {a:.4f}（{t:,} 對）")
a,t=pair_auc(A);  print(f"  綜合分：            場內配對 AUC {a:.4f}")

print("\n=== 2. 加落綜合分（線性），掃幅度")
for g_ in (11,22,44,88,176):
    b,c,m,lo,hi=boot_pair_delta(A, lambda g,k=g_: g.ability.values + k*0.45*0.2362*g.t_dv.values)
    v="✅" if lo>0 else ("❌" if hi<0 else "➖")
    print(f"  ×{g_:>3}（綜合分 SD {g_*0.45*0.2362*df.t_dv.std():.3f} 分）: {b:.4f} → {c:.4f}  Δ {m:+.4f} [{lo:+.4f},{hi:+.4f}] {v}")

print("\n=== 3. 只做拆糊（場內綜合分差 < δ 先用場地 delta 排先後）")
def tiebreak(g, delta, k=1000.0):
    v=g.ability.values.copy()
    order=np.argsort(-v)
    out=v.astype(float).copy()
    for ii in range(len(order)-1):
        i,j=order[ii],order[ii+1]
        if abs(v[i]-v[j])<delta:
            # 喺呢個窄帶入面用場地 delta 做次序（幅度細到唔會跨越個帶）
            out[i]=v[i]+ (delta/2)*np.tanh(k*g.t_dv.values[i])*0.5
            out[j]=v[j]+ (delta/2)*np.tanh(k*g.t_dv.values[j])*0.5
    return out
for delta in (0.5,1.0,2.0,4.0):
    b,c,m,lo,hi=boot_pair_delta(A, lambda g,d=delta: tiebreak(g,d))
    v="✅" if lo>0 else ("❌" if hi<0 else "➖")
    print(f"  δ={delta:>4} 分: {b:.4f} → {c:.4f}  Δ {m:+.4f} [{lo:+.4f},{hi:+.4f}] {v}")

print("\n=== 4. 只喺極端 decile 出手（|delta| 大 + 樣本厚）")
q_lo,q_hi=df.t_dv.quantile([0.10,0.90])
print(f"  10%/90% 分位 = {q_lo:+.4f} / {q_hi:+.4f}")
def sparse(g,k):
    v=g.ability.values.astype(float).copy()
    d=g.t_dv.values; n=g.t_dv_n.values
    hit=((d<=q_lo)|(d>=q_hi))&(n>=100)
    v[hit]+= k*np.sign(d[hit])
    return v
for k in (0.5,1.0,2.0,3.0):
    b,c,m,lo,hi=boot_pair_delta(A, lambda g,kk=k: sparse(g,kk))
    v="✅" if lo>0 else ("❌" if hi<0 else "➖")
    print(f"  ±{k} 分（只 20% 馬）: {b:.4f} → {c:.4f}  Δ {m:+.4f} [{lo:+.4f},{hi:+.4f}] {v}")

print("\n=== 5. 首選層：場地 delta 差嘅首選，係咪真係比較唔掂")
tops=[]
for g in RACES:
    i=g.ability.values.argmax()
    tops.append({"placed":g.placed.values[i],"won":g.won.values[i],"t_dv":g.t_dv.values[i]})
T=pd.DataFrame(tops)
lo_c=T[T.t_dv<=T.t_dv.quantile(0.25)]; hi_c=T[T.t_dv>=T.t_dv.quantile(0.75)]
print(f"  首選場地 delta 最差 25%（n={len(lo_c)}）：上名 {100*lo_c.placed.mean():.1f}%、頭馬 {100*lo_c.won.mean():.1f}%")
print(f"  首選場地 delta 最好 25%（n={len(hi_c)}）：上名 {100*hi_c.placed.mean():.1f}%、頭馬 {100*hi_c.won.mean():.1f}%")
diffs=[]
rng=np.random.default_rng(0)
for _ in range(2000):
    s1=lo_c.sample(len(lo_c),replace=True,random_state=int(rng.integers(1e9)))
    s2=hi_c.sample(len(hi_c),replace=True,random_state=int(rng.integers(1e9)))
    diffs.append(s2.placed.mean()-s1.placed.mean())
d=np.array(diffs)
print(f"  差 {100*d.mean():+.1f}pp [{100*np.percentile(d,2.5):+.1f},{100*np.percentile(d,97.5):+.1f}]"
      f" {'✅' if np.percentile(d,2.5)>0 else '➖ CI 跨零'}")
