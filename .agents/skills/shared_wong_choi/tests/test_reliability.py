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
        "superseded_locked": 0,
        "availability": 1.0,
        "target": 0.95,
        "minimum_slots": 20,
        "status": "provisional",
    }
    assert report["domains"]["nba"]["status"] == "no_data"


def test_run_slo_enforces_target_after_minimum_sample(tmp_path: Path):
    for index in range(20):
        _run(
            tmp_path,
            "au",
            f"slot-{index}",
            1,
            "failed" if index == 0 else "succeeded",
        )
    report = collect_reliability(
        tmp_path, now=datetime(2026, 8, 26, tzinfo=timezone.utc)
    )
    assert report["domains"]["au"]["availability"] == 0.95
    assert report["domains"]["au"]["status"] == "pass"


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


def _poll(root, slot, state, at, status=None, target="2026-08-25"):
    path = root / "runs" / "nba" / target / "postgame" / slot / "attempt-1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    ops = [{"detail": {"source_payload": {"status": status}}}] if status else []
    path.write_text(json.dumps({"idempotency_key": f"wc:nba:{slot}", "attempt": 1, "state": state,
                                "mode": "postgame", "target_date": target, "completed_at": at,
                                "operations": ops}), encoding="utf-8")


def test_lock_skip_superseded_by_later_success_is_not_a_failure(tmp_path: Path):
    """2026-11-25：15 分鐘 poller 撞鎖 skipped_locked、之後同 mode／日子成功 = 被取代；冇之後成功 = 照計失敗。"""
    _poll(tmp_path, "t1", "blocked", "2026-08-25T10:00:00+00:00", "skipped_locked")
    _poll(tmp_path, "t2", "succeeded", "2026-08-25T10:15:00+00:00")
    _poll(tmp_path, "t3", "blocked", "2026-08-25T10:30:00+00:00", "skipped_locked")   # 之後冇成功
    _poll(tmp_path, "t4", "blocked", "2026-08-25T09:00:00+00:00", "other_block")      # 唔係撞鎖
    nba = collect_reliability(tmp_path, now=datetime(2026, 8, 26, tzinfo=timezone.utc))["domains"]["nba"]
    assert nba["superseded_locked"] == 1
    assert (nba["slots"], nba["healthy"], nba["failed_or_partial"]) == (3, 1, 2)
