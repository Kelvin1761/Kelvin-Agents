#!/usr/bin/env python3
"""Review and archive a completed NBA Wong Choi analysis day.

The next day's scheduled NBA analysis is performed by the NBA orchestrator.
This helper deliberately owns only the post-game side: run the reflector,
confirm that a results-backed training snapshot was produced, then move the
completed folder to the canonical NBA analysis archive.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[4]
REFLECTOR = SCRIPT_DIR / "nba_reflector_orchestrator.py"

sys.path.insert(0, str(WORKSPACE_ROOT))
from wongchoi_paths import NBA_ANALYSIS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and archive one NBA analysis date.")
    parser.add_argument("--date", required=True, help="Australia/Sydney analysis date (YYYY-MM-DD).")
    args = parser.parse_args()

    analysis_date = datetime.strptime(args.date, "%Y-%m-%d").date().isoformat()
    source = WORKSPACE_ROOT / f"{analysis_date} NBA Analysis"
    destination = NBA_ANALYSIS / source.name

    if not source.is_dir():
        return emit("skipped", analysis_date, "No live analysis folder exists.")

    try:
        subprocess.run(
            [sys.executable, str(REFLECTOR), "--date", analysis_date, "--dir", str(source)],
            cwd=WORKSPACE_ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return emit("review_failed", analysis_date, f"Reflector exited with code {exc.returncode}.")

    summary_path = source / f"Reflector_Run_Summary_{analysis_date}.json"
    if not summary_path.is_file():
        return emit("archive_skipped", analysis_date, "Reflector summary was not created.")

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        training_snapshot = Path(str(summary["training_snapshot"]))
        results_path = Path(str(summary["results_path"]))
        verification_path = Path(str(summary["verification_path"]))
        rows_recorded = int(summary.get("rows_recorded") or 0)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return emit("archive_skipped", analysis_date, f"Invalid reflector summary: {exc}")

    if rows_recorded <= 0 or not all(path.is_file() for path in (training_snapshot, results_path, verification_path)):
        return emit(
            "archive_skipped",
            analysis_date,
            "Missing results-backed training artifacts; keeping the live folder in place.",
        )

    NBA_ANALYSIS.mkdir(parents=True, exist_ok=True)
    final_destination = destination
    if final_destination.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final_destination = NBA_ANALYSIS / f"{source.name} rerun {stamp}"
    shutil.move(str(source), str(final_destination))
    return emit("archived", analysis_date, "Review complete and folder archived.", archive_path=str(final_destination))


def emit(status: str, analysis_date: str, message: str, **extra: str) -> int:
    print(json.dumps({"status": status, "analysis_date": analysis_date, "message": message, **extra}, ensure_ascii=False))
    return 0 if status in {"skipped", "archived", "archive_skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
