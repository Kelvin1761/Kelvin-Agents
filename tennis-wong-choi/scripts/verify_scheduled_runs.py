#!/usr/bin/env python3
"""Phase 0.2's exit test, as a command rather than an eyeball.

    two consecutive days on which a SCHEDULED -- not manual -- 09:00 run
    produces a card with priced matches, verified from the log rather than
    assumed

Every clause there matters, and the log could not answer any of them until
2026-08-11. It had no record of who started a run, so a morning pass someone
typed by hand looked exactly like one launchd fired -- which is how the
pipeline ran three days dark: the manual runs simply stopped, and the only
scheduled job was the 18:00 one that asks Sportsbet for a book that is not open
yet. "Verified from the log rather than assumed" is the whole point, so this
reads the log.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/verify_scheduled_runs.py --days 7
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LOG = PROJECT_DIR / "data" / "logs" / "tennis_daily_schedule.log"

# [2026-08-11T09:00:04+10:00] Starting SAME-DAY refresh for 2026-08-11 ... run_source=launchd mode=card
_START = re.compile(
    r"^\[(?P<stamp>[0-9T:+\-]{19,})\].*run_source=(?P<source>\w+)\s+mode=(?P<mode>\w+)"
)
_HEALTH = re.compile(r"^\[(?P<stamp>[0-9T:+\-]{19,})\] HEALTH_JSON (?P<payload>\{.*\})$")


def log_generations(log_path: Path) -> list[Path]:
    """The current log plus its rotated generations, oldest first.

    The scheduler rotates at 8MB. Reading only the live file would let a
    rotation silently erase one of the two mornings the exit test is judged on,
    which is the same class of mistake as the empty listing that read as a
    successful run.
    """
    rotated = sorted(
        (path for path in log_path.parent.glob(log_path.name + ".*")
         if path.suffix.lstrip(".").isdigit()),
        key=lambda path: int(path.suffix.lstrip(".")),
        reverse=True,
    )
    return [*rotated, log_path]


def read_runs(log_path: Path) -> list[dict]:
    """Pair each run's start line with the health line that followed it."""
    runs: list[dict] = []
    pending: dict | None = None
    lines: list[str] = []
    read_any = False
    for path in log_generations(log_path):
        try:
            lines.extend(path.read_text(errors="replace").splitlines())
            read_any = True
        except OSError as exc:
            if path == log_path:
                raise SystemExit(f"cannot read {log_path}: {exc}")
    if not read_any:
        raise SystemExit(f"cannot read {log_path}")
    for line in lines:
        start = _START.match(line)
        if start:
            pending = {
                "started_at": start["stamp"],
                "source": start["source"],
                "mode": start["mode"],
                "health": None,
            }
            runs.append(pending)
            continue
        health = _HEALTH.match(line)
        if health and pending is not None:
            try:
                pending["health"] = json.loads(health["payload"])
            except ValueError:
                pending["health"] = None
    return runs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-priced", type=int, default=1,
                    help="a card needs at least this many priced matches")
    ap.add_argument("--scheduled-hour", type=int, default=9,
                    help="the hour the card job is scheduled for, local time")
    ap.add_argument("--tolerance-minutes", type=int, default=45,
                    help="how far from the scheduled time still counts as the "
                         "scheduled run")
    args = ap.parse_args()

    runs = read_runs(args.log)
    # `run_source=launchd` says launchd started it -- NOT that the schedule did.
    # `launchctl kickstart` produces a genuine launchd run at any hour, so a
    # wiring test run by hand would otherwise satisfy the very exit test it was
    # meant to prepare for. The clause is "a SCHEDULED 09:00 run", so the clock
    # is part of the evidence.
    cards = [
        run for run in runs
        if run["mode"] == "card" and run["source"] == "launchd"
        and _near_scheduled_time(run["started_at"], args.scheduled_hour,
                                 args.tolerance_minutes)
    ]
    off_schedule = [
        run for run in runs
        if run["mode"] == "card" and run["source"] == "launchd"
        and run not in cards
    ]
    if off_schedule:
        print(f"note: {len(off_schedule)} launchd card run(s) fired away from "
              f"{args.scheduled_hour:02d}:00 (kickstart or a missed-window "
              f"catch-up) and do NOT count toward the exit test:")
        for run in off_schedule[-5:]:
            print(f"  {run['started_at']}")
        print()
    # One verdict per calendar day: the day passes if any scheduled card run
    # that day priced something.
    by_day: dict[str, dict] = {}
    for run in cards:
        day = run["started_at"][:10]
        health = run["health"]
        # No HEALTH_JSON is unknown, not zero. The 2026-08-13 scheduled run
        # built a priced card and then died in the post-success deploy before
        # this line could be emitted. Printing that as priced=0 falsely blamed
        # the provider for a number the log never contained.
        priced = health.get("priced") if health is not None else None
        current = by_day.get(day)
        if current is None or _priced_score(priced) > _priced_score(current.get("priced")):
            by_day[day] = {
                "priced": priced,
                "fixtures": health.get("fixtures") if health is not None else None,
                "severity": health.get("severity") if health is not None else None,
                "started_at": run["started_at"],
            }

    days = sorted(by_day)[-args.days:]
    print(f"log: {args.log}")
    print(f"runs recorded: {len(runs)}  scheduled card runs: {len(cards)}")
    missing_health = sum(run["health"] is None for run in cards)
    if missing_health:
        print(f"scheduled card runs missing HEALTH_JSON: {missing_health} "
              "(priced/fixtures are UNKNOWN, not zero)")
    if not cards:
        manual = [r for r in runs if r["mode"] == "card" and r["source"] != "launchd"]
        print(f"\nNO scheduled card run has been recorded yet "
              f"({len(manual)} manual ones).")
        # "Not installed" and "installed but not yet due" are the same empty
        # result, and reporting the wrong one is how a broken schedule reads as
        # a young one. Ask launchd which it is.
        installed, detail = _job_installed(JOB_LABEL)
        if installed:
            print(f"The .card job IS installed ({detail}). It has simply not "
                  f"fired at {args.scheduled_hour:02d}:00 yet -- the exit test "
                  f"needs two such mornings.")
        else:
            print(f"The .card job is NOT installed ({detail}). Run "
                  f"scripts/install_macos_launchd.sh")
        print("EXIT TEST: NOT MET")
        return 1

    print(f"\n{'day':>12} {'priced':>7} {'fixtures':>9} {'severity':>16}  first run")
    for day in days:
        row = by_day[day]
        print(f"{day:>12} {str(row['priced']):>7} {str(row['fixtures']):>9} "
              f"{str(row['severity']):>16}  {row['started_at']}")

    passing = [day for day in sorted(by_day)
               if by_day[day]["priced"] is not None
               and by_day[day]["priced"] >= args.min_priced]
    consecutive = _longest_consecutive(passing)
    print(f"\ndays with a priced scheduled card: {len(passing)}  "
          f"longest consecutive run: {consecutive}")
    met = consecutive >= 2
    print("EXIT TEST: " + ("MET" if met else "NOT MET"))
    return 0 if met else 1


