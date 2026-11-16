"""Kelvin 2026-11-17：(a)「報咗一星期內嘅比賽 → 今仗似熱身」深挖；(b) 大幅增程（≥400 米）可唔可以入分、乜情況下入。

殘差 = 入頭三 − p（live dump I1，之前季校準），dev 2020–23／holdout 2024–25，bootstrap（按賽日）500。
資料：HKJC 馬匹頁每仗（日期、場地、路程、班次、名次）。
(a) 用咗今仗之後嘅出賽 —— 只係研究；live 要賽前已知嘅報名資料。
(b) 只用日期早過今仗嘅往績。
用法：python3 diag_warmup_distance.py <live dump I1>
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


def dd(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def feats(rr, i):
    t = rr[i]
    d0 = t["d"]
    dist, cls = F.num(t.get("distance")), F.num(t.get("class"))
    past, fut = rr[:i], rr[i + 1:]
    f = {}
    # (a) 下仗好快再出（研究）
    nx = fut[0] if fut else None
    g = dd(d0, nx["d"]) if nx else None
    soon = g is not None and g <= 7
    ncls, ndist, npos = (F.num(nx.get("class")), F.num(nx.get("distance")), F.pos(nx.get("pos"))) if nx else (None,) * 3
    hv_now = "跑馬地" in str(t.get("venue_track") or "")
    hv_next = nx is not None and "跑馬地" in str(nx.get("venue_track") or "")
    f.update({
        "A 下仗 ≤7 日（全部）": soon,
        "A 下仗 ≤3 日": g is not None and g <= 3,
        "A 下仗 4–7 日": g is not None and 4 <= g <= 7,
        "A 下仗 8–10 日": g is not None and 8 <= g <= 10,
        "A ≤7 日＋下仗班次較高": soon and ncls is not None and cls is not None and ncls < cls,
        "A ≤7 日＋下仗同班": soon and ncls is not None and ncls == cls,
        "A ≤7 日＋下仗班次較低": soon and ncls is not None and cls is not None and ncls > cls,
        "A ≤7 日＋下仗增程 ≥200": soon and ndist and dist and ndist - dist >= 200,
        "A ≤7 日＋下仗同程（±100）": soon and ndist and dist and abs(ndist - dist) <= 100,
        "A ≤7 日＋下仗減程 ≥200": soon and ndist and dist and dist - ndist >= 200,
        "A ≤7 日＋今仗跑馬地": soon and hv_now,
        "A ≤7 日＋今仗沙田": soon and not hv_now,
        "A ≤7 日＋轉場地": soon and hv_now != hv_next,
        "A ≤7 日＋下仗入位（事後）": soon and npos is not None and npos <= 3,
        "A ≤7 日＋下仗唔入位（事後）": soon and npos is not None and npos > 3,
        "A ≤7 日＋今仗三至五班": soon and cls is not None and cls >= 3,
        "A ≤7 日＋今仗一二班": soon and cls is not None and cls <= 2,
    })
    # (b) 大幅增減程（對上仗）
    if past and dist:
        pd = F.num(past[-1].get("distance"))
        if pd:
            up, down = dist - pd >= 400, pd - dist >= 400
            longest = max((F.num(q.get("distance")) or 0) for q in past)
            placed_far = any((F.num(q.get("distance")) or 0) >= dist - 100 and (F.pos(q.get("pos")) or 99) <= 3 for q in past)
            tried = longest >= dist - 100
            lp = F.pos(past[-1].get("pos"))
            f.update({
                "B 大幅增程 ≥400（全部）": up,
                "B 增程＋從未跑過咁遠（±100）": up and not tried,
                "B 增程＋跑過咁遠但未上名": up and tried and not placed_far,
                "B 增程＋喺咁遠上過名": up and placed_far,
                "B 增程＋上仗 ≤1200 → 今仗 ≥1600": up and pd <= 1200 and dist >= 1600,
                "B 增程＋三至五班": up and cls is not None and cls >= 3,
                "B 增程＋一二班": up and cls is not None and cls <= 2,
                "B 增程＋上仗入位": up and lp is not None and lp <= 3,
                "B 增程＋上仗唔入位": up and lp is not None and lp > 3,
                "B 增程＋在港 ≤5 仗": up and len(past) <= 5,
                "B 增程＋在港 >5 仗": up and len(past) > 5,
                "B 大幅減程 ≥400（全部）": down,
                "B 減程＋喺呢個路程上過名": down and any(abs((F.num(q.get("distance")) or 0) - dist) <= 100 and (F.pos(q.get("pos")) or 99) <= 3 for q in past),
                "B 減程＋上仗入位": down and lp is not None and lp <= 3,
                "B 減程＋上仗唔入位": down and lp is not None and lp > 3,
            })
    return f


def main():
    import hkjc_history_replay_pit as p
    runs, _ = F.load()
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    pos_in = {code: {q["d"]: i for i, q in enumerate(rr)} for code, rr in runs.items()}
    key = {}
    for r in df.itertuples():
        i = pos_in.get(r.HorseID, {}).get(r.d)
        if i is not None:
            key[(r.d, int(r.RaceNo), int(r.Rank))] = feats(runs[r.HorseID], i)
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
            f = key.get((x["date"], x["race"], h["pos"]))
            if f is not None:
                recs.append(dict(s=s, d=x["date"], y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + b * z))), f=f))
    print(f"馬次 {len(recs)}")
    rng = np.random.default_rng(0)
    names = []
    for r in recs:
        for k in r["f"]:
            if k not in names:
                names.append(k)
    for k in names:
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            days = defaultdict(list)
            for r in recs:
                if lo <= r["s"] <= hi and r["f"].get(k):
                    days[r["d"]].append(r["y"] - r["p"])
            n = sum(len(v) for v in days.values())
            if n < 30:
                out.append(f"n={n}"); continue
            dk = list(days)
            mean = np.mean([e for v in days.values() for e in v])
            bt = [np.mean([e for j in rng.integers(0, len(dk), len(dk)) for e in days[dk[j]]]) for _ in range(500)]
            out.append(f"{100*mean:+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={n}")
        seas = " ".join(f"{100*np.mean(v):+.0f}" if len(v) >= 20 else "." for v in
                        ([r["y"] - r["p"] for r in recs if r["s"] == s and r["f"].get(k)] for s in sorted({r["s"] for r in recs})))
        print(f"{k}｜dev {out[0]}｜holdout {out[1]}｜逐季 {seas}")


if __name__ == "__main__":
    main()
