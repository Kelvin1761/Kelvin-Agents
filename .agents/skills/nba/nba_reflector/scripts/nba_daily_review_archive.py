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
SETTLEMENT = WORKSPACE_ROOT / "Horse_Racing_Dashboard" / "settle_dashboard_bets.py"

sys.path.insert(0, str(WORKSPACE_ROOT))
from wongchoi_paths import NBA_ANALYSIS  # noqa: E402

DASHBOARD_BACKEND = WORKSPACE_ROOT / "Horse_Racing_Dashboard" / "backend"
sys.path.insert(0, str(DASHBOARD_BACKEND))
from services.multisport_exporter import export_nba_snapshot  # noqa: E402


def verification_is_complete(path: Path, *, allow_empty: bool = False) -> tuple[bool, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload["summary"]
        total = int(summary.get("total_legs") or 0)
        hits = int(summary.get("hits") or 0)
        misses = int(summary.get("misses") or 0)
        voids = int(summary.get("voids") or 0)
        unverified = int(summary.get("unverified") or 0)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return False, f"invalid_verification:{exc}"
    if total <= 0 and not allow_empty:
        return False, "no_verification_legs"
    if unverified:
        return False, f"unverified_legs:{unverified}"
    if hits + misses + voids != total:
        return False, "verification_totals_do_not_balance"
    return True, "complete"


def is_valid_no_bet(analysis_date: str) -> bool:
    snapshot = export_nba_snapshot(WORKSPACE_ROOT, target_date=analysis_date)
    recommendations = snapshot.get("recommendations") or []
    warnings = {str(value) for value in snapshot.get("warnings") or []}
    return (
        not recommendations
        and snapshot.get("validation_status") == "blocked"
        and bool(warnings)
        and warnings <= {"no_validated_nba_combos"}
    )


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

    artifacts_exist = all(
        path.is_file() for path in (training_snapshot, results_path, verification_path)
    )
    valid_no_bet = rows_recorded <= 0 and is_valid_no_bet(analysis_date)
    if (rows_recorded <= 0 and not valid_no_bet) or not artifacts_exist:
        return emit(
            "archive_skipped",
            analysis_date,
            "Missing results-backed training artifacts; keeping the live folder in place.",
        )

    verification_complete, verification_reason = verification_is_complete(
        verification_path,
        allow_empty=valid_no_bet,
    )
    if not verification_complete:
        return emit(
            "archive_skipped",
            analysis_date,
            f"Verification incomplete ({verification_reason}); keeping the live folder in place.",
        )

    settlement_output = source / f"Dashboard_Settlement_Proposal_{analysis_date}.json"
    try:
        subprocess.run(
            [
                sys.executable,
                str(SETTLEMENT),
                "--nba-dir",
                str(source),
                "--output",
                str(settlement_output),
            ],
            cwd=WORKSPACE_ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return emit(
            "settlement_export_failed",
            analysis_date,
            f"Settlement proposal exited with code {exc.returncode}; keeping live folder.",
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
