from __future__ import annotations

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


def test_prop_strategy_enables_only_proven_family_and_filters_longshots():
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
    assert family_for_market("game_handicap", "Set 1 Game Handicap -1.5") == "game_handicap"
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
    assert out == {"graded": 0, "voided": 1, "still_pending": 0}
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
        over_odds=2.4, under_odds=1.55, predicted_mean=12.0,
        curve=ace_model.MATCH_ACE_CURVE,
    )
    assert tw is not None and tw.value_side is not None  # a clear value side exists
    stripped = _strip_value(tw)
    assert stripped.value_side is None
    assert stripped.value_odds is None
    assert stripped.edge == 0.0
    assert stripped.ev <= 0.0


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
