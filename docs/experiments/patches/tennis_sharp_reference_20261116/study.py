"""EXP-20261116-15: Sportsbet match-winner vs sharp close (see PROTOCOL.md)."""
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

DB = sys.argv[1]
DL = sys.argv[2]
SPLIT = date(2026, 9, 1)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s.replace("-", " ")).split()


def td_key(name):  # "Auger-Aliassime F." -> (["auger","aliassime"], "f")
    parts = str(name).strip().split(" ")
    initials = [p for p in parts if p.endswith(".")]
    sur = " ".join(p for p in parts if not p.endswith("."))
    return norm(sur), (norm(initials[0])[0][0] if initials and norm(initials[0]) else "")


def matches_name(full, key):
    toks = norm(full)
    sur, ini = key
    if not sur or len(toks) < len(sur) + 1:
        return False
    for i in range(1, len(toks) - len(sur) + 1):
        if toks[i:i + len(sur)] == sur:
            return (not ini) or toks[0][0] == ini
    return False


rows = []
for f, tour in (("atp2026.xlsx", "ATP"), ("wta2026.xlsx", "WTA")):
    d = pd.read_excel(f"{DL}/{f}")
    d = d[(d["Comment"] == "Completed") & d["BFEW"].notna() & d["BFEL"].notna()]
    for _, r in d.iterrows():
        if r.BFEW <= 1 or r.BFEL <= 1:
            continue
        rows.append(dict(tour=tour, date=r.Date.date(), w=td_key(r.Winner), l=td_key(r.Loser),
                         bw=float(r.BFEW), bl=float(r.BFEL), surface=r.Surface, rnd=r.Round))
by_date = defaultdict(list)
for i, r in enumerate(rows):
    by_date[(r["tour"], r["date"])].append(i)

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
ms = conn.execute("""
  SELECT m.id, m.match_date, m.start_time_utc, m.tour, pa.name an, pb.name bn
  FROM matches m JOIN players pa ON pa.id=m.player_a_id JOIN players pb ON pb.id=m.player_b_id
  WHERE COALESCE(m.fixture_status,'') != 'DISPUTED'
    AND EXISTS (SELECT 1 FROM odds_snapshots o WHERE o.match_id=m.id AND o.bookmaker='Sportsbet')""").fetchall()
pair = {}
used = defaultdict(list)
for m in ms:
    md = date.fromisoformat(m["match_date"])
    tours = [m["tour"]] if m["tour"] in ("ATP", "WTA") else ["ATP", "WTA"]
    hits = []
    for t in tours:
        for dd in (-1, 0, 1):
            for i in by_date.get((t, md + timedelta(days=dd)), []):
                r = rows[i]
                if matches_name(m["an"], r["w"]) and matches_name(m["bn"], r["l"]):
                    hits.append((i, "a"))
                elif matches_name(m["bn"], r["w"]) and matches_name(m["an"], r["l"]):
                    hits.append((i, "b"))
    if len(hits) == 1:
        pair[m["id"]] = hits[0]
        used[hits[0][0]].append(m["id"])
pair = {mid: v for mid, v in pair.items() if len(used[v[0]]) == 1}
print(f"tennis-data rows with BFE: {len(rows)}; our matches with Sportsbet odds: {len(ms)}; paired: {len(pair)}")

recs = []
for m in ms:
    if m["id"] not in pair:
        continue
    i, winner_side = pair[m["id"]]
    r = rows[i]
    snaps = conn.execute("""SELECT player_a_odds a, player_b_odds b, fetched_at FROM odds_snapshots
        WHERE match_id=? AND bookmaker='Sportsbet' AND market='match_winner' AND fetched_at < ?
        ORDER BY id""", (m["id"], m["start_time_utc"].replace("+00:00", "Z") if m["start_time_utc"] else "")).fetchall()
    snaps = [s for s in snaps if s["a"] > 1 and s["b"] > 1]
    if not snaps:
        continue
    # reference odds in our a/b orientation
    ra, rb = (r["bw"], r["bl"]) if winner_side == "a" else (r["bl"], r["bw"])
    recs.append(dict(match=m["id"], date=r["date"], tour=r["tour"], a_won=winner_side == "a",
                     ra=ra, rb=rb, first=(snaps[0]["a"], snaps[0]["b"]), last=(snaps[-1]["a"], snaps[-1]["b"])))
print(f"paired with a pre-start Sportsbet snapshot: {len(recs)}")


