#!/usr/bin/env python3
"""Every 15 min: Betfair tennis MATCH_ODDS capture + Sportsbet-vs-Betfair paper decisions.

EXP-20261116-19. Read-only on Betfair (the AU client refuses any non-read
method). Writes only `betfair_markets`, `betfair_price_snapshots` and
`sharp_forward_picks`; the card, 精選, dashboard and every replay never read
them. Never sends Telegram (the 18:00 daily run sends the milestones) and never
touches the daily run's lock or control-plane slots.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))

try:  # package import under pytest
    from .tennis_daily_schedule import LOG_DIR, _rotate, disk_headroom
except ImportError:  # direct script execution under launchd
    from tennis_daily_schedule import LOG_DIR, _rotate, disk_headroom  # type: ignore

OWN_LOCK = LOG_DIR / "tennis_betfair_tick.lock"
LOG_PATH = LOG_DIR / "tennis_betfair_tick.log"


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    _rotate(LOG_PATH)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_tick(conn, *, snapshot=None, record=None) -> dict:
    from tennis_wc.select import sharp_forward
    from tennis_wc.sources import betfair_prices

    snapshot = snapshot or betfair_prices.snapshot
    record = record or sharp_forward.record
    out: dict = {}
    try:
        out["betfair"] = snapshot(conn)
    except Exception as exc:  # noqa: BLE001 -- a tick must report, not die
        out["betfair_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["decisions"] = record(conn)
    except Exception as exc:  # noqa: BLE001
        out["decisions_error"] = f"{type(exc).__name__}: {exc}"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    if os.environ.get("TENNIS_BETFAIR_DISABLED") == "1":
        log("betfair tick disabled by TENNIS_BETFAIR_DISABLED=1")
        return 0
    headroom = disk_headroom()
    if not headroom["ok"]:
        log(f"betfair tick skipped: DISK HEADROOM TOO LOW: {headroom['detail']}")
        return 75
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with OWN_LOCK.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("betfair tick skipped: previous tick still running")
            return 0
        from tennis_wc.store.db import get_connection

        with get_connection() as conn:
            summary = run_tick(conn)
        log("betfair tick " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
