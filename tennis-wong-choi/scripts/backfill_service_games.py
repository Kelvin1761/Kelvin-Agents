#!/usr/bin/env python3
"""Backfill service-games exposure from immutable stored history payloads.

The source CSVs were already stored in ``raw_api_responses``.  Reusing the
latest snapshot per provider/entity avoids a network dependency and updates
only the new denominator column; player identity and every other feature stay
untouched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2020)
    args = parser.parse_args()

    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.ingest_sackmann import _float_or_none

    init_db()
    conn = get_connection()
    snapshots = conn.execute(
        """
        SELECT raw.* FROM raw_api_responses raw
        JOIN (
            SELECT provider_name,entity_external_id,MAX(id) AS max_id
            FROM raw_api_responses
            WHERE provider_name IN ('jeff_sackmann','tennismylife_history')
              AND entity_type='match_history'
            GROUP BY provider_name,entity_external_id
        ) latest ON latest.max_id=raw.id
        ORDER BY raw.provider_name,raw.entity_external_id
        """
    ).fetchall()

    before = conn.execute(
        "SELECT COUNT(*) FROM player_match_history "
        "WHERE service_games_played IS NOT NULL"
    ).fetchone()[0]
    prepared: list[tuple[float, str, str]] = []
    source_rows = 0
    used_snapshots = 0
    for snapshot in snapshots:
        entity = str(snapshot["entity_external_id"] or "")
        try:
            year = int(entity.rsplit("-", 1)[-1])
        except ValueError:
            continue
        if year < args.start_year:
            continue
        payload = json.loads(snapshot["response_json"])
        if not isinstance(payload, list):
            continue
        provider = str(snapshot["provider_name"])
        tour = "WTA" if entity.startswith("WTA-") else "ATP"
        used_snapshots += 1
        source_rows += len(payload)
        for row in payload:
            base = f"{tour}-{row.get('tourney_id')}-{row.get('match_num')}"
            winner_games = _float_or_none(row.get("w_SvGms"))
            loser_games = _float_or_none(row.get("l_SvGms"))
            if winner_games is not None:
                prepared.append((winner_games, provider, f"{base}-winner"))
            if loser_games is not None:
                prepared.append((loser_games, provider, f"{base}-loser"))

    changes_before = conn.total_changes
    conn.executemany(
        "UPDATE player_match_history SET service_games_played=? "
        "WHERE source_provider=? AND provider_match_id=?",
        prepared,
    )
    conn.commit()
    updated = conn.total_changes - changes_before
    after = conn.execute(
        "SELECT COUNT(*) FROM player_match_history "
        "WHERE service_games_played IS NOT NULL"
    ).fetchone()[0]
    print(json.dumps({
        "start_year": args.start_year,
        "snapshots": used_snapshots,
        "source_rows": source_rows,
        "updates_attempted": len(prepared),
        "rows_matched": updated,
        "coverage_before": before,
        "coverage_after": after,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
