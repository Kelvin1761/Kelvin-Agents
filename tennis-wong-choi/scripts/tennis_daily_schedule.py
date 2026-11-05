#!/usr/bin/env python3
"""Tennis Wong Choi scheduled runs (Sydney time; launchd templates in ../launchd).

  --night [auto|21:00|23:00]  21:00 prices TOMORROW and always sends 精選;
                              23:00 re-prices and sends only new picks.
  --refresh-today             09:00 backup: prices TODAY, sends 補充精選 if any.
  (default)                   18:00 daily: review yesterday, archive, warm tomorrow.

The night job runs outside the control plane; the 09:00/18:00 jobs run through
it (``--control-json`` prints the outcome it reads). One lock serialises them.
Log lines ``run_source=… mode=…`` and ``HEALTH_JSON {…}`` are read by
tennis_card_recovery.py / verify_scheduled_runs.py.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))

LOG_DIR = Path(os.environ.get("TENNIS_LOG_DIR") or (PROJECT_DIR / "data" / "logs"))
LOCK_NAME = "tennis_daily_schedule.lock"
TIMEZONE = "Australia/Sydney"
MAX_LOG_BYTES = 8 * 1024 * 1024
LOG_BACKUPS = 5
NIGHT_LOCK_WAIT_SECONDS = 40 * 60
DASHBOARD_SETTLEMENT = PROJECT_DIR.parent / "Horse_Racing_Dashboard" / "settle_dashboard_bets.py"


class TemporaryDataUnavailable(RuntimeError):
    """Live data missing for now; retry later (exit 75)."""


class AnalysisBoardMissing(RuntimeError):
    """The board is absent on a day it cannot legitimately be (exit 70)."""


# --------------------------------------------------------------------------- plumbing

def local_today() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def _rotate(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return
    except OSError:
        return
    oldest = path.with_suffix(path.suffix + f".{LOG_BACKUPS}")
    if oldest.exists():
        oldest.unlink()
    for index in range(LOG_BACKUPS - 1, 0, -1):
        source = path.with_suffix(path.suffix + f".{index}")
        if source.exists():
            source.rename(path.with_suffix(path.suffix + f".{index + 1}"))
    path.rename(path.with_suffix(path.suffix + ".1"))


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    path = LOG_DIR / "tennis_daily_schedule.log"
    _rotate(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def notify(text: str, *, audience: str = "primary") -> bool:
    from tennis_wc.publish.telegram import notify as send

    return send(text, audience=audience)


def disk_headroom(db_path: Path | None = None) -> dict:
    """Twice the database (VACUUM/backup) and at least 2GB must be free."""
    try:
        db_bytes = (db_path or PROJECT_DIR / "tennis_wc.db").stat().st_size
    except OSError:
        db_bytes = 0
    required = max(int(db_bytes * 2.0), 2 * 1024 ** 3)
    free = shutil.disk_usage(PROJECT_DIR).free
    return {"ok": free >= required, "free_bytes": free, "required_bytes": required,
            "detail": f"{free / 1024 ** 3:.1f}GB free, {required / 1024 ** 3:.1f}GB required "
                      f"for a {db_bytes / 1024 ** 3:.1f}GB database"}


def preflight() -> None:
    from tennis_wc.config import get_settings
    from tennis_wc.store.migrations import init_db
    from tennis_wc.diagnostics import run_network_check

    diagnosis = run_network_check().get("diagnosis")
    if diagnosis != "network_ready":
        raise TemporaryDataUnavailable(f"live network preflight failed ({diagnosis})")
    settings = get_settings()
    mock = [name for name in ("tennis_provider", "odds_provider")
            if str(getattr(settings, name) or "mock").lower() == "mock"]
    if mock:
        raise AnalysisBoardMissing(f"live provider config invalid: {', '.join(mock)} resolved to mock")
    init_db()
    log(f"Preflight passed. tennis={settings.tennis_provider} odds={settings.odds_provider}")


# --------------------------------------------------------------------------- analysis

def analyse(match_date: str, *, today: str) -> dict:
    """Price one date; raise when readiness says the board is broken or incomplete."""
    from tennis_wc import run
    from tennis_wc.store.db import get_connection
    from tennis_wc.store.maintenance import prune_raw_response_bodies, prune_superseded_feature_snapshots

    log(f"Running analysis for {match_date} (horizon={run.horizon(match_date, today)})")
    payload = run.price_day(match_date, today=today)
    errors, warnings = payload["source_errors"], payload["source_warnings"]
    log(f"Analysis complete. matches={payload['matches_analysed']} valid={payload['valid_feature_snapshots']} "
        f"props={payload['props_priced']} report={payload['report_path']}")
    if errors:
        log(f"WARNING: {len(errors)} source(s) failed: {json.dumps(errors, ensure_ascii=False)[:2000]}")
    if warnings:
        log(f"WARNING: {len(warnings)} source(s) degraded: {json.dumps(warnings, ensure_ascii=False)[:2000]}")
    try:
        with get_connection() as conn:
            pruned = prune_raw_response_bodies(conn, keep_days=7, dry_run=False)
            prune_superseded_feature_snapshots(conn, keep_days=7, dry_run=False)
        if pruned.get("rows"):
            log(f"Compacted {pruned['rows']} superseded API payloads losslessly.")
    except Exception as exc:  # noqa: BLE001 - retention never fails a run
        log(f"Retention step skipped: {exc}")
    ready = payload["readiness"]
    coverage = payload.get("odds_coverage") or {}
    log("HEALTH_JSON " + json.dumps({
        "date": match_date, "horizon": ready["horizon"], "severity": ready["severity"],
        "fixtures": coverage.get("fixtures"), "priced": coverage.get("priced_matches"),
        "analysed": payload["matches_analysed"], "props": payload["props_priced"],
        "source_errors": len(errors), "source_warnings": len(warnings)}, ensure_ascii=False))
    observed = "; ".join(ready["observed"]) or "none"
    if ready["severity"] == "error":
        raise AnalysisBoardMissing(f"analysis for {match_date} is BROKEN, not merely early: {observed}")
    if ready["severity"] == "retry":
        raise TemporaryDataUnavailable(f"analysis for {match_date} is incomplete: {observed}")
    if ready["severity"] == "expected_empty":
        log(f"Book not open for {match_date} yet ({observed}).")
    return payload


def publish(match_date: str, label: str, *, main: bool) -> list[dict]:
    from tennis_wc.publish.telegram import publish_featured

    try:
        return publish_featured(match_date, label, main=main)
    except Exception as exc:  # noqa: BLE001 - never mask the run outcome
        log(f"精選 {label} failed: {exc}")
        return []


def publish_dashboard(match_date: str, payload: dict | None) -> None:
    """Report, evidence and dashboard deploy, AFTER 精選 so they carry the picks."""
    from tennis_wc import run

    if payload is None:
        log(f"Dashboard deploy skipped for {match_date}: no completed analysis.")
        return
    try:
        out = run.publish_day(match_date, payload)
        log(f"Dashboard deploy: {json.dumps(out.get('cloudflare_deploy'), ensure_ascii=False)}")
    except Exception as exc:  # noqa: BLE001 - a dashboard failure never fails the run
        log(f"Dashboard deploy failed: {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- the three jobs

def night(today: date, label: str) -> int:
    """21:00 main card / 23:00 top-up for tomorrow. Never raises."""
    target = (today + timedelta(days=1)).isoformat()
    main = label == "21:00"
    failure = None
    payload = None
    try:
        preflight()
        payload = analyse(target, today=today.isoformat())
    except Exception as exc:  # noqa: BLE001 - still publish what was priced
        failure = f"{type(exc).__name__}: {exc}"
        log(f"NIGHT {label}: analysis failed: {failure}")
    added = publish(target, label, main=main and failure is None)
    publish_dashboard(target, payload)
    if failure and main:
        notify(f"⚠️ Tennis 21:00 精選抓盤失敗（{target}）：{failure[:300]}\n"
               f"已記錄 {len(added)} 注；23:00 同明朝 09:00 會再試。")
    log(f"NIGHT {label}: done, +{len(added)} 精選")
    return 1 if failure else 0


def card(today: date) -> None:
    """09:00 backup: price today, top up 精選."""
    payload = None
    try:
        preflight()
        payload = analyse(today.isoformat(), today=today.isoformat())
    finally:
        publish(today.isoformat(), "09:00", main=False)
        publish_dashboard(today.isoformat(), payload)


def daily(today: date) -> None:
    """18:00: review + settle yesterday, ROI board, archive; warm tomorrow."""
    from tennis_wc import run
    from tennis_wc.publish.telegram import forward_milestone, send_roi_board

    yesterday = (today - timedelta(days=1)).isoformat()
    preflight()
    _lowtier_corpus(yesterday)
    log(f"Reviewing previous day: {yesterday}")
    review = run.review_day(yesterday)
    log(f"Review: graded={review['settlement']['graded']} voided={review['settlement']['voided']} "
        f"pending_for_date={review['pending_for_date']}")
    if os.environ.get("TENNIS_NOTIFY_PERFORMANCE") == "1":
        try:
            send_roi_board(yesterday, today.isoformat())
        except Exception as exc:  # noqa: BLE001
            log(f"ROI board skipped: {exc}")
    try:
        forward_milestone(LOG_DIR)
    except Exception as exc:  # noqa: BLE001
        log(f"精選 forward milestone check skipped: {exc}")
    _dashboard_settlements(yesterday)
    if run.results_extracted(review):
        _archive(yesterday)
    tomorrow = (today + timedelta(days=1)).isoformat()
    publish_dashboard(tomorrow, analyse(tomorrow, today=today.isoformat()))
    if today.weekday() == 6:
        try:
            from tennis_wc.publish.weekly import send_weekly

            send_weekly(today.isoformat())
            log("Weekly review sent.")
        except Exception as exc:  # noqa: BLE001
            log(f"Weekly review skipped: {exc}")


def _lowtier_corpus(match_date: str) -> None:
    """TennisExplorer scoreboard -> history (the only ITF source)."""
    from tennis_wc.sources.ingest_tennisexplorer_history import ingest_tennisexplorer_history

    try:
        summary = ingest_tennisexplorer_history(match_date, None)
        log(f"Lower-tier corpus: {summary.get('matches')} matches, {summary.get('players_created')} new players")
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: lower-tier corpus top-up failed: {exc}")


def _dashboard_settlements(match_date: str) -> None:
    if not DASHBOARD_SETTLEMENT.is_file():
        return
    try:
        result = subprocess.run([sys.executable, str(DASHBOARD_SETTLEMENT), "--date", match_date, "--apply"],
                                cwd=str(PROJECT_DIR.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding="utf-8", errors="replace", timeout=90)
        if result.stdout.strip():
            log(f"Dashboard settlement: {result.stdout.strip()[-1200:]}")
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: dashboard auto-settlement failed: {exc}")


def _archive(match_date: str) -> None:
    """Move the Drive analysis folder into 'Archieve Tennis Analysis' once results are in."""
    from tennis_wc.publish.report import drive_dir

    source = drive_dir(match_date)
    destination = source.parent / "Archieve Tennis Analysis" / source.name
    if not source.exists():
        return
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination = destination.with_name(f"{source.name} rerun {datetime.now():%Y%m%d-%H%M%S}")
        shutil.move(str(source), str(destination))
        log(f"Archived {source.name} -> {destination}")
    except OSError as exc:
        log(f"Archive deferred for {source.name}: {exc}")


# --------------------------------------------------------------------------- entry

def _lock(path: Path, wait_seconds: int):
    handle = path.open("w")
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(30)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--today", help="Override today's Sydney date (YYYY-MM-DD).")
    parser.add_argument("--source", default="manual", help="launchd / recovery / manual (logged).")
    parser.add_argument("--refresh-today", action="store_true", help="09:00 backup pass for today.")
    parser.add_argument("--night", nargs="?", const="auto", choices=("auto", "21:00", "23:00"))
    parser.add_argument("--control-json", action="store_true", help="Print the control-plane outcome.")
    parser.add_argument("--force", action="store_true", help=argparse.SUPPRESS)  # passed by recovery
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else local_today()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if args.night:
        label = args.night
        if label == "auto":
            label = "21:00" if datetime.now(ZoneInfo(TIMEZONE)).hour < 22 else "23:00"
        lock = _lock(LOG_DIR / LOCK_NAME, NIGHT_LOCK_WAIT_SECONDS)
        if lock is None:
            log(f"NIGHT {label}: scheduler busy for 40 min; giving up.")
            notify(f"⚠️ Tennis {label} 精選未能開始：排程塞住 40 分鐘。")
            return 75
        with lock:
            log(f"Starting NIGHT {label} for {today + timedelta(days=1)}. run_source={args.source} mode=night")
            return night(today, label)

    mode = "card" if args.refresh_today else "daily"
    target = (today if args.refresh_today else today + timedelta(days=1)).isoformat()

    def done(code: int, status: str, reason: str | None = None) -> int:
        if args.control_json:
            out = {"status": status, "mode": mode, "target_date": target, "exit_code": code}
            if reason:
                out["reason"] = reason
            print(json.dumps(out, ensure_ascii=False, sort_keys=True))
        return code

    headroom = disk_headroom()
    if not headroom["ok"]:
        log(f"DISK HEADROOM TOO LOW: {headroom['detail']} -- refusing to start.")
        return done(75, "partial", "disk_headroom_low")
    lock = _lock(LOG_DIR / LOCK_NAME, 0)
    if lock is None:
        log("Another Tennis Wong Choi run is already active; exiting.")
        return done(0, "blocked", "scheduler_locked")
    with lock:
        log(f"Starting {mode} for {target}. run_source={args.source} mode={mode}")
        try:
            if args.refresh_today:
                card(today)
            else:
                daily(today)
        except AnalysisBoardMissing as exc:
            log(f"BOARD MISSING: {exc}")
            notify(f"🎾 Tennis Wong Choi — 出唔到咭\n{exc}")
            return done(70, "failed", "analysis_board_missing")
        except TemporaryDataUnavailable as exc:
            log(f"TEMPORARY DATA FAILURE: {exc}")
            return done(75, "partial", "temporary_data_unavailable")
        except Exception as exc:  # noqa: BLE001
            log(f"{mode} failed: {type(exc).__name__}: {exc}")
            return done(1, "failed", f"{type(exc).__name__}: {exc}")
        log(f"{'Same-day refresh' if args.refresh_today else 'Scheduled workflow'} complete.")
        return done(0, "succeeded")


if __name__ == "__main__":
    raise SystemExit(main())
