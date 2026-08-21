from __future__ import annotations

import pytest

from tennis_wc.props import ace_model
from tennis_wc.props.ace_model import AceProfile, PricedAceLeg


def _seed_history(conn, player_id, opponent_id, n, aces, start="2025-01-01"):
    for i in range(n):
        conn.execute(
            """INSERT INTO player_match_history
               (provider_match_id, player_id, opponent_id, tour, match_date,
                tournament_external_id, tournament_level, round, format, won,
                source_provider, raw_response_id, created_at, surface, ace_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"H{player_id}-{i}", player_id, opponent_id, "ATP", f"2025-01-{i+1:02d}",
             "T1", "ATP250", "R1", "BO3", 1, "test", 0, "now", "hard", float(aces)),
        )


def _seed_player(conn, pid, name):
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, name, "ATP", "test", "now", "now"),
    )


def _seed_match(conn, mid, a, b, date="2026-01-01"):
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, f"M{mid}", "ATP", date, 1, a, b, "R1", "test", "now", "now"),
    )


# --------------------------------------------------------------------------- #
# Calibration curve
# --------------------------------------------------------------------------- #
def test_interp_prob_over_monotonic_decreasing_in_line():
    mean = 10.0
    probs = [ace_model.interp_prob_over(line, mean) for line in range(2, 20)]
    assert all(a >= b - 1e-9 for a, b in zip(probs, probs[1:])), "P(over) must fall as line rises"


def test_interp_repairs_non_monotonic_empirical_curve():
    noisy = [(0.5, 0.8), (1.0, 0.4), (1.5, 0.45), (2.0, 0.1)]
    probs = [ace_model.interp_prob_over(line, 10.0, noisy) for line in range(5, 21)]
    assert all(a >= b - 1e-9 for a, b in zip(probs, probs[1:]))


def test_interp_prob_over_clamps_and_bounds():
    assert ace_model.interp_prob_over(0, 10) == 0.0
    assert ace_model.interp_prob_over(10, 0) == 0.0
    # far below range -> near the low-line ceiling; far above -> small positive
    assert ace_model.interp_prob_over(1, 10) >= 0.90
    assert 0.0 < ace_model.interp_prob_over(40, 10) < 0.15


def test_prediction_blends_conceded():
    a = AceProfile(1, 10, 8.0, 8.0, conceded_mean=4.0, serve_estimate=8.0)
    b = AceProfile(2, 10, 6.0, 6.0, conceded_mean=10.0, serve_estimate=6.0)
    mean = ace_model.predict_match_ace_mean(a, b)
    # a serves into b's high concede (10) -> a_pred pulled up; total plausible
    assert 12.0 <= mean <= 16.0


def test_player_ace_exposure_uses_rate_times_expected_service_games():
    player = AceProfile(
        1, 10, 8.0, 8.0, conceded_mean=4.0, serve_estimate=8.0,
        service_games_mean=12.0, ace_rate=0.50, conceded_ace_rate=0.40,
    )
    opponent = AceProfile(
        2, 10, 6.0, 6.0, conceded_mean=10.0, serve_estimate=6.0,
        service_games_mean=12.0, ace_rate=0.30, conceded_ace_rate=0.20,
    )

    # 70% own ace rate + 30% opponent conceded rate, over 12 service games.
    assert ace_model.predict_player_ace_exposure_mean(player, opponent, 12.0) == 4.92


def test_player_ace_negative_binomial_probability_can_feed_the_pricer():
    probability = ace_model.negative_binomial_over_probability(
        line=5.5, mean=6.0, size=3.0,
    )
    priced = ace_model.price_two_way(
        1, "player_aces", "Player A", 5.5, 2.0, 1.8, 6.0,
        ace_model.PLAYER_ACE_CURVE,
        raw_probability_over=probability,
    )

    assert priced is not None
    assert priced.model_prob_over == round(probability, 4)


# --------------------------------------------------------------------------- #
# Anchor selection — the load-bearing fix: never a longshot
# --------------------------------------------------------------------------- #
def _leg(line, odds, blended, ev):
    return PricedAceLeg(match_id=1, line=line, decimal_odds=odds, model_prob=blended,
                        market_prob_fair=blended, blended_prob=blended, edge=0.0, ev=ev,
                        is_value=ev > 0, predicted_mean=10.0)


def test_anchor_prefers_high_hit_low_line_not_longshot():
    legs = [
        _leg(5, 1.05, 0.88, -0.05),   # very safe
        _leg(7, 1.20, 0.74, -0.02),   # safe, highest line >= target 0.70
        _leg(13, 8.0, 0.09, 0.10),    # longshot, +EV but tiny prob
    ]
    anchor = ace_model.anchor_leg(legs, target_prob=0.70)
    assert anchor.line == 7, "anchor must be the highest SAFE line, never the longshot"


def test_anchor_falls_back_to_safest_when_none_clear_target():
    legs = [_leg(9, 1.5, 0.55, -0.1), _leg(11, 2.0, 0.40, -0.1)]
    anchor = ace_model.anchor_leg(legs, target_prob=0.70)
    assert anchor.line == 9, "fallback picks the highest-probability leg, not the longest odds"


def test_anchor_none_when_no_legs():
    assert ace_model.anchor_leg([]) is None


def test_prop_strategy_stays_research_only_on_small_sample():
    from tennis_wc.props import strategy

    gate = strategy.recommendation_gate(
        {
            "settled": 119,
            "model": {"brier": 0.20},
            "market": {"brier": 0.22},
        },
        {
            "by_family": {
                "player_aces": {"settled": 100, "roi": 0.10},
                "match_total_aces": {"settled": 100, "roi": 0.05},
            }
        },
    )

    assert gate["status"] == "RESEARCH_ONLY"
    assert gate["recommendations_enabled"] is False


@pytest.fixture
def allowlist_open(monkeypatch):
    """Widen the go-live allowlist for tests about the EVIDENCE GATE.

    Two separate questions: `recommendation_gate` answers "has this family earned
    a tier", and `LIVE_FAMILIES` answers "are we willing to stake it on day one".
    The tests below are about the first, and use families (player_aces) that are
    deliberately not on the day-one list, so they say so rather than quietly
    relying on the list containing everything.
    """
    from tennis_wc.props import strategy

    monkeypatch.setattr(strategy, "LIVE_FAMILIES",
                        frozenset(strategy.LIVE_FAMILIES | {"player_aces"}))
    return None


def test_prop_strategy_enables_only_proven_family_and_filters_longshots(allowlist_open):
    from tennis_wc.props import strategy

    gate = strategy.recommendation_gate(
        {
            "settled": 150,
            "model": {"brier": 0.19},
            "market": {"brier": 0.21},
            "by_family": {
                "player_aces": {
                    "settled": 130,
                    "model": {"brier": 0.19},
                    "market": {"brier": 0.21},
                },
                "match_total_aces": {
                    "settled": 130,
                    "model": {"brier": 0.22},
                    "market": {"brier": 0.21},
                },
            },
        },
        {
            "by_family": {
                "player_aces": {"settled": 60, "roi": 0.04},
                "match_total_aces": {"settled": 60, "roi": -0.01},
            }
        },
    )

    assert gate["status"] == "VALIDATED_SINGLE"
    assert gate["enabled_families"] == ["player_aces"]
    base = {
        "market_key": "total_player_one_aces_7_5",
        "prob": 0.61,
        "data_quality": 0.90,
        "odds": 1.90,
        "edge": 0.06,
        "ev": 0.08,
    }
    assert strategy.leg_is_formal_candidate(base, gate)
    assert not strategy.leg_is_formal_candidate(base | {"odds": 2.30}, gate)


def test_player_aces_can_enter_reversible_early_main_on_profitable_trend(allowlist_open):
    from tennis_wc.props import strategy

    gate = strategy.recommendation_gate(
        {
            "settled": 58,
            "by_family": {
                "player_aces": {
                    "settled": 58,
                    "model": {"brier": 0.2371},
                    "market": {"brier": 0.2512},
                }
            },
        },
        {
            "by_family_formal_profile": {
                "player_aces": {"settled": 3, "roi": 0.14}
            }
        },
    )

    assert gate["status"] == "EARLY_MAIN"
    assert gate["enabled_families"] == ["player_aces"]
    assert gate["validated_families"] == []
    assert gate["early_main_families"] == ["player_aces"]
    assert gate["family_states"]["player_aces"]["tier"] == "EARLY_MAIN"
    assert gate["warnings"]


def test_early_main_auto_downgrades_when_eligible_roi_turns_negative():
    from tennis_wc.props import strategy

    score = {
        "settled": 58,
        "by_family": {
            "player_aces": {
                "settled": 58,
                "model": {"brier": 0.2371},
                "market": {"brier": 0.2512},
            }
        },
    }
    roi = {
        "by_family_formal_profile": {
            "player_aces": {"settled": 4, "roi": -0.01}
        }
    }

    gate = strategy.recommendation_gate(score, roi)

    assert gate["status"] == "RESEARCH_ONLY"
    assert gate["enabled_families"] == []
    assert gate["family_states"]["player_aces"]["tier"] == "RESEARCH_ONLY"


def test_prop_gate_uses_live_eligible_roi_not_high_odds_research_roi():
    from tennis_wc.props import strategy

    score = {
        "settled": 130,
        "by_family": {
            "player_aces": {
                "settled": 130,
                "model": {"brier": 0.18},
                "market": {"brier": 0.20},
            }
        },
    }
    roi = {
        "by_family": {"player_aces": {"settled": 80, "roi": 0.25}},
        "by_family_formal_profile": {
            "player_aces": {"settled": 60, "roi": -0.04}
        },
    }
    gate = strategy.recommendation_gate(score, roi)
    assert gate["status"] == "RESEARCH_ONLY"
    assert gate["family_states"]["player_aces"]["roi"] == -0.04


def test_match_total_aces_stays_research_even_if_historical_gate_passes():
    from tennis_wc.props import strategy

    gate = strategy.recommendation_gate(
        {
            "settled": 150,
            "by_family": {
                "match_total_aces": {
                    "settled": 130,
                    "model": {"brier": 0.17},
                    "market": {"brier": 0.19},
                }
            },
        },
        {
            "by_family_formal_profile": {
                "match_total_aces": {"settled": 60, "roi": 0.10}
            }
        },
    )

    assert gate["status"] == "RESEARCH_ONLY"
    assert gate["enabled_families"] == []
    assert gate["family_states"]["match_total_aces"]["enabled"] is False
    assert (
        gate["family_states"]["match_total_aces"]["recommendable_player_prop"]
        is False
    )


def test_formal_prop_stake_is_confidence_haircut_tenth_kelly_with_caps():
    from tennis_wc.props import strategy

    low_confidence = strategy.formal_stake_units(0.62, 1.80, 69)
    normal = strategy.formal_stake_units(0.62, 1.80, 80)
    capped_single = strategy.formal_stake_units(0.80, 2.00, 95)
    capped_combo = strategy.formal_stake_units(0.55, 2.20, 85, combo=True)
    capped_early = strategy.formal_stake_units(0.80, 2.00, 95, early=True)

    assert low_confidence == 0.0
    assert normal == 1.0
    assert capped_single == 2.0
    assert capped_combo == 1.0
    assert capped_early == 0.5


def test_prop_registry_classifies_expanded_player_markets():
    from tennis_wc.props.registry import family_for_market

    assert family_for_market(
        "total_games", "Alex De Minaur Total Games 12.5"
    ) == "player_total_games"
    assert family_for_market(
        "alex_to_win_at_least_1_set", "Alex To Win At Least 1 Set"
    ) == "player_win_a_set"
    assert family_for_market(
        "total_alex_double_faults_3_5", "Total Alex Double Faults 3.5"
    ) == "player_double_faults"
    assert family_for_market(
        "set_1_game_6_break_points", "Set 1 Game 6 Break Points"
    ) == "micro_break_points"
    assert family_for_market("winner_related", "Set 1 Winner") == "first_set_winner"
    assert family_for_market("game_handicap", "Game Handicap -4.5") == "player_game_handicap"
    assert family_for_market("set_handicap", "Alternative Set Handicap 1.5") == "player_set_handicap"
    assert family_for_market(
        "game_handicap", "Set 1 Game Handicap -1.5"
    ) == "player_first_set_game_handicap"
    assert family_for_market(
        "to_win_1st_set_and_win_match", "To win 1st set and win match"
    ) == "player_first_set_match"
    assert family_for_market("set_betting", "Set Betting") == "player_exact_set_score"
    assert family_for_market("set_betting", "Set 1 Correct Score") == "set_betting"


def test_player_handicap_models_are_complementary_and_conservative():
    import math
    from tennis_wc.props import player_model

    set_cover, set_margin = player_model.set_handicap_cover_probability(-1.5, 0.80)
    game_cover, game_margin = player_model.game_handicap_cover_probability(-3.5, 22.0, 0.80)
    assert 0 < set_cover < 1 and set_margin > 0
    assert 0 < game_cover < 1 and game_margin > 0
    unshrunk_game_cover = 1 - 0.5 * (
        1 + math.erf((3.5-game_margin) / (5.2*math.sqrt(2)))
    )
    assert abs(game_cover-0.5) < abs(unshrunk_game_cover-0.5)

    priced = player_model.price_spread_two_way(
        1, "player_set_handicap_1.5", 1, "A", 2, "B",
        -1.5, 1.5, 2.25, 1.60, set_cover, set_margin,
    )
    assert priced is not None
    assert abs(priced.fair_prob_a_cover + (1-priced.fair_prob_a_cover) - 1) < 1e-9
    assert priced.model_prob_a_cover == round(set_cover, 4)

    # Three-way/integer handicaps have a push state and must not enter this
    # complementary two-way contract.
    assert player_model.price_spread_two_way(
        1, "player_game_handicap_4", 1, "A", 2, "B",
        -4.0, 4.0, 2.0, 2.0, 0.5, 4.0,
    ) is None


def test_exact_set_score_pricing_is_a_complete_four_way_distribution():
    from tennis_wc.props import player_model

    prop = player_model.price_exact_set_score(
        1, "player_exact_set_score", 1, "A", 2, "B",
        {"a20": 2.1, "a21": 4.0, "b20": 4.5, "b21": 5.5},
        0.65, temper=0.25,
    )
    assert prop is not None and len(prop.selections) == 4
    assert abs(sum(row.model_prob for row in prop.selections)-1) < 0.001
    assert abs(sum(row.fair_prob for row in prop.selections)-1) < 0.001
    assert abs(sum(row.tempered_prob for row in prop.selections)-1) < 0.001
    assert abs(sum(row.blended_prob for row in prop.selections)-1) < 0.001
    assert player_model.price_exact_set_score(
        1, "player_exact_set_score", 1, "A", 2, "B",
        {"a20": 2.1, "a21": 4.0}, 0.65,
    ) is None


def test_first_set_match_double_uses_the_complete_four_outcome_market():
    from tennis_wc.props import player_model

    prop = player_model.price_first_set_match_outcomes(
        1, "player_first_set_match", 1, "A", 2, "B",
        {"a_win": 2.0, "a_lose": 7.0, "b_win": 2.8, "b_lose": 6.0},
        {"a_win": 0.45, "a_lose": 0.10, "b_win": 0.35, "b_lose": 0.10},
    )

    assert prop is not None and len(prop.selections) == 4
    assert sum(row.fair_prob for row in prop.selections) == pytest.approx(1.0, abs=0.001)
    assert sum(row.model_prob for row in prop.selections) == pytest.approx(1.0, abs=0.001)
    assert all(not row.is_value for row in prop.selections if not row.first_set_won)


# --------------------------------------------------------------------------- #
# Longshot rungs are refused at pricing time (fake-edge trap)
# --------------------------------------------------------------------------- #
def test_price_ace_legs_refuses_longshot_lines(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    init_db()
    conn = get_connection()
    # seed 8 prior ace matches each for players 1 and 2 (mean ~ 5 aces each)
    _seed_history(conn, 1, 2, 8, 5.0)
    _seed_history(conn, 2, 1, 8, 5.0)
    conn.commit()
    # predicted mean ~10; offer a sane line (9) and a longshot (30)
    legs = ace_model.price_ace_legs(conn, 99, 1, 2, "2026-01-01", "hard",
                                    offered_lines={9.0: 1.8, 30.0: 26.0})
    priced = {int(lg.line) for lg in legs}
    assert 9 in priced
    assert 30 not in priced, "line beyond 1.25x predicted mean must be refused"


def test_price_ace_legs_empty_when_thin_history(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    init_db()
    conn = get_connection()
    # only 2 prior matches -> below _MIN_HISTORY -> no fabricated pricing
    _seed_history(conn, 1, 2, 2, 5.0)
    conn.commit()
    assert ace_model.price_ace_legs(conn, 1, 1, 2, "2026-01-01", "hard", {9.0: 1.8}) == []


def test_temper_haircut_cannot_flip_raw_model_direction_into_fake_edge():
    # Raw model strongly supports OVER, while an extreme temper would pull the
    # staking probability below the market and previously fabricate UNDER value.
    tw = ace_model.price_two_way(
        1, "total_aces_8_5", "match", 8.5, 1.35, 3.2, 12.0,
        [(0.70, 0.80), (0.71, 0.80)], within_range_ratio=2.0, temper=0.95,
    )
    assert tw is not None
    assert tw.model_prob_over > tw.fair_prob_over
    assert tw.value_side != "under"
    from tennis_wc.props.player_model import price_head_to_head
    head = price_head_to_head(
        1, "winner_related", 1, "A", 2, "B", 1.35, 3.2, 0.80, temper=0.95
    )
    assert head is not None
    assert head.value_player_id != 2


def test_conceded_aces_join_uses_exact_provider_match_pair(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    conn = get_connection()
    for day in range(1, 6):
        date = f"2025-01-{day:02d}"
        base = f"ATP-T-{day}"
        for provider_match_id, player_id, opponent_id, aces in (
            (f"{base}-winner", 1, 2, 5.0),
            (f"{base}-loser", 2, 1, 7.0),
        ):
            conn.execute(
                """INSERT INTO player_match_history
                   (provider_match_id, player_id, opponent_id, tour, match_date,
                    tournament_external_id, tournament_level, round, format, won,
                    source_provider, raw_response_id, created_at, surface, ace_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (provider_match_id, player_id, opponent_id, "ATP", date, "T", "ATP250",
                 "R1", "BO3", 1, "test", 0, "now", "hard", aces),
            )
        # Same players/date but not the counterpart of player 1's row.  The old
        # date-only join pulled this 99 into conceded form and duplicated days.
        conn.execute(
            """INSERT INTO player_match_history
               (provider_match_id, player_id, opponent_id, tour, match_date,
                tournament_external_id, tournament_level, round, format, won,
                source_provider, raw_response_id, created_at, surface, ace_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"UNRELATED-{day}-loser", 2, 1, "ATP", date, "OTHER", "ATP250",
             "R1", "BO3", 1, "test", 0, "now", "hard", 99.0),
        )
    conn.commit()

    profile = ace_model.player_ace_profile(conn, 1, "2026-01-01", "hard")
    assert profile.overall_mean == 5.0
    assert profile.conceded_mean == 7.0


# --------------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------------- #
def _rec(conn, settlement, *, line, selection, side, odds, model_p, market_p,
         market_key="total_aces_in_the_match", scope="match", subject=None,
         stake=1.0, value=True, match_id=1, raw_p=None):
    settlement.record_prop(
        conn, match_id=match_id, match_date="2026-01-01", match_label="A vs B",
        market_key=market_key, line=line, selection=selection, side=side,
        prop_scope=scope, subject_player_id=subject, decimal_odds=odds,
        model_prob=model_p, market_prob_fair=market_p, blended_prob=model_p,
        model_prob_raw=model_p if raw_p is None else raw_p, temper_strength=0.0,
        edge=model_p - market_p, ev=model_p * odds - 1, predicted_mean=13.0,
        stake_units=stake, is_value=value)


# --------------------------------------------------------------------------- #
# Two-way pricing
# --------------------------------------------------------------------------- #
def test_price_two_way_devigs_and_picks_value_side():
    # model thinks aces LOW: pred mean 8, line 12.5 -> model P(over) small ->
    # under should be the value side.
    tw = ace_model.price_two_way(1, "total_aces_12_5", "match", 9.5,
                                 over_odds=1.90, under_odds=1.90, predicted_mean=9.0,
                                 curve=ace_model.MATCH_ACE_CURVE)
    assert tw is not None
    # exact two-way de-vig of equal odds -> ~0.5 each
    assert abs(tw.fair_prob_over - 0.5) < 0.02
    # at ratio ~1.06 model P(over) < 0.5 -> under is the value side
    assert tw.value_side in ("under", None)


def test_price_two_way_refuses_out_of_range_line():
    tw = ace_model.price_two_way(1, "total_aces_30_5", "match", 30.5,
                                 over_odds=2.0, under_odds=1.8, predicted_mean=9.0,
                                 curve=ace_model.MATCH_ACE_CURVE)
    assert tw is None, "line far above predicted mean must be refused"


def test_player_ace_prediction_uses_own_curve():
    p_over = ace_model.interp_prob_over(5.5, 6.0, ace_model.PLAYER_ACE_CURVE)
    m_over = ace_model.interp_prob_over(5.5, 6.0, ace_model.MATCH_ACE_CURVE)
    assert p_over != m_over, "player and match curves must differ"
    assert 0.0 < p_over < 1.0


# --------------------------------------------------------------------------- #
# Settlement + review
# --------------------------------------------------------------------------- #
def test_settlement_grades_over_and_under(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement
    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute("INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json) VALUES (1,1,'t','now', ?)",
                 ('{"player_a_aces": 8, "player_b_aces": 5}',))  # total 13
    conn.commit()
    assert settlement.actual_total_aces(conn, 1) == 13.0
    assert settlement.actual_player_aces(conn, 1, 1) == 8.0
    # match total 13: Over 7+ wins; Under 15.5 wins; player_a Over 9.5 loses (8<9.5)
    _rec(conn, settlement, line=7.0, selection="7+", side="over", odds=1.5, model_p=0.7, market_p=0.72)
    _rec(conn, settlement, line=15.5, selection="Under 15.5", side="under", odds=1.9,
         model_p=0.6, market_p=0.55, market_key="total_aces_15_5")
    _rec(conn, settlement, line=9.5, selection="Over 9.5", side="over", odds=2.0, model_p=0.5, market_p=0.48,
         market_key="total_a_aces_9_5", scope="player", subject=1)
    conn.commit()
    out = settlement.settle_props(conn)
    assert out["graded"] == 3
    roi = settlement.prop_roi_report(conn)
    # 7+ win (+0.5), under 15.5 win (+0.9), player over 9.5 loss (-1.0) -> +0.4
    assert roi["overall"]["settled"] == 3 and roi["overall"]["wins"] == 2
    assert abs(roi["overall"]["pnl"] - 0.4) < 1e-6
    assert "over" in roi["by_side"] and "under" in roi["by_side"]
    assert set(roi["by_odds_band"]) == {
        "<1.60", "1.60-1.99", "2.00-2.24",
    }


def test_prop_settlement_voids_retired_matches(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json) "
        "VALUES (1,1,'t','now', ?)",
        ('{"player_a_aces": 2, "player_b_aces": 1, "retired": true}',),
    )
    _rec(conn, settlement, line=7.5, selection="Under 7.5", side="under",
         odds=1.9, model_p=0.7, market_p=0.5)
    conn.commit()

    out = settlement.settle_props(conn)
    row = conn.execute(
        "SELECT result_status, profit_loss_units FROM prop_tracker"
    ).fetchone()
    assert out == {"graded": 0, "voided": 1, "regraded_to_void": 0, "still_pending": 0}
    assert row["result_status"] == "VOID"
    assert row["profit_loss_units"] == 0


def test_scorecard_compares_model_and_market(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement
    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute("INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json) VALUES (1,1,'t','now', ?)",
                 ('{"player_a_aces": 8, "player_b_aces": 5}',))
    conn.commit()
    # record several over-side rows with model/market probs; grade; scorecard
    for i, line in enumerate((5.0, 7.0, 9.0, 11.0)):
        _rec(conn, settlement, line=line, selection=f"{int(line)}+", side="over", odds=1.5,
             model_p=0.6, market_p=0.7, stake=0.0, value=False)
    conn.commit()
    settlement.settle_props(conn)
    sc = settlement.model_vs_market_scorecard(conn)
    assert sc["settled"] == 4
    assert sc["model"] is not None and sc["market"] is not None
    assert "verdict" in sc


def test_scorecard_can_score_a_frozen_holdout_window(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2, date="2026-06-01")
    _seed_match(conn, 2, 1, 2, date="2026-08-01")
    conn.execute(
        "INSERT INTO match_results (match_id,winner_player_id,source_provider,created_at,score_json) "
        "VALUES (1,1,'t','now','{\"player_a_aces\":8,\"player_b_aces\":5}'),"
        "(2,2,'t','now','{\"player_a_aces\":2,\"player_b_aces\":1}')"
    )
    _rec(conn, settlement, match_id=1, line=5.0, selection="5+", side="over",
         odds=1.9, model_p=0.7, market_p=0.6, stake=0.0, value=False)
    _rec(conn, settlement, match_id=2, line=5.0, selection="5+", side="over",
         odds=1.9, model_p=0.7, market_p=0.6, stake=0.0, value=False)
    conn.execute(
        "UPDATE prop_tracker SET match_date=(SELECT match_date FROM matches "
        "WHERE matches.id=prop_tracker.match_id)"
    )
    conn.commit()
    settlement.settle_props(conn)

    train = settlement.model_vs_market_scorecard(
        conn, as_of_date="2026-07-01"
    )
    holdout = settlement.model_vs_market_scorecard(
        conn, since_date="2026-07-01"
    )

    assert train["settled"] == 1
    assert holdout["settled"] == 1


def test_temper_reduces_confidence_and_ev():
    from tennis_wc.props import calibration
    # tempering pulls prob toward 0.5
    assert abs(calibration.temper_probability(0.8, 0.5) - 0.65) < 1e-9
    assert calibration.temper_probability(0.5, 0.9) == 0.5
    # a tempered two-way prop has a smaller |edge| than the untempered one
    raw = ace_model.price_two_way(1, "total_aces_8_5", "match", 7.5, 2.0, 1.9, 9.0,
                                  ace_model.MATCH_ACE_CURVE, temper=0.0)
    tem = ace_model.price_two_way(1, "total_aces_8_5", "match", 7.5, 2.0, 1.9, 9.0,
                                  ace_model.MATCH_ACE_CURVE, temper=0.30)
    if raw.value_side and tem.value_side:
        assert abs(tem.edge) <= abs(raw.edge) + 1e-9


def test_current_strength_defaults_conservative_when_few_settled(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import calibration
    init_db()
    assert calibration.current_strength(get_connection()) == calibration.DEFAULT_STRENGTH


def test_market_blend_never_crosses_or_invents_opposite_edge():
    from tennis_wc.props import calibration

    assert calibration.blend_with_market(0.80, 0.55, 0.40) == 0.65
    assert calibration.blend_with_market(0.20, 0.45, 0.40) == 0.35
    priced = ace_model.price_two_way(
        1, "total_aces_9_5", "match", 9.5, 1.90, 1.90, 13.0,
        ace_model.MATCH_ACE_CURVE, model_weight=0.0,
    )
    assert priced is not None
    # A zero model weight shrinks the staking probability all the way to the
    # market, but selection reads the odds-blind model, so the prop is still a
    # candidate -- on the side the raw model actually favours, never the other.
    assert priced.blended_prob == priced.fair_prob_over
    assert priced.model_prob_over > priced.fair_prob_over
    assert priced.value_side == "over"

    mirrored = ace_model.price_two_way(
        1, "total_aces_9_5", "match", 9.5, 1.90, 1.90, 8.0,
        ace_model.MATCH_ACE_CURVE, model_weight=0.0,
    )
    assert mirrored is not None
    assert mirrored.model_prob_over < mirrored.fair_prob_over
    assert mirrored.value_side == "under"


def test_family_reliability_is_quality_filtered_and_as_of_safe(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import calibration, settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    for index in range(21):
        match_id = index + 1
        date = f"2026-01-{match_id:02d}"
        _seed_match(conn, match_id, 1, 2, date=date)
        conn.execute(
            "INSERT INTO feature_snapshots "
            "(match_id,player_id,feature_set_version,features_json,"
            "provenance_json,data_quality_score,created_at) "
            "VALUES (?,?,?, '{}','{}',65,'now')",
            (match_id, 1, "test"),
        )
        settlement.record_prop(
            conn, match_id=match_id, match_date=date, match_label="A vs B",
            market_key="player_win_a_set_1", line=0.5, selection="Yes",
            side="over", prop_scope="player_win_set", subject_player_id=1,
            decimal_odds=1.9, model_prob=0.7, model_prob_raw=0.7,
            temper_strength=0.0, market_prob_fair=0.5, blended_prob=0.6,
            edge=0.1, ev=0.14, predicted_mean=0.7, stake_units=1.0,
            is_value=True,
        )
        conn.execute(
            "UPDATE prop_tracker SET result_status='WON',profit_loss_units=.9 "
            "WHERE match_id=?", (match_id,),
        )
    _seed_match(conn, 99, 1, 2, date="2026-03-01")
    conn.execute(
        "INSERT INTO feature_snapshots "
        "(match_id,player_id,feature_set_version,features_json,provenance_json,"
        "data_quality_score,created_at) VALUES (99,1,'test','{}','{}',65,'now')"
    )
    settlement.record_prop(
        conn, match_id=99, match_date="2026-03-01", match_label="A vs B",
        market_key="player_win_a_set_1", line=0.5, selection="Yes",
        side="over", prop_scope="player_win_set", subject_player_id=1,
        decimal_odds=1.9, model_prob=0.9, model_prob_raw=0.9,
        temper_strength=0.0, market_prob_fair=0.5, blended_prob=0.7,
        edge=0.2, ev=0.33, predicted_mean=0.9, stake_units=1.0,
        is_value=True,
    )
    conn.execute(
        "UPDATE prop_tracker SET result_status='LOST',profit_loss_units=-1 "
        "WHERE match_id=99"
    )
    conn.commit()

    profile = calibration.family_reliability(
        conn, "player_win_a_set", as_of_date="2026-02-01"
    )
    assert profile.settled == 21
    assert profile.raw_weight == 1.0
    assert 0 < profile.model_weight < profile.raw_weight


def test_ace_reliability_uses_prematch_serve_history_not_match_quality(
    tmp_path, monkeypatch
):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import calibration, settlement

    init_db()
    conn = get_connection()
    for player_id, name in ((1, "A"), (2, "B"), (3, "C"), (4, "D")):
        _seed_player(conn, player_id, name)
    _seed_history(conn, 1, 2, 10, 8)
    _seed_history(conn, 2, 1, 10, 5)
    for match_id, player_a, player_b, quality in (
        (1, 1, 2, 0),
        (2, 3, 4, 100),
    ):
        _seed_match(conn, match_id, player_a, player_b, date="2026-02-01")
        conn.execute(
            "INSERT INTO feature_snapshots "
            "(match_id,player_id,feature_set_version,features_json,"
            "provenance_json,data_quality_score,created_at) "
            "VALUES (?,?,'test','{}','{}',?,'now')",
            (match_id, player_a, quality),
        )
        settlement.record_prop(
            conn, match_id=match_id, match_date="2026-02-01",
            match_label="test", market_key=f"total_player_{player_a}_aces_7_5",
            line=7.5, selection="Over 7.5", side="over",
            prop_scope="player", subject_player_id=player_a,
            decimal_odds=1.9, model_prob=0.65, model_prob_raw=0.65,
            temper_strength=0.0, market_prob_fair=0.52, blended_prob=0.55,
            edge=0.03, ev=0.045, predicted_mean=8.0, stake_units=0.0,
            is_value=False,
        )
        conn.execute(
            "UPDATE prop_tracker SET result_status='WON' WHERE match_id=?",
            (match_id,),
        )
    conn.commit()

    profile = calibration.family_reliability(
        conn, "player_aces", as_of_date="2026-03-01"
    )
    assert profile.settled == 1


def test_confidence_score_is_not_hit_probability_and_normalises_quality():
    from tennis_wc.props import strategy

    gate = {
        "enabled_families": ["player_aces"],
        "family_states": {
            "player_aces": {
                "scorecard_settled": 120,
                "model_brier": 0.19,
                "market_brier": 0.21,
            }
        },
    }
    leg = {"market_key": "total_alex_aces_7_5", "data_quality": 65,
           "prob": 0.90}
    score = strategy.confidence_score(leg, gate)
    assert score == strategy.confidence_score(leg | {"data_quality": 0.65}, gate)
    assert score != 90


def test_predict_total_games_more_for_close_matches():
    from tennis_wc.props import games_model
    close = games_model.predict_total_games(0.5, best_of=3)   # coin-flip
    lopsided = games_model.predict_total_games(0.9, best_of=3)  # heavy fav
    assert close > lopsided, "closer matches should predict more games"
    assert games_model.predict_total_games(0.5, best_of=5) > close, "BO5 > BO3"
    assert games_model.predict_total_games(None) is None


def test_price_games_two_way_devigs():
    from tennis_wc.props import games_model
    tw = games_model.price_games_two_way(1, "total_match_games_22_5", 22.5,
                                         over_odds=1.9, under_odds=1.9, match_prob=0.55)
    assert tw is not None
    assert tw.market_key == "total_match_games_22_5"
    assert abs(tw.fair_prob_over - 0.5) < 0.02
    assert 0.0 < tw.model_prob_over < 1.0


def test_games_settlement_grades_total_games(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement
    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute("INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json) VALUES (1,1,'t','now', ?)",
                 ('{"player_a_games": 13, "player_b_games": 11}',))  # 24 total
    conn.commit()
    assert settlement.actual_total_games(conn, 1) == 24.0
    # Over 22.5 wins (24>22.5); Under 22.5 would lose
    _rec(conn, settlement, line=22.5, selection="Over 22.5", side="over", odds=1.9,
         model_p=0.55, market_p=0.5, market_key="total_match_games_22_5", scope="match_games")
    conn.commit()
    settlement.settle_props(conn)
    roi = settlement.prop_roi_report(conn)
    assert roi["overall"]["settled"] == 1 and roi["overall"]["wins"] == 1
    assert "match_total_games" in roi["by_family"]


def test_expanded_player_props_settle_against_named_player(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results "
        "(match_id, winner_player_id, source_provider, created_at, score_json) "
        "VALUES (1,1,'t','now', ?)",
        ('{"player_a_games":13,"player_b_games":11,"player_a_sets":2,'
         '"player_b_sets":1,"player_a_double_faults":4,'
         '"player_b_double_faults":2,"sets":['
         '{"player_a_games":6,"player_b_games":4},'
         '{"player_a_games":4,"player_b_games":6},'
         '{"player_a_games":6,"player_b_games":1}]}',),
    )
    _rec(
        conn, settlement, line=12.5, selection="Over 12.5", side="over",
        odds=1.9, model_p=0.6, market_p=0.52,
        market_key="player_total_games_1_12.5", scope="player_games", subject=1,
    )
    _rec(
        conn, settlement, line=0.5, selection="Yes", side="over",
        odds=1.4, model_p=0.8, market_p=0.72,
        market_key="player_win_a_set_2", scope="player_win_set", subject=2,
    )
    _rec(
        conn, settlement, line=3.5, selection="Over 3.5", side="over",
        odds=1.9, model_p=0.6, market_p=0.52,
        market_key="player_double_faults_1_3.5",
        scope="player_double_faults", subject=1,
    )
    _rec(
        conn, settlement, line=0.5, selection="A", side="over",
        odds=1.8, model_p=0.62, market_p=0.55,
        market_key="first_set_winner_1", scope="player_first_set", subject=1,
    )
    conn.commit()

    result = settlement.settle_props(conn)
    statuses = [
        row["result_status"] for row in
        conn.execute("SELECT result_status FROM prop_tracker ORDER BY id").fetchall()
    ]
    assert result["graded"] == 4
    assert statuses == ["WON", "WON", "WON", "WON"]


def test_player_handicaps_settle_from_game_and_set_margins(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results "
        "(match_id, winner_player_id, source_provider, created_at, score_json) "
        "VALUES (1,1,'t','now', ?)",
        ('{"player_a_games":13,"player_b_games":8,'
         '"player_a_sets":2,"player_b_sets":0}',),
    )
    assert settlement.actual_player_margin(conn, 1, 1, "games") == 5
    assert settlement.actual_player_margin(conn, 1, 1, "sets") == 2
    _rec(
        conn, settlement, line=4.5, selection="A (-4.5)", side="over",
        odds=1.9, model_p=0.60, market_p=0.52,
        market_key="player_game_handicap_4.5",
        scope="player_game_margin", subject=1,
    )
    _rec(
        conn, settlement, line=4.5, selection="B (+4.5)", side="under",
        odds=1.9, model_p=0.40, market_p=0.48,
        market_key="player_game_handicap_4.5",
        scope="player_game_margin", subject=1,
    )
    _rec(
        conn, settlement, line=1.5, selection="A (-1.5)", side="over",
        odds=2.1, model_p=0.55, market_p=0.47,
        market_key="player_set_handicap_1.5",
        scope="player_set_margin", subject=1,
    )
    conn.commit()

    result = settlement.settle_props(conn)
    rows = conn.execute(
        "SELECT result_status FROM prop_tracker ORDER BY id"
    ).fetchall()
    assert result["graded"] == 3
    assert [row["result_status"] for row in rows] == ["WON", "LOST", "WON"]


def test_first_set_match_and_handicap_settle_from_first_set_score(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results "
        "(match_id, winner_player_id, source_provider, created_at, score_json) "
        "VALUES (1,1,'t','now', ?)",
        ('{"player_a_sets":2,"player_b_sets":1,"sets":['
         '{"player_a_games":4,"player_b_games":6},'
         '{"player_a_games":6,"player_b_games":3},'
         '{"player_a_games":6,"player_b_games":2}]}',),
    )
    assert settlement.actual_player_first_set_margin(conn, 1, 1) == -2.0
    assert settlement.actual_player_first_set_and_match(conn, 1, 1, False) == 1.0
    _rec(
        conn, settlement, line=0.5,
        selection="A Lose 1st Set & Win Match", side="over", odds=7.0,
        model_p=0.15, market_p=0.12,
        market_key="player_first_set_match_1_lose_first",
        scope="player_first_set_match", subject=1,
    )
    _rec(
        conn, settlement, line=1.5, selection="A (-1.5)", side="over",
        odds=2.1, model_p=0.55, market_p=0.48,
        market_key="player_first_set_game_handicap_1.5",
        scope="player_first_set_game_margin", subject=1,
    )
    conn.commit()

    result = settlement.settle_props(conn)
    rows = conn.execute(
        "SELECT result_status FROM prop_tracker ORDER BY id"
    ).fetchall()
    assert result["graded"] == 2
    assert [row["result_status"] for row in rows] == ["WON", "LOST"]


def test_exact_set_score_settlement_and_scorecard_count_one_match(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results "
        "(match_id, winner_player_id, source_provider, created_at, score_json) "
        "VALUES (1,1,'t','now', ?)",
        ('{"player_a_sets":2,"player_b_sets":1}',),
    )
    outcomes = ((1, "A 2-0", 0.32), (1, "A 2-1", 0.28),
                (2, "B 2-0", 0.22), (2, "B 2-1", 0.18))
    for player_id, selection, probability in outcomes:
        sets_lost = int(selection[-1])
        _rec(
            conn, settlement, line=0.5, selection=selection, side="over",
            odds=1/probability, model_p=probability, market_p=probability,
            market_key=f"player_exact_set_score_{player_id}_{sets_lost}",
            scope="player_exact_set_score", subject=player_id,
            stake=0.0, value=False,
        )
    conn.commit()
    result = settlement.settle_props(conn)
    statuses = conn.execute(
        "SELECT selection,result_status FROM prop_tracker ORDER BY id"
    ).fetchall()
    assert result["graded"] == 4
    assert [(row["selection"], row["result_status"]) for row in statuses] == [
        ("A 2-0", "LOST"), ("A 2-1", "WON"),
        ("B 2-0", "LOST"), ("B 2-1", "LOST"),
    ]
    scorecard = settlement.model_vs_market_scorecard(conn)
    assert scorecard["settled"] == 4
    assert scorecard["by_family"]["player_exact_set_score"]["settled"] == 1


def test_record_prop_idempotent(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement
    init_db()
    conn = get_connection()
    for _ in range(3):
        _rec(conn, settlement, line=7.0, selection="7+", side="over", odds=1.5, model_p=0.7, market_p=0.72)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM prop_tracker").fetchone()[0]
    assert n == 1, "same prop_key must upsert, not duplicate"


def test_wta_ace_props_never_flag_value():
    """Ungradeable markets must not surface value bets: WTA aces have no
    settleable data source, so value flags are stripped (still priced/logged)."""
    from tennis_wc.props import ace_model
    from tennis_wc.props.daily import _aces_gradeable, _strip_value

    assert _aces_gradeable("ATP")
    assert not _aces_gradeable("WTA")
    assert not _aces_gradeable(None)
    assert not _aces_gradeable("UNKNOWN")

    tw = ace_model.price_two_way(
        1, "total_aces_9_5", "match", 9.5,
        over_odds=2.2, under_odds=1.6, predicted_mean=12.0,
        curve=ace_model.MATCH_ACE_CURVE,
    )
    assert tw is not None and tw.value_side is not None  # a clear value side exists
    stripped = _strip_value(tw)
    assert stripped.value_side is None
    assert stripped.value_odds is None
    assert stripped.edge == 0.0
    assert stripped.ev <= 0.0


def test_high_odds_props_are_priced_but_never_flagged_as_value():
    tw = ace_model.price_two_way(
        1, "total_aces_9_5", "match", 9.5,
        over_odds=2.40, under_odds=1.55, predicted_mean=12.0,
        curve=ace_model.MATCH_ACE_CURVE,
    )
    assert tw is not None
    assert tw.value_side is None
    assert tw.value_odds is None


def test_probability_floor_is_per_family_not_global():
    """The hit-probability floor is a sizing limit, not a selection one.

    `player_win_a_set` is priced on underdogs: a 0.55 floor and the old 2.25
    ceiling excluded, by construction, the only segment that has made money
    (odds >= 2.20 returned +16.2% over 165 settled bets, while the 1.60-1.89
    band inside the old limits returned -16.2%).  Families without a registered
    profile keep the conservative default.
    """
    from tennis_wc.props.player_model import price_probability_two_way
    from tennis_wc.props.registry import value_profile

    assert value_profile("player_win_a_set_a").min_probability == 0.0
    assert value_profile("player_total_games_a").min_probability == 0.58

    underdog = price_probability_two_way(
        1, "player_win_a_set_a", "player_match", 2.25, 1.60,
        raw_yes=0.65, model_weight=0.50,
    )
    assert underdog is not None and underdog.blended_prob < 0.55
    assert underdog.value_side == "yes"

    # A family on the default profile still refuses prices beyond its ceiling.
    beyond_ceiling = price_probability_two_way(
        1, "player_total_games_a", "player_match", 3.00, 1.40,
        raw_yes=0.65, model_weight=0.50,
    )
    assert beyond_ceiling is not None
    assert beyond_ceiling.value_side is None


def test_surface_curves_present_and_fallback():
    from tennis_wc.props import ace_model

    for surf in ("hard", "clay", "grass"):
        assert ace_model.match_curve_for_surface(surf) == ace_model.MATCH_ACE_CURVE_BY_SURFACE[surf]
        assert ace_model.player_curve_for_surface(surf) == ace_model.PLAYER_ACE_CURVE_BY_SURFACE[surf]
        # Both scopes are survival curves: harder lines cannot become likelier.
        for curve in (
            ace_model.MATCH_ACE_CURVE_BY_SURFACE[surf],
            ace_model.PLAYER_ACE_CURVE_BY_SURFACE[surf],
        ):
            probs = [p for _, p in curve]
            assert all(a >= b for a, b in zip(probs, probs[1:]))
    # unknown/carpet fall back sensibly
    assert ace_model.match_curve_for_surface(None) == ace_model.MATCH_ACE_CURVE
    assert ace_model.match_curve_for_surface("carpet") == ace_model.MATCH_ACE_CURVE_BY_SURFACE["hard"]
    # grass survives higher at the same ratio than clay (more aces on grass)
    from tennis_wc.props.ace_model import interp_prob_over
    g = interp_prob_over(10, 10.0, ace_model.match_curve_for_surface("grass"))
    c = interp_prob_over(10, 10.0, ace_model.match_curve_for_surface("clay"))
    assert g > c


def test_games_v2_hold_ratio_scales_mean():
    from tennis_wc.props import games_model

    # Bucket boundaries + neutrality of unknown.
    assert games_model.hold_ratio(None) == 1.0
    assert games_model.hold_ratio(1.30) == 0.971
    assert games_model.hold_ratio(1.50) == 1.000
    assert games_model.hold_ratio(1.70) == 1.049
    base = games_model.predict_total_games(0.5, 3)
    big_serve = games_model.predict_total_games(0.5, 3, hold_sum=1.70)
    breakfest = games_model.predict_total_games(0.5, 3, hold_sum=1.30)
    assert big_serve > base > breakfest
    assert abs(big_serve / base - 1.049) < 1e-9


# --------------------------------------------------------------------------- #
# Games props are priced-but-never-staked (2026-07-25)
# --------------------------------------------------------------------------- #
def test_games_props_are_never_value_bets():
    """match_total_games is the one family reliably losing money (11 settled,
    ROI -33.3%) and the games model under-predicts by ~1.9 games, so games props
    must stay priced/logged for the scorecard but never reach the betting card."""
    from tennis_wc.props import daily as props_daily

    assert props_daily._games_bettable() is False

    # A games O/U the model disagrees with hard enough to normally flag value.
    tw = props_daily.games_model.price_games_two_way(
        1, "total_match_games_20_5", 20.5, over_odds=1.90, under_odds=1.90,
        match_prob=0.5, best_of=3,
    )
    assert tw is not None
    stripped = props_daily._strip_value(tw)
    assert stripped.value_side is None, "games prop must not carry a value side"
    assert stripped.edge == 0.0
    assert stripped.ev <= 0.0
    # still usable for the board / scorecard
    assert stripped.predicted_mean is not None


# --------------------------------------------------------------------------- #
# Raw model probability must stay separate from the staking haircut (2026-07-25)
# --------------------------------------------------------------------------- #
def test_temper_does_not_contaminate_raw_model_probability():
    """The temper haircut used to overwrite model_prob_over, so the scorecard
    graded a probability already pulled toward 0.5 while the temper strength was
    itself chosen from that scorecard. raw must be temper-free."""
    kw = dict(match_id=1, market_key="total_aces_9_5", scope="match", line=9.5,
              over_odds=1.90, under_odds=1.90, predicted_mean=13.0,
              curve=ace_model.MATCH_ACE_CURVE)
    plain = ace_model.price_two_way(**kw, temper=0.0)
    tempered = ace_model.price_two_way(**kw, temper=0.35)
    assert plain is not None and tempered is not None

    # raw is identical regardless of the haircut in force
    assert tempered.model_prob_over == plain.model_prob_over
    # the haircut lands on the staking number instead, pulling it toward 0.5
    assert tempered.temper_strength == 0.35
    assert abs(tempered.tempered_prob_over - 0.5) < abs(plain.model_prob_over - 0.5)
    # and it is recorded, so any row can be audited later
    assert plain.temper_strength == 0.0


def test_scorecard_grades_raw_not_tempered(tmp_path, monkeypatch):
    """A model that is overconfident scores BETTER after tempering (pulling toward
    0.5 lowers Brier). Grading the tempered column therefore flatters the model --
    the scorecard must read the raw one."""
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json)"
        " VALUES (1,1,'t','now', ?)", ('{"player_a_aces": 2, "player_b_aces": 1}',))
    conn.commit()
    # Confident OVER calls (raw 0.90) that all LOSE; tempered version says 0.60.
    for line in (5.0, 7.0, 9.0, 11.0):
        _rec(conn, settlement, line=line, selection=f"{int(line)}+", side="over",
             odds=1.5, model_p=0.60, market_p=0.55, raw_p=0.90, stake=0.0, value=False)
    conn.commit()
    settlement.settle_props(conn)

    raw_sc = settlement.model_vs_market_scorecard(conn, use_raw=True)
    tempered_sc = settlement.model_vs_market_scorecard(conn, use_raw=False)
    assert raw_sc["graded_on"] == "model_prob_raw"
    assert raw_sc["settled"] == 4
    # every leg lost, so the confident raw model must look WORSE than the softened one
    assert raw_sc["model"]["brier"] > tempered_sc["model"]["brier"], (
        "grading the tempered column hides the raw model's overconfidence")


def test_scorecard_excludes_legacy_rows_instead_of_mixing(tmp_path, monkeypatch):
    """Pre-2026-07-25 rows only stored the tempered value. Counting them as raw
    would silently blend two different quantities."""
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A"); _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute(
        "INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json)"
        " VALUES (1,1,'t','now', ?)", ('{"player_a_aces": 8, "player_b_aces": 5}',))
    conn.commit()
    for line in (5.0, 7.0):
        _rec(conn, settlement, line=line, selection=f"{int(line)}+", side="over",
             odds=1.5, model_p=0.6, market_p=0.7, stake=0.0, value=False)
    conn.commit()
    settlement.settle_props(conn)
    # simulate legacy rows: raw column never populated
    conn.execute("UPDATE prop_tracker SET model_prob_raw = NULL WHERE line = 5.0")
    conn.commit()

    sc = settlement.model_vs_market_scorecard(conn, use_raw=True)
    assert sc["settled"] == 1, "legacy row must not be graded as raw"
    assert sc["legacy_rows_excluded"] == 1


def _gate_payloads(*, roi, settled, scorecard_n, loss_probability,
                   model_brier=0.30, market_brier=0.20, drawdown=-1.0):
    """Scorecard + ROI payloads for one family, shaped as the gate reads them."""
    scorecard = {
        "settled": scorecard_n,
        "by_family": {
            "player_aces": {
                "settled": scorecard_n,
                "model": {"brier": model_brier},
                "market": {"brier": market_brier},
            }
        },
    }
    roi_payload = {
        "by_family_formal_profile": {
            "player_aces": {
                "settled": settled,
                "roi": roi,
                "loss_probability": loss_probability,
                "max_drawdown_units": drawdown,
            }
        }
    }
    return scorecard, roi_payload


def test_family_graduates_on_credible_profit_without_beating_market_brier(allowlist_open):
    """Profit is the graduation test; calibration skill is only one route to it.

    Requiring the Brier win first meant 0 of 9 families could ever graduate,
    so the card printed "no bet" while several families were profitable.
    """
    from tennis_wc.props.strategy import recommendation_gate

    scorecard, roi = _gate_payloads(
        roi=0.12, settled=60, scorecard_n=200, loss_probability=0.04,
        model_brier=0.30, market_brier=0.20,  # model clearly WORSE than market
    )
    gate = recommendation_gate(scorecard, roi)

    state = gate["family_states"]["player_aces"]
    assert state["model_beats_market"] is False
    assert state["credible_profit"] is True
    assert state["tier"] == "VALIDATED"
    assert gate["status"] == "VALIDATED_SINGLE"


def test_profit_that_does_not_survive_resampling_is_refused():
    from tennis_wc.props.strategy import recommendation_gate

    scorecard, roi = _gate_payloads(
        roi=0.12, settled=60, scorecard_n=200, loss_probability=0.42,
    )
    gate = recommendation_gate(scorecard, roi)

    assert gate["family_states"]["player_aces"]["tier"] == "RESEARCH_ONLY"
    assert gate["status"] == "RESEARCH_ONLY"


def test_profitable_family_is_paused_when_fixed_short_window_is_losing(allowlist_open):
    """A profitable lifetime must not mask a sharp genuinely recent reversal.

    The old "recent" window was 30% of the family's whole date span and kept
    expanding as history grew.  On 2026-08-20 it still admitted win-a-set even
    though its latest 100 formal bets were deeply negative.
    """
    from tennis_wc.props.strategy import recommendation_gate

    scorecard, roi = _gate_payloads(
        roi=0.12, settled=400, scorecard_n=400, loss_probability=0.02,
    )
    roi["by_family_formal_profile"]["player_aces"].update({
        "short_term_settled": 100,
        "short_term_roi": -0.20,
    })

    state = recommendation_gate(scorecard, roi)["family_states"]["player_aces"]
    assert state["short_term_holds"] is False
    assert state["tier"] == "RESEARCH_ONLY"


def test_drawdown_is_judged_at_the_stake_the_tier_actually_uses():
    """The recorded dip is on the 1u research book; a tier bets its own cap.

    player_game_handicap's -45.9u over 760 research bets is -23.0u at the early
    tier's half unit -- inside the -25u limit rather than outside it, and
    judging the smaller decision by the larger book's dip compares two
    different quantities.
    """
    from tennis_wc.props.strategy import (
        recommendation_gate, MAX_FAMILY_DRAWDOWN_UNITS, MAX_EARLY_STAKE_UNITS,
    )

    # -40u on the research book is -20u at the early tier's half unit, inside
    # the limit, and -80u at the full stake, well outside it.
    scorecard, roi = _gate_payloads(
        roi=0.20, settled=80, scorecard_n=300, loss_probability=0.01,
        drawdown=-40.0,
    )
    state = recommendation_gate(scorecard, roi)["family_states"]["player_aces"]
    assert state["tier"] == "EARLY_MAIN"
    assert state["drawdown_at_early_stake"] > MAX_FAMILY_DRAWDOWN_UNITS

    # Deep enough to fail even at the early stake: refused outright.
    scorecard, roi = _gate_payloads(
        roi=0.20, settled=80, scorecard_n=300, loss_probability=0.01,
        drawdown=-60.0,
    )
    assert recommendation_gate(scorecard, roi)["family_states"]["player_aces"]["tier"] \
        == "RESEARCH_ONLY"


def test_brier_route_still_graduates_a_sample_too_small_to_resample():
    from tennis_wc.props.strategy import recommendation_gate

    scorecard, roi = _gate_payloads(
        roi=0.28, settled=4, scorecard_n=65, loss_probability=None,
        model_brier=0.2380, market_brier=0.2480,
    )
    gate = recommendation_gate(scorecard, roi)

    state = gate["family_states"]["player_aces"]
    assert state["model_beats_market"] is True
    assert state["tier"] == "EARLY_MAIN"


def test_bootstrap_refuses_to_score_a_tiny_sample():
    from tennis_wc.props.settlement import (
        MIN_BOOTSTRAP_SAMPLE,
        bootstrap_loss_probability,
        running_drawdown,
    )

    winners = [(0.9, 1.0)] * (MIN_BOOTSTRAP_SAMPLE - 1)
    assert bootstrap_loss_probability(winners) is None
    assert bootstrap_loss_probability(winners + [(0.9, 1.0)]) == 0.0
    assert bootstrap_loss_probability([(-1.0, 1.0)] * MIN_BOOTSTRAP_SAMPLE) == 1.0
    # Drawdown is peak-to-trough on the settled order, not the final balance.
    assert running_drawdown([(1.0, 1.0), (-3.0, 1.0), (5.0, 1.0)]) == -3.0


def test_formal_candidate_probability_floor_reads_the_odds_blind_model():
    """The floor must test the same number the pricer selected on.

    `prob` is the market-blended value used for staking. Testing it here
    re-applies the market shrink at the recommendation step: on 2026-08-08 all
    three player_aces legs cleared quality and confidence and failed only this,
    the nearest by 0.003.
    """
    from tennis_wc.props import strategy

    gate = {
        "enabled_families": ["player_aces"],
        "family_states": {
            "player_aces": {
                "scorecard_settled": 200,
                "model_brier": 0.2380,
                "market_brier": 0.2480,
            }
        },
    }
    leg = {
        "market_key": "total_player_one_aces_7_5",
        "prob": 0.577,      # blended: under the 0.58 floor
        "prob_raw": 0.641,  # odds-blind model: over it
        "data_quality": 1.0,
        "odds": 1.76,
        "edge": 0.06,
        "ev": 0.08,
    }
    assert strategy.leg_is_formal_candidate(leg, gate)
    # A leg the raw model does NOT back is still refused.
    assert not strategy.leg_is_formal_candidate(leg | {"prob_raw": 0.52}, gate)
    # Payloads written before prob_raw existed keep the old behaviour.
    legacy = {key: value for key, value in leg.items() if key != "prob_raw"}
    assert not strategy.leg_is_formal_candidate(legacy, gate)


def test_raw_selected_probability_follows_the_backed_side():
    from tennis_wc.reports.daily_report import _raw_selected_probability
    from tennis_wc.props.ace_model import TwoWayProp

    over = TwoWayProp(
        match_id=1, market_key="k", scope="player", line=7.5, over_odds=1.9,
        under_odds=1.9, predicted_mean=8.0, model_prob_over=0.64,
        fair_prob_over=0.5, value_side="over", value_odds=1.9, edge=0.1,
        ev=0.2, blended_prob=0.55, tempered_prob_over=0.6, temper_strength=0.2,
    )
    assert _raw_selected_probability({"tw": over, "side": "over"}) == 0.64
    # Backing the other side inverts it rather than reusing the over figure.
    assert abs(_raw_selected_probability({"tw": over, "side": "under"}) - 0.36) < 1e-9
    assert _raw_selected_probability({"side": "over"}) is None


def test_selected_leg_never_sizes_to_zero_units():
    """A recommendation at 0u is a bet nobody can act on.

    Selection reads the odds-blind model while sizing reads the blended one, so
    a legitimately selected leg can land on a non-positive blended Kelly.
    """
    from tennis_wc.props import strategy

    # 0.559 * 1.77 = 0.989 -> Kelly is negative on the blended probability.
    assert strategy.formal_stake_units(0.559, 1.77, 79) == 0.0
    staked = strategy.formal_stake_units(0.559, 1.77, 79, early=True, selected=True)
    assert staked == strategy.STAKE_ROUND_UNITS
    assert staked <= strategy.MAX_EARLY_STAKE_UNITS
    # A positive-Kelly leg is unaffected by the flag.
    assert strategy.formal_stake_units(0.528, 2.06, 79, early=True, selected=True) == \
        strategy.formal_stake_units(0.528, 2.06, 79, early=True)
    # Confidence below the floor still refuses to stake at all.
    assert strategy.formal_stake_units(0.559, 1.77, 40, early=True, selected=True) == 0.0


def test_game_handicap_margin_is_unbiased_at_an_even_match():
    """An even match must predict a zero game margin, not a lean.

    The share equation is borrowed from player TOTAL games; reused for the
    MARGIN it returned -0.34 games at p=0.5, a standing bias against whichever
    player the fixture stores first.
    """
    from tennis_wc.props.player_model import game_handicap_cover_probability

    _, margin = game_handicap_cover_probability(0.0, 21.0, 0.5)
    assert margin == 0.0
    # Symmetric inputs must give mirrored margins.
    _, favoured = game_handicap_cover_probability(0.0, 21.0, 0.8)
    _, against = game_handicap_cover_probability(0.0, 21.0, 0.2)
    assert abs(favoured + against) < 1e-9
    assert favoured > 0
    # A pick-em match on a zero line is a coin flip after the shrink.
    cover, _ = game_handicap_cover_probability(0.0, 21.0, 0.5)
    assert abs(cover - 0.5) < 1e-9


def test_joint_simulator_exposes_first_set_match_and_game_margin_outcomes():
    from tennis_wc.props.match_simulator import simulate_match

    distribution = simulate_match(0.75, 0.75, trials=4000, dispersion=0.0)
    outcomes = distribution.first_set_match_outcomes()

    assert sum(outcomes.values()) == pytest.approx(1.0)
    assert outcomes["a_win"] == pytest.approx(outcomes["b_win"], abs=0.04)
    assert distribution.expected_first_set_margin() == pytest.approx(0.0, abs=0.20)
    assert (
        distribution.first_set_game_handicap_cover(-1.5, "a")
        + distribution.first_set_game_handicap_cover(1.5, "b")
    ) == pytest.approx(1.0)


def test_no_signal_predictions_do_not_reach_the_prop_models(tmp_path, monkeypatch):
    """P == 0.5000 exactly is the combiner saying it knows nothing.

    Seven of the nine families priced off that value as though it were a view:
    24.3% of stored predictions are exactly 0.5000.
    """
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.daily import _match_prob_map

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A")
    _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2, date="2026-08-08")
    _seed_match(conn, 2, 1, 2, date="2026-08-08")
    for match_id, probability in ((1, 0.5), (2, 0.62)):
        conn.execute(
            "INSERT INTO predictions (match_id, feature_set_version, "
            "selection_player_id, selection_name, model_probability, decision, "
            "stake_units, confidence, risk, pricing_json, created_at) "
            "VALUES (?, 'v1', 1, 'A', ?, 'NO_BET', 0, 'low', 'low', '{}', 'now')",
            (match_id, probability),
        )
    conn.commit()

    prob_map = _match_prob_map(conn, "2026-08-08")
    assert 1 not in prob_map, "the no-signal fallback must not be priced"
    assert prob_map[2] == 0.62


def test_count_prop_keeps_its_history_after_reading_the_value_limits():
    """Regression: the value limits were bound to the same name as the history.

    price_count_two_way takes a CountProfile; rebinding `profile` to the
    family's ValueProfile made every predicted_mean / history_n read below it
    an AttributeError. It stayed invisible because player_double_faults has
    never had a fixture with 10 prior matches, and price_ace_props_for_date
    does not catch per-prop exceptions -- one qualifying fixture would have
    taken down the whole day's board.
    """
    from tennis_wc.props.player_model import CountProfile, price_count_two_way

    history = CountProfile(1, 12, 3.0, tuple([3.0] * 8 + [1.0] * 4))
    prop = price_count_two_way(
        1, "player_double_faults_1_2_5", "player", 2.5, 1.90, 1.90, history
    )

    assert prop is not None
    assert prop.predicted_mean == 3.0
    assert prop.factors == {"history_n": 12, "history_mean": 3.0}


def test_ace_ladder_blends_on_the_learned_weight_like_every_other_family():
    """The ace ladder was the last path still on the fixed _MARKET_SHRINK.

    It kept 75% of the raw model while family_reliability had fitted 0.33 for
    player_aces -- and player_aces is the only family the gate lets bet.
    """
    from tennis_wc.props import ace_model

    model_p, market_fair, odds = 0.70, 0.50, 2.00
    legs = ace_model.price_ace_legs.__doc__
    assert "learned reliability" in legs

    from tennis_wc.props.calibration import blend_with_market

    # weight 0.33 must land nearer the market than the legacy 0.75 did.
    learned = blend_with_market(model_p, market_fair, 0.3328)
    legacy = (1 - ace_model._MARKET_SHRINK) * model_p + ace_model._MARKET_SHRINK * market_fair
    assert abs(learned - market_fair) < abs(legacy - market_fair)
    assert round(learned, 4) == 0.5666


def test_game_margin_slope_matches_the_measured_relationship():
    """The borrowed share curve implied ~6.1 games per unit of probability.

    Fitted on 1,241 settled matches the real figure is 11.26, and the market's
    own probability fits 11.17 on the same outcomes -- so it is a property of
    tennis, not of our model. At ~6.1 the model could not represent a one-sided
    scoreline at all, and the -6.5 and -7.5 lines returned -39% and -32%.
    """
    from tennis_wc.props.player_model import game_handicap_cover_probability

    total = 21.0
    _, low = game_handicap_cover_probability(0.0, total, 0.2)
    _, high = game_handicap_cover_probability(0.0, total, 0.8)
    slope = (high - low) / 0.6
    assert 10.5 <= slope <= 12.0, f"slope {slope:.2f} is off the measured 11.26"

    # Still unbiased and symmetric at a pick-em.
    _, even = game_handicap_cover_probability(0.0, total, 0.5)
    assert even == 0.0
    assert abs(low + high) < 1e-9

    # Margin does NOT scale with match length: a longer match is a CLOSER
    # match, and the fit carries no total-games term, so the slope is per unit
    # of probability alone.
    _, short_match = game_handicap_cover_probability(0.0, 16.0, 0.8)
    _, long_match = game_handicap_cover_probability(0.0, 30.0, 0.8)
    assert abs(long_match - short_match) < 1e-9

    # A one-sided scoreline is now reachable; 72.1% of matches finish beyond
    # the +/-3.1 games the old curve could express.
    _, extreme = game_handicap_cover_probability(0.0, total, 0.95)
    assert extreme > 4.5


def test_game_handicap_joint_variant_uses_fitted_hold_and_dispersion(monkeypatch):
    """The holdout-winning handicap variant is family-local: fitted holds plus
    match-day dispersion must not silently change every other prop family."""
    from tennis_wc.props import daily, match_simulator

    calls = {}
    sentinel = object()

    def fake_holds(_conn, _meta, _subject_id, *, use_fitted=None):
        calls["use_fitted"] = use_fitted
        return 0.81, 0.69

    def fake_simulate(hold_a, hold_b, *, trials, dispersion):
        calls.update(
            hold_a=hold_a, hold_b=hold_b, trials=trials, dispersion=dispersion
        )
        return sentinel

    monkeypatch.setattr(daily, "_holds_for", fake_holds)
    monkeypatch.setattr(match_simulator, "simulate_match", fake_simulate)

    distribution = daily._game_handicap_distribution(
        object(), {"player_a_id": 1}, 1, trials=1500
    )

    assert distribution is sentinel
    assert calls == {
        "use_fitted": True,
        "hold_a": 0.81,
        "hold_b": 0.69,
        "trials": 1500,
        "dispersion": match_simulator.FITTED_HOLD_GAP_DISPERSION,
    }


def test_player_games_joint_variant_uses_fitted_hold_and_dispersion(monkeypatch):
    from tennis_wc.props import daily, match_simulator

    calls = {}
    sentinel = object()

    def fake_holds(_conn, _meta, _subject_id, *, use_fitted=None):
        calls["use_fitted"] = use_fitted
        return 0.80, 0.70

    monkeypatch.setattr(daily, "_holds_for", fake_holds)

    def fake_simulate(hold_a, hold_b, *, trials, dispersion):
        calls.update(
            hold_a=hold_a, hold_b=hold_b, trials=trials, dispersion=dispersion
        )
        return sentinel

    monkeypatch.setattr(match_simulator, "simulate_match", fake_simulate)

    distribution = daily._player_games_distribution(
        object(), {"player_a_id": 1}, 1, trials=1500
    )

    assert distribution is sentinel
    assert calls == {
        "use_fitted": True,
        "hold_a": 0.80,
        "hold_b": 0.70,
        "trials": 1500,
        "dispersion": match_simulator.FITTED_HOLD_GAP_DISPERSION,
    }


def test_set_outcome_props_share_one_joint_distribution():
    """Win-a-set, set handicap and exact score are different reads of the
    same four mutually exclusive BO3 outcomes, not three fitted curves."""
    from tennis_wc.props import daily, player_model

    joint = daily._set_joint_probabilities(0.70)
    outcomes = joint["outcomes"]

    assert joint["win_a_set_a"] == 1.0 - outcomes["b20"]
    assert joint["win_a_set_b"] == 1.0 - outcomes["a20"]

    cover, _margin = player_model.set_handicap_cover_probability(
        -1.5, 0.70, outcome_probs=outcomes
    )
    assert cover == outcomes["a20"]

    exact = player_model.price_exact_set_score(
        1, "player_exact_set_score", 1, "A", 2, "B",
        {"a20": 3.0, "a21": 4.0, "b20": 5.0, "b21": 6.0},
        0.70,
        outcome_probs=outcomes,
    )
    assert exact is not None
    by_key = {
        (selection.player_id, selection.sets_lost): selection.model_prob
        for selection in exact.selections
    }
    assert by_key[(1, 0)] == round(outcomes["a20"], 4)
    assert by_key[(1, 1)] == round(outcomes["a21"], 4)
    assert by_key[(2, 0)] == round(outcomes["b20"], 4)
    assert by_key[(2, 1)] == round(outcomes["b21"], 4)


def test_roi_report_can_carve_out_a_holdout_window(tmp_path, monkeypatch):
    """A coefficient fitted on the early period must be scored on the late one.

    Without this the only available comparison grades a change on its own
    training data, which is how player_win_a_set showed +6.7% overall while
    losing 10.5% on the 119 bets it had never been fitted to.
    """
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import prop_roi_report

    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A")
    _seed_player(conn, 2, "B")
    for index, (day, status, pnl) in enumerate(
        (("2026-05-01", "WON", 0.9), ("2026-05-02", "WON", 0.9),
         ("2026-08-01", "LOST", -1.0), ("2026-08-02", "LOST", -1.0)),
        start=1,
    ):
        _seed_match(conn, index, 1, 2, date=day)
        conn.execute(
            "INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, "
            "market_key, line, selection, decimal_odds, model_prob, side, prop_scope, "
            "subject_player_id, stake_units, is_value, result_status, "
            "profit_loss_units, recorded_at, updated_at) "
            f"VALUES ('k{index}', {index}, '{day}', 'x', 'total_a_aces_5_5', 5.5, "
            f"'over', 1.9, 0.6, 'over', 'player', 1, 1.0, 1, '{status}', {pnl}, "
            "'now', 'now')"
        )
    conn.commit()

    everything = prop_roi_report(conn)["overall"]
    train = prop_roi_report(conn, as_of_date="2026-07-01")["overall"]
    holdout = prop_roi_report(conn, since_date="2026-07-01")["overall"]

    assert everything["settled"] == 4
    assert train["settled"] == 2 and train["roi"] > 0
    assert holdout["settled"] == 2 and holdout["roi"] < 0
    # The windows partition the record: no row counted twice or dropped.
    assert train["settled"] + holdout["settled"] == everything["settled"]


def test_itf_props_are_priced_but_never_staked():
    """Settleable is not the same as beatable.

    ITF became settleable earlier the same day and was opened for betting on
    that basis. Measured on 482 settled fixtures our match probability then
    scored Brier 0.2330 against the market's 0.1838, bootstrapped gap +0.0492
    with a 95% CI of [+0.035, +0.063] -- the market is measurably better
    informed there, so betting into it is a choice to pay the takeout.
    """
    from tennis_wc.props import daily

    assert daily._tier_of("ITF W35 Southaven USA") == "ITF"
    assert daily._tier_of("M15 Monastir Futures") == "ITF"
    assert daily._tier_of("ATP Challenger 75 Lexington") == "CHALLENGER"
    assert daily._tier_of("National Bank Open") == "TOUR"
    assert daily._tier_of(None) == "UNKNOWN"

    assert not daily._tier_bettable("ITF W15 Antalya")
    assert daily._tier_bettable("WTA Berlin")
    assert daily._tier_bettable("ATP Challenger 75 Lexington")
    # An allow-list, not a block-list. Blocking only ITF let the system's very
    # first recommendation be a UTR exhibition -- a tier that never reached the
    # 40-fixture minimum to be measured at all.
    assert daily._tier_of("UTR Men Kawaguchi JPN") == "UTR"
    assert not daily._tier_bettable("UTR Men Kawaguchi JPN")
    assert not daily._tier_bettable("")


def test_a_decayed_edge_does_not_graduate_on_its_old_streak():
    """Whole-record ROI cannot tell "profitable" from "was profitable".

    The out-of-sample split found player_win_a_set at +14.3% over its first 272
    bets and -3.2% over the next 86. A bootstrap over the whole record sees one
    healthy number and would have staked a streak that had already stopped.
    """
    from tennis_wc.props.strategy import recommendation_gate

    scorecard = {
        "settled": 800,
        "by_family": {
            "player_win_a_set": {
                "settled": 800,
                "model": {"brier": 0.30},
                "market": {"brier": 0.20},
            }
        },
    }

    def gate_for(recent_roi):
        return recommendation_gate(scorecard, {
            "by_family_formal_profile": {
                "player_win_a_set": {
                    "settled": 358, "roi": 0.10, "loss_probability": 0.02,
                    "max_drawdown_units": -3.0, "recent_settled": 119,
                    "recent_roi": recent_roi,
                }
            }
        })

    decayed = gate_for(-0.032)
    state = decayed["family_states"]["player_win_a_set"]
    assert state["recent_holds"] is False
    # It no longer graduates to a full or early stake -- but with 358 settled
    # bets and a credible whole-record profit it may still probe at one unit.
    # The recent number is the warning; the stake is the answer to it.
    assert state["tier"] == "PROBE"
    assert state["validated"] is False and state["early_main"] is False

    # No recent window recorded (too few bets) leaves the old behaviour intact.
    assert gate_for(None)["family_states"]["player_win_a_set"]["tier"] == "VALIDATED"


def test_full_stakes_need_a_credibly_profitable_recent_window():
    """Flat is not an edge, and the recent window is the more relevant data.

    The whole record already has to clear a bootstrap; applying a weaker
    "merely not losing" standard to the recent window would be inconsistent.
    player_win_a_set sits exactly on this line: +10.08% over 358 bets and
    +0.32% over its last 122.
    """
    from tennis_wc.props.strategy import recommendation_gate

    scorecard = {
        "settled": 800,
        "by_family": {
            "player_win_a_set": {
                "settled": 800,
                "model": {"brier": 0.30},
                "market": {"brier": 0.20},
            }
        },
    }

    def gate_for(recent_roi, recent_loss_probability):
        return recommendation_gate(scorecard, {
            "by_family_formal_profile": {
                "player_win_a_set": {
                    "settled": 358, "roi": 0.10, "loss_probability": 0.02,
                    "max_drawdown_units": -3.0, "recent_settled": 122,
                    "recent_roi": recent_roi,
                    "recent_loss_probability": recent_loss_probability,
                }
            }
        })

    flat = gate_for(0.0032, 0.44)
    state = flat["family_states"]["player_win_a_set"]
    assert state["recent_holds"] is True, "flat is not losing"
    assert state["recent_credible"] is False, "flat is not an edge either"
    assert state["tier"] == "EARLY_MAIN", "a half-unit probe, not full stakes"

    working = gate_for(0.08, 0.03)
    assert working["family_states"]["player_win_a_set"]["tier"] == "VALIDATED"


def test_player_games_constants_are_not_refitted_on_the_actual_total():
    """A refit that looks right on paper and loses in the pipeline.

    Fitted on 921 settled props the share curve comes back
    0.5027 + 0.2193*(P-0.5) with a 2.51-game residual, against the shipped
    0.4187 + 0.1465*P with 4.50. Every part of that looks like an improvement
    and none of it is: the residual was measured around share x the ACTUAL
    match total, while pricing only has the games model's ESTIMATE of it, so
    the two errors compound. Replayed, player_total_games' Brier went 0.2733 ->
    0.3036 with the new SD and 0.2802 with the slope and centre alone, against
    a market at 0.2482. The shipped constants stay until something beats them
    end to end rather than in isolation.
    """
    from tennis_wc.props import player_model as pm

    assert pm._PLAYER_GAMES_SD == 4.50
    assert pm._PLAYER_GAMES_MEAN_BIAS == 0.75

    total = 25.16
    _, even = pm.player_games_over_probability(9.5, total, 0.5)
    _, favourite = pm.player_games_over_probability(9.5, total, 0.8)
    assert favourite > even, "a favourite still wins more games"


def test_a_match_total_wearing_a_player_name_is_not_priced():
    """One player cannot win 29 games in a best-of-three.

    68 props reached the tracker with lines of 17.5 to 21.5 under a
    player_total_games market key and settled actual values up to 29. The serve
    simulator found them by inverting at both tails -- predicting 0.0-0.1 where
    66.7% landed -- and excluding them moved its holdout Brier from behind the
    shipped model to ahead of it.
    """
    from tennis_wc.props.daily import MAX_PLAYER_GAMES_LINE

    # A best-of-three winner takes at most 7+6+7 games.
    assert MAX_PLAYER_GAMES_LINE < 20
    # The dominant legitimate line, 12.5, and its neighbours must survive.
    assert MAX_PLAYER_GAMES_LINE > 13.5
    # The lines whose settled outcomes were physically impossible must not.
    for suspect in (17.5, 18.5, 19.5, 20.5, 21.5):
        assert suspect > MAX_PLAYER_GAMES_LINE


def test_early_tier_is_reachable_by_a_family_too_small_to_resample():
    """EARLY_MIN_FAMILY_SETTLED was 3 and unreachable.

    The bootstrap needs 20 bets, so a family with 3 to 19 could never satisfy
    credible_profit however it performed, and the early tier's own threshold
    was dead text. first_set_winner sat there at 15 bets and +33.5%.
    """
    from tennis_wc.props.strategy import recommendation_gate

    scorecard = {
        "settled": 500,
        "by_family": {
            "first_set_winner": {
                "settled": 500,
                "model": {"brier": 0.2367},   # does NOT beat the market
                "market": {"brier": 0.2030},
            }
        },
    }

    def gate_for(settled, roi, recent_roi, loss_probability):
        return recommendation_gate(scorecard, {
            "by_family_formal_profile": {
                "first_set_winner": {
                    "settled": settled, "roi": roi,
                    "loss_probability": loss_probability,
                    "max_drawdown_units": -2.0,
                    "recent_settled": settled, "recent_roi": recent_roi,
                    "recent_loss_probability": None,
                }
            }
        })

    thin = gate_for(15, 0.3353, 0.3353, None)
    assert thin["family_states"]["first_set_winner"]["tier"] == "EARLY_MAIN"

    # Still refused when the recent window has turned, however good the total.
    turned = gate_for(15, 0.3353, -0.05, None)
    assert turned["family_states"]["first_set_winner"]["tier"] == "RESEARCH_ONLY"

    # And once there ARE enough bets to resample, the bootstrap governs again.
    resampled = gate_for(40, 0.10, 0.05, 0.44)
    assert resampled["family_states"]["first_set_winner"]["tier"] == "RESEARCH_ONLY"


def test_every_priced_family_can_be_given_its_own_value_profile():
    """A registered ValueProfile must reach the pricer that decides value.

    ``first_set_winner`` could not be given one. Its Sportsbet market key is
    ``winner_related`` and the family only resolves once the market NAME is
    also in hand, so ``value_profile(market_key)`` inside ``price_head_to_head``
    landed on the default and any entry in ``VALUE_PROFILES`` was ignored --
    silently, because the default happened to be what it was already using.
    An A/B that raised the ceiling to 4.0 returned numbers identical to the
    baseline, which is the only way it showed up.
    """
    from tennis_wc.props import registry
    from tennis_wc.props.player_model import price_head_to_head

    # 3.20 / 1.30: player A is a 4.4-to-1 first-set outsider by the book and a
    # 40% chance by the model, so it is value at a 4.0 ceiling and not at 2.25.
    def priced(profile):
        original = registry.VALUE_PROFILES.get("first_set_winner")
        registry.VALUE_PROFILES["first_set_winner"] = profile
        try:
            return price_head_to_head(
                1, "winner_related", 10, "A", 11, "B", 3.20, 1.30, 0.40,
                model_weight=0.5, family="first_set_winner",
            )
        finally:
            if original is None:
                registry.VALUE_PROFILES.pop("first_set_winner", None)
            else:
                registry.VALUE_PROFILES["first_set_winner"] = original

    tight = priced(registry.ValueProfile(max_odds=2.25))
    assert tight.value_player_id is None, "2.25 ceiling must exclude a 3.20 shot"

    loose = priced(registry.ValueProfile(max_odds=4.0))
    assert loose.value_player_id == 10, (
        "a registered profile must reach the pricer -- it did not, because the "
        "family was resolved from Sportsbet's key alone"
    )


def test_the_family_of_a_market_needs_its_name_not_just_its_key():
    """The four keys where key-only resolution disagrees, pinned.

    Every other pricer synthesises its own market key so the family reads back
    from the key; these four arrive from the feed and do not.
    """
    from tennis_wc.props.registry import family_for_market

    for key, name, family in (
        ("winner_related", "Set 1 Winner", "first_set_winner"),
        ("set_betting", "Set Betting", "player_exact_set_score"),
        ("total_games", "Adam Walton Total Games 12.5", "player_total_games"),
        ("game_handicap", "Set 1 Game Handicap -1.5", "player_first_set_game_handicap"),
    ):
        assert family_for_market(key, name) == family
        assert family_for_market(key, "") != family, (
            f"{key} now resolves without its name; the guard in "
            "price_head_to_head can be revisited"
        )


def test_every_odds_grouping_helper_carries_the_feed_market_name():
    """The name is half the identity, and one helper was dropping it.

    Sportsbet reuses `winner_related` across several markets, so a closing-price
    lookup on key + selection alone finds the wrong one -- that is how a bet
    whose price had not moved reported +74.66% CLV. Every grouping helper must
    therefore carry the feed's market_name through, and on 2026-08-11
    `_head_to_head_odds` was the one that did not: all nine first_set_winner
    value bets that day had a partial identity and were skipped for CLV.
    """
    from tennis_wc.props import daily

    class Row(dict):
        def __getitem__(self, key):
            return self.get(key)

    rows = [
        Row(match_id=1, market_key="winner_related", market_name="Set 1 Winner",
            selection_name="Alice", line=None, odds=1.8),
        Row(match_id=1, market_key="winner_related", market_name="Set 1 Winner",
            selection_name="Bob", line=None, odds=2.1),
    ]
    meta = {"a_name": "Alice", "b_name": "Bob"}
    grouped = daily._head_to_head_odds(rows, meta)
    assert grouped, "the fixture should group"
    bucket = next(iter(grouped.values()))
    assert bucket["market_name"] == "Set 1 Winner"
    assert bucket["a_name"] == "Alice" and bucket["b_name"] == "Bob"
    assert daily._feed_identity(bucket, "winner_related", "a") == (
        "winner_related", "Set 1 Winner", "Alice", None
    )

    joint = daily._first_set_match_odds([
        Row(match_id=1, market_key="to_win_1st_set_and_win_match",
            market_name="To win 1st set and win match",
            selection_name="Alice Yes", selection_side="player_a", line=None, odds=2.0),
        Row(match_id=1, market_key="to_win_1st_set_and_win_match",
            market_name="To win 1st set and win match",
            selection_name="Bob Yes", selection_side="player_b", line=None, odds=2.8),
        Row(match_id=1, market_key="to_lose_1st_set_and_win_match",
            market_name="To lose 1st set and win match",
            selection_name="Alice Yes", selection_side="player_a", line=None, odds=7.0),
        Row(match_id=1, market_key="to_lose_1st_set_and_win_match",
            market_name="To lose 1st set and win match",
            selection_name="Bob Yes", selection_side="player_b", line=None, odds=6.0),
    ], meta)
    assert set(joint[1]) >= {"a_win", "a_lose", "b_win", "b_lose"}
    assert joint[1]["a_win"]["selection_name"] == "Alice Yes"

    # And the other three helpers, so this cannot regress in one of them alone.
    two_way = daily._two_way_odds([
        Row(match_id=1, market_key="total_games", market_name="Alice Total Games 10.5",
            selection_name="Over 10.5", line=10.5, odds=1.9),
    ])
    assert next(iter(two_way.values()))["market_name"] == "Alice Total Games 10.5"

    yes_no = daily._yes_no_odds([
        Row(match_id=1, market_key="win_a_set", market_name="Alice to win a set",
            selection_name="Alice Yes", line=None, odds=1.5),
    ])
    assert next(iter(yes_no.values()))["market_name"] == "Alice to win a set"


def test_the_registered_value_profiles_are_exactly_these():
    """A profile that appears without a measurement must fail the suite.

    On 2026-08-10 an entry appeared in VALUE_PROFILES mid-session that nobody
    in the session wrote -- `first_set_winner: _UNDERDOG_PROFILE`, a 6.0
    ceiling -- and it contradicted the measurement taken that day: past 4.0 the
    eight settled props claimed 0.37-0.55 against a market-implied 0.17-0.23 and
    went 0 for 8. It was overwritten with the measured 4.0.

    Its origin was never established. No hook, no other agent referencing
    VALUE_PROFILES, no editor artefact, and the two sibling worktrees were six
    days stale and are separate directories. So this pins the table instead: the
    next unexplained change to what may be staked breaks the build rather than
    shipping quietly.

    Changing a number here is fine. Changing it without changing this test, and
    without a measurement in the commit, is the thing being prevented.
    """
    from tennis_wc.props.registry import (
        DEFAULT_VALUE_PROFILE, VALUE_PROFILES, value_profile_for_family,
    )

    assert DEFAULT_VALUE_PROFILE.min_edge == 0.06, (
        "the default edge floor is a measured value: ROI rises monotonically "
        "with the size of the disagreement and the 0.04-0.08 band was the only "
        "losing one, in both windows and in four of five families"
    )
    assert set(VALUE_PROFILES) == {
        "player_win_a_set", "player_game_handicap", "first_set_winner",
    }, "a family gained or lost a registered profile"

    first_set = value_profile_for_family("first_set_winner")
    assert (first_set.max_odds, first_set.min_probability) == (4.0, 0.0), (
        "4.0 is where the model stops finding value and starts disagreeing; "
        "0.0 is so the gate judges the same 58 bets the pricer stakes"
    )
    underdog = value_profile_for_family("player_win_a_set")
    assert (underdog.max_odds, underdog.min_probability) == (6.0, 0.0)
    assert value_profile_for_family("player_game_handicap") == underdog


def test_a_family_that_earned_its_tier_is_still_held_back_off_the_allowlist():
    """2.1's decision: earning a tier is not the same as being staked on day one.

    player_game_handicap clears the evidence gate and is half of all exposure --
    and it is the half that loses out of sample (-4.13% over the later window).
    Excluding the largest family is the point, not an oversight.
    """
    from tennis_wc.props import strategy

    scorecard = {
        "settled": 200,
        "by_family": {"player_game_handicap": {
            "settled": 200, "model": {"brier": 0.19}, "market": {"brier": 0.21}}},
    }
    roi = {
        "overall": {"settled": 600, "roi": 0.11},
        "by_family_formal_profile": {"player_game_handicap": {
            "settled": 590, "roi": 0.1145, "loss_probability": 0.01,
            "max_drawdown_units": -10.0, "recent_settled": 98,
            "recent_roi": -0.0413, "recent_loss_probability": 0.6}},
    }
    gate = strategy.recommendation_gate(scorecard, roi)
    state = gate["family_states"]["player_game_handicap"]

    assert state["earned_tier"] is True
    assert state["on_live_allowlist"] is False
    assert "not on the go-live allowlist" in state["held_back_reason"]
    assert "player_game_handicap" not in gate["enabled_families"]
    assert gate["held_back_by_allowlist"] == ["player_game_handicap"]
    # Loud, not silent: a family that disappears from the card without a reason
    # is indistinguishable from a family that stopped producing bets.
    assert any("上線白名單" in warning for warning in gate["warnings"])


def test_the_allowlist_names_exactly_the_two_families_decided_on():
    """Pinned so widening it is a deliberate edit with a reason, not a drift."""
    from tennis_wc.props.strategy import LIVE_FAMILIES, LIVE_FAMILY_NOTES

    assert LIVE_FAMILIES == frozenset({"player_win_a_set", "first_set_winner"})
    assert set(LIVE_FAMILY_NOTES) == LIVE_FAMILIES


def test_an_unknown_or_missing_family_is_never_staked():
    from tennis_wc.props.strategy import family_may_be_staked

    assert family_may_be_staked("player_win_a_set") is True
    assert family_may_be_staked("player_game_handicap") is False
    assert family_may_be_staked("player_first_set_game_handicap") is False
    assert family_may_be_staked("player_first_set_match") is False
    assert family_may_be_staked(None) is False
    assert family_may_be_staked("") is False


def test_the_stop_rule_numbers_are_pinned():
    """Pre-registered 2026-08-11. A stop that can drift is not pre-registered."""
    from tennis_wc.props import strategy

    assert strategy.LIVE_STOP_DRAWDOWN_UNITS == -20.0
    assert strategy.LIVE_REVIEW_AFTER_SETTLED == 200
    assert strategy.LIVE_INTERIM_CHECK_SETTLED == 100
    assert strategy.LIVE_INTERIM_MIN_ROI == -0.10
    assert strategy.LIVE_UNIT_VALUE_AUD == 1.0
    assert strategy.live_stake_aud(0.5) == 0.5


def test_the_hard_stop_fires_on_drawdown_and_names_the_number():
    from tennis_wc.props.strategy import live_stop_state

    state = live_stop_state(settled=150, pnl_units=-12.0,
                            max_drawdown_units=-20.5, roi=-0.08)
    assert state["action"] == "STOP"
    assert "-20.0u" in state["breaches"][0]
    assert "20.50u" in state["breaches"][0].replace("-", "")


def test_the_interim_tripwire_pauses_rather_than_stops():
    from tennis_wc.props.strategy import live_stop_state

    state = live_stop_state(settled=100, pnl_units=-11.0,
                            max_drawdown_units=-12.0, roi=-0.11)
    assert state["action"] == "PAUSE"
    assert "mechanical fault" in state["breaches"][0]


def test_the_tripwire_does_not_fire_before_its_bet_count():
    """99 bets at -11% is noise. The checkpoint exists to catch faults, and
    firing it early trains you to ignore it."""
    from tennis_wc.props.strategy import live_stop_state

    state = live_stop_state(settled=99, pnl_units=-11.0,
                            max_drawdown_units=-12.0, roi=-0.11)
    assert state["action"] == "CONTINUE"
    assert state["breaches"] == []


def test_a_healthy_book_continues_and_counts_down_to_the_review():
    from tennis_wc.props.strategy import live_stop_state

    state = live_stop_state(settled=120, pnl_units=+8.0,
                            max_drawdown_units=-5.0, roi=0.13)
    assert state["action"] == "CONTINUE"
    assert state["review_due"] is False
    assert state["bets_until_review"] == 80


def test_the_drawdown_limits_are_two_different_books():
    """MAX_FAMILY_DRAWDOWN_UNITS is the flat-1u research book; the live stop is
    the 0.5u book. Comparing them unscaled is the mistake check_stop_rule.py
    made in its first version, so the relationship is asserted rather than
    trusted to a comment."""
    from tennis_wc.props import strategy

    assert strategy.RESEARCH_STAKE_UNITS == 1.0
    assert strategy.MAX_EARLY_STAKE_UNITS < strategy.RESEARCH_STAKE_UNITS
    # -18.27u recorded on the research book is -9.13u at the live cap, which is
    # inside the -20u stop. The unscaled number would read as nearly stopping.
    recorded = -18.27
    at_live_stake = recorded * strategy.MAX_EARLY_STAKE_UNITS / strategy.RESEARCH_STAKE_UNITS
    assert at_live_stake > strategy.LIVE_STOP_DRAWDOWN_UNITS
    assert round(at_live_stake, 2) == -9.13
