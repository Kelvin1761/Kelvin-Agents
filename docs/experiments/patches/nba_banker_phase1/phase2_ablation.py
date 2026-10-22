"""EXP-20261022-02 harness. Protocol frozen in the EXP doc (commit 3de4335e) before this ran."""
import sys, itertools
import numpy as np, pandas as pd

c = pd.read_csv(sys.argv[1]).dropna(subset=["y"])
c["ext"] = pd.to_datetime(c["extraction_time"])
late = (pd.to_datetime(c["date"]) + pd.Timedelta(hours=19) - (c["ext"] - pd.Timedelta(hours=14))).dt.total_seconds() < 0
c = c[~late].copy()
c["ret"] = c["y"] * c["price"] - 1
days = sorted(c["date"].unique())
assert len(days) == 31, len(days)
DEV, GAP, HOLD = days[:19], days[19:20], days[20:]
assert len(HOLD) == 11
print("dev", DEV[0], DEV[-1], "gap", GAP, "holdout", HOLD[0], HOLD[-1])

A0 = (c.hit_l10 >= .8) & (c.hit_l5 >= .8) & (c.price >= 1.2) & (c["cov"] <= .65) & \
     ((c.avg_l10 - c.line) / c.line >= .15) & (c.l3_avg >= c.line)
BANDS = [(1.2, 1.3), (1.3, 1.45), (1.2, 1.45), (1.3, 1.6), (1.45, 1.8)]
dev_c = c[c.date.isin(DEV)]
best = None
for lo, hi in BANDS:
    m = A0[dev_c.index] & dev_c.price.between(lo, hi, inclusive="left")
    n = int(m.sum()); roi = dev_c.loc[m, "ret"].mean() if n else float("nan")
    print(f"  dev band [{lo},{hi}) n={n} ROI={roi:+.3f}")
    if n >= 100 and (best is None or roi > best[0]): best = (roi, lo, hi)
PLO, PHI = best[1], best[2]
print("P band frozen from dev:", (PLO, PHI))

def band(lo, hi): return c.price.between(lo, hi, inclusive="left")
ARMS = {
    "A0": (A0, True),
    "S": (A0 & c.stat.isin(["PTS", "REB"]), True),
    "C": (A0 & (c["cov"] <= .35), True),
    "P": (A0 & band(PLO, PHI), True),
    "N": (A0, False),
    "ALL": (A0 & c.stat.isin(["PTS", "REB"]) & (c["cov"] <= .35) & band(PLO, PHI), False),
}

def build_combos(pool, target):
    out = []
    for (date, game), g in pool.groupby(["date", "game"]):
        g = g.sort_values(["hit_l10", "hit_l5", "price"], ascending=[False, False, True])
        combo, players = [], set()
        for _, r in g.iterrows():
            if r.player in players: continue
            team_n = sum(1 for x in combo if x.team == r.team)
            pts_n = sum(1 for x in combo if x.team == r.team and x.stat == "PTS")
            if team_n >= 3 or (r.stat == "PTS" and pts_n >= 2): continue
            combo.append(r); players.add(r.player)
            odds = np.prod([x.price for x in combo])
            if target:
                if len(combo) >= 2 and 2.0 <= odds <= 3.5: break
                if odds > 3.5: combo.pop(); players.discard(r.player)
            elif len(combo) == 2: break
            if len(combo) >= 3: break
        odds = float(np.prod([x.price for x in combo])) if combo else 0
        if len(combo) >= 2 and (not target or 2.0 <= odds <= 3.5):
            out.append(dict(date=date, game=game, legs=len(combo), odds=odds, hit=int(all(x.y == 1 for x in combo))))
    return pd.DataFrame(out)

def roi_by_days(m, ds):
    d = c[m & c.date.isin(ds)]
    return d.ret.sum(), len(d)

def boot_diff(m_arm, m_a0, ds, n=2000, seed=11):
    rng = np.random.default_rng(seed)
    per = {d: (c[m_arm & (c.date == d)].ret.agg(["sum", "count"]).values, c[m_a0 & (c.date == d)].ret.agg(["sum", "count"]).values) for d in ds}
    out = []
    for _ in range(n):
        pick = rng.choice(ds, len(ds))
        a = sum(per[d][0][0] for d in pick); an = sum(per[d][0][1] for d in pick)
        b = sum(per[d][1][0] for d in pick); bn = sum(per[d][1][1] for d in pick)
        if an and bn: out.append(a / an - b / bn)
    return np.percentile(out, [2.5, 97.5])

res = {}
print("\n== per-arm legs (flat ROI) and combos")
for name, (m, target) in ARMS.items():
    row = {}
    for lab, ds in [("dev", DEV), ("hold", HOLD)]:
        s, n = roi_by_days(m, ds)
        row[lab] = (s / n if n else float("nan"), n)
    pool = c[m]
    cb = build_combos(pool[pool.date.isin(HOLD)], target)
    comb = (f"combos={len(cb)} hit={cb.hit.mean():.3f} avg_odds={cb.odds.mean():.2f} "
            f"ROI_upper={((cb.hit * cb.odds) - 1).mean():+.3f}") if len(cb) else "combos=0"
    res[name] = row
    print(f"{name:4s} dev legs ROI={row['dev'][0]:+.3f} (n={row['dev'][1]})  hold legs ROI={row['hold'][0]:+.3f} (n={row['hold'][1]})  | hold {comb}")

print("\n== verdicts vs A0 (primary: holdout leg ROI diff, day-cluster bootstrap)")
for name in ["S", "C", "P", "N", "ALL"]:
    lo, hi = boot_diff(ARMS[name][0], ARMS["A0"][0], HOLD)
    d_hold = res[name]["hold"][0] - res["A0"]["hold"][0]
    d_dev = res[name]["dev"][0] - res["A0"]["dev"][0]
    if name == "N":
        verdict = "n/a for legs (N only changes combo build; legs identical to A0)"
    elif lo > 0 and d_dev > 0: verdict = "improves"
    elif hi < 0: verdict = "regresses"
    else: verdict = "not shown"
    print(f"{name:4s} hold dROI={d_hold:+.3f} CI[{lo:+.3f},{hi:+.3f}]  dev dROI={d_dev:+.3f}  -> {verdict}")
