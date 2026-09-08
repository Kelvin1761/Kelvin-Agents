"""Walk-forward：每個賽日只用「當日之前」嘅資料估場地偏好，再喺當日驗證。
點解要咁做：master stats 係全季快照，直接用會前視（見 memory: au-people-stats-have-lookahead）。"""
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database/comprehensive_stats")
m = pd.read_csv(ROOT/"all_race_results_master.csv")
m = m[m.Rank!=99].copy().sort_values("Date").reset_index(drop=True)
base = m.groupby("Venue").Place.mean()
m["exp"] = m.Venue.map(base)
K = 100.0   # EB shrink，同 JT_RATING_PARAMS 一致

def build(hist, keys):
    """回傳 (整體 edge, 場地 delta) 兩個 dict —— 全部 EB shrink 向 0。"""
    g = hist.groupby(keys).agg(n=("Place","size"), obs=("Place","sum"), exp=("exp","sum"))
    overall = ((g.obs-g.exp)/(g.n+K)).to_dict()
    gv = hist.groupby(keys+["Venue"]).agg(n=("Place","size"), obs=("Place","sum"), exp=("exp","sum"))
    gv["edge"] = (gv.obs-gv.exp)/(gv.n+K)
    delta = {}
    for idx,row in gv.iterrows():
        ent = idx[:-1] if len(keys)>1 else idx[0]
        delta[(ent, idx[-1])] = row.edge - overall.get(ent, 0.0)
    return overall, delta

dates = sorted(m.Date.unique())
start = [i for i,d in enumerate(dates) if d>="2025-09-01"][0]
rows=[]
for i in range(start, len(dates)):
    d = dates[i]
    hist = m[m.Date < d]
    today = m[m.Date == d]
    if len(hist) < 3000: continue
    jo, jd = build(hist, ["Jockey"])
    to, td = build(hist, ["Trainer"])
    co, cd = build(hist, ["Jockey","Trainer"])
    for _,r in today.iterrows():
        rows.append({
            "Place": r.Place, "Venue": r.Venue, "Odds": r.Odds, "race": f"{d}|{r.RaceNo}",
            "j_all": jo.get(r.Jockey,0.0), "j_dv": jd.get((r.Jockey,r.Venue),0.0),
            "t_all": to.get(r.Trainer,0.0), "t_dv": td.get((r.Trainer,r.Venue),0.0),
            "c_all": co.get((r.Jockey,r.Trainer),0.0), "c_dv": cd.get(((r.Jockey,r.Trainer),r.Venue),0.0),
        })
df = pd.DataFrame(rows)
print(f"out-of-sample 行數 {len(df)}, 場次 {df.race.nunique()}, 日期 {len(df.race.str[:10].unique())}")

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
def auc(cols):
    X = df[cols].values; y = df.Place.values
    mdl = LogisticRegression(max_iter=1000).fit(X,y)
    return roc_auc_score(y, mdl.predict_proba(X)[:,1])

def boot_delta(base_cols, add_cols, n=400):
    """配對 bootstrap：同一批場次，兩個模型 AUC 之差。"""
    y=df.Place.values
    p0 = LogisticRegression(max_iter=1000).fit(df[base_cols],y).predict_proba(df[base_cols])[:,1]
    p1 = LogisticRegression(max_iter=1000).fit(df[base_cols+add_cols],y).predict_proba(df[base_cols+add_cols])[:,1]
    races = df.race.unique(); idx = {r:np.where(df.race.values==r)[0] for r in races}
    rng=np.random.default_rng(0); out=[]
    for _ in range(n):
        s = np.concatenate([idx[r] for r in rng.choice(races,len(races),replace=True)])
        out.append(roc_auc_score(y[s],p1[s])-roc_auc_score(y[s],p0[s]))
    return np.mean(out), np.percentile(out,2.5), np.percentile(out,97.5)

print("\n單獨 AUC（越大越有排序力，0.5 = 冇）")
for c,label in [("j_all","騎師整體"),("j_dv","騎師場地 delta"),("t_all","練馬師整體"),
                ("t_dv","練馬師場地 delta"),("c_all","騎練組合整體"),("c_dv","組合場地 delta")]:
    print(f"  {label:<14} AUC {roc_auc_score(df.Place, df[c]):.4f}")

print("\n邊際貢獻（加落已有嘅整體分之上）")
for base_cols, add, label in [
    (["j_all","t_all"], ["j_dv"], "＋騎師場地 delta"),
    (["j_all","t_all"], ["t_dv"], "＋練馬師場地 delta"),
    (["j_all","t_all"], ["j_dv","t_dv"], "＋騎師＋練馬師場地 delta"),
    (["j_all","t_all"], ["c_all"], "＋騎練組合（整體）"),
    (["j_all","t_all","c_all"], ["c_dv"], "＋組合場地 delta"),
]:
    a0 = auc(base_cols); mean,lo,hi = boot_delta(base_cols, add)
    verdict = "✅ 顯著" if lo>0 else ("❌ 顯著負" if hi<0 else "➖ CI 跨零")
    print(f"  {label:<24} baseline AUC {a0:.4f} → Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict}")
df.to_parquet("wf_features.parquet")
