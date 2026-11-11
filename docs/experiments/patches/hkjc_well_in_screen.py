"""EXP-20261111-08：HKJC well-in（模型能力 vs 官方評分）screening，只量度。

用法：
  PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_well_in_screen.py <dump.jsonl>
<dump.jsonl> = hkjc_eval_harness.py run --dump-matrix 嘅輸出（baseline 引擎）。
評分由每場排位表重新讀（賽前資料）。
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts", REPO):
    sys.path.insert(0, str(p))

HANDICAP = {"第一班", "第二班", "第三班", "第四班", "第五班"}


def ratings_for(md: Path, race_no: int):
    import hkjc_auto_orchestrator as orch
    path = orch._racecard_path_for_logic(md / f"Race_{race_no}_Logic.json", race_no)
    if not path or not Path(path).exists():
        return None, {}
    cls, info = orch._parse_racecard_meta(Path(path).read_text(encoding="utf-8"))
    out = {}
    for num, e in info.items():   # info 同時用馬名同馬號做 key；只要馬號
        if str(num).isdigit() and e.get("rating") is not None:
            out[int(num)] = int(e["rating"])
    return cls, out


def build(dump_path):
    import wongchoi_paths
    from hkjc_racing_engine import dimensions
    w_ca = dimensions._CLASS_WEIGHT
    root = Path(wongchoi_paths.HK_RACING)
    rows = []
    for line in open(dump_path, encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("horses"):
            continue
        if r.get("meeting_dead_fields") and set(r["meeting_dead_fields"]) - {"track_going_score", "trackwork_trend_score"}:
            continue   # 同 compare 一樣剔死欄位場次（只容許兩個長期死嘅）
        cls, rat = ratings_for(root / r["meeting"], int(r["race"]))
        if not any(c in str(cls) for c in HANDICAP):
            continue
        for h in r["horses"]:
            if h["debut"] or h["pos"] is None or h["n"] not in rat:
                continue
            rows.append({
                "race": f"{r['meeting']}|{r['race']}", "date": r["date"], "cls": cls,
                "place": float(h["pos"] <= 3), "raw": h["raw"],
                "A": h["raw"] - w_ca * h["m"].get("class_advantage", 60.0),
                "R": rat[h["n"]], "wscore": h["f"].get("weight_score"),
            })
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df = df[g.R.transform("std") > 0]
    df = df[df.groupby("race").race.transform("size") >= 5].copy()
    g = df.groupby("race")
    for c in ("A", "R", "raw"):
        df["z" + c] = (df[c] - g[c].transform("mean")) / g[c].transform("std").replace(0, np.nan)
    df = df.dropna(subset=["zA", "zR", "zraw"])
    g = df.groupby("race")
    df["exp"] = g.place.transform("mean")
    df["rA"] = g.A.rank(pct=True)
    df["rR"] = g.R.rank(pct=True)
    return df.reset_index(drop=True)


def coef_ci(df, cols, target="zR", n=1000):
    def fit(d):
        m = LogisticRegression(max_iter=2000, C=1e6).fit(d[cols], d.place)
        return m.coef_[0][cols.index(target)]
    point = fit(df)
    races = df.race.unique()
    idx = {r: np.where(df.race.values == r)[0] for r in races}
    rng = np.random.default_rng(0)
    bs = [fit(df.iloc[np.concatenate([idx[r] for r in rng.choice(races, len(races))])]) for _ in range(n)]
    return point, np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def group_ci(df, mask, ref, n=1000):
    a = (df.place - df.exp)[mask].values
    b = (df.place - df.exp)[ref].values
    rng = np.random.default_rng(1)
    bs = [rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)]
    return (a.mean() - b.mean()) * 100, np.percentile(bs, 2.5) * 100, np.percentile(bs, 97.5) * 100, len(a), len(b)


def main():
    df = build(sys.argv[1])
    print(f"讓磅賽 {df.race.nunique()} 場 / {len(df)} 匹（{df.date.min()} → {df.date.max()}）")
    print(f"相關：ρ(A, R) 場內 = {df[['zA','zR']].corr(method='spearman').iloc[0,1]:+.3f}；"
          f"ρ(weight_score, R) = {df[['wscore','zR']].corr(method='spearman').iloc[0,1]:+.3f}")

    print("\n主測試：place ~ zA + zR，zR 係數 [95% CI]（負 = well-in 有利）")
    p, lo, hi = coef_ci(df, ["zA", "zR"])
    print(f"  zR {p:+.4f} [{lo:+.4f},{hi:+.4f}]")
    pa, loa, hia = coef_ci(df, ["zA", "zR"], target="zA")
    print(f"  zA {pa:+.4f} [{loa:+.4f},{hia:+.4f}]")
    print("對照：place ~ z(raw 完整模型) + zR")
    p2, lo2, hi2 = coef_ci(df, ["zraw", "zR"])
    print(f"  zR {p2:+.4f} [{lo2:+.4f},{hi2:+.4f}]")

    print("\n輔助：well-in 組（A 頭三分一 而且 R 尾三分一）vs A 頭三分一其餘")
    topA = df.rA > 2 / 3
    wellin = topA & (df.rR <= 1 / 3)
    d, l, h, na, nb = group_ci(df, wellin, topA & ~wellin)
    print(f"  超額差 {d:+.2f}pp [{l:+.2f},{h:+.2f}]  n={na} vs {nb}")
    print(f"  well-in 上名率 {df.place[wellin].mean()*100:.1f}%（期望 {df.exp[wellin].mean()*100:.1f}%）；"
          f"其餘 A 頭三分一 {df.place[topA & ~wellin].mean()*100:.1f}%")

    print("\n分層：A 三分位 × R 三分位 上名超額（pp）")
    df["tA"] = pd.cut(df.rA, [0, 1/3, 2/3, 1.0001], labels=["A低", "A中", "A高"])
    df["tR"] = pd.cut(df.rR, [0, 1/3, 2/3, 1.0001], labels=["R低", "R中", "R高"])
    tab = df.assign(ex=(df.place - df.exp) * 100).pivot_table(index="tA", columns="tR", values="ex", aggfunc="mean", observed=True)
    cnt = df.pivot_table(index="tA", columns="tR", values="place", aggfunc="size", observed=True)
    print(tab.round(2).to_string()); print(cnt.to_string())


if __name__ == "__main__":
    main()
