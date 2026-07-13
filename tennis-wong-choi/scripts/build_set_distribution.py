"""Set-win distribution: empirical table vs iid inversion vs current heuristics.

Dataset: BO3 completed season-file matches (Sackmann cache + TML fresh),
set score parsed from the score string, first-set winner from set 1.
Input bucket: favourite's rank-implied match prob (live uses the model's
match prob, which the external backtest showed is well calibrated).
Outcomes: fav 2-0 / fav 2-1 / dog 2-1 / dog 2-0, and P(fav wins set 1).
Holdout: matches on/after 2025-10-01.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from io import StringIO
from urllib.request import Request, urlopen

sys.path.insert(0, "src")
from tennis_wc.database.db import get_connection

CUTOFF = "2027-01-01"
OUTCOMES = ("F20", "F21", "D21", "D20")


def _rows():
    conn = get_connection()
    out = []
    for r in conn.execute(
        """
        SELECT endpoint, response_json FROM raw_api_responses
        WHERE provider_name='jeff_sackmann' AND endpoint LIKE '%matches_20%'
          AND id IN (SELECT MAX(id) FROM raw_api_responses
                     WHERE provider_name='jeff_sackmann' AND endpoint LIKE '%matches_20%'
                     GROUP BY endpoint)
        """
    ).fetchall():
        out.extend(json.loads(r["response_json"]))
    urls = [f"https://stats.tennismylife.org/data/{y}_challenger.csv" for y in range(2020, 2027)]
    urls += [f"https://stats.tennismylife.org/data/atp_quali/{y}_atp_quali.csv" for y in range(2020, 2027)]
    urls.append("https://stats.tennismylife.org/data/2026.csv")
    seen_2026_main = "20260601"
    for url in urls:
        try:
            req = Request(url, headers={"User-Agent": "TennisWongChoi/0.1"})
            with urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8-sig")
        except Exception:
            continue
        for row in csv.DictReader(StringIO(text)):
            if url.endswith("/2026.csv") and str(row.get("tourney_date") or "") < seen_2026_main:
                continue
            out.append(row)
    return out


_SET_RE = re.compile(r"^(\d+)-(\d+)")


def parse_sets(score: str | None):
    """-> (sets_w, sets_l, first_set_winner_won) or None. Excludes RET/W.O."""
    s = str(score or "")
    if not s or "RET" in s.upper() or "W/O" in s.upper() or "DEF" in s.upper():
        return None
    sw = sl = 0
    first = None
    for token in s.split():
        m = _SET_RE.match(token)
        if not m:
            return None
        a, b = int(m.group(1)), int(m.group(2))
        if a == b:
            return None
        won = a > b
        if first is None:
            first = won
        sw += 1 if won else 0
        sl += 0 if won else 1
    if sw != 2 or sl > 1:
        return None
    return sw, sl, first


def build():
    recs = []
    for r in _rows():
        if int(float(r.get("best_of") or 3)) != 3:
            continue
        parsed = parse_sets(r.get("score"))
        if parsed is None:
            continue
        _sw, sl, first_won_by_winner = parsed
        try:
            wr, lr = float(r.get("winner_rank") or 0), float(r.get("loser_rank") or 0)
        except (TypeError, ValueError):
            continue
        if not wr or not lr:
            continue
        d = str(r.get("tourney_date") or "")
        date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else None
        if not date:
            continue
        p_winner = lr / (wr + lr)  # rank-implied win prob of the actual winner
        fav_won = p_winner >= 0.5
        fav_prob = p_winner if fav_won else 1 - p_winner
        if fav_won:
            outcome = "F20" if sl == 0 else "F21"
            fav_took_set1 = first_won_by_winner
        else:
            outcome = "D20" if sl == 0 else "D21"
            fav_took_set1 = not first_won_by_winner
        recs.append({"date": date, "fav_prob": fav_prob, "outcome": outcome, "fav_set1": fav_took_set1})
    return recs


def bucket(p):
    return min(0.95, max(0.50, round(p * 20) / 20))


def fit(train):
    dist = defaultdict(lambda: defaultdict(int))
    s1 = defaultdict(lambda: [0, 0])
    for r in train:
        b = bucket(r["fav_prob"])
        dist[b][r["outcome"]] += 1
        s1[b][0] += 1 if r["fav_set1"] else 0
        s1[b][1] += 1
    table = {}
    for b in sorted(dist):
        n = sum(dist[b].values())
        if n < 300:
            continue
        table[b] = {
            **{o: dist[b][o] / n for o in OUTCOMES},
            "set1": s1[b][0] / s1[b][1],
            "n": n,
        }
    return table


def iid_dist(match_prob):
    """Invert M = p^2(3-2p) for the per-set prob, derive the 4-outcome dist."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if mid * mid * (3 - 2 * mid) < match_prob:
            lo = mid
        else:
            hi = mid
    p = (lo + hi) / 2
    return {"F20": p * p, "F21": 2 * p * p * (1 - p), "D21": 2 * p * (1 - p) * (1 - p),
            "D20": (1 - p) * (1 - p), "set1": p}


