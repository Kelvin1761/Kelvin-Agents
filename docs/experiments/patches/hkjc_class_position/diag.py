"""Kelvin 2026-11-16 方向 (a)：今仗評分「班內位置」—— 負磅殘差真正來源（EXP-20261116-07：一二班高評分被高估）。
殘差 = 入頭三 − p（live I1 dump，之前季校準）。特徵全部來自排位表（賽前已知）：評分、評分+/-（上仗至今調整）、班次。
班內位置 = 評分減該班次評分上限（HKJC 讓賽範圍：一班 ≥100（上限當 120）、二班 100、三班 80、四班 60、五班 40），每 10 分。
用法：python3 diag.py <I1.jsonl>
"""
import glob
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

M = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/replay_all"
TOP = {"第一班": 120, "第二班": 100, "第三班": 80, "第四班": 60, "第五班": 40}


def load_cards():
    card, rcls = {}, {}
    for f in glob.glob(f"{M}/*/*排位表.md"):
        t = open(f, encoding="utf-8").read()
        d = re.search(r"日期:\s*(\S+)", t).group(1); rn = int(re.search(r"場次:\s*第(\d+)場", t).group(1))
        rcls[(d, rn)] = (re.search(r"班次:\s*(\S+)", t) or [None, ""])[1]
        for b in re.split(r"\n(?=馬號:)", t)[1:]:
            def g(k):
                m = re.search(rf"{k}:\s*([+-]?\d+)", b)
                return float(m.group(1)) if m else None
            if g("馬號") is not None:
                card[(d, rn, int(g("馬號")))] = dict(r=g("評分"), dr=g(r"評分\+/-"), w=g("負磅"))
    return card, rcls


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def calibrate(rows):
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    out = {}
    for s in sorted(by):
        X, Y = [], []
        for x in [y for t in by if t < s for y in by[t]] or by[s]:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        out[s] = (m.intercept_[0], m.coef_[0][0])
    return out


def main():
    card, rcls = load_cards()
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    cal = calibrate(rows)
    recs = []
    for x in rows:
        s = season(x["date"]); c = rcls.get((x["date"], x["race"]), "")
        if s < 2020 or c not in TOP:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        cs = [card.get((x["date"], x["race"], int(h["n"]))) for h in hs]
        rts = [v["r"] for v in cs if v and v["r"] is not None]
        if len(rts) < 4:
            continue
        r = np.array([h["raw"] for h in hs]); z = r - r.mean(); a, b = cal[s]
        mean_r = np.mean(rts)
        for h, v, zz in zip(hs, cs, z):
            if not v or v["r"] is None:
                continue
            recs.append(dict(s=s, c=c, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + b * zz))),
                             rel=(v["r"] - mean_r) / 10, band=(v["r"] - TOP[c]) / 10, dr=v["dr"]))
    print("馬次", len(recs))
    rng = np.random.default_rng(0)

    def ols(sub, keys):
        X = np.column_stack([[r[k] for r in sub] for k in keys] + [np.ones(len(sub))])
        y = np.array([r["y"] - r["p"] for r in sub])
        bt = []
        for _ in range(300):
            i = rng.integers(0, len(sub), len(sub)); bt.append(np.linalg.lstsq(X[i], y[i], rcond=None)[0][:-1])
        bt = np.array(bt) * 100; est = np.linalg.lstsq(X, y, rcond=None)[0][:-1] * 100
        return " ".join(f"{k} {e:+.2f}[{np.percentile(bt[:, j],2.5):+.2f},{np.percentile(bt[:, j],97.5):+.2f}]" for j, (k, e) in enumerate(zip(keys, est)))
    for lab, lo, hi in (("dev", 2020, 2023), ("holdout", 2024, 2025)):
        print(f"== {lab}（pp／10 分）")
        for c in list(TOP) + ["全部讓賽"]:
            sub = [r for r in recs if lo <= r["s"] <= hi and (c == "全部讓賽" or r["c"] == c) and r["dr"] is not None]
            if len(sub) < 300:
                continue
            print(f"  {c} n={len(sub)}｜只放場內相對 {ols(sub, ['rel'])}｜場內＋班內位置 {ols(sub, ['rel', 'band'])}｜評分調整 {ols(sub, ['dr'])}")
        # 班內位置分段（全部讓賽）
        sub = [r for r in recs if lo <= r["s"] <= hi]
        for name, f in (("超出班頂(>0)", lambda r: r["band"] > 0), ("班頂 0~−5", lambda r: -0.5 <= r["band"] <= 0),
                        ("班中 −5~−15", lambda r: -1.5 <= r["band"] < -0.5), ("班底 <−15", lambda r: r["band"] < -1.5),
                        ("剛加分≥+5", lambda r: (r["dr"] or 0) >= 5), ("剛減分≤−5", lambda r: (r["dr"] or 0) <= -5)):
            y = np.array([r["y"] - r["p"] for r in sub if f(r)])
            bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(400)]
            print(f"  {name} n={len(y)} {100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}]")


if __name__ == "__main__":
    main()
