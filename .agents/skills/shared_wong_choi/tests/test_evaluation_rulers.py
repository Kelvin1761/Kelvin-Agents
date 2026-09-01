from __future__ import annotations

import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.evaluation_rulers import (  # noqa: E402
    RulerValidationError,
    load_evaluation_ruler,
    validate_release_separation,
)


def test_all_domains_have_frozen_versioned_rulers() -> None:
    expected_versions = {
        Domain.AU: "au-v2",
        Domain.HKJC: "hkjc-v2",
        Domain.TENNIS: "tennis-v1",
        Domain.NBA: "nba-v1",
    }
    expected_stages = {
        Domain.AU: "production",
        Domain.HKJC: "production",
        Domain.TENNIS: "shadow",
        Domain.NBA: "shadow",
    }

    for domain, version in expected_versions.items():
        ruler = load_evaluation_ruler(domain)
        assert ruler.schema_version == "wong-choi-evaluation-ruler/v1"
        assert ruler.ruler_id == version
        assert ruler.domain is domain
        assert ruler.status == "frozen"
        assert ruler.platform_baseline_commit == "6c1528c08585ba2185c1d5e04344db87095245a9"
        assert ruler.model_baseline_commit == "8b149c85aafa96d199eb838241d9a4958ec5d9b6"
        assert ruler.model_release_id.startswith(f"wc:{domain.value}:model-release:")
        assert ruler.model_stage == expected_stages[domain]
        assert {case["expected"] for case in ruler.fixture_cases} == {
            "win",
            "regression",
            "noise",
        }


def test_horse_rulers_protect_gold_good_and_support_ranking_path() -> None:
    for domain in (Domain.AU, Domain.HKJC):
        ruler = load_evaluation_ruler(domain)
        assert ruler.metric_names("primary") == {"gold", "good_positional"}
        assert {
            "top3_capture_at5",
            "mean_top3_model_rank",
            "competitive_recall_at5",
            "ndcg_at5",
            "top5_pairwise_auc",
        }.issubset(ruler.metric_names("ranking"))
        assert {"field_size", "venue", "going"}.issubset(set(ruler.cohorts))
        assert ruler.sample_policy["monitoring_increment"] == 50


def test_tennis_ruler_is_point_in_time_family_specific_and_market_relative() -> None:
    ruler = load_evaluation_ruler(Domain.TENNIS)

    assert ruler.point_in_time_required is True
    assert ruler.family_specific is True
    assert ruler.price_snapshot_policy == "earliest_verifiable_pre_match"
    assert {"brier_gain_vs_market", "log_loss_gain_vs_market"}.issubset(
        ruler.metric_names("primary")
    )
    assert {"calibration_error", "clv", "roi", "coverage"}.issubset(
        ruler.metric_names("guardrail")
    )
    assert ruler.sample_policy == {
        "mode": "family_floor_plus_power",
        "monitoring_increment": 200,
        "promotion_floor": 600,
        "power_required": True,
    }


def test_nba_ruler_cannot_promote_before_forward_live_gate() -> None:
    ruler = load_evaluation_ruler(Domain.NBA)

    assert ruler.decision_mode == "descriptive_only"
    assert ruler.promotion_allowed is False
    assert ruler.sample_policy["initial_live_gate"] == 30
    assert ruler.sample_policy["monitoring_increment_after_gate"] == 100
    assert ruler.sample_policy["promotion_floor"] is None
    assert {"season_phase", "market_family", "odds_bucket", "injury_freshness"}.issubset(
        set(ruler.cohorts)
    )


def test_review_cadence_is_machine_readable() -> None:
    for domain in Domain:
        review = load_evaluation_ruler(domain).review
        assert review["weekly"] == {"weekday": "monday", "time": "09:00", "timezone": "Australia/Sydney"}
        assert review["monthly"] == {"ordinal_week": 1, "weekday": "monday"}
        assert review["ruler_review_days"] == 90
        assert review["incident_freezes_queue"] is True


def test_ruler_and_candidate_change_in_same_release_fails_closed() -> None:
    with pytest.raises(RulerValidationError, match="separate release"):
        validate_release_separation(
            ruler_changed=True,
            candidate_model_changed=True,
        )

    validate_release_separation(ruler_changed=True, candidate_model_changed=False)
    validate_release_separation(ruler_changed=False, candidate_model_changed=True)
