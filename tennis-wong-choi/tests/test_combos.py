from __future__ import annotations

import os


def _leg(match_id, name, side, market_key, odds, prob, edge=0.05, conf=80, factors=None):
    from tennis_wc.betting.combos import Leg

    return Leg(
        leg_id=f"{match_id}|{market_key}|{name}",
        match_id=match_id,
        match_label=f"M{match_id}",
        selection_name=name,
        market_key=market_key,
        market_name=market_key,
        selection_side=side,
        line=None,
        decimal_odds=odds,
        model_probability=prob,
        no_vig_probability=1 / odds,
        edge=edge,
        confidence=conf,
        factors=factors or {},
    )


def _set_stake_env():
    os.environ["MAX_STAKE_UNITS"] = "5.0"
    os.environ["MIN_STAKE_UNITS"] = "1.0"
    os.environ["KELLY_FRACTION"] = "0.5"
    os.environ["STAKE_ROUND_INCREMENT"] = "0.5"
    os.environ["DEFAULT_BANKROLL_UNITS"] = "100"


def test_independent_combo_monte_carlo_matches_analytic():
    from tennis_wc.betting.combos import build_combo, monte_carlo_hit

    _set_stake_env()
    a = _leg(1, "A", "player_a", "match_winner", 1.8, 0.62, 0.06)
    b = _leg(2, "B", "player_a", "match_winner", 1.9, 0.60, 0.05)
    combo = build_combo((a, b))
    assert combo is not None
    # Cross-match legs are independent: analytic == naive.
    assert combo["correlation_penalty"] == 0.0
    assert abs(combo["adjusted_hit"] - 0.62 * 0.60) < 1e-6
    # MC (run on demand) should match the analytic independent product.
    mc = monte_carlo_hit((a, b))
    assert abs(mc["mean_hit"] - combo["adjusted_hit"]) < 0.02


def test_negative_ev_combo_is_rejected():
    from tennis_wc.betting.combos import build_combo

    _set_stake_env()
    # Two short-priced legs whose product is -EV.
    a = _leg(1, "A", "player_a", "match_winner", 1.2, 0.55, 0.0)
    b = _leg(2, "B", "player_a", "match_winner", 1.2, 0.55, 0.0)
    assert build_combo((a, b)) is None


def test_same_match_legs_get_correlation_haircut():
    from tennis_wc.betting.combos import correlation_penalty

    a = _leg(5, "E", "player_a", "match_winner", 1.7, 0.66)
    b = _leg(5, "E", "player_a", "to_win_1st_set", 1.9, 0.62)
    # Same match + same player + match/set markets -> meaningful positive correlation.
    assert correlation_penalty((a, b)) > 0.0


def test_opposite_side_same_match_combo_invalid():
    from tennis_wc.betting.combos import build_combo

    _set_stake_env()
    a = _leg(1, "A", "player_a", "match_winner", 2.0, 0.60)
    b = _leg(1, "B", "player_b", "match_winner", 2.0, 0.55)
    assert build_combo((a, b)) is None


def test_tiers_only_emit_positive_ev_combos():
    from tennis_wc.betting.combos import build_combinations, classify_tier

    _set_stake_env()
    legs = [
        _leg(1, "A", "player_a", "match_winner", 1.8, 0.62, 0.06),
        _leg(2, "B", "player_a", "match_winner", 1.9, 0.60, 0.05),
        _leg(3, "C", "player_a", "match_winner", 2.6, 0.46, 0.08),
        _leg(4, "D", "player_a", "match_winner", 3.6, 0.34, 0.10),
    ]
    result = build_combinations(legs, max_legs=3)
    for section in result["tiers"].values():
        for combo in section:
            assert combo["combo_ev"] > 0
            assert combo["stake_units"] >= 1.0


def test_leg_quality_uses_factors_including_pressure():
    from tennis_wc.betting.combos import leg_quality_score

    plain = _leg(1, "A", "player_a", "match_winner", 1.8, 0.60, 0.05)
    with_factors = _leg(
        1, "A", "player_a", "match_winner", 1.8, 0.60, 0.05,
        factors={"pressure_edge": 0.72, "serve_return_edge": 0.66, "surface_elo_edge": 0.68},
    )
    # Strong supporting factors (incl. pressure) raise the leg's quality score.
    assert leg_quality_score(with_factors) > leg_quality_score(plain)
