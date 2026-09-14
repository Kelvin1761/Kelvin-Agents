from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".agents" / "skills"))

from shared_wong_choi.research_tennis_feature_provenance import _projection
from tennis_wc.research_evidence import build_prediction_artifacts


EVENT = "2026-09-01"
CUTOFF = datetime(2026, 8, 31, 23, tzinfo=timezone.utc)
COMPONENTS = (
    "surface_elo_edge", "overall_elo_edge", "serve_return_edge",
    "recent_form_edge", "opponent_rank_bucket_edge", "tournament_level_edge",
    "round_performance_edge", "big_match_edge", "pressure_edge",
    "head_to_head_edge", "fatigue_edge",
)


def _point(value, raw_id=901, *, at="2026-08-31T22:00:00+00:00"):
    provider = "sportsbet" if raw_id == 902 else "tennismylife"
    endpoint = "/odds" if raw_id == 902 else "/ratings"
    return {
        "value": value,
        "provenance": {
            "source_provider": provider,
            "source_endpoint": endpoint,
            "source_timestamp": at,
            "calculated_at": "2026-08-31T22:30:00+00:00",
            "raw_response_id": raw_id,
            "warnings": [],
        },
    }


def _snapshot():
    return {
        "match_id": _point(501),
        "feature_set_version": "stage3.v1",
        "player_a": {"id": _point(11), "surface_elo": _point(1650)},
        "player_b": {"id": _point(22), "surface_elo": _point(1550)},
        "match_context": {"tour": _point("ATP"), "level": _point("ATP 250")},
        "market": {
            "player_a_odds": _point(1.8, 902),
            "player_b_odds": _point(2.1, 902),
        },
        "entity_mapping_complete": True,
    }


def _pricing():
    return {
        "selection_player_id": 11,
        "model_probability": 0.62,
        "no_vig_market_probability": 0.54,
        "current_market_odds": 1.8,
        "edge": 0.08,
        "model": {
            "components": [
                {
                    "name": name,
                    "probability": 0.62 if name == "surface_elo_edge" else 0.5,
                    "weight": 0.65 if name == "surface_elo_edge" else 0.1,
                    "active": name == "surface_elo_edge",
                    "reason": "verified" if name == "surface_elo_edge" else "neutral",
                    "warnings": [] if name == "surface_elo_edge" else ["neutral_fixture"],
                }
                for name in COMPONENTS
            ]
        },
    }


def _raws():
    return {
        901: {
            "id": 901,
            "provider_name": "tennismylife",
            "endpoint": "/ratings",
            "response_json": json.dumps({"ratings": [1650, 1550], "tour": "ATP"}),
            "fetched_at": "2026-08-31T22:00:00+00:00",
            "created_at": "2026-08-31T22:00:01+00:00",
        },
        902: {
            "id": 902,
            "provider_name": "sportsbet",
            "endpoint": "/odds",
            "response_json": json.dumps({"player_a_odds": 1.8, "player_b_odds": 2.1}),
            "fetched_at": "2026-08-31T22:00:00+00:00",
            "created_at": "2026-08-31T22:00:01+00:00",
        },
    }


def _observation(snapshot=None, pricing=None):
    return {
        "prediction_id": 101,
        "prediction_created_at": "2026-08-31T22:30:00+00:00",
        "snapshot": snapshot or _snapshot(),
        "pricing": pricing or _pricing(),
    }


def test_builds_consumer_verified_feature_and_raw_artifacts() -> None:
    artifacts = build_prediction_artifacts(
        event_id=EVENT,
        captured_at=CUTOFF,
        observations=[_observation()],
        raw_responses=_raws(),
    )

    feature_name = f"Tennis_Feature_Evidence_{EVENT}.json"
    assert feature_name in artifacts
    payload = json.loads(artifacts[feature_name])
    raw_artifacts = {
        name: content for name, content in artifacts.items()
        if name.startswith(f"Tennis_Raw_Evidence_{EVENT}_")
    }
    projection, blockers = _projection(
        artifacts[feature_name],
        event_id=EVENT,
        cutoff=CUTOFF,
        recommendations={101: {"id": 101, "edge": 0.08}},
        raw_artifacts=raw_artifacts,
    )

    assert blockers == set()
    assert projection["rows"] == [{
        "prediction_id": 101,
        "active_components": 1,
        "component_inputs": 2,
        "raw_inputs": 2,
        "verified": True,
        "blockers": [],
    }]
    assert payload["rows"][0]["raw_input_ids"] == [901, 902]


