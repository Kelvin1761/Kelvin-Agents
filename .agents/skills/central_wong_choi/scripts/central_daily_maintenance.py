#!/usr/bin/env python3
"""Nightly Central Wong Choi durability maintenance."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
SHARED_RACING = SKILLS_ROOT / "shared_racing" / "scripts"
sys.path.insert(0, str(SKILLS_ROOT))
sys.path.insert(0, str(SHARED_RACING))

from racing_telegram import send_message  # noqa: E402
from shared_wong_choi.dashboard_backup import (  # noqa: E402
    DashboardBackupError,
    backup_d1_ledger,
    collect_d1_backup_status,
)
from shared_wong_choi.storage_status import DEFAULT_WARM_ROOT  # noqa: E402


SYDNEY = ZoneInfo("Australia/Sydney")
BackupFunction = Callable[..., dict[str, Any]]
NotifyFunction = Callable[..., dict[str, Any]]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _already_complete(status: dict[str, Any], clock: datetime) -> bool:
    if status.get("status") != "ok" or not status.get("warm_verified"):
        return False
    raw = status.get("snapshot_at")
    if not raw:
        return False
    try:
        snapshot = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    return snapshot.astimezone(SYDNEY).date() == clock.astimezone(SYDNEY).date()


def _message(run: dict[str, Any]) -> str:
    if run["status"] == "succeeded":
        result = run.get("backup") or {}
        counts = result.get("row_counts") or {}
        return "\n".join(
            (
                "✅ 中央旺財 nightly durability 完成",
                f"D1：bets {counts.get('bets', 0)} · settlements {counts.get('settlements', 0)} · audit {counts.get('audit_log', 0)}",
                f"WARM：{(result.get('warm') or {}).get('status', 'unknown')}",
                f"COLD：{(result.get('cold') or {}).get('status', '未設定')}",
                f"SQL：{((result.get('sql') or {}).get('sha256') or '?')[:12]}",
            )
        )
    if run["status"] == "dormant":
        return "中央旺財 nightly durability：今日已完成，冇重複 export。"
    return "❌ 中央旺財 nightly durability 失敗\n" + str(run.get("error") or "unknown")[:1000]


def run_maintenance(
    repo_root: Path,
    state_root: Path,
    *,
    warm_root: Path,
    cold_root: Path | None,
    clock: datetime | None = None,
    backup_fn: BackupFunction = backup_d1_ledger,
    notify_fn: NotifyFunction = send_message,
    notify: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    now = clock or datetime.now(timezone.utc)
    target_date = now.astimezone(SYDNEY).date().isoformat()
    latest = collect_d1_backup_status(state_root, now=now)
    if _already_complete(latest, now):
        run = {
            "schema_version": "wong-choi-central-maintenance-run/v1",
            "status": "dormant",
            "reason": "today_already_verified",
            "target_date": target_date,
            "started_at": now.isoformat(),
            "backup_status": latest,
        }
        return run
    try:
        result = backup_fn(
            repo_root / "Horse_Racing_Dashboard",
            state_root,
            warm_root=warm_root,
            cold_root=cold_root,
            now=now,
        )
        run = {
            "schema_version": "wong-choi-central-maintenance-run/v1",
            "status": "succeeded" if result.get("status") == "pass" else "partial",
            "target_date": target_date,
            "started_at": now.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "backup": result,
        }
    except DashboardBackupError as exc:
        run = {
            "schema_version": "wong-choi-central-maintenance-run/v1",
            "status": "failed",
            "target_date": target_date,
            "started_at": now.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }
    stamp = now.astimezone(timezone.utc).strftime("%H%M%S.%fZ")
    run_path = state_root / "runs" / "central" / target_date / "durability" / f"{stamp}.json"
    _atomic_json(run_path, run)
    run["run_log"] = str(run_path)
    if notify:
        run["telegram"] = notify_fn(_message(run), audience="primary")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(os.environ.get("WC_PRIMARY_REPO_ROOT", REPO_ROOT)))
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT", Path.home() / "WongChoiData" / "WongChoiControl")),
    )
    parser.add_argument(
        "--warm-root",
        type=Path,
        default=Path(os.environ.get("WC_WARM_ARCHIVE_ROOT", str(DEFAULT_WARM_ROOT))),
    )
    parser.add_argument("--cold-root", type=Path)
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()
    cold_raw = args.cold_root or os.environ.get("WC_COLD_MIRROR_ROOT", "")
    lock_path = args.state_root.expanduser() / "locks" / "central-durability.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "dormant", "reason": "already_running"}))
            return 0
        result = run_maintenance(
            args.repo,
            args.state_root,
            warm_root=args.warm_root,
            cold_root=Path(cold_raw) if cold_raw else None,
            notify=not args.no_notify,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"succeeded", "dormant"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
