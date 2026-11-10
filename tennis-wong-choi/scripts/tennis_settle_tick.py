#!/usr/bin/env python3
"""Hourly 精選 settlement, so a result shows on the dashboard soon after the match.

Measured read-only on 2026-11-10 (40 精選): results were read only at the four
scheduled runs, so a pick settled a median 8.1h after its start (1.7h-16h).

Every hour at :35 (launchd `com.antigravity.tennis-wong-choi.settle`):
  1. find PENDING 精選 whose match started 90 minutes to 12 hours ago;
     none -> exit without any network call;
  2. fetch results for those dates and run the normal settlement;
  3. redeploy the dashboard only if a 精選 was actually settled.

It never prices, never changes a pick and never sends Telegram. It takes the
daily scheduler lock without waiting and skips the tick when a scheduled run
holds it; :35 is 25 minutes clear of every scheduled start (:00 and :30), so
holding the lock for a tick cannot make a card run see "already running".
Disable with TENNIS_SETTLE_TICK_DISABLED=1.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from datetime import datetime
from pathlib import Path

try:  # package import under pytest
    from .tennis_daily_schedule import LOCK_NAME, LOG_DIR, _rotate, disk_headroom
except ImportError:  # direct script execution under launchd
    from tennis_daily_schedule import LOCK_NAME, LOG_DIR, _rotate, disk_headroom  # type: ignore

LOG_PATH = LOG_DIR / "tennis_settle_tick.log"


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    _rotate(LOG_PATH)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_tick(*, settle=None, deploy=None) -> dict:
    if settle is None:
        from tennis_wc.run import settle_finished_featured as settle
    summary = settle()
    if summary.get("settled"):
        if deploy is None:
            from tennis_wc.publish.dashboard import deploy_settled as deploy
        summary["dashboard"] = deploy(summary["latest_date"])
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-deploy", action="store_true", help="Settle only; do not redeploy the dashboard.")
    args = parser.parse_args(argv)
    if os.environ.get("TENNIS_SETTLE_TICK_DISABLED") == "1":
        log("settle tick disabled by TENNIS_SETTLE_TICK_DISABLED=1")
        return 0
    headroom = disk_headroom()
    if not headroom["ok"]:
        log(f"settle tick skipped: DISK HEADROOM TOO LOW: {headroom['detail']}")
        return 75
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (Path(LOG_DIR) / LOCK_NAME).open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("settle tick skipped: a scheduled run is active")
            return 0
        try:
            summary = run_tick(deploy=(lambda day: {"attempted": False, "status": "skipped"})
                               if args.no_deploy else None)
        except Exception as exc:  # noqa: BLE001 - a tick must report, not die
            log(f"settle tick failed: {type(exc).__name__}: {exc}")
            return 1
        log("settle tick " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
