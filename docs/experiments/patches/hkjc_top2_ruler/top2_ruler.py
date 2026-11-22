"""HKJC 頭二尺原型（Kelvin 2026-11-23「先整頭二尺」）。

主指標：頭二 Plackett–Luce 對數似然（逐場）：
  P(第一) = softmax(β·(raw − 場均))，P(第二 | 第一已走) = 同一個 softmax 剷走頭馬再正規化。
  頭二損失 = −[log P(第一) + log P(第二 | 第一)]。β 由訓練段 fit（同 v5 一樣：dev 逐季 walk-forward；holdout 用全 dev），
  baseline 同候選各自 fit。Δ = 候選 − baseline（每場），按賽日 bootstrap；null = 候選 raw Δ 場內洗牌。
報埋：舊「頭二選有中」、首選贏、頭二都入頭三。
用法：python3 top2_ruler.py <base> <cand> [--window dev|holdout] [--null N] [--quiet]
"""
import json, sys
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize_scalar
WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31")}
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def load(p): return {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x}
def race_rx(x, raws=None):
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]) if raws is None else np.asarray(raws, float)
    pos = np.array([h["pos"] for h in hs])
    return r - r.mean(), pos
def pl_loss(rc, pos, b):
    order = np.argsort(pos, kind="stable")
    i1, i2 = order[0], order[1]
    z = b * rc; z = z - z.max()
    e = np.exp(z); s = e.sum()
    return -(np.log(e[i1] / s) + np.log(e[i2] / (s - e[i1])))
def fit(races):
    data = [race_rx(x) for x in races]
    data = [(rc, pos) for rc, pos in data if (pos == 1).sum() == 1 and (pos == 2).sum() >= 1]
    f = lambda b: sum(pl_loss(rc, pos, b) for rc, pos in data)
    return minimize_scalar(f, bounds=(0.0, 2.0), method="bounded").x
def ok_race(x):
    pos = [h["pos"] for h in x["horses"] if h["pos"]]
    return pos.count(1) == 1 and 2 in pos
def judge(B, C, window="dev", nnull=200, quiet=False, seed=0):
    keys = sorted(set(B) & set(C)); lo, hi = WIN[window]
    test = [k for k in keys if lo <= B[k]["date"] <= hi and ok_race(B[k])]
    devk = [k for k in sorted(B) if WIN["dev"][0] <= B[k]["date"] <= WIN["dev"][1]]
    if window == "dev":
        par = {}
        for ts in (2021, 2022, 2023):
            tr = [k for k in devk if season(B[k]["date"]) < ts]
            par[ts] = (fit([B[k] for k in tr]), fit([C[k] for k in tr if k in C]))
        test = [k for k in test if season(B[k]["date"]) in par]
        P = lambda k: par[season(B[k]["date"])]
    else:
        pb, pc = fit([B[k] for k in devk]), fit([C[k] for k in devk if k in C]); P = lambda k: (pb, pc)
    rows = []
    for k in test:
        bb, bc = P(k)
        rb, pos = race_rx(B[k]); rc_, _ = race_rx(C[k])
        lb, lc = pl_loss(rb, pos, bb), pl_loss(rc_, pos, bc)
        hs = [h for h in B[k]["horses"] if h["pos"]]
        top3 = {h["n"] for h in hs if h["pos"] <= 3}; win = [h["n"] for h in hs if h["pos"] == 1][0]
        def m(x):
            p2 = [n for n in x["picks"] if n in {h["n"] for h in hs}][:2]
            return [float(any(n in top3 for n in p2)), float(p2[0] == win), float(all(n in top3 for n in p2))]
        rows.append({"k": k, "d": B[k]["date"], "dl": lc - lb, "m": np.array(m(C[k])) - np.array(m(B[k]))})
    days = sorted({r["d"] for r in rows}); byd = defaultdict(list)
    for i, r in enumerate(rows): byd[r["d"]].append(i)
    dl = np.array([r["dl"] for r in rows]); M = np.array([r["m"] for r in rows])
    rng = np.random.default_rng(seed); bl, bm = [], []
    for _ in range(2000):
        ii = np.concatenate([byd[days[j]] for j in rng.integers(0, len(days), len(days))]); bl.append(dl[ii].mean()); bm.append(M[ii].mean(0))
    bl, bm = np.array(bl), np.array(bm)
    null = []
    for _ in range(nnull):
        tot = 0.0
        for r in rows:
            k = r["k"]; bb, bc = P(k)
            bh = {h["n"]: h["raw"] for h in B[k]["horses"]}; ch = {h["n"]: h["raw"] for h in C[k]["horses"]}
            hs = [h for h in B[k]["horses"] if h["pos"]]
            d = np.array([ch[h["n"]] - bh[h["n"]] for h in hs]); raws = np.array([h["raw"] for h in hs]) + rng.permutation(d)
            rcn, pos = race_rx(B[k], raws); tot += pl_loss(rcn, pos, bc) - pl_loss(race_rx(B[k])[0], pos, bb)
        null.append(tot / len(rows))
    null = np.array(null); d = dl.mean()
    out = {"n": len(rows), "d": d, "lo": np.percentile(bl, 2.5), "hi": np.percentile(bl, 97.5),
           "null": (null > d).mean() if nnull else float("nan"), "m": M.mean(0) * 100,
           "mlo": np.percentile(bm, 2.5, axis=0) * 100, "mhi": np.percentile(bm, 97.5, axis=0) * 100}
    if not quiet:
        print(f"窗 {window}：{len(rows)} 場")
        print(f"Δ頭二 PL 損失（每場）{d:+.5f} [{out['lo']:+.5f},{out['hi']:+.5f}]｜好過 null {100*out['null']:.0f}%")
        for i, lab in enumerate(("頭二選有中", "首選贏", "頭二都入頭三")):
            print(f"{lab} {out['m'][i]:+.2f} [{out['mlo'][i]:+.2f},{out['mhi'][i]:+.2f}]")
    return out
if __name__ == "__main__":
    a = sys.argv
    judge(load(a[1]), load(a[2]), a[a.index("--window") + 1] if "--window" in a else "dev", int(a[a.index("--null") + 1]) if "--null" in a else 200)
