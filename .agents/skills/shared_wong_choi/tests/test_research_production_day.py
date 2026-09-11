from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain, RunIdentity, RunState
from shared_wong_choi.control import RunManifest, manifest_path
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_production_day import (
    inspect_production_day,
    production_day_review_event,
    production_day_schedule,
    verify_production_day_evidence,
)


DAY = date(2026, 9, 3)
AS_OF = datetime(2026, 9, 4, 2, 0, tzinfo=timezone.utc)
COMMIT = "a" * 40


def _attestation(tmp_path: Path, domain: Domain, day: date = DAY) -> Path:
    schedule = production_day_schedule(domain, day)
    payload = {
        "schema_version": "wong-choi-production-day-attestation/v1",
        "append_only": True,
        "domain": domain.value,
        "production_day": day.isoformat(),
        "generated_at": AS_OF.isoformat(),
        "policy_digest": schedule["policy_digest"],
        "producer_commit": COMMIT,
        "installed_schedule_digest": "b" * 64,
        "expected_runs": schedule["expected_runs"],
        "trigger_coverage_complete": True,
        "model_promotion_allowed": False,
    }
    payload["content_hash"] = _hash(payload)
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    return path


def _terminal_runs(
        root: Path, domain: Domain, day: date = DAY,
        *, omit: int | None = None, running: int | None = None,
        failed: int | None = None):
    expected = production_day_schedule(domain, day)["expected_runs"]
    for index, item in enumerate(expected):
        if index == omit:
            continue
        identity = RunIdentity(
            domain,
            item["mode"],
            date.fromisoformat(item["target_date"]),
            item["scheduled_slot"],
        )
        started = datetime.fromisoformat(item["scheduled_at"]).astimezone(timezone.utc)
        manifest = RunManifest.create(
            manifest_path(root, identity), identity, at=started,
        )
        manifest.transition(RunState.RUNNING, at=started)
        if index != running:
            manifest.transition(
                RunState.FAILED if index == failed else RunState.SUCCEEDED,
                at=started + timedelta(minutes=1),
            )
    return expected


def test_all_expected_terminal_runs_close_day_but_preserve_failure_health(tmp_path):
    runs = tmp_path / "runs"
    expected = _terminal_runs(runs, Domain.AU, failed=1)
    attestation = _attestation(tmp_path, Domain.AU)

    report = inspect_production_day(
        run_root=runs,
        attestation_path=attestation,
        domain=Domain.AU,
        production_day=DAY,
        as_of=AS_OF,
    )

    assert report["production_day_closed"] is True
    assert report["schedule_attestation_verified"] is True
    assert report["counts"]["expected"] == len(expected)
    assert report["counts"]["terminal"] == len(expected)
    assert report["counts"]["failed"] == 1
    assert report["operational_health"] == "attention"
    assert report["model_promotion_allowed"] is False
    event = production_day_review_event(report)
    assert event.kind == "production_day_closed"
    assert event.production_day == DAY
    assert event.evidence_digest == report["content_hash"]
    verify_production_day_evidence(
        report,
        run_root=runs,
        attestation_path=attestation,
        domain=Domain.AU,
        production_day=DAY,
        as_of=AS_OF,
        reverify_source=True,
    )


def test_all_runs_without_approved_attestation_never_close_day(tmp_path):
    runs = tmp_path / "runs"
    _terminal_runs(runs, Domain.NBA)

    report = inspect_production_day(
        run_root=runs,
        attestation_path=None,
        domain=Domain.NBA,
        production_day=DAY,
        as_of=AS_OF,
    )

    assert report["production_day_closed"] is False
    assert report["schedule_attestation_verified"] is False
    assert report["closure_blockers"] == ["schedule_attestation_missing"]
    with pytest.raises(ValueError, match="not closed"):
        production_day_review_event(report)


@pytest.mark.parametrize(
    ("omit", "running", "blocker"),
    [(0, None, "expected_run_missing"), (None, 0, "expected_run_nonterminal")],
)
def test_missing_or_nonterminal_expected_run_cannot_close_day(
        tmp_path, omit, running, blocker):
    runs = tmp_path / "runs"
    _terminal_runs(runs, Domain.AU, omit=omit, running=running)

    report = inspect_production_day(
        run_root=runs,
        attestation_path=_attestation(tmp_path, Domain.AU),
        domain=Domain.AU,
        production_day=DAY,
        as_of=AS_OF,
    )

    assert report["production_day_closed"] is False
    assert blocker in report["closure_blockers"]
    assert report["counts"]["missing" if omit is not None else "nonterminal"] == 1


