import sqlite3
from datetime import datetime, timezone

import pytest

import tennis_wc.featured as F


def cand(prop_id, match_id, edge, ev=0.05, odds=2.0):
    return F.Candidate(
        prop_id=prop_id, match_id=match_id, market_key="player_game_handicap_2.5",
        selection="X +2.5", match_label=f"M{match_id}", start_time_utc="2026-11-07T10:00:00Z",
        odds=odds, edge=edge, ev=ev, model_prob=0.6,
    )


def test_one_pick_per_match_highest_edge():
    picks = F.choose([cand(1, 1, 0.10), cand(2, 1, 0.20), cand(3, 1, 0.15)], set(), 10)
    assert [p.prop_id for p in picks] == [2]


def test_tie_break_edge_then_ev_then_odds():
    same_edge = [cand(1, 1, 0.1, ev=0.05), cand(2, 1, 0.1, ev=0.07)]
    assert F.choose(same_edge, set(), 10)[0].prop_id == 2
    same_ev = [cand(1, 1, 0.1, ev=0.05, odds=1.8), cand(2, 1, 0.1, ev=0.05, odds=2.2)]
    assert F.choose(same_ev, set(), 10)[0].prop_id == 2


def test_cap_and_ordering():
    many = [cand(i, i, edge=i / 100) for i in range(1, 16)]
    picks = F.choose(many, set(), 10)
    assert len(picks) == 10
    assert [p.match_id for p in picks] == list(range(15, 5, -1))


def test_zero_is_allowed():
    assert F.choose([], set(), 10) == []
    assert F.choose([cand(1, 1, 0.3)], set(), 0) == []


def test_top_up_only_adds_new_matches():
    picks = F.choose([cand(1, 1, 0.9), cand(2, 2, 0.1)], {1}, 3)
    assert [p.match_id for p in picks] == [2]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prop_tracker (id INTEGER PRIMARY KEY, result_status TEXT, actual_value REAL)")
    return c


def test_record_freezes_and_respects_daily_cap(conn, monkeypatch):
    now = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(F, "candidates", lambda c, d, n: [cand(i, i, i / 100) for i in range(1, 8)])
    first = F.record(conn, "2026-11-07", "21:00", now)
    assert [r["rank"] for r in first] == list(range(1, 8))
    # A later pass sees better prices for featured matches plus five new matches.
    monkeypatch.setattr(
        F, "candidates",
        lambda c, d, n: [cand(100 + i, i, 0.99, odds=9.0) for i in range(1, 8)]
        + [cand(200 + i, 50 + i, 0.5) for i in range(5)],
    )
    second = F.record(conn, "2026-11-07", "23:00", now)
    assert len(second) == 3  # cap of ten
    assert [r["rank"] for r in second] == [8, 9, 10]
    frozen = conn.execute("SELECT odds FROM featured_picks WHERE match_id = 1").fetchone()[0]
    assert frozen == 2.0
    assert F.record(conn, "2026-11-07", "09:00", now) == []


def test_profit_uses_frozen_odds(conn, monkeypatch):
    now = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(F, "candidates", lambda c, d, n: [cand(1, 1, 0.2, odds=2.5), cand(2, 2, 0.1)])
    F.record(conn, "2026-11-07", "21:00", now)
    conn.execute("INSERT INTO prop_tracker VALUES (1, 'WON', 1), (2, 'LOST', 0)")
    rows = F.picks_with_results(conn)
    assert [r["unit_profit"] for r in rows] == [1.5, -1.0]
    perf = F.performance(rows)
    assert perf["settled"] == 2 and perf["pnl"] == 0.5 and perf["ci_low"] is None


def test_void_and_pending_are_not_settled():
    rows = [
        {"result_status": "VOID", "unit_profit": 0.0},
        {"result_status": "PENDING", "unit_profit": None},
        {"result_status": "WON", "unit_profit": 1.0},
    ]
    perf = F.performance(rows)
    assert perf["settled"] == 1 and perf["pending"] == 1


def test_forward_verdict_rules():
    base = {"settled": 249, "ci_low": 0.01, "ci_high": 0.2}
    assert F.forward_verdict(base) is None
    assert F.forward_verdict(base | {"settled": 250}) == "ELIGIBLE_FOR_RELEASE_REVIEW"
    assert F.forward_verdict({"settled": 250, "ci_low": -0.3, "ci_high": -0.01}) == "REJECT"
    assert F.forward_verdict({"settled": 250, "ci_low": -0.1, "ci_high": 0.1}) == "CONTINUE_TO_600"
    assert F.forward_verdict({"settled": 600, "ci_low": -0.1, "ci_high": 0.1}) == "NOT_PROVEN"


def test_paused_families_are_not_featured():
    from tennis_wc.props.registry import family_for_market

    for key in ("player_aces_123", "player_double_faults_9", "player_exact_set_score_4"):
        assert family_for_market(key) not in F.FAMILIES
    for key in ("player_game_handicap_2.5", "first_set_winner_3075", "player_win_a_set_582"):
        assert family_for_market(key) in F.FAMILIES
