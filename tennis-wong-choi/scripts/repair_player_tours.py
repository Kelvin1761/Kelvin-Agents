#!/usr/bin/env python3
"""Repair `players.tour` from ranking / provider-id / opponent evidence.

Why: ESPN labelled women's matches at joint events ATP by scoreboard, the
TennisExplorer corpus labelled every women's ITF match ATP, and
`get_or_create_player` copied each row's label onto the player. By 2026-10-30
that held 19 WTA ranking rows a day ("canonical player identity changed") and
left ~3,000 women stored as ATP. The write paths are fixed in the same change;
this corrects what they already wrote. See `tennis_wc.identity.player_tour`.

Also renames merge targets whose official WTA id the feed renamed after the
merge (Sunam -> Hyojoo Jeong, Kalyakina -> Pankratova). Those merges are right;
the old names stay as aliases.

Report only unless --apply. Every applied value is logged in
`player_tour_repairs` with its old value; --revert RUN_ID undoes a run.

  PYTHONPATH=src .venv/bin/python scripts/repair_player_tours.py --report out.json
  PYTHONPATH=src .venv/bin/python scripts/repair_player_tours.py --apply
  PYTHONPATH=src .venv/bin/python scripts/repair_player_tours.py --revert tour-repair-...
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", metavar="RUN_ID")
    ap.add_argument("--report", type=Path, help="write the full plan as JSON here")
    args = ap.parse_args()

    from tennis_wc.identity.player_tour import (
        apply_tour_repairs,
        plan_tour_repairs,
        revert_tour_repairs,
    )

    writes = bool(args.apply or args.revert)
    # A dry run cannot write: read-only at the connection, not by convention.
    conn = sqlite3.connect(args.db if writes else f"file:{args.db}?mode=ro", uri=not writes, timeout=60)
    conn.row_factory = sqlite3.Row
    if args.revert:
        print(json.dumps({"reverted": revert_tour_repairs(conn, args.revert)}, indent=2))
        return 0

    plan = plan_tour_repairs(conn)
    print(json.dumps(plan["summary"], indent=2, sort_keys=True))
    for label in ("renames", "unresolved_name_mismatches", "conflicts", "mixed_records"):
        for item in plan[label][:15]:
            print(f"{label}: {json.dumps(item, ensure_ascii=False, default=str)[:300]}")
    if args.report:
        args.report.write_text(json.dumps(plan, indent=1, ensure_ascii=False, default=str))
        print(f"full plan -> {args.report}")
    if not args.apply:
        print("dry run: nothing written (pass --apply)")
        return 0
    run_id = "tour-repair-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    applied = apply_tour_repairs(conn, plan, run_id)
    print(json.dumps({"run_id": run_id, "applied": applied}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
