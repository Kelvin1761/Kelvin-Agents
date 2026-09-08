"""同一個問題，但唔用賠率控制 —— 純粹問：「某啲騎師喺跑馬地好啲」呢句本身量唔量得穩。"""
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database/comprehensive_stats")
m = pd.read_csv(ROOT / "all_race_results_master.csv")
m = m[m.Rank != 99].copy()
ST, HV = "沙田", "跑馬地"
base = m.groupby("Venue").Place.mean()          # 只食走場地基準（馬匹數唔同）
m["exp_place"] = m.Venue.map(base)

def pref(df, keys, min_n):
    g = df.groupby(keys + ["Venue"]).agg(n=("Place","size"), obs=("Place","sum"), exp=("exp_place","sum"))
    g["edge"] = (g.obs - g.exp)/g.n
    w = g.reset_index().pivot_table(index=keys, columns="Venue", values=["n","edge"])
    w.columns = [f"{a}_{b}" for a,b in w.columns]
    w = w.dropna()
    w = w[(w[f"n_{ST}"]>=min_n)&(w[f"n_{HV}"]>=min_n)]
    w["d"] = w[f"edge_{ST}"]-w[f"edge_{HV}"]
    return w

pbar = m.Place.mean()
print("=== 未控制馬匹質素：場地偏好離散度 vs 噪音")
for keys,label,min_n in ([["Jockey"],"騎師",100],[["Trainer"],"練馬師",100],[["Jockey","Trainer"],"騎練組合",25]):
    w = pref(m, keys, min_n)
    noise = np.sqrt(pbar*(1-pbar)*(1/w[f"n_{ST}"]+1/w[f"n_{HV}"]))
    obs, exp = w.d.std(), np.sqrt((noise**2).mean())
    real = np.sqrt(max(obs**2-exp**2,0))
    print(f"  {label} n={len(w):>3}: 觀測 SD {obs:.4f} / 噪音 {exp:.4f} → 真訊號 SD {real:.4f} ({max(obs**2-exp**2,0)/obs**2*100:.0f}% 方差)")

print("\n=== 拆半重測 (20 seeds)")
for keys,label,min_n in ([["Jockey"],"騎師",50],[["Trainer"],"練馬師",50],[["Jockey","Trainer"],"騎練組合",12]):
    cors=[]; sizes=[]
    for seed in range(20):
        h=m.copy(); h["half"]=np.random.default_rng(seed).integers(0,2,len(h))
        a=pref(h[h.half==0],keys,min_n)["d"]; b=pref(h[h.half==1],keys,min_n)["d"]
        j=pd.concat([a.rename("a"),b.rename("b")],axis=1).dropna()
        if len(j)>5: cors.append(j.a.corr(j.b)); sizes.append(len(j))
    print(f"  {label}: r={np.mean(cors):+.3f} [{np.percentile(cors,5):+.3f},{np.percentile(cors,95):+.3f}] n≈{int(np.mean(sizes))}")

print("\n=== 跨季 24/25 → 25/26")
s1=m[m.Date<"2025-08-01"]; s2=m[m.Date>="2025-08-01"]
for keys,label,min_n in ([["Jockey"],"騎師",50],[["Trainer"],"練馬師",50],[["Jockey","Trainer"],"騎練組合",15]):
    a=pref(s1,keys,min_n)["d"].rename("prior"); b=pref(s2,keys,min_n)["d"].rename("later")
    j=pd.concat([a,b],axis=1).dropna()
    print(f"  {label}: n={len(j)}, r={j.prior.corr(j.later):+.3f}")

print("\n=== 場地偏好最極端嘅騎師／練馬師（門檻 100/100）")
for keys,label in ([["Jockey"],"騎師"],[["Trainer"],"練馬師"]):
    w=pref(m,keys,100).sort_values("d")
    show=pd.concat([w.head(4),w.tail(4)])
    for idx,r in show.iterrows():
        print(f"  {label} {str(idx):<8} 沙田 {r[f'n_{ST}']:>4.0f} 仗 edge {r[f'edge_{ST}']:+.3f} | "
              f"跑馬地 {r[f'n_{HV}']:>4.0f} 仗 edge {r[f'edge_{HV}']:+.3f} | 差 {r.d:+.3f}")
