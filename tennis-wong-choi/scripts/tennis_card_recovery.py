#!/usr/bin/env python3
"""Guarded recovery for a missed Tennis card or missed dashboard publish.

This job only retries the normal, deterministic scheduler.  It never edits
code, changes model rules, or treats a failed dashboard publish as a failed
card.  Two delayed launchd checks cover transient disk/network/provider
failures without repeatedly repricing a card that already completed.  When the
card exists but Cloudflare is stale, it republishes from the live race snapshot
and verifies the production alias; the model is not rerun.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

try:  # package import under pytest
    from .tennis_daily_schedule import (
        LOG_DIR, PROJECT_DIR, disk_headroom, local_today, notify,
    )
    from .verify_scheduled_runs import read_runs
except ImportError:  # direct script execution under launchd
    from tennis_daily_schedule import (  # type: ignore
        LOG_DIR, PROJECT_DIR, disk_headroom, local_today, notify,
    )
    from verify_scheduled_runs import read_runs  # type: ignore


RUNNER = PROJECT_DIR / "scripts" / "run_tennis_daily_schedule.sh"
SCHEDULE_LOG = LOG_DIR / "tennis_daily_schedule.log"
LOCK_PATH = LOG_DIR / "tennis_daily_schedule.lock"
STATE_PATH = LOG_DIR / "tennis_card_recovery_state.json"
MAX_ATTEMPTS = 2
MAX_DASHBOARD_ATTEMPTS = 2
LIVE_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"
DASHBOARD_DEPLOY = PROJECT_DIR.parent / "deploy.sh"
RUNTIME_DIR = PROJECT_DIR / "data" / "runtime"
VERIFY_ATTEMPTS = 6
VERIFY_GAP_SECONDS = 15


def successful_card_for_day(log_path: Path, day: str) -> dict | None:
    """Return evidence of a completed priced card, regardless of deploy status."""
    try:
        runs = read_runs(log_path)
    except SystemExit:
        return None
    for run in reversed(runs):
        if run.get("mode") != "card" or str(run.get("started_at", ""))[:10] != day:
            continue
        health = run.get("health") or {}
        try:
            priced = int(health.get("priced") or 0)
        except (TypeError, ValueError):
            priced = 0
        if priced > 0 and health.get("severity") not in {"error", "retry"}:
            return run
    return None


def load_state(path: Path, day: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    if payload.get("day") != day:
        return {
            "day": day,
            "analysis_attempts": 0,
            "dashboard_attempts": 0,
            "low_disk_alerted": False,
        }
    # Migrate the first release's single counter without losing its guard.
    payload.setdefault("analysis_attempts", int(payload.pop("attempts", 0) or 0))
    payload.setdefault("dashboard_attempts", 0)
    payload.setdefault("low_disk_alerted", False)
    return payload


def save_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def runner_active(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            except OSError:
                pass
    return False


def _live_payload(destination: Path | None = None) -> dict | None:
    """Read production with cache bypass; optionally persist the validated JSON."""
    url = f"{LIVE_URL}?cb={int(datetime.now().timestamp() * 1000)}"
    request = urllib.request.Request(url, headers={
        "User-Agent": "TennisWongChoi-Recovery/1.0",
        "Cache-Control": "no-cache, max-age=0",
        "Pragma": "no-cache",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        payload = json.loads(raw)
        # This snapshot is the authority for race data.  Refuse to deploy from
        # an error page, empty object, or partial response.
        if not isinstance(payload, dict) or not payload.get("meetings") or not payload.get("races"):
            return None
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_suffix(destination.suffix + ".tmp")
            temp.write_bytes(raw)
            temp.replace(destination)
        return payload
    except (OSError, ValueError):
        return None


def live_tennis_status(day: str) -> dict | None:
    payload = _live_payload()
    if payload is None:
        return None
    tennis = (((payload.get("sports_feed") or {}).get("sports") or {}).get("tennis") or {})
    run_id = str(tennis.get("analysis_run_id") or "")
    status = str(tennis.get("validation_status") or "")
    return {
        "published": run_id == f"tennis:{day}" and status in {"valid", "partial"},
        "run_id": run_id,
        "status": status,
    }


def recover_dashboard(day: str) -> tuple[bool, str]:
    """Republish the current DB feed without rerunning Tennis analysis."""
    snapshot = RUNTIME_DIR / f"dashboard-recovery-{day}.json"
    if _live_payload(snapshot) is None:
        return False, "讀唔到完整 live race snapshot；為免覆蓋賽馬資料，冇發佈"
    if not DASHBOARD_DEPLOY.is_file():
        return False, f"搵唔到 dashboard deploy script：{DASHBOARD_DEPLOY}"

    env = os.environ.copy()
    env["WC_DASHBOARD_BASE_SNAPSHOT"] = str(snapshot)
    try:
        completed = subprocess.run(
            [str(DASHBOARD_DEPLOY)],
            cwd=PROJECT_DIR.parent,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Cloudflare deploy 30 分鐘逾時"
    if completed.returncode != 0:
        output = "\n".join((completed.stdout or "", completed.stderr or "")).strip()
        return False, f"Cloudflare deploy exit {completed.returncode}：{output[-500:]}"

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        live = live_tennis_status(day)
        if live and live["published"]:
            return True, f"production 已核實：{live['run_id']} / {live['status']}"
        if attempt < VERIFY_ATTEMPTS:
            time.sleep(VERIFY_GAP_SECONDS)
    last = live or {"run_id": "unreachable", "status": "unknown"}
    return False, ("deploy command 成功，但 production alias 未核實到新 Tennis feed："
                   f"{last['run_id']} / {last['status']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recover a missed Tennis betting card.")
    parser.add_argument("--today", help="Override Sydney date (YYYY-MM-DD).")
    parser.add_argument("--log", type=Path, default=SCHEDULE_LOG)
    parser.add_argument("--state", type=Path, default=STATE_PATH)
    parser.add_argument(
        "--control-json",
        action="store_true",
        help="Emit one final machine-readable control-plane outcome.",
    )
    args = parser.parse_args(argv)

    day = args.today or local_today().isoformat()

    def finish(code: int, status: str, reason: str) -> int:
        if args.control_json:
            print(
                json.dumps(
                    {
                        "status": status,
                        "mode": "recovery",
                        "target_date": day,
                        "exit_code": code,
                        "reason": reason,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        return code

    state = load_state(args.state, day)
    card = successful_card_for_day(args.log, day)
    if card:
        live = live_tennis_status(day)
        if live and live["published"]:
            print(f"RECOVERY NOT NEEDED: {day} card and production dashboard are current.")
            return finish(0, "dormant", "card_and_dashboard_current")
        if runner_active(LOCK_PATH):
            print("DASHBOARD RECOVERY DEFERRED: a Tennis scheduler run is already active.")
            return finish(0, "blocked", "scheduler_locked")
        attempts = int(state.get("dashboard_attempts") or 0)
        if attempts >= MAX_DASHBOARD_ATTEMPTS:
            print(f"DASHBOARD RECOVERY EXHAUSTED: {attempts}/{MAX_DASHBOARD_ATTEMPTS} "
                  f"attempts used for {day}.")
            return finish(1, "failed", "dashboard_recovery_exhausted")
        state["dashboard_attempts"] = attempts + 1
        state["dashboard_last_started_at"] = datetime.now().isoformat(timespec="seconds")
        save_state(args.state, state)
        print(f"DASHBOARD RECOVERY STARTED: attempt {state['dashboard_attempts']}/"
              f"{MAX_DASHBOARD_ATTEMPTS} for {day}; analysis will not be rerun.")
        ok, detail = recover_dashboard(day)
        if ok:
            notify(f"✅ Tennis Dashboard 自動復原完成：{day}\n{detail}")
            print(f"DASHBOARD RECOVERY COMPLETE: {detail}")
            return finish(0, "succeeded", "dashboard_recovered")
        notify(
            f"🎾 Tennis Dashboard 自動復原未成功：{day}\n"
            f"attempt {state['dashboard_attempts']}/{MAX_DASHBOARD_ATTEMPTS}\n"
            f"{detail[-500:]}\n分析及投注咭仍然保留，下一個復原時段會再試。"
        )
        print(f"DASHBOARD RECOVERY FAILED: {detail}")
        return finish(75, "partial", "dashboard_recovery_failed")

    if runner_active(LOCK_PATH):
        print("RECOVERY DEFERRED: a Tennis scheduler run is already active.")
        return finish(0, "blocked", "scheduler_locked")

    attempts = int(state.get("analysis_attempts") or 0)
    if attempts >= MAX_ATTEMPTS:
        print(f"RECOVERY EXHAUSTED: {attempts}/{MAX_ATTEMPTS} attempts used for {day}.")
        return finish(1, "failed", "analysis_recovery_exhausted")

    headroom = disk_headroom()
    if not headroom["ok"]:
        print(f"RECOVERY DEFERRED: disk headroom too low ({headroom['detail']}).")
        if not state.get("low_disk_alerted"):
            notify(
                "🎾 Tennis 自動復原暫停：磁碟空間不足\n"
                f"{headroom['detail']}\n"
                "系統冇刪除任何檔案；騰出空間後下一個復原時段會再試。"
            )
            state["low_disk_alerted"] = True
            save_state(args.state, state)
        return finish(75, "partial", "disk_headroom_low")

    state["analysis_attempts"] = attempts + 1
    state["last_started_at"] = date.today().isoformat()
    save_state(args.state, state)
    print(f"RECOVERY STARTED: attempt {state['analysis_attempts']}/{MAX_ATTEMPTS} for {day}.")
    env = os.environ.copy()
    env["TENNIS_NOTIFY_HEALTH"] = "1"
    # A recovered card is still the day's completed card. Send the same formal
    # recommendation content as the 09:00 pass, to both configured recipients.
    env["TENNIS_NOTIFY_BETS"] = "1"
    try:
        completed = subprocess.run(
            [str(RUNNER), "--source", "recovery", "--refresh-today", "--today", day],
            cwd=PROJECT_DIR,
            env=env,
            timeout=7200,
            check=False,
        )
    except subprocess.TimeoutExpired:
        notify(f"🎾 Tennis 自動復原逾時：{day}（attempt {state['analysis_attempts']}）")
        return finish(75, "partial", "analysis_recovery_timeout")

    if completed.returncode == 0 and successful_card_for_day(args.log, day):
        print(f"RECOVERY COMPLETE: {day} card restored.")
        return finish(0, "succeeded", "card_recovered")

    notify(
        f"🎾 Tennis 自動復原未成功：{day}\n"
        f"exit={completed.returncode} · attempt {state['analysis_attempts']}/{MAX_ATTEMPTS}\n"
        "系統保留所有原始資料，下一個復原時段會再試；未知錯誤唔會自動改 code。"
    )
    code = completed.returncode or 1
    return finish(
        code,
        "partial" if code in (75, 124) else "failed",
        "analysis_recovery_failed",
    )


if __name__ == "__main__":
    raise SystemExit(main())
