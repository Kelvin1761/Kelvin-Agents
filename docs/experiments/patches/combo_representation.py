"""Q1 專用：騎練組合而家嘅「攤入騎師分/練馬師分」表示法，同「獨立 leaf」比。
Walk-forward point-in-time，唔用全季快照。"""
import pandas as pd, numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database/comprehensive_stats")
m = pd.read_csv(ROOT/"all_race_results_master.csv"); m=m[m.Rank!=99].copy().sort_values("Date").reset_index(drop=True)
base = m.groupby("Venue").Place.mean(); m["exp"]=m.Venue.map(base); K=100.0

def combo_adj(starts, win_rate, place_rate):
    if starts < 40: return 0.0
    if win_rate>=14.0 or place_rate>=36.0: return 4.0
    if win_rate>=11.0 or place_rate>=30.0: return 2.0
    if win_rate<=7.0 and place_rate<=23.0: return -2.0
    return 0.0

dates=sorted(m.Date.unique()); start=[i for i,d in enumerate(dates) if d>="2025-09-01"][0]
rows=[]
for d in dates[start:]:
    hist=m[m.Date<d]; today=m[m.Date==d]
    if len(hist)<3000: continue
    def edges(keys):
        g=hist.groupby(keys).agg(n=("Place","size"),obs=("Place","sum"),exp=("exp","sum"))
        return ((g.obs-g.exp)/(g.n+K)).to_dict()
    jo, to = edges(["Jockey"]), edges(["Trainer"])
    cg=hist.groupby(["Jockey","Trainer"]).agg(n=("Place","size"),wins=("Win","sum"),places=("Place","sum"),exp=("exp","sum"))
    cg["win_rate"]=cg.wins/cg.n*100; cg["place_rate"]=cg.places/cg.n*100
    cg["edge"]=(cg.places-cg.exp)/(cg.n+K)
    craw=cg.to_dict("index")
    for _,r in today.iterrows():
        c=craw.get((r.Jockey,r.Trainer))
        rows.append({"Place":r.Place,"race":f"{d}|{r.RaceNo}",
                     "j":jo.get(r.Jockey,0.0),"t":to.get(r.Trainer,0.0),
                     "c_edge":(c["edge"] if c else 0.0),
                     "c_starts":(c["n"] if c else 0),
                     "c_adj":(combo_adj(c["n"],c["win_rate"],c["place_rate"]) if c else 0.0)})
df=pd.DataFrame(rows); df.to_csv("combo_wf.csv",index=False)
y=df.Place.values
print(f"樣本 {len(df)} 行 / {df.race.nunique()} 場 (2025-09 起 out-of-sample)")
print(f"組合有記錄        : {(df.c_starts>0).mean()*100:.1f}%")
print(f"組合 ≥40 仗（入分）: {(df.c_starts>=40).mean()*100:.1f}%")
print(f"實際攞到非零調整   : {(df.c_adj!=0).mean()*100:.1f}%  分佈 {df.c_adj.value_counts().to_dict()}")
print(f"\n55/45 攤分損耗：組合調整落到維度分只剩 0.55²+0.45² = {0.55**2+0.45**2:.3f} 倍")
print(f"  即係 ±4 分嘅『馬房皇牌組合』，實際只郁到騎練訊號維度 ±{4*0.505:.2f} 分")
print(f"  再乘維度權重 23.62% → 綜合分只郁 ±{4*0.505*0.2362:.3f} 分")
print(f"  如果做獨立 leaf 佔維度 20%：±4 → 維度 ±{4*0.2:.2f} 分（同一個 ±4 唔會被攤走）")

def bootstrap(p0,p1,n=400):
    races=df.race.unique(); idx={r:np.where(df.race.values==r)[0] for r in races}
    rng=np.random.default_rng(0); out=[]
    for _ in range(n):
        s=np.concatenate([idx[r] for r in rng.choice(races,len(races),replace=True)])
        out.append(roc_auc_score(y[s],p1[s])-roc_auc_score(y[s],p0[s]))
    return np.mean(out),np.percentile(out,2.5),np.percentile(out,97.5)

def fit(cols):
    X=df[cols].values; return LogisticRegression(max_iter=1000).fit(X,y).predict_proba(X)[:,1]

print("\n表示法對比（同一批 out-of-sample 行）")
p_now = fit(["j","t","c_adj"])          # 而家：離散 ±4/±2/−2（攤分損耗喺線性模型入面等同縮 scale）
p_cont= fit(["j","t","c_edge"])         # 連續：組合實際超額上名率
p_none= fit(["j","t"])
for label,p in [("冇組合",p_none),("離散 ±4/±2/−2（現行）",p_now),("連續超額率",p_cont)]:
    print(f"  {label:<22} AUC {roc_auc_score(y,p):.4f}")
mean,lo,hi=bootstrap(p_now,p_cont)
print(f"  連續 vs 離散: Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {'✅' if lo>0 else ('❌' if hi<0 else '➖ CI 跨零')}")
mean,lo,hi=bootstrap(p_none,p_now)
print(f"  離散 vs 冇組合: Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {'✅' if lo>0 else ('❌' if hi<0 else '➖ CI 跨零')}")

print("\n組合門檻掃描（≥N 仗先入分，用連續超額率）")
for thr in (0,20,40,60,80):
    col=np.where(df.c_starts>=thr, df.c_edge, 0.0)
    tmp=df.assign(cc=col)
    p=LogisticRegression(max_iter=1000).fit(tmp[["j","t","cc"]],y).predict_proba(tmp[["j","t","cc"]])[:,1]
    print(f"  ≥{thr:>2} 仗: 覆蓋 {(df.c_starts>=thr).mean()*100:5.1f}%  AUC {roc_auc_score(y,p):.4f}")