JOB_LABEL = "com.antigravity.tennis-wong-choi.card"


def _priced_score(value) -> int:
    """Comparison key where a recorded zero outranks an absent health record."""
    try:
        return int(value) if value is not None else -1
    except (TypeError, ValueError):
        return -1


def _job_installed(label: str) -> tuple[bool, str]:
    """Ask launchd whether the job exists, and say so either way."""
    import os
    import subprocess

    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not ask launchctl: {exc}"
    if result.returncode != 0:
        return False, "launchctl does not know this label"
    runs = "unknown"
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("runs ="):
            runs = stripped.split("=", 1)[1].strip()
    return True, f"loaded, {runs} run(s) so far"


def _near_scheduled_time(stamp: str, hour: int, tolerance_minutes: int) -> bool:
    """Did this run start close enough to the scheduled time to BE it?"""
    from datetime import datetime

    try:
        started = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    minutes_from = abs((started.hour * 60 + started.minute) - hour * 60)
    # A run just before midnight is not close to an 09:00 slot; no wraparound.
    return minutes_from <= tolerance_minutes


def _longest_consecutive(days: list[str]) -> int:
    from datetime import date, timedelta

    best = run = 0
    previous = None
    for value in days:
        try:
            current = date.fromisoformat(value)
        except ValueError:
            continue
        run = run + 1 if previous is not None and current - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = current
    return best


if __name__ == "__main__":
    raise SystemExit(main())
