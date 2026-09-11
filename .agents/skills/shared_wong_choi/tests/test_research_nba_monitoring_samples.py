from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_nba_monitoring_samples import (
    inspect_nba_monitoring_samples,
    monitoring_sample_snapshot,
    verify_nba_monitoring_sample_report,
)
from test_research_nba_settlement_source import END, settled_fixture


def settled_source(tmp_path):
    return settled_fixture(tmp_path, research_projection=True)


def test_exact_forward_recommendation_feature_and_result_join_makes_one_sample(tmp_path):
    evidence, _day, _snapshot, _verification = settled_source(tmp_path)
    report = inspect_nba_monitoring_samples(root=evidence, as_of=END)
    sample = monitoring_sample_snapshot(report)

    assert report["candidate_settlements"] == 1
    assert report["qualified_recommendations"] == 1
    assert report["blocked_settlements"] == 0
    assert sample.domain is Domain.NBA
    assert sample.scope == "all"
    assert sample.basis == "forward_settled_recommendations"
    assert sample.unit_ids == frozenset({report["units"][0]["unit_id"]})
    assert report["terminal_labels_emitted"] is False
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize(
    ("fault", "blocker"),
    [
        ("missing_projection", "recommendation_projection_missing"),
        ("changed_identity", "recommendation_result_mismatch"),
        ("extra_result", "recommendation_result_mismatch"),
    ],
)
def test_unbound_or_inexact_recommendation_result_never_becomes_sample(
        tmp_path, fault, blocker):
    projection_mode = "missing" if fault == "missing_projection" else True
    result_fault = {"changed_identity": "different_line", "extra_result": "extra"}.get(fault)
    evidence, _day, _snapshot, _verification = settled_fixture(
        tmp_path, research_projection=projection_mode, fault=result_fault,
    )
    report = inspect_nba_monitoring_samples(root=evidence, as_of=END)
    assert blocker in report["candidates"][0]["blockers"]
    assert report["units"] == []


def test_existing_game_level_prediction_without_recommendation_projection_is_zero(tmp_path):
    evidence, _day, _snapshot, _verification = settled_fixture(tmp_path)
    report = inspect_nba_monitoring_samples(root=evidence, as_of=END)
    assert report["qualified_recommendations"] == 0
    assert report["units"] == []
    assert report["source_coverage_complete"] is False


def test_parent_rebuild_rejects_rehashed_sample_identity(tmp_path):
    evidence, _day, _snapshot, _verification = settled_fixture(
        tmp_path, research_projection=True,
    )
    report = inspect_nba_monitoring_samples(root=evidence, as_of=END)
    report["units"][0]["unit_id"] += ":forged"
    report["content_hash"] = _hash({
        key: value for key, value in report.items() if key != "content_hash"
    })
    with pytest.raises((ValueError, RuntimeError)):
        verify_nba_monitoring_sample_report(
            report, root=evidence, as_of=END,
        )


def test_no_settlement_is_explicit_empty_not_healthy(tmp_path):
    from test_research_nba_settlement_source import prediction_fixture

    evidence, _day, _snapshot = prediction_fixture(
        tmp_path, research_projection=True,
    )
    report = inspect_nba_monitoring_samples(root=evidence, as_of=END)
    assert report["candidate_settlements"] == 0
    assert report["verified_monitoring_samples"] == 0
    assert report["source_coverage_complete"] is False
