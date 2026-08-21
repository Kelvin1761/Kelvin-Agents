#!/usr/bin/env python3
"""Refuse to start the scheduled run without room to finish it.

On 2026-08-11 the volume filled completely -- 0 bytes free, to the point where
the shell could not write a command's output. The scheduled card job would have
failed at 09:00 with a write error, and the failure would have looked like every
other failure: an absent card.

The cause was ordinary: a 2.5GB replay clone in scratch, a 2.7GB pre-repair
backup, and a database that is itself 2.7GB. Any run that clones or backs up
needs multiples of the database free, and nothing checked.

Exit 1 when headroom is short, so the job fails LOUDLY and early rather than
half-way through a write.

  PYTHONPATH=src .venv/bin/python scripts/check_disk_headroom.py
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
# The card run itself is small, but settlement and review rewrite pages of the
# database, and SQLite needs room for a journal the size of what it touches.
# Two database-widths is the smallest number that is not a guess.
MULTIPLE_OF_DB = 2.0
FLOOR_BYTES = 2 * 1024 ** 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument("--multiple", type=float, default=MULTIPLE_OF_DB)
    args = ap.parse_args()

    usage = shutil.disk_usage(PROJECT_DIR)
    try:
        db_bytes = args.db.stat().st_size
    except OSError:
        db_bytes = 0
    required = max(int(db_bytes * args.multiple), FLOOR_BYTES)

    def gb(value: int) -> str:
        return f"{value / 1024 ** 3:.1f}GB"

    print(f"database: {gb(db_bytes)}   free: {gb(usage.free)}   "
          f"required: {gb(required)} ({args.multiple}x the database, floor "
          f"{gb(FLOOR_BYTES)})")
    if usage.free < required:
        print("FAIL -- not enough headroom. A run that cannot write looks "
              "exactly like a run that found nothing.")
        print("  largest recoverable items are usually a *.bak-* beside the "
              "database and clones under the scratch directory.")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
