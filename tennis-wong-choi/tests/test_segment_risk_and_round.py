from __future__ import annotations

from tennis_wc.betting.segment_risk import apply_segment_risk, segment_risk
from tennis_wc.modelling.pricing import price_match_snapshot
from tennis_wc.modelling.probability_model import predict_match_probability


def _player(surface_elo, overall_elo, rank, round_rate):
    return {
        "name": f"P{rank}",
        "id": {"value": rank},
        "surface_elo": {"value": surface_elo},
        "overall_elo": {"value": overall_elo},
        "current_rank": {"value": rank},
        "tournament_level_stats": {},
        "opponent_rank_buckets": {},
        "round_stats": {"shrinked_win_rate": {"value": round_rate}},
        "big_match_stats": {},
    }


def _snapshot(level, round_value, odds_a=1.50, odds_b=2.70):
    return {
        # Strong round signal for A (0.80) vs B (0.20) so an ACTIVE round
        # component would visibly move the probability.
        "player_a": _player(1900, 1880, 20, 0.80),
        "player_b": _player(1800, 1810, 48, 0.20),
        "match_context": {
            "tour": {"value": "WTA"},
            "level": {"value": level},
            "round": {"value": round_value},
        },
        "market": {"player_a_odds": {"value": odds_a}, "player_b_odds": {"value": odds_b}},
    }


# --- Bug 1: round feature must be neutralised when round metadata is unconfirmed ---

def test_round_component_neutralised_when_round_unknown():
    result = predict_match_probability(_snapshot("WTA_500", "UNKNOWN"))
    comp = next(c for c in result["components"] if c["name"] == "round_performance_edge")
    assert comp["active"] is False
    assert "round_unknown" in comp["warnings"]


def test_round_component_active_when_round_confirmed():
    result = predict_match_probability(_snapshot("WTA_500", "R32"))
    comp = next(c for c in result["components"] if c["name"] == "round_performance_edge")
    assert comp["active"] is True


def test_unknown_round_does_not_inflate_probability():
    # The strong (0.80 vs 0.20) round split must not push the price when the
    # round is UNKNOWN — the heuristic bucket is noise, not signal.
    p_unknown = predict_match_probability(_snapshot("WTA_500", "UNKNOWN"))["player_a_probability"]
    p_known = predict_match_probability(_snapshot("WTA_500", "R32"))["player_a_probability"]
    assert p_known > p_unknown


# --- Bug 2: segment risk applied once, at pricing time ---

def test_segment_shrink_applied_for_wta_250():
    label, discount = segment_risk("WTA", "WTA_250")
    assert discount == 0.05 and label == "中波動(250)"
    priced = price_match_snapshot(_snapshot("WTA_250", "R32"))
    assert priced["segment_risk_discount"] == 0.05
    # Shrunk model prob must sit strictly between the raw prob and the market.
    no_vig = priced["no_vig_market_probability"]
    assert no_vig < priced["model_probability"] < 0.999


def test_no_shrink_for_premium_levels():
    priced = price_match_snapshot(_snapshot("WTA_500", "R32"))
    assert priced["segment_risk_discount"] == 0.0
    assert priced["segment_risk_label"] == ""


def test_apply_segment_risk_is_noop_without_market():
    prob, edge = apply_segment_risk(0.80, 0.15, None, 0.05)
    assert prob == 0.80 and edge == 0.15


def test_apply_segment_risk_shrinks_toward_market():
    prob, edge = apply_segment_risk(0.80, 0.20, 0.60, 0.10)
    # 0.60 + (0.80 - 0.60) * 0.90 = 0.78 ; edge 0.20 * 0.90 = 0.18
    assert abs(prob - 0.78) < 1e-9
    assert abs(edge - 0.18) < 1e-9
