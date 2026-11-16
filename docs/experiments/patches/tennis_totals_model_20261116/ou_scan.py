"""Blind over/under scan of Sportsbet two-way totals markets we never priced. Read-only, exploratory."""
import sqlite3, json, re
from collections import defaultdict
import numpy as np
import sys
DB = sys.argv[1] if len(sys.argv) > 1 else "tennis-wong-choi/tennis_wc.db"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
# results: completed, consistent across sources
res = defaultdict(list)
for mid, sj in c.execute("SELECT match_id, score_json FROM match_results WHERE score_json IS NOT NULL"):
    try: s = json.loads(sj)
    except Exception: continue
    sets = s.get("sets") or []
    if not sets: continue
    a, b = s.get("player_a_sets"), s.get("player_b_sets")
    if max(a or 0, b or 0) < 2: continue  # retirement / incomplete
    res[mid].append(tuple((x["player_a_games"], x["player_b_games"]) for x in sets))
result = {m: v[0] for m, v in res.items() if len(set(v)) == 1}
start = dict(c.execute("SELECT id, start_time_utc FROM matches WHERE COALESCE(fixture_status,'')!='DISPUTED'"))
def outcome(mname, line, sets):
    n = mname.lower()
    if n in ("total sets 2.5", "total sets"): v = len(sets)
    elif n == "match total games": v = sum(a + b for a, b in sets)
    else:
        m = re.match(r"set (\d) total games(?: over/under [\d.]+)?$", n)
        if not m: return None
        k = int(m.group(1)) - 1
        if k >= len(sets): return None
        v = sum(sets[k])
    return v
MARKETS = ("Total Sets 2.5", "Total Sets", "Match Total Games")
rows = c.execute(f"""SELECT match_id, market_name, selection_name, line, odds, fetched_at, id FROM market_odds_snapshots
  WHERE bookmaker='Sportsbet' AND (market_name IN {MARKETS} OR market_name LIKE 'Set _ Total Games Over/Under %' OR market_name IN ('Set 1 Total Games','Set 2 Total Games'))
  ORDER BY id""").fetchall()
first = {}
for mid, mn, sel, line, odds, f, i in rows:
    if mid not in result or not start.get(mid) or not (f < start[mid].replace("+00:00", "Z")): continue
    side = "over" if sel.lower().startswith("over") else "under" if sel.lower().startswith("under") else None
    if side is None or line is None: continue
    key = (mid, mn, line, side)
    if key not in first: first[key] = (odds, f)
recs = defaultdict(list)
for (mid, mn, line, side), (odds, f) in first.items():
    if side != "over": continue
    u = first.get((mid, mn, line, "under"))
    if not u or odds <= 1 or u[0] <= 1: continue
    v = outcome(mn, line, result[mid])
    if v is None or v == line: continue
    io, iu = 1/odds, 1/u[0]
    fam = "Total Sets 2.5" if mn.startswith("Total Sets") else "Match Total Games" if mn == "Match Total Games" else ("Set 1 games" if mn.startswith("Set 1") else "Set 2 games")
    recs[fam].append(dict(match=mid, date=f[:10], line=line, oo=odds, ou=u[0], po=io/(io+iu), margin=io+iu-1, over=v > line))
rng = np.random.default_rng(20260826)
def roi(xs, side):
    pl = np.array([(x["oo"]-1 if x["over"] else -1.0) if side == "over" else (x["ou"]-1 if not x["over"] else -1.0) for x in xs])
    mids = [x["match"] for x in xs]; by = defaultdict(list)
    for i, m in enumerate(mids): by[m].append(i)
    ks = list(by); num = np.array([pl[by[k]].sum() for k in ks]); den = np.array([len(by[k]) for k in ks])
    st = [num[s].sum()/den[s].sum() for s in (rng.integers(0, len(ks), len(ks)) for _ in range(2000))]
    return pl.mean(), *np.percentile(st, [2.5, 97.5])
for fam, xs in recs.items():
    y = np.array([x["over"] for x in xs]); p = np.array([x["po"] for x in xs])
    print(f"\n{fam}: {len(xs)} lines / {len(set(x['match'] for x in xs))} matches, {min(x['date'] for x in xs)}..{max(x['date'] for x in xs)}, margin median {np.median([x['margin'] for x in xs])*100:.1f}%")
    print(f"  over hit {y.mean():.3f} vs fair {p.mean():.3f}")
    for side in ("over", "under"):
        m, lo, hi = roi(xs, side); print(f"  blind {side:5s} ROI {m*100:+.1f}% [{lo*100:+.1f}, {hi*100:+.1f}]")
    # by price of over side
    for lab, cond in (("over fav (po>=.5)", p >= 0.5), ("over dog (po<.5)", p < 0.5)):
        sub = [x for x, k in zip(xs, cond) if k]
        if len(sub) > 30:
            mo = roi(sub, "over"); mu = roi(sub, "under")
            print(f"  {lab:18s} n={len(sub):4d} over {mo[0]*100:+.1f}% [{mo[1]*100:+.1f},{mo[2]*100:+.1f}]  under {mu[0]*100:+.1f}% [{mu[1]*100:+.1f},{mu[2]*100:+.1f}]")
