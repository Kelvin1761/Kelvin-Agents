"""EXP-20261116-17: fatigue residual on top of the closing market (see PROTOCOL.md).
usage: python3 study.py <dir with atp2026.xlsx, wta2026.xlsx>"""
import sys
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.optimize import minimize

DL = sys.argv[1]
SPLIT = date(2026, 8, 1)
FEATS = ["F1", "F2", "F3", "F4", "F5"]


def num(x):
    try:
        return 0 if pd.isna(x) else int(float(x))
    except (TypeError, ValueError):
        return 0


def load(f, tour):
    d = pd.read_excel(f"{DL}/{f}")
    out = []
    for _, r in d.iterrows():
        g = sum(num(r[f"W{i}"]) + num(r[f"L{i}"]) for i in range(1, 6) if f"W{i}" in r.index)
        s = num(r.Wsets) + num(r.Lsets)
        out.append(dict(tour=tour, date=r.Date.date(), w=str(r.Winner).strip(), l=str(r.Loser).strip(),
                        games=g, sets=s, comment=r.Comment, aw=r.AvgW, al=r.AvgL, bw=r.BFEW, bl=r.BFEL))
    return out


rows = load("atp2026.xlsx", "ATP") + load("wta2026.xlsx", "WTA")
hist = defaultdict(list)  # (tour, name) -> [(date, games, sets)]
for r in rows:
    for p in (r["w"], r["l"]):
        hist[(r["tour"], p)].append((r["date"], r["games"], r["sets"]))


def feats(tour, name, d):
    h = [x for x in hist[(tour, name)] if x[0] < d]
    w3 = [x for x in h if x[0] >= d - timedelta(days=3)]
    f1 = sum(x[1] for x in w3)
    f2 = sum(x[2] for x in w3)
    f3 = int(any(x[0] == d - timedelta(days=1) for x in h))
    f4 = sum(1 for x in h if x[0] >= d - timedelta(days=7))
    last = max(h, key=lambda x: x[0]) if h else None
    f5 = sum(x[1] for x in h if last and x[0] == last[0]) if last and (d - last[0]).days <= 2 else 0
    return np.array([f1, f2, f3, f4, f5], float)


def fair(pa, pb):
    try:
        pa, pb = float(pa), float(pb)
    except (TypeError, ValueError):
        return None
    if not (pa > 1 and pb > 1):
        return None
    ia, ib = 1 / pa, 1 / pb
    return ia / (ia + ib)


E = []
for r in rows:
    if r["comment"] != "Completed":
        continue
    fw = fair(r["aw"], r["al"])
    if fw is None:
        continue
    a_is_w = r["w"] < r["l"]
    A, B = (r["w"], r["l"]) if a_is_w else (r["l"], r["w"])
    fa = fw if a_is_w else 1 - fw
    fb_ = fair(r["bw"], r["bl"])
    fbA = None if fb_ is None else (fb_ if a_is_w else 1 - fb_)
    x = feats(r["tour"], A, r["date"]) - feats(r["tour"], B, r["date"])
    E.append(dict(date=r["date"], tour=r["tour"], y=int(a_is_w), fair=fa, bfair=fbA, **dict(zip(FEATS, x))))
df = pd.DataFrame(E)
df["dev"] = df.date < SPLIT
lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
print(f"evaluation rows {len(df)}  dev {df.dev.sum()}  holdout {(~df.dev).sum()}")
print("feature nonzero share (dev):", {f: round((df[df.dev][f] != 0).mean(), 3) for f in FEATS})


def fit(X, y):
    def nll(w):
        z = X @ w
        return np.sum(np.logaddexp(0, z) - y * z)
    w0 = np.zeros(X.shape[1]); w0[1] = 1
    return minimize(nll, w0, method="BFGS").x


def ll(X, y, w):
    z = X @ w
    return -(y * z - np.logaddexp(0, z))  # per-row loss


def boot(v, n=4000, seed=20260826):
    rng = np.random.default_rng(seed)
    m = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(n)])
    return v.mean(), np.quantile(m, 0.025), np.quantile(m, 0.975)


def run(base_col, label):
    d = df[df[base_col].notna()].copy()
    d["lf"] = lg(d[base_col].astype(float))
    dv, ho = d[d.dev], d[~d.dev]
    Xb = lambda t: np.c_[np.ones(len(t)), t.lf]
    wb = fit(Xb(dv), dv.y.values)
    lb = ll(Xb(ho), ho.y.values, wb)
    print(f"\n[{label}] dev {len(dv)} holdout {len(ho)}  baseline a,b = {wb.round(3)}  holdout LL {lb.mean():.4f}")
    res = {}
    for f in FEATS:
        Xf = lambda t: np.c_[np.ones(len(t)), t.lf, t[f]]
        wf = fit(Xf(dv), dv.y.values)
        lf_ = ll(Xf(ho), ho.y.values, wf)
        m, lo, hi = boot(lb - lf_)
        # dev-only check of the same improvement (in-sample)
        mdev = (ll(Xb(dv), dv.y.values, wb) - ll(Xf(dv), dv.y.values, wf)).mean()
        res[f] = (wf[2], m, lo, hi)
        print(f"  {f}: g={wf[2]:+.4f}  dev ΔLL {mdev*1000:+.3f}e-3  holdout ΔLL {m*1000:+.3f}e-3 [{lo*1000:+.3f}, {hi*1000:+.3f}]")
    return res


r1 = run("fair", "Avg close (primary)")
run("bfair", "Betfair close (sensitivity)")
g, m, lo, hi = r1["F1"]
v = "PROMISING" if (lo > 0 and g < 0) else ("REJECT" if hi < 0 else "NO EVIDENCE")
print(f"\nPRIMARY F1 verdict: {v}")
# descriptive: market calibration by F1 bucket on holdout (actual - fair)
ho = df[~df.dev]
for name, mask in (("A much more tired (F1<=-20)", ho.F1 <= -20), ("similar", ho.F1.abs() < 20), ("B much more tired (F1>=20)", ho.F1 >= 20)):
    s = ho[mask]
    print(f"  {name}: n={len(s)} actual {s.y.mean():.3f} fair {s.fair.mean():.3f} gap {s.y.mean()-s.fair.mean():+.3f}")
