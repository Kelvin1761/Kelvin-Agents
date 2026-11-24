"""Locked F4 confirmation. Usage: python3 study.py <data dir>."""
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def fair(w, l):
    try:
        w, l = float(w), float(l)
    except (TypeError, ValueError):
        return None
    if not (w > 1 and l > 1 and np.isfinite(w) and np.isfinite(l)):
        return None
    return (1 / w) / (1 / w + 1 / l)


def fit(X, y):
    def nll(w):
        z = X @ w
        return np.sum(np.logaddexp(0, z) - y * z)
    w0 = np.zeros(X.shape[1])
    w0[1] = 1
    result = minimize(nll, w0, method="BFGS")
    # BFGS may report precision loss despite a usable solution; show status.
    return result.x, result.message


def ll(X, y, w):
    z = X @ w
    return np.logaddexp(0, z) - y * z


def boot(v, n=4000, seed=20260826):
    v = np.asarray(v, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.array([v[rng.integers(0, len(v), len(v))].mean() for _ in range(n)])
    return v.mean(), *np.quantile(means, [0.025, 0.975])


def main(path):
    rows = []
    history = defaultdict(list)
    # Protocol specifies 2024–2025 history; 2026 cannot precede evaluation dates.
    for year in (2024, 2025):
        for tour in ("ATP", "WTA"):
            data = pd.read_excel(path / f"{tour.lower()}{year}.xlsx")
            for _, r in data.iterrows():
                d = pd.Timestamp(r.Date).date()
                w, l = str(r.Winner).strip(), str(r.Loser).strip()
                history[tour, w].append(d)
                history[tour, l].append(d)
                rows.append((tour, d, w, l, r))
    for dates in history.values():
        dates.sort()

    def count(tour, player, d):
        dates = history[tour, player]
        return bisect_left(dates, d) - bisect_left(dates, d - timedelta(days=7))

    records = []
    for tour, d, w, l, r in rows:
        fw = fair(r.get("AvgW"), r.get("AvgL"))
        if r.Comment != "Completed" or fw is None or d < date(2024, 1, 8):
            continue
        a_won = w < l
        a, b = (w, l) if a_won else (l, w)
        bf = fair(r.get("BFEW"), r.get("BFEL"))
        records.append(dict(year=d.year, tour=tour, round=r["Round"], y=int(a_won),
                            F4=count(tour, a, d)-count(tour, b, d),
                            avg=fw if a_won else 1-fw,
                            bf=None if bf is None else (bf if a_won else 1-bf),
                            avg_a=r.AvgW if a_won else r.AvgL,
                            avg_b=r.AvgL if a_won else r.AvgW,
                            bf_a=r.get("BFEW") if a_won else r.get("BFEL"),
                            bf_b=r.get("BFEL") if a_won else r.get("BFEW")))
    df = pd.DataFrame(records)
    print(f"Evaluation rows: FIT 2024 {sum(df.year == 2024)}; CONFIRM 2025 {sum(df.year == 2025)}")
    print("Bootstrap: 4000 match resamples; seed 20260826; percentile 95% CI")

    def run(col, label):
        data = df[df[col].notna()].copy()
        p = np.clip(data[col].astype(float), 1e-6, 1-1e-6)
        data["lf"] = np.log(p / (1-p))
        train, test = data[data.year == 2024], data[data.year == 2025]
        print(f"\n{label}: FIT n={len(train)}, CONFIRM n={len(test)}")
        if len(train) == 0 or len(test) == 0:
            print("  unavailable: market prices missing in FIT or CONFIRM")
            return None
        xb = lambda t: np.c_[np.ones(len(t)), t.lf]
        xf = lambda t: np.c_[np.ones(len(t)), t.lf, t.F4]
        wb, sb = fit(xb(train), train.y.to_numpy())
        wf, sf = fit(xf(train), train.y.to_numpy())
        print(f"  fit baseline={wb} feature={wf}; optimizer: {sb}; {sf}")
        test = test.copy()
        test["delta"] = ll(xb(test), test.y.to_numpy(), wb) - ll(xf(test), test.y.to_numpy(), wf)
        def report(name, sub):
            if len(sub) == 0:
                print(f"  {name}: n=0")
                return
            m, lo, hi = boot(sub.delta.to_numpy())
            print(f"  {name}: n={len(sub)} ΔLL={m:+.8f} CI [{lo:+.8f}, {hi:+.8f}]")
        report("all", test)
        if col == "avg":
            report('excluding 1st Round', test[test['round'] != '1st Round'])
            for tour in ('ATP', 'WTA'):
                report(tour, test[test.tour == tour])
        return wf[2], boot(test.delta.to_numpy())

    primary = run('avg', 'Avg close primary and secondary subsets')
    run('bf', 'Betfair close sensitivity')
    print('\nSecondary ROI: |F4| >= 2; 1u per match')
    picks = df[(df.year == 2025) & (df.F4.abs() >= 2)]
    for market in ('avg', 'bf'):
        subset = picks if market == 'avg' else picks[picks.bf.notna()]
        busy_a = subset.F4 > 0
        odds = np.where(busy_a, subset[f'{market}_a'], subset[f'{market}_b']).astype(float)
        won = np.where(busy_a, subset.y == 1, subset.y == 0)
        profit = np.where(won, (odds - 1) * (0.95 if market == 'bf' else 1), -1)
        if len(profit):
            m, lo, hi = boot(profit)
            print(f'  {market}: n={len(profit)} ROI={m:+.4%} CI [{lo:+.4%}, {hi:+.4%}]')
        else:
            print(f'  {market}: n=0')
    print('\nSecondary calibration (actual - Avg fair); outer buckets include any values beyond ±9')
    for year in (2024, 2025):
        t = df[df.year == year]
        for name, mask in [('−9..−3', t.F4 <= -3), ('−2..−1', t.F4.between(-2, -1)),
                           ('0', t.F4 == 0), ('+1..+2', t.F4.between(1, 2)), ('+3..+9', t.F4 >= 3)]:
            s = t[mask]
            print(f'  {year} {name}: n={len(s)} actual={s.y.mean():.4f} fair={s.avg.mean():.4f} gap={s.y.mean()-s.avg.mean():+.4f}')
    print(f"Observed F4 range: {df.F4.min()}..{df.F4.max()}")
    g, (_, lo, hi) = primary
    verdict = 'CONFIRMED' if g > 0 and lo > 0 else ('REJECT' if g <= 0 or hi < 0 else 'NO EVIDENCE')
    print(f'PRIMARY VERDICT: {verdict}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: python3 study.py <data dir>')
    main(Path(sys.argv[1]))
