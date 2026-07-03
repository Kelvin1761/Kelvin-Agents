#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None


PROJECT_DIR = Path(__file__).resolve().parents[1]
ANTIGRAVITY_DIR = PROJECT_DIR.parent
ARCHIVE_DIR = ANTIGRAVITY_DIR / "Archieve Tennis Analysis"
LOG_DIR = PROJECT_DIR / "data" / "logs"
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
TIMEZONE = "Australia/Sydney"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily Tennis Wong Choi scheduler runner.")
    parser.add_argument("--today", help="Override today's date in YYYY-MM-DD for testing.")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip tomorrow run-daily.")
    parser.add_argument("--skip-review", action="store_true", help="Skip yesterday review/archive.")
    parser.add_argument("--no-archive", action="store_true", help="Review yesterday but do not move the folder.")
    args = parser.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOG_DIR / "tennis_daily_schedule.lock"
    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Another Tennis Wong Choi daily run is already active; exiting.")
            return 0

        today = date.fromisoformat(args.today) if args.today else local_today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        log(f"Starting scheduled workflow. today={today} review={yesterday} analysis={tomorrow}")

        try:
            run_cli("init-db")
            if not args.skip_review:
                review_payload = review_previous_day(yesterday.isoformat())
                if not args.no_archive:
                    archive_previous_day(yesterday.isoformat(), review_payload)
            if not args.skip_analysis:
                analyse_next_day(tomorrow.isoformat())
        except subprocess.CalledProcessError as exc:
            log(f"Command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}")
            return exc.returncode or 1
        except Exception as exc:
            log(f"Workflow failed: {exc}")
            return 1

        log("Scheduled workflow complete.")
        return 0


def local_today() -> date:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo(TIMEZONE)).date()
    return datetime.now().date()


def review_previous_day(match_date: str) -> dict:
    log(f"Reviewing previous day: {match_date}")
    payload = run_cli_json("review-date", "--date", match_date)
    report_path = payload.get("review_report_path")
    qa_path = payload.get("settlement_qa_report_path")
    log(f"Review written. summary={report_path or 'none'} qa={qa_path or 'none'}")
    return payload


def analyse_next_day(match_date: str) -> None:
    log(f"Running next-day analysis: {match_date}")
    payload = run_cli_json("run-daily", "--date", match_date)
    matches = intish(payload.get("matches_analysed"))
    source_errors = payload.get("source_errors") or []
    log(
        "Analysis complete. "
        f"matches={payload.get('matches_analysed')} "
        f"valid={payload.get('valid_feature_snapshots')} "
        f"dir={payload.get('analysis_dir')}"
    )

    # A zero-match run caused by upstream data sources failing is NOT a normal
    # "no bets today" outcome - it means the pipeline never saw any matches.
    # Make it loud so it is not silently mistaken for a quiet betting day.
    if matches == 0 and source_errors:
        sources = ", ".join(str(err.get("source", "?")) for err in source_errors)
        log(f"WARNING: 0 matches analysed because data sources failed: {sources}. Details: {compact_json(source_errors)}")

    # Store the generated recommendations for tomorrow so the next review can settle them.
    clv = run_cli_json("sync-clv-tracker", "--date", match_date)
    combos = run_cli_json("sync-combo-tracker", "--date", match_date)
    log(f"Trackers synced. clv={compact_json(clv)} combo={compact_json(combos)}")


def archive_previous_day(match_date: str, review_payload: dict) -> None:
    source = ANTIGRAVITY_DIR / f"{match_date} Tennis Analysis"
    destination = ARCHIVE_DIR / source.name

    if not source.exists():
        if destination.exists():
            log(f"Archive already contains {destination.name}; no live folder to move.")
            return
        log(f"No analysis folder found for {match_date}; archive skipped.")
        return

    if not can_archive(review_payload):
        log(f"Review did not confirm result extraction for {match_date}; archive skipped.")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    final_destination = destination
    if final_destination.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final_destination = ARCHIVE_DIR / f"{source.name} rerun {stamp}"

    shutil.move(str(source), str(final_destination))
    log(f"Archived {source.name} -> {final_destination}")


def can_archive(payload: dict) -> bool:
    if not payload.get("review_report_path") or not payload.get("settlement_qa_report_path"):
        return False

    settlement = payload.get("settlement") or {}
    tracker = settlement.get("tracker_settlement") or {}
    combo = settlement.get("combo_settlement") or {}
    result_health = ((settlement.get("auto_refresh") or {}).get("results") or {})
    tml = result_health.get("tennismylife") or {}
    resolver = result_health.get("resolver") or {}

    extracted = any(
        intish(value) > 0
        for value in (
            result_health.get("imported"),
            result_health.get("winners_seen"),
            result_health.get("lookup_winners_seen"),
            tml.get("results_imported"),
            tml.get("rows_seen"),
            tml.get("lookup_rows_seen"),
            resolver.get("event_result_imported"),
            resolver.get("provider_rows_imported"),
            resolver.get("local_history_imported"),
            settlement.get("settled"),
            tracker.get("settled"),
            combo.get("settled"),
        )
    )
    pending = sum(
        intish(value)
        for value in (
            settlement.get("pending_without_result"),
            tracker.get("pending_without_result"),
            combo.get("pending_without_result"),
        )
    )
    return extracted or pending == 0


def run_cli_json(*args: str) -> dict:
    output = run_cli(*args)
    payload = last_top_level_json(output)
    if isinstance(payload, dict):
        return payload
    raise RuntimeError(f"Expected JSON object from {' '.join(args)}, got: {output[-500:]}")


def last_top_level_json(output: str) -> object:
    decoder = json.JSONDecoder()
    parsed: list[object] = []
    for match in re.finditer(r"(?m)^\{", output):
        try:
            payload, _ = decoder.raw_decode(output[match.start() :])
        except json.JSONDecodeError:
            continue
        parsed.append(payload)
    if parsed:
        return parsed[-1]
    return json.loads(output)


def run_cli(*args: str) -> str:
    python = PYTHON if PYTHON.exists() else Path(sys.executable)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [str(python), "-m", "tennis_wc.cli", *args]
    log(f"$ {' '.join(cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    output = completed.stdout.strip()
    if output:
        log(output)
    return output


def compact_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def intish(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    with (LOG_DIR / "tennis_daily_schedule.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
