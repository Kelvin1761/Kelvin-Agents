#!/usr/bin/env python3
"""Leakage-safe chronological replay of the current player-prop strategy.

The source database is never modified.  A consistent SQLite backup is created
in a temporary directory, its prop tracker is cleared, and every stored market
date is priced and settled in chronological order.  Family calibration at each
date can therefore see only earlier settled outcomes.

WHAT THE OUTPUT IS, AND IS NOT

It answers "what would today's model have said", which is legitimate evidence.
It is NOT a track record: the prices are re-read now, for matches already
played. `--rebuild-source-tracker` writes exactly that into the live table, and
on 2026-08-10 one such run wrote 9,594 of the 13,658 rows -- three months of
match dates from 2026-05-10 -- after which the tracker read +2.86% ROI while
its provably pre-match rows read -23.38% (CI [-33.92, -12.65]).

Every row this script writes is now stamped `is_point_in_time = 0` by
`record_prop`, so the judgement surfaces exclude it automatically and the two
kinds of row can no longer be confused. That is why the summary below asks for
`point_in_time_only=False` explicitly: on its own output the gated reports are
correctly empty, and a replay has to opt in to reading a replay.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/replay_prop_strategy.py \
      --source-db tennis_wc.db --through 2026-08-01
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


def _backup_database(source: Path, destination: Path) -> None:
    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_conn:
        with sqlite3.connect(destination) as destination_conn:
            source_conn.backup(destination_conn)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-db",
        type=Path,
        default=PROJECT_DIR / "tennis_wc.db",
    )
    parser.add_argument(
        "--through",
        help="include market dates up to YYYY-MM-DD (default: latest stored date)",
    )
    parser.add_argument(
        "--rebuild-source-tracker",
        action="store_true",
        help=(
            "WRITE the replay into --source-db instead of a throwaway clone. "
            "The existing prop_tracker is copied to prop_tracker_pre_rebuild "
            "first. Use when the stored tracker was written by pricing code "
            "that no longer exists, so the evidence gate is reading rows the "
            "current model never produced."
        ),
    )
    parser.add_argument(
        "--discard-point-in-time-record",
        action="store_true",
        help=(
            "Required alongside --rebuild-source-tracker when the live tracker "
            "holds provably pre-match rows. Those rows are the only real "
            "record and cannot be regenerated."
        ),
    )
    args = parser.parse_args()
    source = args.source_db.expanduser().resolve()
    if not source.is_file():
        parser.error(f"database not found: {source}")

    if args.rebuild_source_tracker:
        # This DELETEs the live tracker. Rows that were provably written before
        # their match are the only real record there is, they cannot be
        # regenerated, and one unguarded run of this flag is what destroyed
        # three months of them. Refuse unless the operator says so in as many
        # words.
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as probe:
            try:
                at_risk = probe.execute(
                    "SELECT COUNT(*) FROM prop_tracker WHERE is_point_in_time = 1"
                ).fetchone()[0]
            except sqlite3.Error:
                at_risk = 0
        if at_risk and not args.discard_point_in_time_record:
            parser.error(
                f"--rebuild-source-tracker would delete {at_risk} provably "
                "pre-match rows, which are the only real record and cannot be "
                "rebuilt. They are archived to prop_tracker_pre_rebuild, but "
                "the live table is what every report reads. Re-run with "
                "--discard-point-in-time-record if that is genuinely intended."
            )
        return _run_replay(source, args.through, rebuild=True)

    with tempfile.TemporaryDirectory(prefix="tennis-prop-replay-") as tmp:
        clone = Path(tmp) / "replay.db"
        _backup_database(source, clone)
        return _run_replay(clone, args.through, rebuild=False, source_label=source)


def _run_replay(database: Path, through, rebuild: bool, source_label=None) -> int:
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"

    # Import after DATABASE_URL is pinned to the database being replayed.
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.daily import price_ace_props_for_date
    from tennis_wc.props.settlement import (
        model_vs_market_scorecard,
        prop_roi_report,
        settle_props,
    )
    from tennis_wc.props.strategy import recommendation_gate

    conn = get_connection()
    archived = None
    if rebuild:
        # Keep what the daily card actually published.  The replay answers
        # "what would today's model have said", which is the right evidence
        # base, but it is not a record of what was recommended at the time.
        conn.execute("DROP TABLE IF EXISTS prop_tracker_pre_rebuild")
        conn.execute(
            "CREATE TABLE prop_tracker_pre_rebuild AS SELECT * FROM prop_tracker"
        )
        archived = conn.execute(
            "SELECT COUNT(*) FROM prop_tracker_pre_rebuild"
        ).fetchone()[0]
    conn.execute("DELETE FROM prop_tracker")
    conn.commit()
    date_params: tuple = ()
    date_clause = ""
    if through:
        date_clause = "AND m.match_date <= ?"
        date_params = (through,)
    dates = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT DISTINCT m.match_date
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            WHERE 1=1 {date_clause}
            ORDER BY m.match_date
            """,
            date_params,
        ).fetchall()
    ]
    for match_date in dates:
        price_ace_props_for_date(conn, match_date, log=True, earliest_odds=True)
        settle_props(conn)

    # Explicitly ungated: every row above was just written for a match that has
    # already been played, so the point-in-time corpus is empty by construction.
    # A replay reading a replay is the one honest use of this flag.
    scorecard = model_vs_market_scorecard(conn, point_in_time_only=False)
    roi = prop_roi_report(conn, point_in_time_only=False)
    payload = {
        "source_db": str(source_label or database),
        "rebuilt_source_tracker": rebuild,
        "archived_rows": archived,
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "dates_replayed": len(dates),
        "scorecard": scorecard,
        "roi": roi,
        "strategy": recommendation_gate(scorecard, roi),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
