from __future__ import annotations

import sys
from pathlib import Path


SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHARED))

from model_evaluation_decision import (  # noqa: E402
    CandidateVerdict,
    EvaluationInput,
    MetricEvidence,
    build_evaluation_input,
    evaluate_candidate,
)


def metric(dev=0.0, terminal=0.0, low=0.0, high=0.0, *, higher=True):
    return MetricEvidence(dev, terminal, low, high, higher)


def candidate(**changes) -> EvaluationInput:
    values = {
        "domain": "au",
        "baseline_sample_hash": "same",
        "candidate_sample_hash": "same",
        "baseline_races": 1000,
        "candidate_races": 1000,
        "holdout_locked": True,
        "leakage_audit_passed": True,
        "primary": {
            "gold": metric(),
            "good_positional": metric(),
        },
        "ranking": {
            "top3_capture_at5": metric(0.01, 0.01, 0.002, 0.018),
            "mean_top3_model_rank": metric(-0.04, -0.03, -0.05, -0.01, higher=False),
        },
    }
    values.update(changes)
    return EvaluationInput(**values)


def test_gold_or_good_supported_gain_is_primary_win():
    result = evaluate_candidate(
        candidate(
            primary={
                "gold": metric(0.01, 0.02, 0.003, 0.037),
                "good_positional": metric(),
            }
        )
    )
    assert result["verdict"] == CandidateVerdict.PRIMARY_WIN.value


def test_primary_neutral_supported_ranking_gain_is_ranking_win():
    result = evaluate_candidate(candidate())
    assert result["verdict"] == CandidateVerdict.RANKING_WIN.value
    assert "top3_capture_at5" in result["detail"]["ci_supported_metrics"]


def test_lower_mean_model_rank_is_interpreted_as_improvement():
    result = evaluate_candidate(candidate())
    assert result["verdict"] == CandidateVerdict.RANKING_WIN.value
    assert "mean_top3_model_rank" in result["detail"]["positive_metrics"]


def test_any_primary_regression_rejects_ranking_gain():
    result = evaluate_candidate(
        candidate(
            primary={
                "gold": metric(-0.001, 0.0, -0.01, 0.01),
                "good_positional": metric(),
            }
        )
    )
    assert result["verdict"] == CandidateVerdict.REJECT.value
    assert result["reason"] == "primary_regression"


def test_ranking_gain_needs_two_positive_metrics_and_one_supported_ci():
    result = evaluate_candidate(
        candidate(
            ranking={
                "top3_capture_at5": metric(0.01, 0.01, -0.01, 0.03),
                "ndcg_at5": metric(0.0, 0.0, -0.01, 0.01),
            }
        )
    )
    assert result["verdict"] == CandidateVerdict.REJECT.value
    assert result["reason"] == "ranking_evidence_too_weak"


def test_holdout_or_sample_mutation_fails_closed():
    assert evaluate_candidate(candidate(holdout_locked=False))["reason"] == "holdout_not_locked"
    assert (
        evaluate_candidate(candidate(candidate_sample_hash="different"))["reason"]
        == "sample_hash_changed"
    )


def test_hkjc_uses_same_canonical_gold_and_positional_good_names():
    result = evaluate_candidate(candidate(domain="hkjc"))
    assert result["verdict"] == CandidateVerdict.RANKING_WIN.value


def test_unregistered_metric_cannot_be_cherry_picked():
    result = evaluate_candidate(
        candidate(
            ranking={
                "top3_capture_at5": metric(0.01, 0.01, 0.001, 0.02),
                "metric_invented_after_holdout": metric(1, 1, 1, 1),
            }
        )
    )
    assert result["reason"] == "unregistered_ranking_metric"


def test_builder_locks_whole_dates_and_builds_paired_primary_evidence():
    dates = ["2026-01-01"] * 4 + ["2026-01-02"] * 4
    baseline = [
        {"gold": False, "good_positional": False, "top3_capture_at5": 0.5,
         "ndcg_at5": 0.5}
        for _ in dates
    ]
    candidate_rows = [dict(row) for row in baseline]
    for row in candidate_rows:
        row.update({"gold": True, "top3_capture_at5": 0.8, "ndcg_at5": 0.8})
    built = build_evaluation_input(
        domain="au",
        dates=dates,
        baseline_rows=baseline,
        candidate_rows=candidate_rows,
        leakage_audit_passed=True,
        ranking_metrics=("top3_capture_at5", "ndcg_at5"),
    )
    assert built.holdout_locked is True
    assert built.primary["gold"].terminal_delta == 1.0
    assert built.primary["gold"].terminal_ci_low == 1.0
    assert evaluate_candidate(built)["verdict"] == CandidateVerdict.PRIMARY_WIN.value


def test_builder_rejects_changed_holdout_and_missing_leakage_audit():
    rows = [
        {"gold": False, "good_positional": False, "top3_capture_at5": 0.5,
         "ndcg_at5": 0.5}
        for _ in range(10)
    ]
    built = build_evaluation_input(
        domain="hkjc",
        dates=[f"2026-01-{index + 1:02d}" for index in range(10)],
        baseline_rows=rows,
        candidate_rows=rows,
        leakage_audit_passed=False,
        holdout_fraction=0.2,
        ranking_metrics=("top3_capture_at5", "ndcg_at5"),
    )
    assert evaluate_candidate(built)["reason"] == "holdout_not_locked"
