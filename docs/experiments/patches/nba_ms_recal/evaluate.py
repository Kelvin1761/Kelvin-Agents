"""EXP-20261124-60 (amendment 1): post-hoc recalibration of the published MS p_final.

usage: python3 evaluate.py <legs.csv> dev|holdout
  dev      leave-one-day-out on 11-05..11-11, picks R2 or R3
  holdout  fits on all dev days, scores 11-12..11-24 once (day-clustered bootstrap)
legs.csv comes from build_dataset.py.
"""
import csv, math, sys, random
import numpy as np

STATS = ("pts", "reb", "ast", "fg3m")
DEV = ("2026-11-05", "2026-11-11")
HOLD = ("2026-11-12", "2026-11-24")
SEED, DRAWS = 20261124, 2000


def lg(p):
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1 - p))


def load(path):
    out = []
    for r in csv.DictReader(open(path)):
        if r["target_date"] < DEV[0] or r["target_date"] == "2026-11-19":
            continue
        try:
            pf, pr, y = float(r["p_final"]), float(r["price_at_model"]), int(r["y"])
        except (ValueError, TypeError):
            continue
        if pr <= 1:
            continue
        m = lg(1 / pr)
        out.append(dict(d=r["target_date"], s=r["market"], f=lg(pf), m=m, pf=pf, y=y,
                        line=float(r["line"]), ou=r["ou_line"], ouf=r["ou_fair_over"]))
    return out


def design(rows, form):
    X = []
    for r in rows:
        x = [1.0 if r["s"] == s else 0.0 for s in STATS] + [r["f"]]
        if form == "R2":
            x += [r["m"], r["m"] ** 2]
        elif form == "R3":
            for s in STATS:
                on = 1.0 if r["s"] == s else 0.0
                x += [on * r["m"], on * r["m"] ** 2]
        X.append(x)
    return np.array(X)


def fit(X, y, l2=1e-3):
    w = np.zeros(X.shape[1]); w[4] = 1.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (y - p) - l2 * w
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w += step
        if np.abs(step).max() < 1e-9:
            break
    return w


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def preds(train, test, form):
    w = fit(design(train, form), np.array([r["y"] for r in train], float))
    return 1 / (1 + np.exp(-design(test, form) @ w)), w


def boot(days, diff):
    """diff: per-row array; days: per-row day labels. Day-clustered bootstrap of the mean."""
    rng = random.Random(SEED)
    ud = sorted(set(days))
    by = {d: diff[np.array(days) == d] for d in ud}
    ms = []
    for _ in range(DRAWS):
        pick = [rng.choice(ud) for _ in ud]
        v = np.concatenate([by[d] for d in pick]); ms.append(v.mean())
    ms.sort()
    return diff.mean(), ms[int(0.025 * DRAWS)], ms[int(0.975 * DRAWS) - 1]


def main():
    rows = load(sys.argv[1]); mode = sys.argv[2]
    dev = [r for r in rows if DEV[0] <= r["d"] <= DEV[1]]
    hold = [r for r in rows if HOLD[0] <= r["d"] <= HOLD[1]]
    print(f"dev {len(dev)} legs / {len(set(r['d'] for r in dev))} days; holdout {len(hold)} / {len(set(r['d'] for r in hold))} days")
    if mode == "dev":
        days = sorted(set(r["d"] for r in dev))
        res = {f: [] for f in ("R1", "R2", "R3")}
        base = []
        for d in days:
            tr = [r for r in dev if r["d"] != d]; te = [r for r in dev if r["d"] == d]
            y = np.array([r["y"] for r in te], float)
            base.append(ll(np.array([r["pf"] for r in te]), y))
            for f in res:
                res[f].append(ll(preds(tr, te, f)[0], y))
        b = np.concatenate(base); dl = [d for d, rr in zip(days, base) for _ in range(len(rr))]
        print(f"p_final LODO log-loss {b.mean():.4f}")
        for f, v in res.items():
            v = np.concatenate(v)
            m, lo, hi = boot(dl, v - b)
            print(f"{f}: {v.mean():.4f}  Δ vs p_final {m:+.4f} [{lo:+.4f}, {hi:+.4f}]")
        return
    form = sys.argv[3]
    y = np.array([r["y"] for r in hold], float)
    b = ll(np.array([r["pf"] for r in hold]), y)
    pc, w = preds(dev, hold, form); p1, w1 = preds(dev, hold, "R1")
    dl = [r["d"] for r in hold]
    print(f"{form} coefficients {np.round(w, 4).tolist()}")
    print(f"R1 coefficients {np.round(w1, 4).tolist()}")
    print(f"holdout log-loss p_final {b.mean():.4f}  R1 {ll(p1, y).mean():.4f}  {form} {ll(pc, y).mean():.4f}")
    for name, v in (("cand - p_final", ll(pc, y) - b), ("cand - R1", ll(pc, y) - ll(p1, y)), ("R1 - p_final", ll(p1, y) - b)):
        m, lo, hi = boot(dl, v)
        print(f"  {name}: {m:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    print("per stat (cand - p_final):")
    for s in STATS:
        idx = np.array([r["s"] == s for r in hold])
        m, lo, hi = boot([d for d, k in zip(dl, idx) if k], (ll(pc, y) - b)[idx])
        print(f"  {s}: n={idx.sum()} {m:+.4f} [{lo:+.4f}, {hi:+.4f}]  mean y {y[idx].mean():.3f} p_final {np.array([r['pf'] for r in hold])[idx].mean():.3f} cand {pc[idx].mean():.3f}")
    idx = np.array([r["pf"] >= 0.7 for r in hold])
    m, lo, hi = boot([d for d, k in zip(dl, idx) if k], (ll(pc, y) - b)[idx])
    print(f"banker-zone p_final>=0.7: n={idx.sum()} {m:+.4f} [{lo:+.4f}, {hi:+.4f}]  y {y[idx].mean():.3f} p_final {np.array([r['pf'] for r in hold])[idx].mean():.3f} cand {pc[idx].mean():.3f}")
    print("calibration by p_final bucket (holdout): bucket n y p_final cand")
    pf = np.array([r["pf"] for r in hold])
    for lo_, hi_ in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .9), (.9, 1.01)):
        k = (pf >= lo_) & (pf < hi_)
        if k.sum():
            print(f"  [{lo_:.1f},{hi_:.1f}) {k.sum():5d} {y[k].mean():.3f} {pf[k].mean():.3f} {pc[k].mean():.3f}")
    ou = [i for i, r in enumerate(hold) if r["ou"] and r["line"] == math.ceil(float(r["ou"]))]
    if ou:
        k = np.array(ou)
        print(f"O/U main-line legs n={len(k)}: actual over {y[k].mean():.3f} p_final {pf[k].mean():.3f} cand {pc[k].mean():.3f} de-vig {np.mean([float(hold[i]['ouf']) for i in k]):.3f}")


if __name__ == "__main__":
    main()
