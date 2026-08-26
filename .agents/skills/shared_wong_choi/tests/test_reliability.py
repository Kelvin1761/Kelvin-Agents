from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.reliability import collect_reliability, run_restore_drill  # noqa: E402


def _run(root: Path, domain: str, slot: str, attempt: int, state: str) -> None:
    path = root / "runs" / domain / slot / f"attempt-{attempt}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "run_id": f"wc:{domain}:{slot}:{attempt}",
                "idempotency_key": f"wc:{domain}:{slot}",
                "attempt": attempt,
                "state": state,
                "completed_at": "2026-08-25T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def test_thirty_day_slo_uses_final_attempt_and_counts_recovery(tmp_path: Path):
    _run(tmp_path, "au", "slot-a", 1, "partial")
    _run(tmp_path, "au", "slot-a", 2, "succeeded")
    _run(tmp_path, "au", "slot-b", 1, "dormant")
    report = collect_reliability(
        tmp_path, now=datetime(2026, 8, 26, tzinfo=timezone.utc)
    )
    assert report["domains"]["au"] == {
        "slots": 2,
        "healthy": 2,
        "failed_or_partial": 0,
        "recovered_by_retry": 1,
        "availability": 1.0,
        "target": 0.95,
        "status": "pass",
    }
    assert report["domains"]["nba"]["status"] == "no_data"


def test_restore_drill_is_exact_and_refuses_overwrite(tmp_path: Path):
    state = tmp_path / "state"
    _run(state, "hkjc", "slot-a", 1, "succeeded")
    (state / "evidence").mkdir(parents=True)
    destination = tmp_path / "restored"
    report = run_restore_drill(state, destination)
    assert report["status"] == "pass"
    assert report["hashes_match"] is True
    try:
        run_restore_drill(state, destination)
    except FileExistsError:
        pass
    else:
        raise AssertionError("restore drill must never overwrite a destination")
