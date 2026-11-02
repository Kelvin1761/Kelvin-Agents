#!/usr/bin/env python3
"""EXP-20261102-07 arm 產生器（Z8／Z10／R8／ZD8）。規格見 protocol —— 唔准喺度改。

    python3 au_draw_bigfield_arms_20261102.py --dump DUMP.json --outdir ARMS
"""
import argparse, copy, json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

START, WARMUP_DAYS = "2026-08-05", 21
ARMS = {"Z8": (8, "z", False), "Z10": (10, "z", False), "R8": (8, "raw", False), "ZD8": (8, "z", True)}


def dist_band(row):
    try:
        d = float(str(row.get("distance")).rstrip("m"))
    except (TypeError, ValueError):
        return None
    return 0 if d <= 1200 else 1 if d <= 1600 else 2


def draw_feature(race, kind):
    """→ 每匹馬 d（越大越內），或者 None（有馬冇檔位）。"""
    try:
        b = [float(x["barrier"]) for x in race["rows"]]
    except (TypeError, ValueError, KeyError):
        return None
    if any(v <= 0 for v in b):
        return None
    n = len(b)
    order = sorted(range(n), key=lambda i: (b[i], race["rows"][i]["n"]))
    rank = [0.0] * n
    for k, i in enumerate(order):
        rank[i] = float(k)
    rank = np.array(rank)
    if kind == "raw":
        return -(rank - rank.mean())
    sd = rank.std()
    return -(rank - rank.mean()) / sd if sd > 0 else rank * 0


def features(race, thr, kind, by_dist):
    n = len(race["rows"])
    width = 3 if by_dist else 1
    if n < thr:
        return np.zeros((n, width))
    d = draw_feature(race, kind)
    if d is None:
        return np.zeros((n, width))
    if not by_dist:
        return d[:, None]
    band = dist_band(race["rows"][0])
    X = np.zeros((n, 3))
    if band is not None:
        X[:, band] = d
    return X


def fit(train):
    """條件 logit：u = a·綜合分 + c·X；回 c / a（綜合分單位）。"""
    if not train:
        return None
    k = train[0][1].shape[1]

    def nll(p):
        t = 0.0
        for ab, X, y in train:
            u = p[0] * ab + X @ p[1:]
            m = u.max()
            t -= (u[y == 1] - (m + np.log(np.exp(u - m).sum()))).sum()
        return t
    p = minimize(nll, np.r_[0.1, np.zeros(k)], method="BFGS").x
    return p[1:] / p[0] if p[0] > 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    races = sorted([r for r in json.loads(Path(a.dump).read_text())["races"] if r["date"] >= START],
                   key=lambda r: (r["date"], r["meeting"], r["race"]))
    days = sorted({r["date"] for r in races})
    desc = {"races": len(races), "days": len(days), "warmup_days": days[:WARMUP_DAYS][-1:], "betas": {}}
    for name, (thr, kind, by_dist) in ARMS.items():
        X_all = [features(r, thr, kind, by_dist) for r in races]
        fit_rows = []
        for r, X in zip(races, X_all):
            ab = np.array([x["ability"] for x in r["rows"]], float)
            y = np.array([int(x["pos"] <= 3) for x in r["rows"]])
            if X.any() and 0 < y.sum() < len(y):
                fit_rows.append((r["date"], (ab - ab.mean(), X, y)))
        built, betas = [], {}
        for i, day in enumerate(days):
            beta = None
            if i >= WARMUP_DAYS:
                beta = fit([t for d, t in fit_rows if d < day])
            betas[day] = None if beta is None else [round(float(v), 4) for v in beta]
        for r, X in zip(races, X_all):
            beta = betas[r["date"]]
            rr = copy.deepcopy(r)
            if beta is not None:
                adj = X @ np.array(beta)
                for x, v in zip(rr["rows"], adj):
                    x["ability"] = round(x["ability"] + float(v), 4)
            built.append(rr)
        desc["betas"][name] = {d: betas[d] for d in days[WARMUP_DAYS::7] + days[-1:]}
        (out / f"{name}.json").write_text(json.dumps({"races": built}))
        print(name, "final beta", betas[days[-1]], flush=True)
    (out / "base.json").write_text(json.dumps({"races": races}))
    (out / "describe.json").write_text(json.dumps(desc, indent=1))


if __name__ == "__main__":
    main()
