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


# --------------------------------------------------------------------------- #
# Settlement
# --------------------------------------------------------------------------- #
def _rec(conn, settlement, *, line, selection, side, odds, model_p, market_p,
         market_key="total_aces_in_the_match", scope="match", subject=None,
         stake=1.0, value=True, match_id=1):
    settlement.record_prop(
        conn, match_id=match_id, match_date="2026-01-01", match_label="A vs B",
        market_key=market_key, line=line, selection=selection, side=side,
        prop_scope=scope, subject_player_id=subject, decimal_odds=odds,
        model_prob=model_p, market_prob_fair=market_p, blended_prob=model_p,
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
