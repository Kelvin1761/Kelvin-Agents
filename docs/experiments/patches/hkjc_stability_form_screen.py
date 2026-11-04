"""HKJC 狀態與穩定性 leaf 篩選（EXP-20261105-03，唔係 A/B）：現行 近績分／穩定性分 vs 直線名次、名次百分位、班次、落後秒數。

全部由賽果庫 point-in-time 重砌：目標賽事只用嗰日之前嘅往績。目標窗 2025-01-01 → 2026-10-10
（2026-10-11 起係 forward holdout，唔用）。指標：場內上名（頭 3）AUC，賽日 bootstrap。
"""
import random
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

rows = pd.read_pickle(sys.argv[1])
rows = rows[rows["Rank"].notna()].copy()
rows["Rank"] = rows["Rank"].astype(float)
rows["race"] = rows["Date"].astype(str) + "|" + rows["Venue"].astype(str) + "|" + rows["RaceNo"].astype(str)
rows["field"] = rows.groupby("race")["Horse"].transform("size")
fin = rows[rows["Rank"] < 90].copy()
winner_t = fin.groupby("race")["FinishTimeSec"].min()
rows["behind"] = rows["FinishTimeSec"] - rows["race"].map(winner_t)
CLASS = {"Group 1": 0.0, "Group 2": 0.5, "Group 3": 1.0, "Class 1": 1.0, "Class 2": 2.0,
         "Class 3": 3.0, "Class 4": 4.0, "Class 5": 5.0, "Griffin": 5.0}
rows["cls"] = rows["RaceClass"].astype(str).map(CLASS)
rows = rows.sort_values(["Date", "RaceNo"])

FORM_PTS = lambda r: 100 if r == 1 else 85 if r == 2 else 75 if r == 3 else 60 if r <= 5 else 40
AU_W = (1.0, 0.8, 0.6, 0.4, 0.3, 0.2)

history = defaultdict(list)  # horse -> list of past runs (newest last)
recs = []
for date, day in rows.groupby("Date", sort=True):
    for race, g in day.groupby("race"):
        today_cls = g["cls"].iloc[0]
        for r in g.itertuples():
            past = history[r.Horse][-6:][::-1]  # newest first
            valid = [p for p in past if p["rank"] < 90]
            rec = dict(date=str(date)[:10], race=race, horse=r.Horse, placed=bool(r.Rank <= 3 and r.Rank > 0),
                       n=len(valid), today_cls=today_cls)
            if valid:
                ranks = [p["rank"] for p in valid]
                w = [1 / (i + 1) for i in range(len(ranks))]
                rec["F0"] = sum(FORM_PTS(x) * wi for x, wi in zip(ranks, w)) / sum(w)
                if len(ranks) >= 3:
                    rec["C0"] = 58 + 7 * sum(x <= 3 for x in ranks) - 5 * sum(x >= 8 for x in ranks)
                else:
                    rec["C0"] = 66.0 if rec["F0"] >= 70 else 60.0
                rec["S0"] = (0.5 * rec["F0"] + 0.4 * rec["C0"]) / 0.9
                zp = [(0.5 - (p["rank"] - 1) / max(p["field"] - 1, 1)) / 0.2887 for p in valid]
                zt = [-(min(p["behind"], 6.0) if p["behind"] == p["behind"] else 3.0) for p in valid]
                zk = [(3.5 - p["cls"]) if p["cls"] == p["cls"] else 0.0 for p in valid]
                aw = AU_W[: len(valid)]
                wm = lambda xs, ws: sum(x * y for x, y in zip(xs, ws)) / sum(ws)
                rec["P"] = wm(zp, aw)
                rec["P_inv"] = wm(zp, w)
                rec["R_inv"] = wm([-p["rank"] for p in valid], w)
                rec["R_cap"] = wm([-min(p["rank"], 12) for p in valid], w)
                rec["T"] = wm(zt, aw)
                rec["K"] = wm(zk, aw)
                rec["drop"] = (today_cls - valid[0]["cls"]) if today_cls == today_cls and valid[0]["cls"] == valid[0]["cls"] else 0.0
            recs.append(rec)
        for r in g.itertuples():
            history[r.Horse].append(dict(rank=r.Rank, field=r.field, behind=r.behind, cls=r.cls))

df = pd.DataFrame(recs)
df = df[(df.date >= "2025-01-01") & (df.date < "2026-10-11") & (df.n >= 2)].copy()
# z-scale per-run families on the pooled sample so (a+b)/2 is balanced
for c in ("P", "T", "K"):
    df[c + "z"] = (df[c] - df[c].mean()) / df[c].std()
df["PK"] = (df.Pz + df.Kz) / 2
df["PT"] = (df.Pz + df.Tz) / 2
df["PTK"] = (df.Pz + df.Tz + df.Kz) / 3
df["PK_drop"] = df.PK + 0.0  # placeholder for readability
CANDS = ["F0", "C0", "S0", "R_inv", "R_cap", "P_inv", "P", "T", "K", "PK", "PT", "PTK", "drop"]
print(f"runners {len(df)} races {df.race.nunique()} meetings {df.date.nunique()} | window {df.date.min()} → {df.date.max()}")


def race_auc(g, col):
    x = g[col].to_numpy(float); y = g.placed.to_numpy(bool)
    if y.all() or not y.any():
        return 0.0, 0
    p, u = x[y], x[~y]
    num = (p[:, None] > u[None, :]).sum() + 0.5 * (p[:, None] == u[None, :]).sum()
    return float(num), p.size * u.size


per_race = {}
for race, g in df.groupby("race"):
    per_race[race] = (g.date.iloc[0], {c: race_auc(g, c) for c in CANDS})
by_date = defaultdict(list)
for race, (d, v) in per_race.items():
    by_date[d].append(v)


def pooled(dates, col):
    num = den = 0.0
    for d in dates:
        for v in by_date[d]:
            num += v[col][0]; den += v[col][1]
    return num / den


dates = sorted(by_date)
point = {c: pooled(dates, c) for c in CANDS}
rng = random.Random(20261105)
boots = defaultdict(list)
for _ in range(1000):
    s = [rng.choice(dates) for _ in dates]
    a = {c: pooled(s, c) for c in CANDS}
    for c in CANDS:
        boots[c].append(a[c] - a["S0"])
print("\n場內上名 AUC（Δ 對現行穩定性 S0，賽日 bootstrap 1000 次）")
for c in CANDS:
    xs = sorted(boots[c]); lo, hi = xs[25], xs[974]
    print(f"  {c:6s} {point[c]:.4f}   Δ {point[c]-point['S0']:+.4f} [{lo:+.4f}, {hi:+.4f}]")

import sys as _s; _s.exit(0)  # 篩選只報 AUC 表
print("")
for c in CANDS:
    rho = df.groupby("race").apply(lambda g: g[c].rank().corr(g["S0"].rank())).mean()
    print(f"  {c:6s} {rho:+.3f}")
