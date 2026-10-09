"""The shadow backbone is priced beside production and must never move it."""
from __future__ import annotations

import math

from tennis_wc.features.elo import elo_probability
from tennis_wc.modelling import probability_model as pm


def _point(value):
    return {"value": value, "provenance": {"source_provider": "test", "warnings": []}}


def _snapshot(shadow=None):
    player = lambda overall, surface: {"overall_elo": _point(overall), "surface_elo": _point(surface)}
    snap = {
        "match_context": {"surface": {"value": "hard"}},
        "player_a": player(1700.0, 1720.0),
        "player_b": player(1600.0, 1580.0),
    }
    if shadow is not None:
        snap["shadow_backbone"] = shadow
    return snap


SHADOW = {
    "surface": "hard",
    "player_a": {"overall": 1710.0, "surface": 1735.0},
    "player_b": {"overall": 1590.0, "surface": None},
}


def test_production_probability_is_identical_with_and_without_the_shadow():
    without = pm.predict_match_probability(_snapshot())
    with_shadow = pm.predict_match_probability(_snapshot(SHADOW))
    for key in ("player_a_probability", "elo_base_logit", "total_nudge_logit", "components"):
        assert without[key] == with_shadow[key]
    assert without["shadow"] is None


def test_shadow_uses_its_own_ratings_weight_and_the_production_nudge():
    out = pm.predict_match_probability(_snapshot(SHADOW))
    shadow = out["shadow"]
    assert shadow["version"] == pm.SHADOW_BACKBONE_VERSION
    logit = lambda p: math.log(p / (1 - p))
    p_over = elo_probability(1710.0, 1590.0)
    p_surf = elo_probability(1735.0, 1590.0)   # missing surface -> overall
    base = pm.SHADOW_SURFACE_WEIGHT * logit(p_surf) + (1 - pm.SHADOW_SURFACE_WEIGHT) * logit(p_over)
    assert abs(shadow["elo_base_logit"] - base) < 1e-5
    expected = 1 / (1 + math.exp(-(base + out["total_nudge_logit"])))
    assert abs(shadow["player_a_probability"] - min(max(expected, 0.02), 0.98)) < 1e-5


def test_shadow_is_absent_when_a_player_has_no_start_of_day_rating():
    shadow = {**SHADOW, "player_b": {"overall": None, "surface": None}}
    assert pm.predict_match_probability(_snapshot(shadow))["shadow"] is None


def test_a_malformed_shadow_never_raises():
    assert pm.predict_match_probability(_snapshot({"player_a": "nonsense"}))["shadow"] is None
