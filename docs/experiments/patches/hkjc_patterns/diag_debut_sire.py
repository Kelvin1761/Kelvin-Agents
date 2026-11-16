"""Kelvin 2026-11-17「初出馬係咪要睇埋父系同母系去評分？」—— point-in-time 診斷（只用今仗日期之前嘅後代往績）。

AU 教訓（memory au-sire-signal-is-leakage）：leave-one-out 會造假訊號，所以呢度嚴格 as-of：
  父系分 = 同一父系嘅其他馬，喺今仗日期之前嘅**香港首 3 仗**入位率（K=30 收縮向全體），樣本 < 10 仗 = 冇。
  外祖父、母系（同母兄弟姊妹）一樣計法。
殘差 = 入頭三 − p（live dump I1，之前季校準）；只睇初出馬（dump `debut`）；按父系分三分位。
用法：python3 diag_debut_sire.py <live dump I1>
"""
import gzip
import json
import sys
from bisect import bisect_left
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402

K = 30
MIN_N = 10


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_pit as p
    runs, prof = F.load()
    # 每個血統鍵：[(日期, 入位)]（每匹後代嘅香港首 3 仗）
    lines = {"父系": defaultdict(list), "外祖父": defaultdict(list), "母系": defaultdict(list)}
    for code, rr in runs.items():
        pr = prof.get(code) or {}
        for q in rr[:3]:
            ps = F.pos(q.get("pos"))
            if ps is None:
                continue
            for k in lines:
                if pr.get(k):
                    lines[k][pr[k]].append((q["d"], code, float(ps <= 3)))
    for k in lines:
        for v in lines[k].values():
            v.sort()
    allp = np.mean([e for v in lines["父系"].values() for _, _, e in v])

    def score(kind, key, d, me):
        v = lines[kind].get(key) or []
        i = bisect_left(v, (d,))
        prior = [e for dd, c, e in v[:i] if c != me]
        if len(prior) < MIN_N:
            return None
        return (sum(prior) + K * allp) / (len(prior) + K)

    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    key = {}
    for r in df.itertuples():
        pr = prof.get(r.HorseID) or {}
        key[(r.d, int(r.RaceNo), int(r.Rank))] = {k: score(k, pr.get(k), r.d, r.HorseID) for k in lines}
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
        for h, z in zip(hs, rc):
            if not h.get("debut"):
                continue
            f = key.get((x["date"], x["race"], h["pos"])) or {}
            recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + b * z))), f=f))
    print(f"初出馬次 {len(recs)}；整體殘差 dev {100*np.mean([r['y']-r['p'] for r in recs if r['s']<=2023]):+.1f}、"
          f"holdout {100*np.mean([r['y']-r['p'] for r in recs if r['s']>=2024]):+.1f}")
    rng = np.random.default_rng(0)
    for kind in lines:
        have = [r for r in recs if r["f"].get(kind) is not None]
        print(f"\n{kind}：有分 {len(have)}／{len(recs)}")
        if len(have) < 90:
            continue
        cut = np.percentile([r["f"][kind] for r in have if r["s"] <= 2023], [33.3, 66.7])
        for name, lo_, hi_ in (("低三分一", -1, cut[0]), ("中", cut[0], cut[1]), ("高三分一", cut[1], 2)):
            out = []
            for lo, hi in ((2020, 2023), (2024, 2025)):
                y = np.array([r["y"] - r["p"] for r in have if lo <= r["s"] <= hi and lo_ < r["f"][kind] <= hi_])
                if len(y) < 30:
                    out.append(f"n={len(y)}"); continue
                bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(500)]
                out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(y)}")
            print(f"  {name}（≤{hi_:.3f}）｜dev {out[0]}｜holdout {out[1]}")


if __name__ == "__main__":
    main()
