"""Kelvin 2026-11-17 Q5：「晨操係咪要配合出賽頻率去睇？出得密要游水恢復，出得疏多操有幫助？」

只用現役馬晨操（EXP-20261115-21 features.jsonl，賽日之前紀錄）；殘差 = 入頭三 − p（live dist_D1，之前季校準）。
出賽頻率 = 距上仗日數（HKJC 馬匹頁）：密 ≤14 日、中 15–34、疏 ≥35。
特徵（同場有紀錄嘅馬之間比較）：sw14 游水（14 日）、g28 快操（28 日）、tr14 踱步、trial42 試閘 —— 按全體三分位分低／中／高。
dev = 2020/21–2023/24、holdout = 2024/25 起（晨操語料細，兩段都報）。用法：python3 diag_trackwork_freq.py <dist_D1.jsonl> <features.jsonl>
"""
import json
import sys
from collections import defaultdict
from datetime import date

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_pit as p
    tw = {(x["date"], x["race"], x["brand"]): x for x in map(json.loads, open(sys.argv[2]))}
    pages, _ = F.load()
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    key = {}
    for r in df.itertuples():
        f = tw.get((r.d, int(r.RaceNo), r.HorseID))
        if not f:
            continue
        past = [q for q in pages.get(r.HorseID, []) if q["d"] < r.d]
        gap = (date.fromisoformat(r.d) - date.fromisoformat(past[-1]["d"])).days if past else None
        key[(r.d, int(r.RaceNo), int(r.Rank))] = dict(f, gap=gap)
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    from sklearn.linear_model import LogisticRegression
    calib = {}
    for s in sorted(by):
        X, Y = [], []
        for x in ([x for t in by if t < s for x in by[t]] or by[s]):
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        calib[s] = (m.intercept_[0], m.coef_[0][0])
    recs = []
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, b = calib[s]
        got = [(h, z, key.get((x["date"], x["race"], h["pos"]))) for h, z in zip(hs, rc)]
        got = [g for g in got if g[2] and g[2].get("gap") is not None]
        if len(got) < 4:
            continue
        for h, z, f in got:
            recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + b * z))), f=f))
    print(f"馬次 {len(recs)}")
    rng = np.random.default_rng(0)
    for feat in ("sw14", "g28", "tr14", "trial42"):
        vals = np.array([r["f"].get(feat) or 0 for r in recs], dtype=float)
        q1, q2 = np.percentile(vals, [33.3, 66.7])
        print(f"\n== {feat}（三分位 ≤{q1:.0f} / ≤{q2:.0f} / >{q2:.0f}）")
        for band, (lo, hi) in (("密 ≤14 日", (0, 14)), ("中 15–34", (15, 34)), ("疏 ≥35", (35, 9999))):
            line = []
            for name, test in (("低", lambda v: v <= q1), ("中", lambda v: q1 < v <= q2), ("高", lambda v: v > q2)):
                out = []
                for wlo, whi in ((2020, 2023), (2024, 2026)):
                    y = np.array([r["y"] - r["p"] for r in recs if wlo <= r["s"] <= whi and lo <= r["f"]["gap"] <= hi
                                  and test(float(r["f"].get(feat) or 0))])
                    if len(y) < 40:
                        out.append(f"n{len(y)}"); continue
                    bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(300)]
                    out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}]n{len(y)}")
                line.append(f"{name} {out[0]}／{out[1]}")
            print(f"  {band}｜" + "｜".join(line))


if __name__ == "__main__":
    main()