def fair(oa, ob, method):
    ia, ib = 1 / oa, 1 / ob
    if method == "prop":
        return ia / (ia + ib)
    lo, hi = 0.5, 3.0  # power: find k with ia^k + ib^k = 1
    for _ in range(60):
        k = (lo + hi) / 2
        if ia ** k + ib ** k > 1:
            lo = k
        else:
            hi = k
    return ia ** k / (ia ** k + ib ** k)


def bets(recs, snap, method, thr):
    out = []
    for x in recs:
        pa = fair(x["ra"], x["rb"], method)
        oa, ob = x[snap]
        eva, evb = oa * pa - 1, ob * (1 - pa) - 1
        side, ev, odds = ("a", eva, oa) if eva >= evb else ("b", evb, ob)
        if ev > thr:
            won = x["a_won"] if side == "a" else not x["a_won"]
            out.append(dict(match=x["match"], pl=odds - 1 if won else -1.0, odds=odds, ev=ev))
    return out


def roi_ci(bs, draws=4000, seed=20260826):
    if not bs:
        return None
    pl = np.array([b["pl"] for b in bs])
    rng = np.random.default_rng(seed)
    st = [pl[rng.integers(0, len(pl), len(pl))].mean() for _ in range(draws)]
    return pl.mean(), *np.percentile(st, [2.5, 97.5])


# context: Sportsbet margin and how far its fair sits from the reference
for snap in ("first", "last"):
    mg = [1 / x[snap][0] + 1 / x[snap][1] - 1 for x in recs]
    bfm = [1 / x["ra"] + 1 / x["rb"] - 1 for x in recs]
    gap = [abs(fair(*x[snap], "prop") - fair(x["ra"], x["rb"], "prop")) for x in recs]
    print(f"{snap}: Sportsbet margin median {np.median(mg)*100:.2f}% | BF close overround median {np.median(bfm)*100:.2f}% | "
          f"|fair gap| median {np.median(gap)*100:.2f}pp, p90 {np.percentile(gap,90)*100:.2f}pp")

for label, part in (("dev", [x for x in recs if x["date"] < SPLIT]), ("holdout", [x for x in recs if x["date"] >= SPLIT])):
    print(f"\n== {label}: {len(part)} matches ({min(x['date'] for x in part)}..{max(x['date'] for x in part)})")
    for snap in ("first", "last"):
        for method in ("prop", "power"):
            for thr in (0.0, 0.02, 0.05):
                bs = bets(part, snap, method, thr)
                tag = " <== PRIMARY" if (snap, method, thr) == ("first", "prop", 0.0) else ""
                if not bs:
                    print(f"  {snap:5s} {method:5s} EV>{thr:.2f}: 0 bets{tag}")
                    continue
                m, lo, hi = roi_ci(bs)
                print(f"  {snap:5s} {method:5s} EV>{thr:.2f}: {len(bs):4d} bets ({len(bs)/len(part)*100:4.1f}%) avg odds {np.mean([b['odds'] for b in bs]):.2f} "
                      f"ROI {m*100:+.1f}% [{lo*100:+.1f}, {hi*100:+.1f}] P/L {sum(b['pl'] for b in bs):+.1f}u{tag}")

# descriptive: theoretical EV against the close (not executable: the close is known only afterwards)
for thr in (0.0, 0.02, 0.05):
    bs = bets(recs, "first", "prop", thr)
    ev = np.array([b["ev"] for b in bs])
    print(f"all {len(recs)}, EV>{thr}: {len(bs)} bets, mean EV vs close {ev.mean()*100:+.2f}%, "
          f"realized {np.mean([b['pl'] for b in bs])*100:+.1f}%")
evs, fav, dog = [], [], []
for x in recs:
    pa = fair(x["ra"], x["rb"], "prop")
    oa, ob = x["first"]
    for p, o in ((pa, oa), (1 - pa, ob)):
        evs.append(o * p - 1)
        (fav if p >= 0.5 else dog).append(o * p - 1)
evs = np.array(evs)
print(f"every side EV: median {np.median(evs)*100:+.2f}%, >0 {(evs>0).mean()*100:.1f}%, "
      f">2% {(evs>0.02).mean()*100:.1f}%, >5% {(evs>0.05).mean()*100:.1f}% | "
      f"fav mean {np.mean(fav)*100:+.2f}%, dog mean {np.mean(dog)*100:+.2f}%")
