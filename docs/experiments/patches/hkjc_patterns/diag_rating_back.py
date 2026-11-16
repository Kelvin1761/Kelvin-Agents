"""Kelvin 2026-11-17：「評分跌返贏馬分」唔止降班 —— 搵邊個子集有訊號（live I1 之上殘差）。

EXP-20261115-15：全部（三至五班）dev +1.4、holdout +0.1；降班＋跌返 +5.2／+5.2。
呢度拆：低過贏馬分幾多、贏馬幾耐之前、而家班次 vs 贏馬時班次、上仗表現、評分係咪連跌。只用日期早過今仗嘅 HKJC 馬匹頁。
用法：python3 diag_rating_back.py <live dump I1>
"""
import json
import sys
from collections import defaultdict
from datetime import date

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, sys.path[0])
import features as F  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def feats(past, today, d):
    tr, tc = F.num(today.get("rating")), F.num(today.get("class"))
    if tr is None or not past:
        return None
    wins = [q for q in past if F.pos(q.get("pos")) == 1 and F.num(q.get("rating")) is not None]
    if not wins:
        return None
    w = wins[-1]
    wr, wc = F.num(w["rating"]), F.num(w.get("class"))
    last = past[-1]
    lc, lp, lr = F.num(last.get("class")), F.pos(last.get("pos")), F.num(last.get("rating"))
    drop = bool(tc and lc and tc > lc)
    gap = tr - wr
    age = (date.fromisoformat(d) - date.fromisoformat(w["d"])).days
    back = gap <= 0 and not drop
    return {
        "（對照）有贏過、評分高過贏馬分 >2": gap > 2 and not drop,
        "評分 ≤ 贏馬分（唔降班）—— 全部": back,
        "接近：高 1–2 分（唔降班）": 0 < gap <= 2 and not drop,
        "等於／低 0–2 分": back and gap >= -2,
        "低 3–5 分": back and -5 <= gap < -2,
        "低 ≥6 分": back and gap < -5,
        "贏馬 ≤365 日內": back and age <= 365,
        "贏馬 >365 日": back and age > 365,
        "而家同贏馬時同班或更低班": back and tc is not None and wc is not None and tc >= wc,
        "而家高過贏馬時班次": back and tc is not None and wc is not None and tc < wc,
        "三至五班": back and tc is not None and tc >= 3,
        "一二班": back and tc is not None and tc <= 2,
        "上仗入位（1–3）": back and lp is not None and lp <= 3,
        "上仗 4–6 名": back and lp is not None and 4 <= lp <= 6,
        "上仗 7 名或以後": back and lp is not None and lp >= 7,
        "評分上仗再跌": back and lr is not None and tr < lr,
        "降班＋跌返（現有標籤）": gap <= 0 and drop,
    }


def main():
    import hkjc_history_replay_pit as p
    runs, _ = F.load()
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    key = {}
    for r in df.itertuples():
        hid = r.HorseID
        past = [q for q in runs.get(hid, []) if q["d"] < r.d]
        today = next((q for q in runs.get(hid, []) if q["d"] == r.d), None)
        if today:
            key[(r.d, int(r.RaceNo), int(r.Rank))] = feats(past, today, r.d)
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    from sklearn.linear_model import LogisticRegression
    calib = {}
    for s in sorted(by):
        X, Y = [], []
        for x in (x for t in by if t < s for x in by[t]) if s > min(by) else by[s]:
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
            f = key.get((x["date"], x["race"], h["pos"]))
            if f:
                recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + b * z))), f=f))
    print(f"有贏過嘅馬次 {len(recs)}")
    rng = np.random.default_rng(0)
    for k in recs[0]["f"]:
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            y = np.array([r["y"] - r["p"] for r in recs if lo <= r["s"] <= hi and r["f"][k]])
            if len(y) < 30:
                out.append(f"n={len(y)}"); continue
            bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(500)]
            out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(y)}")
        seas = " ".join(f"{100*np.mean(v):+.0f}" if len(v) >= 20 else "." for v in
                        ([r["y"] - r["p"] for r in recs if r["s"] == s and r["f"][k]] for s in sorted({r["s"] for r in recs})))
        print(f"{k}｜dev {out[0]}｜holdout {out[1]}｜逐季 {seas}")


if __name__ == "__main__":
    main()
