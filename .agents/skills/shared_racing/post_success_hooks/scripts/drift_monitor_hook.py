"""Run the optional isolated drift environment after successful scoring."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import uuid

REPO = Path(__file__).resolve().parents[5]
MONITOR = REPO / ".agents/skills/shared_racing/monitoring"


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
    return status