def test_attestation_cannot_omit_a_declarative_expected_run(tmp_path):
    path = _attestation(tmp_path, Domain.AU)
    payload = json.loads(path.read_text())
    payload["expected_runs"].pop()
    payload.pop("content_hash")
    payload["content_hash"] = _hash(payload)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="expected schedule"):
        inspect_production_day(
            run_root=tmp_path / "runs",
            attestation_path=path,
            domain=Domain.AU,
            production_day=DAY,
            as_of=AS_OF,
        )


def test_rehashed_run_with_wrong_identity_or_future_completion_fails_closed(tmp_path):
    runs = tmp_path / "runs"
    expected = _terminal_runs(runs, Domain.AU)
    identity = RunIdentity(
        Domain.AU,
        expected[0]["mode"],
        date.fromisoformat(expected[0]["target_date"]),
        expected[0]["scheduled_slot"],
    )
    path = manifest_path(runs, identity)
    payload = json.loads(path.read_text())
    payload["completed_at"] = (AS_OF + timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="chronology"):
        inspect_production_day(
            run_root=runs,
            attestation_path=_attestation(tmp_path, Domain.AU),
            domain=Domain.AU,
            production_day=DAY,
            as_of=AS_OF,
        )


def test_rehashed_report_cannot_forge_expected_run_identity_without_source_recheck(tmp_path):
    runs = tmp_path / "runs"
    _terminal_runs(runs, Domain.AU)
    attestation = _attestation(tmp_path, Domain.AU)
    report = inspect_production_day(
        run_root=runs,
        attestation_path=attestation,
        domain=Domain.AU,
        production_day=DAY,
        as_of=AS_OF,
    )
    report["runs"][0]["run_identity"] = "forged"
    report.pop("content_hash")
    report["content_hash"] = _hash(report)

    with pytest.raises(ValueError, match="row"):
        verify_production_day_evidence(
            report,
            run_root=runs,
            attestation_path=attestation,
            domain=Domain.AU,
            production_day=DAY,
            as_of=AS_OF,
        )


def test_rehashed_report_cannot_omit_expected_run_without_source_recheck(tmp_path):
    runs = tmp_path / "runs"
    _terminal_runs(runs, Domain.AU)
    attestation = _attestation(tmp_path, Domain.AU)
    report = inspect_production_day(
        run_root=runs,
        attestation_path=attestation,
        domain=Domain.AU,
        production_day=DAY,
        as_of=AS_OF,
    )
    report["runs"].pop()
    report["counts"]["expected"] -= 1
    report["counts"]["terminal"] -= 1
    report["counts"]["succeeded"] -= 1
    report.pop("content_hash")
    report["content_hash"] = _hash(report)

    with pytest.raises(ValueError, match="row"):
        verify_production_day_evidence(
            report,
            run_root=runs,
            attestation_path=attestation,
            domain=Domain.AU,
            production_day=DAY,
            as_of=AS_OF,
        )


def test_rehashed_report_cannot_hide_terminal_failure_health(tmp_path):
    runs = tmp_path / "runs"
    _terminal_runs(runs, Domain.AU, failed=0)
    attestation = _attestation(tmp_path, Domain.AU)
    report = inspect_production_day(
        run_root=runs,
        attestation_path=attestation,
        domain=Domain.AU,
        production_day=DAY,
        as_of=AS_OF,
    )
    report["operational_health"] = "healthy"
    report.pop("content_hash")
    report["content_hash"] = _hash(report)

    with pytest.raises(ValueError, match="health"):
        verify_production_day_evidence(
            report,
            run_root=runs,
            attestation_path=attestation,
            domain=Domain.AU,
            production_day=DAY,
            as_of=AS_OF,
        )


def test_sydney_fall_back_identity_collision_is_explicit_and_never_closes(tmp_path):
    fall_back = date(2026, 4, 5)
    schedule = production_day_schedule(Domain.HKJC, fall_back)

    assert schedule["identity_collisions"]
    report = inspect_production_day(
        run_root=tmp_path / "runs",
        attestation_path=None,
        domain=Domain.HKJC,
        production_day=fall_back,
        as_of=datetime(2026, 4, 6, 0, 0, tzinfo=timezone.utc),
    )
    assert report["production_day_closed"] is False
    assert "schedule_identity_collision" in report["closure_blockers"]
