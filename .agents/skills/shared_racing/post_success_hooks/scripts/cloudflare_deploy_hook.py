#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEPLOY_SCRIPT = PROJECT_ROOT / "deploy.sh"
DASHBOARD_ROOT = PROJECT_ROOT / "Horse_Racing_Dashboard"
DASHBOARD_FETCH_LIVE = DASHBOARD_ROOT / "scripts" / "fetch_live_snapshot.py"
DASHBOARD_GENERATOR = DASHBOARD_ROOT / "generate_static.py"
DASHBOARD_LIVE_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"
DISABLE_ENV = "WC_DISABLE_POST_SUCCESS_DEPLOY"
BATCH_MODE_ENV = "WC_POST_SUCCESS_DEPLOY_MODE"
TIMEOUT_ENV = "WC_POST_SUCCESS_DEPLOY_TIMEOUT_SEC"
DEFAULT_TIMEOUT_SEC = 1800
QUEUE_PATH = PROJECT_ROOT / "_temporary_files" / "post_success_deploy_queue.json"


def run_post_success_cloudflare_deploy(
    *,
    source: str,
    target_dir: Path | None = None,
    skip: bool = False,
    batch: bool = False,
    flush_batch: bool = False,
    allow_failure: bool = True,
) -> bool:
    if skip:
        print(f"⏭️ Cloudflare deploy skipped for {source} (--skip-cloudflare-deploy)")
        return False

    if _env_truthy(DISABLE_ENV):
        print(f"⏭️ Cloudflare deploy skipped for {source} ({DISABLE_ENV}=1)")
        return False

    if batch or _deploy_mode() == "batch":
        queue_post_success_deploy(source=source, target_dir=target_dir)
        if flush_batch:
            return flush_post_success_cloudflare_deploy(source=f"{source} batch flush", allow_failure=allow_failure)
        print(f"📦 Cloudflare deploy queued for {source}; flush later with cloudflare_deploy_hook.py --flush-batch")
        return False

    return _run_deploy(
        source=source,
        target_dir=target_dir,
        allow_failure=allow_failure,
        clear_queue_on_success=True,
    )


