from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.evaluation_rulers import (  # noqa: E402
    DEFAULT_RULER_ROOT,
    load_evaluation_ruler,
)
from shared_wong_choi.research_drift_readiness import (  # noqa: E402
    build_drift_readiness,
    verify_drift_readiness,
)
from shared_wong_choi.research_index import _hash  # noqa: E402


NOW = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)


def test_all_domains_project_only_frozen_drift_inputs() -> None:
    for domain in Domain:
        ruler = load_evaluation_ruler(domain)
        report = build_drift_readiness(domain=domain, as_of=NOW)

        assert report["domain"] == domain.value
        assert report["ruler_id"] == ruler.ruler_id
        assert report["model_release_id"] == ruler.model_release_id
        assert report["metric_inputs"] == [
            {
                "name": item["name"],
                "role": item["role"],
                "direction": item["direction"],
            }
            for item in ruler.metrics
        ]
        assert report["cohort_inputs"] == list(ruler.cohorts)
        assert report["review_cadence"] == ruler.review
        assert report["contract_status"] == "blocked_missing_frozen_drift_contract"
        assert report["comparison_window"] is None
        assert report["minimum_drift_samples"] is None
        assert report["decision_thresholds"] is None
        assert report["metric_drift_verified"] is False
        assert report["market_drift_verified"] is False
        assert report["model_promotion_allowed"] is False


def test_market_requirement_follows_ruler_without_inventing_market_authority() -> None:
    for domain in (Domain.AU, Domain.HKJC):
        report = build_drift_readiness(domain=domain, as_of=NOW)
        market = report["market_input"]
        assert market == {
            "status": "not_required_by_ruler",
            "price_snapshot_policy": None,
            "required_source_fields": [],
        }
        assert report["unresolved_contract_fields"] == [
            "comparison_window",
            "minimum_drift_samples",
            "metric_drift_decision_thresholds",
            "producer_artifact_schema",
        ]

    expected = {
        Domain.TENNIS: "earliest_verifiable_pre_match",
        Domain.NBA: "immutable_role_specific_pre_game",
    }
    for domain, policy in expected.items():
        market = build_drift_readiness(domain=domain, as_of=NOW)["market_input"]
        assert market == {
            "status": "source_contract_required",
            "price_snapshot_policy": policy,
            "required_source_fields": [
                "market_identity",
                "selection_identity",
                "captured_at",
                "offered_price",
                "no_vig_methodology",
                "source_artifact_digest",
            ],
        }


def test_readiness_lists_unresolved_authority_instead_of_guessing_thresholds() -> None:
    report = build_drift_readiness(domain=Domain.TENNIS, as_of=NOW)

    assert report["unresolved_contract_fields"] == [
        "comparison_window",
        "minimum_drift_samples",
        "metric_drift_decision_thresholds",
        "market_distribution_fields",
        "market_drift_decision_thresholds",
        "producer_artifact_schema",
    ]
    assert report["source_reverification_required"] is True
    assert report["descriptive_projection_allowed"] is False
    assert "candidate" not in json.dumps(report, sort_keys=True).lower()


def test_rehashed_forgery_cannot_turn_contract_gap_into_verified_drift() -> None:
    report = build_drift_readiness(domain=Domain.NBA, as_of=NOW)
    report["contract_status"] = "ready"
    report["metric_drift_verified"] = True
    report["content_hash"] = _hash(
        {key: value for key, value in report.items() if key != "content_hash"}
    )

    with pytest.raises(ValueError, match="readiness projection differs"):
        verify_drift_readiness(report, domain=Domain.NBA, as_of=NOW)


def test_current_ruler_mutation_invalidates_previous_readiness(tmp_path: Path) -> None:
    ruler_root = tmp_path / "rulers"
    shutil.copytree(DEFAULT_RULER_ROOT, ruler_root)
    report = build_drift_readiness(
        domain=Domain.AU, as_of=NOW, ruler_root=ruler_root,
    )
    path = ruler_root / "au-v2.json"
    payload = json.loads(path.read_text())
    payload["metrics"][0]["direction"] = "minimize"
    path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(ValueError, match="frozen ruler changed"):
        verify_drift_readiness(
            report, domain=Domain.AU, as_of=NOW, ruler_root=ruler_root,
        )


@pytest.mark.parametrize("value", ["2026-09-05T03:00:00", "not-a-time"])
def test_readiness_rejects_unbounded_time(value: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_drift_readiness(domain=Domain.AU, as_of=value)


def test_equivalent_time_offsets_produce_the_same_projection() -> None:
    utc = build_drift_readiness(
        domain=Domain.HKJC, as_of="2026-09-05T03:00:00+00:00",
    )
    sydney = build_drift_readiness(
        domain=Domain.HKJC, as_of="2026-09-05T13:00:00+10:00",
    )

    assert utc == sydney
