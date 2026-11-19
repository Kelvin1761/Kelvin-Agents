"""Run the optional isolated drift environment after successful scoring."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[5]
MONITOR = REPO / ".agents/skills/shared_racing/monitoring"

# Retention (2026-11-19): every scoring run wrote a new report folder here and
# nothing ever removed them — 702MB in five weeks on a Mac with ~15GB free.
# Nothing reads old reports back, so after LOCAL_KEEP_DAYS they move to the
# external archive; if that disk is not mounted they stay put (never written to
# a /Volumes path that silently lands on the internal disk) until
# UNMOUNTED_DELETE_DAYS, after which the advisory output is dropped.
LOCAL_KEEP_DAYS = 3
UNMOUNTED_DELETE_DAYS = 30
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def _archive_base() -> Path:
    sys.path.insert(0, str(REPO))
    from wongchoi_paths import SNAPSHOT_ARCHIVE_ROOT  # one definition of the external archive
    return SNAPSHOT_ARCHIVE_ROOT.parent / "scratch" / "wongchoi-drift"


def _mounted(path: Path) -> bool:
    parts = Path(path).parts
    if len(parts) < 3 or parts[1] != "Volumes":
        return Path(path).is_dir()
    return os.path.ismount(Path("/Volumes") / parts[2])


def _run_time(run: Path) -> datetime:
    try:
        return datetime.strptime(run.name.split("-", 1)[0], STAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromtimestamp(run.stat().st_mtime, timezone.utc)


def prune_old_reports(root: Path, archive: Path | None = None, now: datetime | None = None) -> dict:
    """Move <platform>/<meeting>/<run> folders older than LOCAL_KEEP_DAYS off the Mac."""
    now = now or datetime.now(timezone.utc)
    result = {"moved": 0, "deleted": 0, "kept_unmounted": 0, "errors": 0}
    if not root.is_dir():
        return result
    try:
        archive = archive or _archive_base()
    except Exception:  # noqa: BLE001 — retention must never fail a scoring run
        archive = None
    mounted = archive is not None and _mounted(archive)
    for run in sorted(root.glob("*/*/*")):
        if not run.is_dir():
            continue
        try:
            age = now - _run_time(run)
            if age < timedelta(days=LOCAL_KEEP_DAYS):
                continue
            if mounted:
                target = archive / run.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    shutil.rmtree(run)
                else:
                    shutil.move(str(run), str(target))
                result["moved"] += 1
            elif age >= timedelta(days=UNMOUNTED_DELETE_DAYS):
                shutil.rmtree(run)
                result["deleted"] += 1
            else:
                result["kept_unmounted"] += 1
        except OSError:
            result["errors"] += 1
    for meeting in root.glob("*/*"):
        try:
            if meeting.is_dir() and not any(meeting.iterdir()):
                meeting.rmdir()
        except OSError:
            pass
    return result


def run_drift_advisory(platform: str, meeting: Path) -> dict:
    if os.environ.get("WC_DISABLE_DRIFT_MONITOR") == "1":
        return {"status": "disabled"}
    python = MONITOR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print("Drift advisory: optional environment not installed; scoring complete.")
        return {"status": "not_installed"}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    out = REPO / "scratch/wongchoi-drift" / platform / meeting.name / stamp
    status = {"status": "failed", "mode": "advisory"}
    try:
        out.mkdir(parents=True, exist_ok=False)
        env = dict(os.environ, DO_NOT_TRACK="1", ITERATIVE_DO_NOT_TRACK="1", PYTHONDONTWRITEBYTECODE="1")
        with (out / "run.log").open("w", encoding="utf-8") as log:
            result = subprocess.run([str(python), str(MONITOR / "drift_monitor.py"),
                                     "--platform", platform, "--meeting", str(meeting),
                                     "--out", str(out)], env=env, stdout=log, stderr=log, timeout=60)
        status.update(status="completed" if result.returncode == 0 else "failed", returncode=result.returncode)
        if result.returncode == 0:
            report = json.loads((out / "drift.json").read_text())
            evaluated = sum(c["status"] == "evaluated" for c in report["cohorts"])
            status["evaluated_cohorts"] = evaluated
            print(f"Drift advisory {platform}: {evaluated}/{len(report['cohorts'])} cohorts evaluated. {out / 'drift.json'}")
        else:
            print(f"Drift advisory failed; see {out / 'run.log'}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        status.update(status="unavailable", error=str(exc))
        print(f"Drift advisory unavailable: {exc}")
    try:
        (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    except OSError:
        pass
    try:
        status["retention"] = prune_old_reports(REPO / "scratch/wongchoi-drift")
    except Exception as exc:  # noqa: BLE001 — advisory housekeeping, never fails scoring
        status["retention"] = {"error": str(exc)}
    return status