def test_output_is_deterministic_and_denies_promotion() -> None:
    kwargs = {
        "event_id": EVENT,
        "captured_at": CUTOFF,
        "observations": [_observation()],
        "raw_responses": _raws(),
    }
    first = build_prediction_artifacts(**kwargs)
    second = build_prediction_artifacts(**kwargs)
    assert first == second
    assert b'"model_promotion_allowed"' not in first[f"Tennis_Feature_Evidence_{EVENT}.json"]


def test_zero_effect_nudge_warning_is_projected_inactive() -> None:
    pricing = _pricing()
    component = next(
        item for item in pricing["model"]["components"]
        if item["name"] == "head_to_head_edge"
    )
    component.update(active=True, probability=0.5, warnings=["low_h2h_sample"])

    artifacts = build_prediction_artifacts(
        event_id=EVENT,
        captured_at=CUTOFF,
        observations=[_observation(pricing=pricing)],
        raw_responses=_raws(),
    )
    payload = json.loads(artifacts[f"Tennis_Feature_Evidence_{EVENT}.json"])
    projected = next(
        item for item in payload["rows"][0]["components"]
        if item["name"] == "head_to_head_edge"
    )
    assert projected == {
        "name": "head_to_head_edge",
        "active": False,
        "warnings": ["low_h2h_sample"],
        "inputs": [],
    }


@pytest.mark.parametrize(
    ("component_name", "probability"),
    [
        ("surface_elo_edge", 0.5),
        ("head_to_head_edge", 0.55),
    ],
)
def test_warning_with_model_effect_remains_blocked(
    component_name: str,
    probability: float,
) -> None:
    pricing = _pricing()
    component = next(
        item for item in pricing["model"]["components"]
        if item["name"] == component_name
    )
    component.update(active=True, probability=probability, warnings=["unresolved"])

    with pytest.raises(ValueError, match="unresolved warnings"):
        build_prediction_artifacts(
            event_id=EVENT,
            captured_at=CUTOFF,
            observations=[_observation(pricing=pricing)],
            raw_responses=_raws(),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_component",
        "active_warning",
        "future_raw",
        "raw_provider",
        "post_prediction_point",
    ],
)
def test_unverifiable_model_or_source_fails_closed(fault: str) -> None:
    pricing, raws, snapshot = _pricing(), _raws(), _snapshot()
    if fault == "unknown_component":
        pricing["model"]["components"][0]["name"] = "new_unmapped_edge"
    elif fault == "active_warning":
        pricing["model"]["components"][0]["warnings"] = ["low_sample"]
    elif fault == "future_raw":
        raws[901]["created_at"] = "2026-09-01T00:00:00+00:00"
    elif fault == "raw_provider":
        raws[901]["provider_name"] = "wrong"
    else:
        snapshot["player_a"]["surface_elo"]["provenance"]["calculated_at"] = (
            "2026-08-31T22:45:00+00:00"
        )

    with pytest.raises(ValueError):
        build_prediction_artifacts(
            event_id=EVENT,
            captured_at=CUTOFF,
            observations=[_observation(snapshot=snapshot, pricing=pricing)],
            raw_responses=raws,
        )


def test_missing_or_unpriced_prediction_is_rejected() -> None:
    pricing = _pricing()
    pricing["selection_player_id"] = None
    pricing["model_probability"] = None
    with pytest.raises(ValueError, match="priced prediction"):
        build_prediction_artifacts(
            event_id=EVENT,
            captured_at=CUTOFF,
            observations=[_observation(pricing=pricing)],
            raw_responses=_raws(),
        )
