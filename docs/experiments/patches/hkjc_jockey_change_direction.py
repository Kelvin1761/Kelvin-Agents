"""換騎 direction: kept / upgrade / similar / downgrade, actual vs market-implied (normalised 1/odds), PIT ratings."""
import sys, random
from collections import defaultdict
sys.path[:0] = [".agents/skills/hkjc_racing/hkjc_reflector/scripts", ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts", ".", ".agents/skills/shared_racing"]
import pandas as pd
import pit_backtest as p

rows = p.load_all_rows().copy()
rows = rows[rows["Rank"].notna() & rows["Odds"].notna() & (rows["Odds"] > 0)]
rows["Date"] = rows["Date"].astype(str)
rows = rows.sort_values(["Date", "RaceNo"])
rows["Prev"] = rows.groupby("Horse")["Jockey"].shift(1)
rows["Race"] = rows["Date"] + "_" + rows["RaceNo"].astype(str)
inv = 1.0 / rows["Odds"]
rows["implied"] = inv / inv.groupby(rows["Race"]).transform("sum")

ratings = {}
for d in sorted(rows["Date"].unique()):
    sub = rows[rows["Date"] < d]
    if len(sub) < 2000:
        continue
    ratings[d] = p.build_ratings(sub, "jockey", p._season_tag(d))

out = []
for r in rows.itertuples():
    tab = ratings.get(r.Date)
    if tab is None or not isinstance(r.Prev, str):
        continue
    if r.Prev == r.Jockey:
        g = "kept"; delta = 0.0
    else:
        cur = tab.get(str(r.Jockey).strip()); prv = tab.get(str(r.Prev).strip())
        if not cur or not prv:
            g = "changed_unrated"; delta = None
        else:
            delta = cur["score"] - prv["score"]
            g = "up" if delta >= 3 else ("down" if delta <= -3 else "similar")
    out.append((r.Date, g, delta, r.Win, r.implied, r.Place))
df = pd.DataFrame(out, columns=["Date", "g", "delta", "Win", "implied", "Place"])
print(f"runs {len(df)}  dates {df['Date'].nunique()}  span {df['Date'].min()}→{df['Date'].max()}")


def ci(sub, B=1000):
    dates = sub["Date"].unique(); by = {d: s for d, s in sub.groupby("Date")}; rng = random.Random(5); xs = []
    for _ in range(B):
        samp = pd.concat([by[rng.choice(dates)] for _ in dates])
        xs.append(samp["Win"].sum() / samp["implied"].sum())
    xs.sort(); return xs[int(B * .025)], xs[int(B * .975)]


print(f"{'group':16s} {'n':>6s} {'win%':>6s} {'implied%':>9s} {'actual/implied':>15s}  95% CI (meeting bootstrap)")
for g in ("kept", "up", "similar", "down", "changed_unrated"):
    s = df[df["g"] == g]
    if len(s) < 50:
        continue
    lo, hi = ci(s)
    print(f"{g:16s} {len(s):6d} {s['Win'].mean()*100:6.2f} {s['implied'].mean()*100:9.2f} {s['Win'].sum()/s['implied'].sum():15.3f}  [{lo:.3f}, {hi:.3f}]")
