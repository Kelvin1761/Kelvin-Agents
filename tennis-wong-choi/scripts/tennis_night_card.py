#!/usr/bin/env python3
"""21:00 精選 card and 23:00 top-up for TOMORROW (Sydney).

Kelvin 2026-11-05: betting at 09:00 is impractical; bet 21:00-00:00 like NBA.
21:00 prices tomorrow and always sends the 精選 list (0-10 picks). 23:00
re-prices and sends only picks for matches that opened since. The 09:00 card
job stays as the backup top-up.

Runs outside the control plane, like the recovery and pre-close jobs, so it
can never consume the scheduled 09:00/18:00 slots.
"""
from __future__ import annotations

import argparse
import fcntl
import sys
import time
from datetime import timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import tennis_daily_schedule as scheduler  # noqa: E402

LOCK_WAIT_SECONDS = 40 * 60


def _acquire(lock_file) -> bool:
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(30)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("21:00", "23:00", "auto"), default="auto",
                        help="auto: before 22:00 Sydney is the 21:00 main card, later is 23:00.")
    parser.add_argument("--today", help="Override today's Sydney date (YYYY-MM-DD).")
    args = parser.parse_args(argv)

    if args.label == "auto":
        from datetime import datetime
        from zoneinfo import ZoneInfo

        args.label = "21:00" if datetime.now(ZoneInfo("Australia/Sydney")).hour < 22 else "23:00"
    today = scheduler.date.fromisoformat(args.today) if args.today else scheduler.local_today()
    target = (today + timedelta(days=1)).isoformat()
    main_card = args.label == "21:00"
    scheduler.LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = scheduler.LOG_DIR / "tennis_daily_schedule.lock"
    with lock_path.open("w") as lock_file:
        if not _acquire(lock_file):
            scheduler.log(f"NIGHT {args.label}: scheduler busy for 40 min; giving up.")
            scheduler.notify(f"⚠️ Tennis {args.label} 精選未能開始：排程塞住 40 分鐘。", audience="primary")
            return 75
        scheduler.log(f"NIGHT {args.label}: pricing {target} (today={today})")
        failure = None
        try:
            scheduler.ensure_live_network()
            scheduler.ensure_live_provider_config()
            scheduler.run_cli("init-db")
            scheduler.analyse_next_day(target, today=today.isoformat())
        except Exception as exc:  # noqa: BLE001 - still publish what was priced
            failure = f"{type(exc).__name__}: {exc}"
            scheduler.log(f"NIGHT {args.label}: analysis failed: {failure}")
        try:
            added = scheduler.publish_featured(target, args.label, main=main_card and failure is None)
        except Exception as exc:  # noqa: BLE001
            scheduler.log(f"NIGHT {args.label}: 精選 failed: {exc}")
            failure = failure or f"精選: {exc}"
            added = []
        if failure and main_card:
            scheduler.notify(
                f"⚠️ Tennis 21:00 精選抓盤失敗（{target}）：{failure[:300]}\n"
                f"已記錄 {len(added)} 注；23:00 同明朝 09:00 會再試。",
                audience="primary",
            )
        scheduler.log(f"NIGHT {args.label}: done, +{len(added)} 精選")
        return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
