#!/usr/bin/env python3
"""Repair the two stored orientations that disagreed with the fixture.

Found 2026-08-11 by checking whether the bookmaker's own shorter price won more
often than not. It did on ITF (72.7%) and CHALLENGER (70.7%) and did NOT on TOUR
(53.8%) or UNKNOWN (50.0%), which no tennis result can explain.

Two independent defects, both now fixed at the write path:

  1. `odds_snapshots.player_a_odds` is positional -- every provider fills it
     from its own first listed player -- and `_find_match_id_for_odds` links a
     fixture whose players are in either order. 742 of 6,860 comparable rows
     (10.8%) held the opponent's price; 48.6% of composite-fixture rows.
  2. `market_odds_snapshots.selection_side` is derived at insert, and the
     matches upsert sets `player_a_id = excluded.player_a_id`, silently
     invalidating every side already stored. 8,925 of 40,130 graded rows
     (22.2%) disagreed with their own selection name; 29.1% on TOUR.

Neither is read by the props pipeline -- it resolves players by name and never
selects selection_side -- so this repairs the match-winner path and the stored
record, not prop history.

Report only unless --apply is passed.

  PYTHONPATH=src .venv/bin/python scripts/repair_odds_orientation.py
  PYTHONPATH=src .venv/bin/python scripts/repair_odds_orientation.py --apply
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from tennis_wc.ingestion.ingest_odds import selection_side_for

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    players = {
        row["id"]: (row["a"], row["b"])
        for row in conn.execute(
            """SELECT m.id, pa.name AS a, pb.name AS b FROM matches m
               JOIN players pa ON pa.id = m.player_a_id
               JOIN players pb ON pb.id = m.player_b_id"""
        )
    }

    # 1. selection_side, re-derived from the selection's own name.
    side_fixes: list[tuple] = []
    side_cleared = 0
    for row in conn.execute(
        """SELECT id, match_id, selection_name, selection_side
           FROM market_odds_snapshots WHERE match_id IS NOT NULL"""
    ):
        names = players.get(row["match_id"])
        if not names:
            continue
        side = selection_side_for(names[0], names[1], row["selection_name"])
        if side is None and row["selection_side"] in {"over", "under"}:
            continue
        if side != row["selection_side"]:
            side_fixes.append((side, row["id"]))
            if side is None:
                side_cleared += 1
    print(f"market_odds_snapshots.selection_side to change: {len(side_fixes)}")
    print(f"  ... of which set to NULL (belongs to neither player): {side_cleared}")

    # 2. the positional columns, reordered to the fixture. The provider's own
    #    first player is not stored on the snapshot, so the oriented copy is the
    #    only witness: flip where the pair matches the mirror better than itself.
    odds_fixes: list[tuple] = []
    for row in conn.execute(
        """SELECT o.id, o.player_a_odds ao, o.player_b_odds bo,
                  o.player_a_open_odds aoo, o.player_b_open_odds boo,
                  (SELECT mo.odds FROM market_odds_snapshots mo
                    WHERE mo.match_id = o.match_id AND mo.market_key = 'match_winner'
                      AND mo.selection_name = pa.name
                    ORDER BY mo.id ASC LIMIT 1) AS mkt_a,
                  (SELECT mo.odds FROM market_odds_snapshots mo
                    WHERE mo.match_id = o.match_id AND mo.market_key = 'match_winner'
                      AND mo.selection_name = pb.name
                    ORDER BY mo.id ASC LIMIT 1) AS mkt_b
           FROM odds_snapshots o
           JOIN matches m ON m.id = o.match_id
           JOIN players pa ON pa.id = m.player_a_id
           JOIN players pb ON pb.id = m.player_b_id
           WHERE o.match_id IS NOT NULL"""
    ):
        if None in (row["mkt_a"], row["mkt_b"], row["ao"], row["bo"]):
            continue
        if abs(row["mkt_a"] - row["mkt_b"]) < 1e-9:
            continue
        same = abs(row["ao"] - row["mkt_a"]) + abs(row["bo"] - row["mkt_b"])
        flip = abs(row["ao"] - row["mkt_b"]) + abs(row["bo"] - row["mkt_a"])
        if flip < same:
            odds_fixes.append((row["bo"], row["ao"], row["boo"], row["aoo"], row["id"]))
    print(f"odds_snapshots rows to flip: {len(odds_fixes)}")

    if not args.apply:
        print("\n(report only -- pass --apply to write)")
        return 0

    conn.executemany(
        "UPDATE market_odds_snapshots SET selection_side = ? WHERE id = ?", side_fixes)
    conn.executemany(
        """UPDATE odds_snapshots SET player_a_odds = ?, player_b_odds = ?,
               player_a_open_odds = ?, player_b_open_odds = ? WHERE id = ?""",
        odds_fixes)
    conn.commit()
    print(f"written: {len(side_fixes)} sides, {len(odds_fixes)} price pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
