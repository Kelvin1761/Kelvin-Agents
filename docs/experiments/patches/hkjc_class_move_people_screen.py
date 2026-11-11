"""EXP-20261111-06：練馬師／騎師 × 匹馬升降班 screening（walk-forward，只量度）。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_class_move_people_screen.py [rows.pkl]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_trainer_class_screen import (  # noqa: E402
    OOS_START, boot, edges, fit, load, prep, season_tag, verdict, _r_ci,
)

LADDER = {"Class 5": 5, "Class 4": 4, "Class 3": 3, "Class 2": 2, "Class 1": 1,
          "Group 1": 0, "Group 2": 0, "Group 3": 0}


def add_move(m):
    m = m.copy()
    m["lvl"] = m.RaceClass.astype(str).map(LADDER)
    m = m.sort_values(["HorseID", "Date", "RaceNo"])
    m["prev_lvl"] = m.groupby("HorseID").lvl.shift(1)
    m["prev_date"] = m.groupby("HorseID").Date.shift(1)
    ok = m.lvl.notna() & m.prev_lvl.notna() & (m.prev_date < m.Date)
    m["MV"] = "冇前仗"
    m.loc[ok & (m.lvl < m.prev_lvl), "MV"] = "升班"
    m.loc[ok & (m.lvl > m.prev_lvl), "MV"] = "降班"
    m.loc[ok & (m.lvl == m.prev_lvl), "MV"] = "同班"
    return m.sort_values(["Date", "RaceNo"]).reset_index(drop=True)


def walk_forward(m):
    rows = []
    for d in [x for x in sorted(m.Date.unique()) if x >= OOS_START]:
        hist = m[m.Date < d]
        today = m[m.Date == d]
        jo, _ = edges(hist, ["Jockey"])
        to, _ = edges(hist, ["Trainer"])
        td, _ = edges(hist, ["Trainer", "Distance"])
        tv, _ = edges(hist, ["Trainer", "Venue"])
        hm = hist[hist.MV != "冇前仗"]
        tm, tmn = edges(hm, ["Trainer", "MV"])
        jm, jmn = edges(hm, ["Jockey", "MV"])
        for r in today.itertuples():
            t = to.get(r.Trainer, 0.0)
            j = jo.get(r.Jockey, 0.0)
            has = r.MV != "冇前仗"
            rows.append({
                "Place": r.Place, "race": r.race, "Date": r.Date, "MV": r.MV, "lmkt": r.lmkt,
                "j": j, "t": t,
                "t_dd": td.get((r.Trainer, r.Distance), t) - t,
                "t_dv": tv.get((r.Trainer, r.Venue), t) - t,
                "up": float(r.MV == "升班"), "down": float(r.MV == "降班"),
                "t_mv": (tm.get((r.Trainer, r.MV), t) - t) if has else 0.0,
                "j_mv": (jm.get((r.Jockey, r.MV), j) - j) if has else 0.0,
                "n_tm": tmn.get((r.Trainer, r.MV), 0) if has else 0,
                "n_jm": jmn.get((r.Jockey, r.MV), 0) if has else 0,
            })
    return pd.DataFrame(rows)


def boot975(df, p0, p1, n=400):
    y = df.Place.values
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    out = []
    for _ in range(n):
        s = np.concatenate([idx[r] for r in rng.choice(races, len(races), replace=True)])
        out.append(roc_auc_score(y[s], p1[s]) - roc_auc_score(y[s], p0[s]))
    return np.mean(out), np.percentile(out, 1.25), np.percentile(out, 98.75)


def stability(m, who, min_n=30):
    m = m[m.MV != "冇前仗"].copy()
    m["S"] = m.Date.map(season_tag)
    m["res"] = m.Place - m.exp

    def deltas(sub):
        base = sub.groupby(who).res.mean()
        g = sub.groupby([who, "MV"]).res.agg(["mean", "size"])
        g = g[g["size"] >= min_n]
        return g["mean"] - base.reindex(g.index.get_level_values(0)).values

    out = {}
    j = pd.concat([deltas(m[m.S == "24_25"]), deltas(m[m.S == "25_26"])], axis=1, join="inner").dropna()
    j.columns = ["a", "b"]
    out["cross_season"] = _r_ci(j)
    dates = sorted(m.Date.unique())
    odd = set(dates[::2])
    j2 = pd.concat([deltas(m[m.Date.isin(odd)]), deltas(m[~m.Date.isin(odd)])], axis=1, join="inner").dropna()
    j2.columns = ["a", "b"]
    out["split_half"] = _r_ci(j2)
    return out


def main():
    m = prep(load(sys.argv[1] if len(sys.argv) > 1 else None))
    m["lmkt"] = np.log(m.mkt.clip(1e-4, 0.9999) / (1 - m.mkt.clip(1e-4, 0.9999)))
    m = add_move(m)
    print(f"語料 {len(m)} 行；升降班分佈：", m.MV.value_counts().to_dict())
    print("\n匹馬本身升降班（全語料，相對場內期望）：")
    for mv, s in m.groupby("MV"):
        print(f"  {mv:<4} n={len(s):>6}  上名率 {s.Place.mean()*100:5.1f}%  超額 {(s.Place-s.exp).mean()*100:+5.2f}pp")

    df = walk_forward(m)
    known = df.MV != "冇前仗"
    print(f"\nOOS {len(df)} 行 / {df.race.nunique()} 場；有升降班 {known.mean()*100:.1f}%")
    for who in ("n_tm", "n_jm"):
        k = df.loc[known, who]
        print(f"  {who} 覆蓋（有前仗行）：≥30 仗 {(k>=30).mean()*100:.1f}%  ≥100 仗 {(k>=100).mean()*100:.1f}%")

    print("\n單獨 AUC（只計有前仗行）")
    sub = df[known]
    for c in ["j", "t", "up", "down", "t_mv", "j_mv"]:
        print(f"  {c:<6} {roc_auc_score(sub.Place, sub[c]):.4f}")

    base = ["j", "t", "t_dd", "t_dv", "up", "down"]
    print("\n邊際貢獻 Δ AUC [97.5% CI]（全 OOS）")
    tests = [
        (["j", "t", "t_dd", "t_dv"], ["up", "down"], "匹馬升降班本身（參考）"),
        (base, ["t_mv"], "H1 練馬師 × 升降班【判決】"),
        (base, ["j_mv"], "H2 騎師 × 升降班【判決】"),
        (base + ["t_mv"], ["j_mv"], "騎師 加喺練馬師之上"),
        (["lmkt"] + base, ["t_mv"], "練馬師 加喺市場之上（對照）"),
        (["lmkt"] + base, ["j_mv"], "騎師 加喺市場之上（對照）"),
    ]
    for b, a, label in tests:
        mean, lo, hi = boot975(df, fit(df, b), fit(df, b + a))
        print(f"  {label:<24} Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict(lo, hi)}")

    print("\n分升／降班：加喺 baseline 之上（bootstrap 200，97.5%）")
    for mv in ("升班", "降班", "同班"):
        s = df[df.MV == mv].reset_index(drop=True)
        for c in ("t_mv", "j_mv"):
            mean, lo, hi = boot975(s, fit(s, ["j", "t", "t_dd", "t_dv"]), fit(s, ["j", "t", "t_dd", "t_dv", c]), n=200)
            print(f"  {mv} {c:<5} 行 {len(s):>5}  Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict(lo, hi)}")

    print("\n穩定性（(人, 升降班) ≥30 仗）")
    for who in ("Trainer", "Jockey"):
        for k, (n, r, lo, hi) in stability(m, who).items():
            print(f"  {who:<8} {k:<13} 格數 {n:>3}  r {r:+.3f} [{lo:+.3f},{hi:+.3f}] {verdict(lo, hi)}")

    print("\n相關性（有前仗行，Spearman）")
    print(sub[["t", "j", "up", "down", "t_mv", "j_mv", "lmkt"]].corr(method="spearman").round(3).to_string())


if __name__ == "__main__":
    main()
