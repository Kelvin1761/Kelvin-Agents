#!/usr/bin/env python3
"""Standing guard: the bookmaker's shorter price must win more often than not.

This is the check that caught two independent orientation defects on 2026-08-11,
and it caught them by accident -- nothing ran it. A misoriented price is
invisible to every other test: the odds are real, the match is real, the
selection name is real, and only the pairing is wrong. No unit test on a
hand-built row can see it, and no ROI number distinguishes it from a bad model.

A tier below 55% is an orientation defect, not a tennis result. Both tables are
checked separately because they were wrong independently and by different
mechanisms.

Exit 1 if any tier with enough settled matches fails.

  PYTHONPATH=src .venv/bin/python scripts/check_odds_orientation.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

MIN_GRADED = 30
FLOOR = 0.55
CEILING = 0.85


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import os

    os.environ.setdefault("DATABASE_URL", f"sqlite:///{args.db}")
    from tennis_wc.props.daily import _tier_of

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT m.player_a_id, m.player_b_id, t.name AS tname,
               (SELECT tl.level FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id
                 ORDER BY tl.id DESC LIMIT 1) AS lvl,
               (SELECT mo.odds FROM market_odds_snapshots mo
                 WHERE mo.match_id = m.id AND mo.market_key = 'match_winner'
                   AND mo.selection_side = 'player_a'
                 ORDER BY mo.id ASC LIMIT 1) AS market_a,
               (SELECT mo.odds FROM market_odds_snapshots mo
                 WHERE mo.match_id = m.id AND mo.market_key = 'match_winner'
                   AND mo.selection_side = 'player_b'
                 ORDER BY mo.id ASC LIMIT 1) AS market_b,
               (SELECT o.player_a_odds FROM odds_snapshots o
                 WHERE o.match_id = m.id ORDER BY o.id ASC LIMIT 1) AS positional_a,
               (SELECT o.player_b_odds FROM odds_snapshots o
                 WHERE o.match_id = m.id ORDER BY o.id ASC LIMIT 1) AS positional_b,
               (SELECT r.winner_player_id FROM match_results r
                 WHERE r.match_id = m.id ORDER BY r.id DESC LIMIT 1) AS winner
        FROM matches m LEFT JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.player_a_id <> m.player_b_id
        """
    ).fetchall()

    tables = ("market_odds_snapshots", "odds_snapshots")
    counts: dict = {}
    for row in rows:
        if row["winner"] is None:
            continue
        if row["winner"] not in (row["player_a_id"], row["player_b_id"]):
            continue
        a_won = row["winner"] == row["player_a_id"]
        tier = _tier_of(row["tname"], row["lvl"])
        for table, a_key, b_key in (
            (tables[0], "market_a", "market_b"),
            (tables[1], "positional_a", "positional_b"),
        ):
            a, b = row[a_key], row[b_key]
            if not a or not b or abs(a - b) < 0.02:
                continue
            bucket = counts.setdefault((table, tier), [0, 0])
            bucket[0] += 1
            bucket[1] += (a < b) == a_won

    failures = []
    report: dict = {}
    for (table, tier), (graded, hits) in sorted(counts.items()):
        if graded < MIN_GRADED:
            continue
        rate = hits / graded
        ok = FLOOR <= rate <= CEILING
        report.setdefault(table, {})[tier] = {
            "graded": graded, "favourite_win_rate": round(rate, 4), "ok": ok,
        }
        if not ok:
            failures.append(f"{table}/{tier}: {rate:.1%} of {graded}")

    if args.json:
        print(json.dumps({"report": report, "failures": failures}, indent=2))
    else:
        for table, tiers in report.items():
            print(f"\n{table}")
            for tier, stats in sorted(tiers.items(),
                                      key=lambda kv: -kv[1]["graded"]):
                print(f"  {tier:>12} {stats['graded']:6d} graded  "
                      f"favourite wins {stats['favourite_win_rate']:6.1%}  "
                      f"{'OK' if stats['ok'] else 'FAIL'}")
        print()
        if failures:
            print("FAIL -- a shorter price that loses is a stored orientation, "
                  "not a tennis result:")
            for line in failures:
                print(f"  {line}")
        else:
            print("OK -- every tier with enough settled matches has the "
                  "favourite winning between 55% and 85%.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
