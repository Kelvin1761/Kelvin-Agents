from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import record_settlement_for_event
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_tennis_monitoring_samples import (
    inspect_tennis_monitoring_samples,
    monitoring_sample_snapshots,
    verify_tennis_monitoring_sample_report,
)
from test_research_tennis_feature_provenance import fixture as feature_fixture
from test_research_tennis_settlement_source import END, EVENT, outcome_file


def settled_source(tmp_path, *, cohort=True, cohort_mode="valid", feature_mode="valid"):
    evidence, snapshot = feature_fixture(
        tmp_path, mode=feature_mode, include_cohort=cohort,
        cohort_mode=cohort_mode,
    )
    day = snapshot.parents[1]
    outcome, raw_result = outcome_file(day)
    record_settlement_for_event(
        domain=Domain.TENNIS,
        event_id=EVENT,
        evidence_root=evidence,
        summary={"settled": 1, "pending_without_result": 0},
        artifacts=[outcome, raw_result],
        settled_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        required=True,
    )
    return evidence, snapshot, outcome


def test_verified_pit_outcome_emits_one_family_specific_sample(tmp_path):
    evidence, _snapshot, _outcome = settled_source(tmp_path)
    report = inspect_tennis_monitoring_samples(root=evidence, as_of=END)
    samples = monitoring_sample_snapshots(report)

    assert report["qualified_predictions"] == 1
    assert report["blocked_settlements"] == 0
    assert len(samples) == 1
    assert samples[0].domain is Domain.TENNIS
    assert samples[0].scope == "match_winner_atp"
    assert samples[0].basis == "verified_pit_outcomes"
    assert samples[0].unit_ids == frozenset({report["units"][0]["unit_id"]})
    assert report["terminal_labels_emitted"] is False
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize(
    ("cohort", "cohort_mode", "feature_mode", "blocker"),
    [
        (False, "valid", "valid", "cohort_artifact_missing"),
        (True, "family", "valid", "cohort_family_invalid"),
        (True, "valid", "future", "feature_availability_unverified"),
    ],
)
def test_missing_or_unverified_family_and_pit_inputs_never_make_sample(
        tmp_path, cohort, cohort_mode, feature_mode, blocker):
    evidence, _snapshot, _outcome = settled_source(
        tmp_path, cohort=cohort, cohort_mode=cohort_mode,
        feature_mode=feature_mode,
    )
    report = inspect_tennis_monitoring_samples(root=evidence, as_of=END)
    assert blocker in report["candidates"][0]["blockers"]
    assert report["units"] == []
    assert monitoring_sample_snapshots(report) == ()


def test_rehashed_family_or_sample_identity_is_rebuilt_from_source(tmp_path):
    evidence, _snapshot, _outcome = settled_source(tmp_path)
    report = inspect_tennis_monitoring_samples(root=evidence, as_of=END)
    report["units"][0]["family"] = "match_winner_wta"
    report["content_hash"] = _hash({
        key: value for key, value in report.items() if key != "content_hash"
    })
    with pytest.raises((ValueError, RuntimeError)):
        verify_tennis_monitoring_sample_report(
            report, root=evidence, as_of=END,
        )


def test_no_settlement_is_empty_not_a_healthy_family_baseline(tmp_path):
    evidence, _snapshot = feature_fixture(
        tmp_path, include_cohort=True,
    )
    report = inspect_tennis_monitoring_samples(root=evidence, as_of=END)
    assert report["candidate_settlements"] == 0
    assert report["verified_monitoring_samples"] == 0
    assert report["source_coverage_complete"] is False
    assert monitoring_sample_snapshots(report) == ()
