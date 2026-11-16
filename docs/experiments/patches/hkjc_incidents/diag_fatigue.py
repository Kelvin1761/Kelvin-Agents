"""Kelvin 2026-11-17：疲勞／匆匆再出／密集出賽／大幅增減程／下仗好快再出（熱身？）—— live 之上嘅殘差。

殘差 = 入頭三 − p，p = live dump（I1）raw 用之前季校準（同 diag_round3.py）。
出賽日期用事件報告表嘅賽事列表（load_runs：每匹馬全部出賽，唔理有冇報告）；路程用 dump 嘅場次路程。
「下仗」特徵用咗今仗之後嘅資料 —— 只係研究，唔可以直接做 live 特徵；live 要搵賽前已公開嘅來源（報名表）。
用法：python3 diag_fatigue.py <live dump I1> <old_incidents.json>
"""
import json
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diag import season  # noqa: E402
from diag_full import calibrate, load_runs  # noqa: E402


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def features(hist, i, dist_now):
    """hist = [(date, distance)] 按日期；i = 今仗 index。"""
    d0 = hist[i][0]
    prev = hist[:i]
    if not prev:
        return None
    gap = days(prev[-1][0], d0)
    n30 = sum(1 for d, _ in prev if days(d, d0) <= 30)
    n60 = sum(1 for d, _ in prev if days(d, d0) <= 60)
    nxt = days(d0, hist[i + 1][0]) if i + 1 < len(hist) else None
    pd = prev[-1][1]
    mv = (dist_now - pd) if (dist_now and pd) else None
    f = {
        "相隔 ≤7 日": gap <= 7,
        "相隔 8–10 日": 8 <= gap <= 10,
        "相隔 11–14 日": 11 <= gap <= 14,
        "相隔 15–21 日": 15 <= gap <= 21,
        "相隔 22–35 日（對照）": 22 <= gap <= 35,
        "相隔 36–60 日": 36 <= gap <= 60,
        "相隔 61–120 日": 61 <= gap <= 120,
        "相隔 >120 日": gap > 120,
        "近 30 日已跑 ≥2 仗": n30 >= 2,
        "近 60 日已跑 ≥3 仗": n60 >= 3,
        "近 60 日已跑 ≥4 仗": n60 >= 4,
        "連續第 3 仗、每仗相隔 ≤14 日": i >= 2 and gap <= 14 and days(hist[i - 2][0], prev[-1][0]) <= 14,
        "【研究】下仗 ≤7 日後": nxt is not None and nxt <= 7,
        "【研究】下仗 8–14 日後": nxt is not None and 8 <= nxt <= 14,
        "增程 ≥400 米": mv is not None and mv >= 400,
        "增程 200–399 米": mv is not None and 200 <= mv < 400,
        "減程 200–399 米": mv is not None and -400 < mv <= -200,
        "減程 ≥400 米": mv is not None and mv <= -400,
    }
    return f


def main():
    runs = load_runs(sys.argv[2])
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    dist_of = {(x["date"], x["race"]): x.get("distance") for x in rows}
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
    hist = {c: sorted({(d, dist_of.get((d, n))) for d, n, _, _ in v}) for c, v in runs.items()}
    idx = {c: {d: i for i, (d, _) in enumerate(h)} for c, h in hist.items()}
    calib = calibrate(rows)
    recs = []
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, bb = calib[s]
        for h, z in zip(hs, rc):
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            if not c or x["date"] not in idx[c]:
                continue
            f = features(hist[c], idx[c][x["date"]], x.get("distance"))
            if f is None:
                continue
            recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + bb * z))), f=f))
    print(f"馬次 {len(recs)}")
    rng = np.random.default_rng(0)
    for k in recs[0]["f"]:
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            sub = [r for r in recs if lo <= r["s"] <= hi]
            y = np.array([r["y"] - r["p"] for r in sub if r["f"][k]])
            if len(y) < 30:
                out.append(f"n={len(y)}"); continue
            bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(500)]
            out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(y)} ({100*len(y)/len(sub):.1f}%)")
        seas = []
        for s in sorted({r["s"] for r in recs}):
            y = [r["y"] - r["p"] for r in recs if r["s"] == s and r["f"][k]]
            seas.append(f"{100*np.mean(y):+.0f}" if len(y) >= 20 else ".")
        print(f"{k}｜dev {out[0]}｜holdout {out[1]}｜逐季 {' '.join(seas)}")


if __name__ == "__main__":
    main()
