#!/usr/bin/env python3
"""Leakage-safe chronological replay of the current player-prop strategy.

The source database is never modified.  A consistent SQLite backup is created
in a temporary directory, its prop tracker is cleared, and every stored market
date is priced and settled in chronological order.  Family calibration at each
date can therefore see only earlier settled outcomes.

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
    args = parser.parse_args()
    source = args.source_db.expanduser().resolve()
    if not source.is_file():
        parser.error(f"database not found: {source}")

    if args.rebuild_source_tracker:
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

    scorecard = model_vs_market_scorecard(conn)
    roi = prop_roi_report(conn)
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
