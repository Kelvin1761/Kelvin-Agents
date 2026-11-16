"""Kelvin 2026-11-16 第三輪：事件報告擴闊 —— 受阻、出閘慢（慣性 vs 一次性）、騎法被查詢／告誡（「拉馬」類）、上兩仗。

殘差 = 入頭三 − p，p = live dump（I1，已含走外疊／醫療）raw 用之前季校準。只睇日期嚴格早過今仗嘅賽事報告（賽後公開，賽前已知）。
「有報告」= 嗰場有事件報告（None = 冇報告 → 唔計入該窗）。
用法：python3 diag_round3.py <live dump I1> <old_incidents.json>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
from diag import CATS, season  # noqa: E402
from diag_full import calibrate, load_runs  # noqa: E402

SLOW = CATS["出閘慢／失地"]
BLK = CATS["受阻／搵唔到位"]
RIDE_Q = r"(查詢|研訊).{0,30}(騎法|策騎)|(騎法|策騎).{0,12}(展開研訊|查詢)"
RIDE_WARN = r"告誡.{0,40}(策騎|騎法)|(策騎|騎法).{0,30}(引起小組關注|未能令小組滿意)|100\(2\)|未有力策|未有盡力"
INSTR = r"獲指示|策騎指示"
DISAPPOINT = r"令人失望|難以接受"
MUST_TRIAL = r"必須試閘"


def has(p, s):
    return bool(s) and bool(re.search(p, s))


def features(prev):
    """prev = 之前賽事 [(date, race, sentence|None, no)]，最近嘅喺最後。"""
    rep = [v[2] for v in prev if v[2] is not None]   # 有報告嘅場次（按時間）
    if not prev or prev[-1][2] is None:
        return None
    last = prev[-1][2]
    last5 = rep[-5:]
    prior4 = rep[-5:-1]
    slow_n5 = sum(has(SLOW, s) for s in last5)
    f = {
        "受阻（上仗）": has(BLK, last),
        "受阻（上兩仗任一）": has(BLK, last) or (len(rep) >= 2 and has(BLK, rep[-2])),
        "受阻（只係上上仗）": (not has(BLK, last)) and len(rep) >= 2 and has(BLK, rep[-2]),
        "出閘慢（上仗）": has(SLOW, last),
        "出閘慢：一次性（上仗慢、之前4仗冇）": has(SLOW, last) and len(prior4) >= 2 and not any(has(SLOW, s) for s in prior4),
        "出閘慢：慣性（上仗慢＋之前4仗有）": has(SLOW, last) and any(has(SLOW, s) for s in prior4),
        "出閘慢：近5仗≥2次": slow_n5 >= 2,
        "出閘慢：近5仗≥3次": slow_n5 >= 3,
        "出閘慢：上仗冇、之前4仗≥2次": (not has(SLOW, last)) and sum(has(SLOW, s) for s in prior4) >= 2,
        "騎法被查詢（上仗）": has(RIDE_Q, last),
        "騎師被告誡／未有力策（上仗）": has(RIDE_WARN, last),
        "有策騎指示交代（上仗）": has(INSTR, last),
        "表現令人失望（上仗）": has(DISAPPOINT, last),
        "必須試閘（上仗）": has(MUST_TRIAL, last),
        "騎法被查詢＋冇醫療（上仗）": has(RIDE_Q, last) and not has(CATS["醫療（喘鳴／流鼻血／心律／跛）"], last),
        "冇任何類別（上仗有報告但空白）": last == "",
    }
    return f


def main():
    runs = load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    calib = calibrate(rows)
    recs = []
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, bb = calib[s]
        rank = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
        for h, z in zip(hs, rc):
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            if not c:
                continue
            f = features([v for v in runs[c] if v[0] < x["date"]])
            if f is None:
                continue
            recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + bb * z))), f=f, rk=rank[h["n"]]))
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
