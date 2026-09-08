"""HKJC 騎練訊號：場地拆分（沙田 / 跑馬地）可行性量度。

只做量度，唔改任何 production code。
"""
import pandas as pd, numpy as np
from pathlib import Path

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/HKJC_Race_Results_Database/comprehensive_stats")
m = pd.read_csv(ROOT / "all_race_results_master.csv")
m = m[m.Rank != 99].copy()
m["race_id"] = m.Date.astype(str) + "|" + m.Venue + "|" + m.RaceNo.astype(str)
m["field"] = m.groupby("race_id").Horse.transform("size")

# 市場隱含贏率（場內正規化）→ 控制「馬匹質素」呢個混淆
m["inv"] = 1.0 / m.Odds
m["p_win"] = m.inv / m.groupby("race_id").inv.transform("sum")

# 期望上名率：用 (venue, p_win 十分位) 經驗表 —— 場地基準差異（HV 12 匹 vs ST 14 匹）
# 由呢一步食走，唔會扮成騎師偏好
m["pbin"] = pd.qcut(m.p_win, 20, labels=False, duplicates="drop")
exp_tbl = m.groupby(["Venue", "pbin"]).Place.mean().rename("exp_place")
m = m.join(exp_tbl, on=["Venue", "pbin"])

print("=" * 72)
print("A. 樣本量：兩季 %d 行，%s → %s" % (len(m), m.Date.min(), m.Date.max()))
print(m.Venue.value_counts().to_string())
print("場內平均上名率 by venue:", m.groupby("Venue").Place.mean().round(4).to_dict())
print("平均馬匹數 by venue:", m.groupby("Venue").field.mean().round(2).to_dict())

ST, HV = "沙田", "跑馬地"

def coverage(keys, label):
    piv = m.pivot_table(index=keys, columns="Venue", values="Place", aggfunc="size").fillna(0)
    for a in (25, 50, 100, 200):
        n = int(((piv.get(ST, 0) >= a) & (piv.get(HV, 0) >= a)).sum())
        # 覆蓋率＝今日一匹馬命中呢類 cell 嘅機率
        ok = piv[(piv.get(ST, 0) >= a) & (piv.get(HV, 0) >= a)].index
        rows = m.set_index(keys).index.isin(ok).mean()
        print(f"  {label}: 兩邊各 ≥{a:>3} 仗 → {n:>4} 個實體，覆蓋今日 {rows*100:5.1f}% 出賽行")
    return piv

print("\nB. 場地拆分後仲有幾多樣本")
coverage(["Jockey"], "騎師")
coverage(["Trainer"], "練馬師")
coverage(["Jockey", "Trainer"], "騎練組合")

def venue_pref(df, keys, min_n):
    """每個實體嘅場地偏好 = (實際−期望) 上名率，ST 減 HV。"""
    g = df.groupby(keys + ["Venue"]).agg(n=("Place", "size"), obs=("Place", "sum"), exp=("exp_place", "sum"))
    g["edge"] = (g.obs - g.exp) / g.n
    w = g.reset_index().pivot_table(index=keys, columns="Venue", values=["n", "edge"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.dropna()
    w = w[(w[f"n_{ST}"] >= min_n) & (w[f"n_{HV}"] >= min_n)]
    w["d"] = w[f"edge_{ST}"] - w[f"edge_{HV}"]
    return w

print("\nC. 場地偏好係咪真？（觀測離散度 vs 二項噪音）")
for keys, label, min_n in ([["Jockey"], "騎師", 100], [["Trainer"], "練馬師", 100]):
    w = venue_pref(m, keys, min_n)
    pbar = m.Place.mean()
    noise_sd = np.sqrt(pbar * (1 - pbar) * (1 / w[f"n_{ST}"] + 1 / w[f"n_{HV}"]))
    obs_sd = w.d.std()
    exp_sd = np.sqrt((noise_sd ** 2).mean())
    excess = obs_sd ** 2 - exp_sd ** 2
    print(f"  {label} (n={len(w)}, 門檻 {min_n}): 觀測 SD {obs_sd:.4f} vs 噪音 SD {exp_sd:.4f}"
          f" → 真訊號 SD {np.sqrt(max(excess,0)):.4f}"
          f" | 佔比 {max(excess,0)/obs_sd**2*100:5.1f}%")

print("\nD. 拆半重測（同一季內隨機拆半，睇偏好穩唔穩）")
rng = np.random.default_rng(7)
for keys, label, min_n in ([["Jockey"], "騎師", 100], [["Trainer"], "練馬師", 100]):
    cors = []
    for seed in range(20):
        h = m.copy()
        h["half"] = np.random.default_rng(seed).integers(0, 2, len(h))
        a = venue_pref(h[h.half == 0], keys, min_n // 2)["d"]
        b = venue_pref(h[h.half == 1], keys, min_n // 2)["d"]
        j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
        if len(j) > 5:
            cors.append(j.a.corr(j.b))
    print(f"  {label}: split-half r = {np.mean(cors):.3f}  (n≈{len(j)} 個實體, 20 次)")

print("\nE. 跨季 out-of-sample（24/25 估偏好 → 25/26 驗證）")
s1 = m[m.Date < "2025-08-01"]
s2 = m[m.Date >= "2025-08-01"]
for keys, label, min_n in ([["Jockey"], "騎師", 50], [["Trainer"], "練馬師", 50]):
    a = venue_pref(s1, keys, min_n)["d"].rename("prior")
    b = venue_pref(s2, keys, min_n)["d"].rename("later")
    j = pd.concat([a, b], axis=1).dropna()
    r = j.prior.corr(j.later)
    print(f"  {label}: n={len(j)}, r(24/25 → 25/26) = {r:+.3f}")
