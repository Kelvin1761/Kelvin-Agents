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
def test_settlement_grades_from_score_json(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement
    init_db()
    conn = get_connection()
    _seed_player(conn, 1, "A")
    _seed_player(conn, 2, "B")
    _seed_match(conn, 1, 1, 2)
    conn.execute("INSERT INTO match_results (match_id, winner_player_id, source_provider, created_at, score_json) VALUES (1,1,'t','now', ?)",
                 ('{"player_a_aces": 8, "player_b_aces": 5}',))
    conn.commit()
    assert settlement.actual_total_aces(conn, 1) == 13.0
    # record a winning 7+ and a losing 15+
    settlement.record_prop(conn, match_id=1, match_date="2026-01-01", match_label="A vs B",
                           market_key="total_aces_in_the_match", line=7.0, selection="7+",
                           decimal_odds=1.5, model_prob=0.7, market_prob_fair=0.72,
                           blended_prob=0.71, edge=-0.01, ev=0.05, predicted_mean=13.0,
                           stake_units=1.0, is_value=True)
    settlement.record_prop(conn, match_id=1, match_date="2026-01-01", match_label="A vs B",
                           market_key="total_aces_in_the_match", line=15.0, selection="15+",
                           decimal_odds=6.0, model_prob=0.2, market_prob_fair=0.22,
                           blended_prob=0.21, edge=-0.01, ev=0.05, predicted_mean=13.0,
                           stake_units=1.0, is_value=True)
    out = settlement.settle_props(conn)
    assert out["graded"] == 2
    roi = settlement.prop_roi_report(conn)
    assert roi["settled"] == 2 and roi["wins"] == 1
    # 7+ won (+0.5u), 15+ lost (-1u) -> pnl -0.5u
    assert abs(roi["pnl"] + 0.5) < 1e-6


def test_record_prop_idempotent(tmp_path, monkeypatch):
    from conftest import configure_test_db
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props import settlement
    init_db()
    conn = get_connection()
    for _ in range(3):
        settlement.record_prop(conn, match_id=1, match_date="2026-01-01", match_label="A vs B",
                               market_key="total_aces_in_the_match", line=7.0, selection="7+",
                               decimal_odds=1.5, model_prob=0.7, market_prob_fair=0.72,
                               blended_prob=0.71, edge=-0.01, ev=0.05, predicted_mean=13.0,
                               stake_units=1.0, is_value=True)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM prop_tracker").fetchone()[0]
    assert n == 1, "same prop_key must upsert, not duplicate"
