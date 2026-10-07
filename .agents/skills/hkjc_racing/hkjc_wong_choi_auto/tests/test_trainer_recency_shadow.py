from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine import engine_core  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402
from hkjc_racing_engine.scoring import MATRIX_WEIGHTS, to_display_scale  # noqa: E402


def _base_auto() -> dict:
    features = {
        "jockey_score": 60.0,
        "trainer_score": 60.0,
    }
    matrix = {key: 60.0 for key in MATRIX_WEIGHTS}
    return {
        "feature_scores": features,
        "matrix_scores": matrix,
        "ability_score_raw": 60.0,
        "ability_score": round(to_display_scale(60.0), 2),
        "trainer_signal_detail": {
            "trainer_base": 60.0,
            "trainer_final": 60.0,
        },
    }


def _rating() -> dict:
    return {
        "score": 70.0,
        "starts": 25.0,
        "win_rate": 15.0,
        "place_rate": 38.0,
        "as_of_date": "2026-10-10",
        "latest_result_date": "2026-10-04",
        "half_life_days": 90,
    }


def test_trainer_recency_shadow_changes_only_trainer_signal() -> None:
    engine = RacingEngine(
        {"trainer": "測試練馬師", "_data": {}},
        {"venue": "沙田", "track": "Turf", "race_date": "2026-10-10"},
    )
    with mock.patch.object(engine_core, "get_recency_trainer_rating", return_value=_rating()):
        shadow = engine.build_shadow_profile("trainer_recency_st_early90", _base_auto())

    assert shadow["applied"] is True
    assert shadow["trainer_candidate_score"] == 70.0
    assert shadow["matrix_scores"]["trainer_signal"] == 64.5
    for dimension in MATRIX_WEIGHTS:
        if dimension != "trainer_signal":
            assert shadow["matrix_scores"][dimension] == 60.0


def test_trainer_recency_shadow_is_noop_outside_frozen_scope() -> None:
    contexts = (
        {"venue": "沙田AWT", "race_date": "2026-10-10"},
        {"venue": "跑馬地", "track": "Turf", "race_date": "2026-10-10"},
        {"venue": "沙田", "track": "Turf", "race_date": "2027-01-10"},
    )
    for context in contexts:
        engine = RacingEngine({"trainer": "測試練馬師", "_data": {}}, context)
        with mock.patch.object(engine_core, "get_recency_trainer_rating", return_value=_rating()) as lookup:
            shadow = engine.build_shadow_profile("trainer_recency_st_early90", _base_auto())
        assert shadow["applied"] is False
        assert shadow["ability_delta"] == 0.0
        lookup.assert_not_called()

    debut = RacingEngine(
        {"trainer": "測試練馬師", "is_debut": True, "_data": {}},
        {"venue": "沙田", "track": "Turf", "race_date": "2026-10-10"},
    )
    with mock.patch.object(engine_core, "get_recency_trainer_rating", return_value=_rating()) as lookup:
        shadow = debut.build_shadow_profile("trainer_recency_st_early90", _base_auto())
    assert shadow["applied"] is False
    lookup.assert_not_called()
