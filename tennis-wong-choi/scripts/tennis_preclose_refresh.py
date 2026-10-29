#!/usr/bin/env python3
"""Scheduled near-start odds capture, so a prop CLOSE can differ from the bet.

Measured read-only on 2026-10-14 (props since 2026-09-01 with a feed identity
and a start time): 2,839 of 2,882 props with any pre-start snapshot had EXACTLY
one, median 3.8h before the start. Close == price evaluated, so prop CLV was
zero by construction and told us nothing.

Every 30 minutes (launchd `com.antigravity.tennis-wong-choi.preclose`) this
fetches the event page of each EVALUATED match (prop_tracker / clv_tracker)
starting 15-75 minutes from now, once per match, 3s apart, at most 30 a tick.

It writes only `preclose_odds_snapshots` / `preclose_market_odds_snapshots`.
The close readers union them in; the card and every replay never read them, so
selections and stakes cannot change. It never sends Telegram and never touches
the daily run's log, lock or control-plane slots. It deliberately does NOT
probe the daily lock: taking it even for a microsecond could make a 09:00 card
start see "already running" and exit. Concurrent writes are short inserts into
tables the card never reads, under the 30s SQLite busy timeout.
"""
from __future__ import annotations

# Lock before imports that may probe output paths or initialize runtime state.
if __name__ == "__main__":
    import sys as _cutover_sys
    from pathlib import Path as _CutoverPath
    _cutover_sys.path.insert(0, str(_CutoverPath(__file__).resolve().parents[2] / '.agents' / 'skills'))
    from shared_wong_choi.runtime_cutover_lease import scheduler_entry as _cutover_entry
    _cutover_entry()


import argparse
import fcntl
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

try:  # package import under pytest
    from .tennis_daily_schedule import (
        LOG_DIR, disk_headroom, local_today, rotate_log_if_needed, trim_launchd_capture,
    )
except ImportError:  # direct script execution under launchd
    from tennis_daily_schedule import (  # type: ignore
        LOG_DIR, disk_headroom, local_today, rotate_log_if_needed, trim_launchd_capture,
    )

OWN_LOCK = LOG_DIR / "tennis_preclose_refresh.lock"
LOG_PATH = LOG_DIR / "tennis_preclose_refresh.log"


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    rotate_log_if_needed(LOG_PATH)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_tick(today: str, *, refresh=None) -> dict:
    """Refresh today's and tomorrow's dates (Sydney `match_date`): a match
    shortly after midnight is dated tomorrow but starts within the window."""
    if refresh is None:
        from tennis_wc.betting.ledger import _ensure_tracking_schema
        from tennis_wc.ingestion.ingest_odds import refresh_pre_start_markets

        _ensure_tracking_schema()
        refresh = refresh_pre_start_markets
    day = datetime.fromisoformat(today).date()
    results = []
    for match_date in (day.isoformat(), (day + timedelta(days=1)).isoformat()):
        try:
            results.append(refresh(match_date))
        except Exception as exc:  # noqa: BLE001 -- a tick must report, not die
            results.append({"date": match_date, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "refreshed": sum(int(r.get("refreshed") or 0) for r in results),
        "failed": sum(int(r.get("failed") or 0) + (1 if r.get("error") else 0) for r in results),
        "dates": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--today", help="Override Sydney today (YYYY-MM-DD).")
    args = parser.parse_args(argv)
    for capture in ("launchd.preclose.stdout.log", "launchd.preclose.stderr.log"):
        trim_launchd_capture(LOG_DIR / capture)
    if os.environ.get("TENNIS_PRECLOSE_DISABLED") == "1":
        log("preclose refresh disabled by TENNIS_PRECLOSE_DISABLED=1")
        return 0
    headroom = disk_headroom()
    if not headroom["ok"]:
        log(f"preclose refresh skipped: DISK HEADROOM TOO LOW: {headroom['detail']}")
        return 75
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with OWN_LOCK.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("preclose refresh skipped: previous tick still running")
            return 0
        today = args.today or local_today().isoformat()
        summary = run_tick(today)
        log("preclose refresh " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
