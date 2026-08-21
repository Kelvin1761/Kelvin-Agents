#!/usr/bin/env python3
"""Recover `matches.start_time_utc` from the raw provider payloads we kept.

The provider has always sent it -- `start_time_utc` appears in both the listing
and the per-event response -- and nothing stored it. Without it there is no way
to say which odds snapshot is the CLOSE, and 2,919 of 120,004 stored snapshots
(2.4%) were fetched after the match date while 257 selections swing more than
threefold inside their own history (1.19 -> 67.00). Those are in-running prices,
`weekly_review` already disables CLV as a gate because of them, and the audit
traced a +58% ROI result to the same source.

Every fetched payload is in `raw_api_responses`, so the history is recoverable
rather than lost. Read-only against the payloads; writes only the new column,
and only where it is currently NULL.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/backfill_match_start_times.py --apply
"""
from __future__ import annotations

import argparse
from datetime import timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

_TIME_KEYS = ("start_time_utc", "startTime", "start_time",
              "commence_time", "commenceTime")


def _iso_utc(value) -> str | None:
    from tennis_wc.ingestion.ingest_odds import _parse_datetime

    # A key named like a time can hold a nested object; only scalars parse.
    if not isinstance(value, (str, int, float)):
        return None
    parsed = _parse_datetime(value)
    if not parsed:
        return None
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _walk(node, found: dict) -> None:
    """Collect every (event id -> start time) pair anywhere in the payload."""
    if isinstance(node, dict):
        start = None
        for key in _TIME_KEYS:
            if key in node:
                start = _iso_utc(node.get(key))
                if start:
                    break
        if start:
            for id_key in ("event_id", "eventId", "id", "provider_match_id"):
                value = node.get(id_key)
                if value not in (None, ""):
                    found.setdefault(str(value), start)
        for value in node.values():
            _walk(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk(value, found)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument("--apply", action="store_true",
                    help="write the recovered start times (default: report only)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    missing = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE start_time_utc IS NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    print(f"matches: {total}, without a start time: {missing}")

    found: dict = {}
    rows = conn.execute(
        """SELECT response_json FROM raw_api_responses
           WHERE provider_name = 'sportsbet'
             AND (response_json LIKE '%start_time_utc%'
                  OR response_json LIKE '%startTime%')"""
    ).fetchall()
    print(f"sportsbet payloads carrying a start time: {len(rows)}")
    for row in rows:
        try:
            payload = json.loads(row["response_json"])
        except (TypeError, ValueError):
            continue
        _walk(payload, found)
    print(f"distinct provider event ids with a start time: {len(found)}")

    # matches carry the provider's id in two places; try both rather than
    # assuming which one this provider filled.
    candidates = conn.execute(
        """SELECT id, provider_match_id, market_event_id
           FROM matches WHERE start_time_utc IS NULL"""
    ).fetchall()
    updates = []
    for match in candidates:
        for key in (match["market_event_id"], match["provider_match_id"]):
            if key and str(key) in found:
                updates.append((found[str(key)], match["id"]))
                break
    print(f"matches this can fill: {len(updates)} of {missing}")

    if not args.apply:
        print("\n(report only -- pass --apply to write)")
        return 0
    conn.executemany(
        "UPDATE matches SET start_time_utc = ? WHERE id = ? AND start_time_utc IS NULL",
        updates,
    )
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE start_time_utc IS NULL"
    ).fetchone()[0]
    print(f"written. matches still without a start time: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