def heuristic_dist(match_prob):
    """Current report heuristics, mapped onto the same quantities."""
    comp = 1 - abs(2 * match_prob - 1)
    p3 = min(0.72, max(0.12, 0.20 + comp * 0.42))       # P(3 sets) from total_sets heuristic
    set1 = min(0.92, max(0.55, 0.5 + (match_prob - 0.5) * 0.78))
    # split 3-set prob between F21/D21 proportionally to match prob
    return {"F20": (1 - p3) * match_prob / (match_prob + (1 - match_prob)) if False else max(0.0, match_prob - p3 * match_prob),
            "F21": p3 * match_prob, "D21": p3 * (1 - match_prob),
            "D20": max(0.0, (1 - match_prob) - p3 * (1 - match_prob)), "set1": set1}


def brier(hold, predict):
    tot4 = n4 = tot1 = n1 = tot3 = 0.0
    for r in hold:
        d = predict(r["fav_prob"])
        if d is None:
            continue
        for o in OUTCOMES:
            y = 1.0 if r["outcome"] == o else 0.0
            tot4 += (d[o] - y) ** 2
        n4 += 1
        y1 = 1.0 if r["fav_set1"] else 0.0
        tot1 += (d["set1"] - y1) ** 2
        n1 += 1
        p3 = d["F21"] + d["D21"]
        y3 = 1.0 if r["outcome"] in ("F21", "D21") else 0.0
        tot3 += (p3 - y3) ** 2
    return tot4 / (4 * n4), tot1 / n1, tot3 / n4


if __name__ == "__main__":
    recs = build()
    train = [r for r in recs if r["date"] < CUTOFF]
    hold = [r for r in recs if r["date"] >= CUTOFF]
    print(f"records={len(recs)} train={len(train)} holdout={len(hold)}")
    table = fit(train)
    print("EMPIRICAL TABLE (bucket -> F20/F21/D21/D20, set1, n):")
    for b, d in sorted(table.items()):
        print(f"  {b:.2f}: F20 {d['F20']:.3f} F21 {d['F21']:.3f} D21 {d['D21']:.3f} D20 {d['D20']:.3f} | set1 {d['set1']:.3f} | n={d['n']}")

    def emp(p):
        b = bucket(p)
        if b in table:
            return table[b]
        keys = sorted(table)
        if not keys:
            return None
        nearest = min(keys, key=lambda k: abs(k - b))
        return table[nearest]

    for name, fn in (("heuristic(current)", heuristic_dist), ("iid-inversion", iid_dist), ("empirical", emp)):
        b4, b1, b3 = brier(hold, fn)
        print(f"{name:20s} Brier: 4-outcome {b4:.5f} | set1 {b1:.5f} | goes-3-sets {b3:.5f}")
