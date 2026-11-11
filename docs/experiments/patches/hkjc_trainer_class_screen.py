"""EXP-20261111-05：練馬師 × 班次 screening（walk-forward，只量度）。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_trainer_class_screen.py [rows.pkl]
rows.pkl 係 pit_backtest.load_all_rows() 嘅 pickle；冇就即場載入（慢）。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[3]
K = 100.0
OOS_START = "2025-09-01"


def load(path=None):
    if path:
        return pd.read_pickle(path)
    sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))
    import pit_backtest as pb
    return pb.load_all_rows()


def class_group(c):
    c = str(c)
    if c in ("Class 5", "Class 4", "Class 3", "Class 2"):
        return "C" + c[-1]
    if c == "Class 1" or c.startswith("Group"):
        return "高班"
    return "其他"


def prep(df):
    m = df[(df.Rank.astype(float) < 99)].copy()
    m["Date"] = m.Date.astype(str)
    m["race"] = m.Date + "|" + m.RaceNo.astype(str)
    m["CG"] = m.RaceClass.map(class_group)
    m["Place"] = m.Place.astype(float)
    # 期望值：逐場上名數 ÷ 出賽數（食走馬匹數同班次本身上名率）
    g = m.groupby("race").Place
    m["exp"] = g.transform("sum") / g.transform("size")
    m["Distance"] = pd.to_numeric(m.Distance, errors="coerce").fillna(0).astype(int).astype(str)
    inv = 1.0 / pd.to_numeric(m.Odds, errors="coerce").clip(lower=1.01)
    m["mkt"] = inv / inv.groupby(m.race).transform("sum")
    return m.sort_values(["Date", "RaceNo"]).reset_index(drop=True)


def edges(hist, keys):
    g = hist.groupby(keys).agg(n=("Place", "size"), obs=("Place", "sum"), exp=("exp", "sum"))
    return ((g.obs - g.exp) / (g.n + K)).to_dict(), g.n.to_dict()


def walk_forward(m):
    rows = []
    dates = sorted(m.Date.unique())
    for d in [x for x in dates if x >= OOS_START]:
        hist = m[m.Date < d]
        today = m[m.Date == d]
        jo, _ = edges(hist, ["Jockey"])
        to, _ = edges(hist, ["Trainer"])
        td, _ = edges(hist, ["Trainer", "Distance"])
        tv, _ = edges(hist, ["Trainer", "Venue"])
        tc, tcn = edges(hist, ["Trainer", "CG"])
        for r in today.itertuples():
            t = to.get(r.Trainer, 0.0)
            rows.append({
                "Place": r.Place, "race": r.race, "Date": r.Date, "CG": r.CG, "mkt": r.mkt,
                "j": jo.get(r.Jockey, 0.0), "t": t,
                "t_dd": td.get((r.Trainer, r.Distance), t) - t,
                "t_dv": tv.get((r.Trainer, r.Venue), t) - t,
                "t_dc": tc.get((r.Trainer, r.CG), t) - t,
                "n_tc": tcn.get((r.Trainer, r.CG), 0),
            })
    df = pd.DataFrame(rows)
    df["lmkt"] = np.log(df.mkt.clip(1e-4, 0.9999) / (1 - df.mkt.clip(1e-4, 0.9999)))
    return df


def fit(df, cols):
    return LogisticRegression(max_iter=2000).fit(df[cols], df.Place).predict_proba(df[cols])[:, 1]


def boot(df, p0, p1, n=400):
    y = df.Place.values
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    out = []
    for _ in range(n):
        s = np.concatenate([idx[r] for r in rng.choice(races, len(races), replace=True)])
        out.append(roc_auc_score(y[s], p1[s]) - roc_auc_score(y[s], p0[s]))
    return np.mean(out), np.percentile(out, 2.5), np.percentile(out, 97.5)


def verdict(lo, hi):
    return "✅" if lo > 0 else ("❌" if hi < 0 else "➖")


def season_tag(d):
    y, mo = int(d[:4]), int(d[5:7])
    s = y if mo >= 8 else y - 1
    return f"{s % 100:02d}_{(s + 1) % 100:02d}"


def stability(m, min_n=30):
    """跨季 r：同一 (練馬師, 班次組) 嘅 delta（班次超額率 − 該季練馬師整體超額率）。"""
    m = m.copy()
    m["S"] = m.Date.map(season_tag)
    m["res"] = m.Place - m.exp

    def deltas(sub):
        t = sub.groupby("Trainer").res.mean()
        g = sub.groupby(["Trainer", "CG"]).res.agg(["mean", "size"])
        g = g[g["size"] >= min_n]
        return g["mean"] - t.reindex(g.index.get_level_values(0)).values

    out = {}
    a, b = deltas(m[m.S == "24_25"]), deltas(m[m.S == "25_26"])
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    j.columns = ["a", "b"]
    out["cross_season"] = _r_ci(j)
    dates = sorted(m.Date.unique())
    odd = set(dates[::2])
    a, b = deltas(m[m.Date.isin(odd)]), deltas(m[~m.Date.isin(odd)])
    j2 = pd.concat([a, b], axis=1, join="inner").dropna()
    j2.columns = ["a", "b"]
    out["split_half"] = _r_ci(j2)
    return out


def _r_ci(j, n=2000):
    rng = np.random.default_rng(1)
    r = np.corrcoef(j.a, j.b)[0, 1]
    bs = []
    for _ in range(n):
        s = j.iloc[rng.integers(0, len(j), len(j))]
        bs.append(np.corrcoef(s.a, s.b)[0, 1])
    return len(j), r, np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def main():
    m = prep(load(sys.argv[1] if len(sys.argv) > 1 else None))
    print(f"語料 {len(m)} 行 / {m.race.nunique()} 場 / {m.Date.nunique()} 賽日  {m.Date.min()} → {m.Date.max()}")
    print("班次組分佈：", m.CG.value_counts().to_dict())
    df = walk_forward(m)
    print(f"OOS {len(df)} 行 / {df.race.nunique()} 場 / {df.Date.nunique()} 賽日")
    print(f"練馬師×班次 覆蓋：有記錄 {(df.n_tc>0).mean()*100:.1f}%  ≥30 仗 {(df.n_tc>=30).mean()*100:.1f}%  "
          f"≥100 仗 {(df.n_tc>=100).mean()*100:.1f}%")

    print("\n單獨 AUC")
    for c in ["j", "t", "t_dd", "t_dv", "t_dc"]:
        print(f"  {c:<6} {roc_auc_score(df.Place, df[c]):.4f}")

    print("\n邊際貢獻 Δ AUC [95% CI]")
    tests = [
        (["j", "t"], ["t_dd"], "練馬師同程（live 已有）"),
        (["j", "t"], ["t_dc"], "練馬師班次"),
        (["j", "t", "t_dd"], ["t_dc"], "班次 加喺同程之上"),
        (["j", "t", "t_dd", "t_dv"], ["t_dc"], "班次 加喺同程＋場地之上【判決】"),
        (["lmkt"], ["t_dc"], "班次 加喺市場之上（對照）"),
        (["lmkt", "j", "t", "t_dd", "t_dv"], ["t_dc"], "班次 加喺市場＋全部之上（對照）"),
    ]
    for b, a, label in tests:
        mean, lo, hi = boot(df, fit(df, b), fit(df, b + a))
        print(f"  {label:<26} Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict(lo, hi)}")

    print("\n分班次組：t_dc 加喺 (j,t,t_dd,t_dv) 之上")
    for cg, sub in df.groupby("CG"):
        if sub.race.nunique() < 40:
            print(f"  {cg:<4} 場數 {sub.race.nunique()} 太少，略過")
            continue
        base = ["j", "t", "t_dd", "t_dv"]
        mean, lo, hi = boot(sub.reset_index(drop=True), fit(sub, base), fit(sub, base + ["t_dc"]), n=200)
        print(f"  {cg:<4} 場數 {sub.race.nunique():>4}  Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}] {verdict(lo, hi)}")

    print("\n相關性（OOS 行）")
    print(df[["t", "t_dd", "t_dv", "t_dc", "lmkt"]].corr(method="spearman").round(3).to_string())

    print("\n穩定性（(練馬師,班次組) ≥30 仗，delta 相對同期整體）")
    for k, (n, r, lo, hi) in stability(m).items():
        print(f"  {k:<13} 格數 {n:>3}  r {r:+.3f} [{lo:+.3f},{hi:+.3f}] {verdict(lo, hi)}")
    print("\n分佈 t_dc：")
    print(df.t_dc.describe([.05, .25, .5, .75, .95]).round(4).to_string())


if __name__ == "__main__":
    main()