def _env_truthy(name: str) -> bool:
    value = str(os.environ.get(name, "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _deploy_mode() -> str:
    return str(os.environ.get(BATCH_MODE_ENV, "")).strip().lower()


def queue_post_success_deploy(*, source: str, target_dir: Path | None = None) -> None:
    queue = _read_queue()
    entry = {
        "source": source,
        "target_dir": str(target_dir) if target_dir else "",
        "queued_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    key = (entry["source"], entry["target_dir"])
    existing = {(item.get("source", ""), item.get("target_dir", "")) for item in queue}
    if key not in existing:
        queue.append(entry)
    _write_queue(queue)


def flush_post_success_cloudflare_deploy(*, source: str = "batch", allow_failure: bool = True) -> bool:
    queue = _read_queue()
    if not queue:
        print("📦 Cloudflare deploy queue empty; nothing to flush")
        return False
    print(f"📦 Flushing Cloudflare deploy queue ({len(queue)} queued item(s))")
    return _run_deploy(source=source, target_dir=None, allow_failure=allow_failure, clear_queue_on_success=True)


def _run_deploy(
    *,
    source: str,
    target_dir: Path | None,
    allow_failure: bool,
    clear_queue_on_success: bool,
) -> bool:
    if not DEPLOY_SCRIPT.exists():
        message = f"⚠️ Cloudflare deploy hook missing: {DEPLOY_SCRIPT}"
        if allow_failure:
            print(message)
            return False
        raise FileNotFoundError(message)

    timeout_sec = _deploy_timeout_seconds()
    target_hint = f" [{target_dir}]" if target_dir else ""
    print("=" * 68)
    print(f"☁️ Post-Success Cloudflare Deploy — {source}{target_hint}")
    print("=" * 68)

    deploy_env = os.environ.copy()
    snapshot = _build_target_snapshot(target_dir)
    if _is_scored_meeting(target_dir) and snapshot is None:
        message = (
            "⚠️ Fresh meeting snapshot could not be built; refusing to "
            "report a successful stale Dashboard deploy"
        )
        if allow_failure:
            print(message)
            return False
        raise RuntimeError(message)
    if snapshot is not None:
        deploy_env["WC_DASHBOARD_BASE_SNAPSHOT"] = str(snapshot)
        print(f"📦 Merged fresh meeting into deploy snapshot: {snapshot}")

    try:
        result = subprocess.run(
            [str(DEPLOY_SCRIPT)],
            cwd=PROJECT_ROOT,
            text=True,
            timeout=timeout_sec,
            env=deploy_env,
        )
    except subprocess.TimeoutExpired:
        message = f"⚠️ Cloudflare deploy timed out after {timeout_sec}s"
        if allow_failure:
            print(message)
            return False
        raise SystemExit(message)

    if result.returncode == 0:
        if clear_queue_on_success:
            _clear_queue()
        print(f"✅ Cloudflare deploy finished for {source}")
        return True

    message = f"⚠️ Cloudflare deploy failed for {source} (exit {result.returncode})"
    if allow_failure:
        print(message)
        return False
    raise SystemExit(result.returncode)


def _is_scored_meeting(target_dir: Path | None) -> bool:
    if target_dir is None:
        return False
    meeting = Path(target_dir)
    return meeting.is_dir() and any(meeting.glob("Race_*_Auto_Analysis.md"))


def _build_target_snapshot(target_dir: Path | None) -> Path | None:
    """Merge a freshly scored meeting into live before invoking deploy.sh.

    ``deploy.sh`` intentionally preserves the live projection when no scheduler
    snapshot is supplied.  A direct orchestrator run used to pass ``target_dir``
    only as a log hint, so it could report a successful Cloudflare deploy while
    republishing the old card unchanged.  Build the same incremental snapshot
    used by the daily scheduler whenever the target is a scored meeting.
    """
    if not _is_scored_meeting(target_dir):
        return None
    meeting = Path(target_dir)
    if not DASHBOARD_FETCH_LIVE.exists() or not DASHBOARD_GENERATOR.exists():
        print("⚠️ Dashboard snapshot tools missing; deploy will preserve live projection")
        return None

    work = meeting / "Dashboard_Snapshot"
    work.mkdir(parents=True, exist_ok=True)
    live = work / "live-dashboard-data.json"
    merged = work / "post-success-dashboard-data.json"
    preview = work / "post-success-dashboard.html"
    try:
        fetch = subprocess.run(
            [sys.executable, str(DASHBOARD_FETCH_LIVE),
             "--url", DASHBOARD_LIVE_URL, "--output", str(live)],
            cwd=PROJECT_ROOT,
            text=True,
            timeout=600,
        )
        if fetch.returncode != 0 or not live.exists():
            print(f"⚠️ Could not fetch live snapshot (exit {fetch.returncode}); preserving live projection")
            return None
        merge = subprocess.run(
            [sys.executable, str(DASHBOARD_GENERATOR),
             "--base-snapshot", str(live),
             "--meeting-dir", str(meeting),
             "--output-json", str(merged),
             "--output-html", str(preview)],
            cwd=DASHBOARD_ROOT,
            text=True,
            timeout=1800,
        )
        if merge.returncode != 0 or not merged.exists():
            print(f"⚠️ Could not merge meeting snapshot (exit {merge.returncode}); preserving live projection")
            return None
        return merged
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ Could not build meeting snapshot ({exc}); preserving live projection")
        return None


def _read_queue() -> list[dict[str, str]]:
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _write_queue(queue: list[dict[str, str]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_queue() -> None:
    QUEUE_PATH.unlink(missing_ok=True)


def _deploy_timeout_seconds() -> int:
    raw = str(os.environ.get(TIMEOUT_ENV, "")).strip()
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SEC
    return max(parsed, 30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post-success Cloudflare deploy helper")
    parser.add_argument("--flush-batch", action="store_true", help="Deploy once for all queued analysis runs")
    parser.add_argument("--status", action="store_true", help="Show queued deploy items")
    parser.add_argument("--clear-batch", action="store_true", help="Clear queued deploy items without deploying")
    args = parser.parse_args()

    if args.status:
        queue = _read_queue()
        print(json.dumps(queue, ensure_ascii=False, indent=2))
    elif args.clear_batch:
        _clear_queue()
        print("📦 Cloudflare deploy queue cleared")
    elif args.flush_batch:
        flush_post_success_cloudflare_deploy(source="manual batch flush", allow_failure=False)
    else:
        run_post_success_cloudflare_deploy(source="manual")
