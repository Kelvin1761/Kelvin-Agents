"""Phase 1 baseline over corpus.csv. Descriptive only: no parameter is tuned here.
Population: every quoted Sportsbet milestone with an outcome (DNP voided). Playoff-heavy
(Apr-Jun 2026), so it is NOT the early-season regime; treat as a first read."""
import sys
import numpy as np, pandas as pd

c = pd.read_csv(sys.argv[1]).dropna(subset=["y"])
c["ext"] = pd.to_datetime(c["extraction_time"])
# Drop quotes taken after 19:00 ET on game day (could be in-play): the 2026-04-10 folder, 91 rows.
_late = (pd.to_datetime(c["date"]) + pd.Timedelta(hours=19) - (c["ext"] - pd.Timedelta(hours=14))).dt.total_seconds() < 0
print("dropped late quotes:", int(_late.sum()))
c = c[~_late].copy()
rng = np.random.default_rng(7)


def boot_ci(df, fn, n=2000):
    days = df["date"].unique()
    g = {d: df[df["date"] == d] for d in days}
    out = []
    for _ in range(n):
        s = pd.concat([g[d] for d in rng.choice(days, len(days))])
        out.append(fn(s))
    return np.percentile(out, [2.5, 97.5])


def brier(p, y): return float(np.mean((p - y) ** 2))


def line(label, d):
    if len(d) == 0: return
    roi = float((d["y"] * d["price"] - 1).mean())
    lo, hi = boot_ci(d, lambda s: float((s["y"] * s["price"] - 1).mean()), 600)
    print(f"{label:34s} n={len(d):5d} L10={d['hit_l10'].mean():.3f} implied={d['implied'].mean():.3f} "
          f"actual={d['y'].mean():.3f}  flatROI={roi:+.3f} [{lo:+.3f},{hi:+.3f}]")


print("rows", len(c), "days", c["date"].nunique())
print("\n== leakage checks")
et = c["ext"] - pd.Timedelta(hours=14)  # Sydney (AEST) -> US Eastern
gd = pd.to_datetime(c["date"])
hrs = (gd + pd.Timedelta(hours=19) - et).dt.total_seconds() / 3600  # hours before a 7pm-ET tip
print("quote taken after game day 19:00 ET (suspect in-play/late):", int((hrs < 0).sum()), "of", len(c))
print("hours before a 19:00-ET tip, quantiles 5/50/95:", np.percentile(hrs, [5, 50, 95]).round(1).tolist())
print("L10 uses only prior games: by construction (GAME_DATE < game date)")

print("\n== Brier on all rows: L10 hit-rate vs market-implied")
for s in ["PTS", "REB", "AST", "FG3M", "points", "rebounds", "assists", "threes_made"]:
    d = c[c["stat"] == s]
    if len(d): print(f"{s:12s} n={len(d):5d} L10={brier(d['hit_l10'], d['y']):.4f}  implied={brier(d['implied'], d['y']):.4f}  base_rate={d['y'].mean():.3f}")
print(f"{'ALL':12s} n={len(c):5d} L10={brier(c['hit_l10'], c['y']):.4f}  implied={brier(c['implied'], c['y']):.4f}")

print("\n== banker-style legs: L10>=0.8 & L5>=0.8, price 1.20-1.80 (single-leg flat stake, by stat)")
b = c[(c["hit_l10"] >= .8) & (c["hit_l5"] >= .8) & c["price"].between(1.2, 1.8)]
line("ALL stats", b)
for s in b["stat"].unique(): line(f"  {s}", b[b["stat"] == s])

print("\n== banker-style legs by price band")
for lo, hi in [(1.2, 1.3), (1.3, 1.45), (1.45, 1.6), (1.6, 1.8)]:
    line(f"  price {lo}-{hi}", b[b["price"].between(lo, hi, inclusive="left")])

print("\n== banker-style legs by L10 hit rate")
for h in [.8, .9, 1.0]:
    line(f"  L10={h}", b[np.isclose(b["hit_l10"], h)])

# NOTE: a team-change split is empty here (transfers happen in the off-season; Apr-Jun has none).
# It needs the 2025-10/11 window with 2024-25 history (Phase 3).

print("\n== playoff share of L10 (po_in_l10)")
for k, d in b.groupby(b["po_in_l10"].clip(upper=5)): line(f"  playoff games in L10 = {k}", d)
