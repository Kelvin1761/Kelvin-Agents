import json
import sqlite3
from datetime import datetime, timezone

import pytest

import tennis_wc.select.featured as F
import tennis_wc.select.featured_shadow as S


def cand(prop_id, match_id, edge, odds=2.0):
    return F.Candidate(prop_id=prop_id, match_id=match_id, market_key="first_set_winner_1",
                       selection="A", match_label=f"M{match_id}", start_time_utc="2026-11-07T01:00:00Z",
                       odds=odds, edge=edge, ev=0.05, model_prob=0.5)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prop_tracker (id INTEGER PRIMARY KEY, result_status TEXT, actual_value REAL)")
    return c


NOW = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)


def test_cap3_drops_long_prices_and_takes_next_best_in_match(conn):
    pool = [cand(1, 1, 0.40, odds=3.0), cand(2, 1, 0.10, odds=1.8), cand(3, 2, 0.30, odds=4.5)]
    added = S.record(conn, "2026-11-07", "21:00", NOW, candidates=pool)["cap3"]
    assert [r["prop_id"] for r in added] == [2]  # 3.0 itself is excluded; match 2 has nothing under 3


def test_shadow_is_independent_of_real_featured_and_frozen(conn):
    F.ensure_schema(conn)
    pool = [cand(1, 1, 0.40, odds=3.5), cand(2, 1, 0.10, odds=1.8)]
    S.record(conn, "2026-11-07", "21:00", NOW, candidates=pool)
    # Later pass: better price on the same match must not replace the frozen shadow pick.
    again = S.record(conn, "2026-11-07", "23:00", NOW, candidates=[cand(9, 1, 0.9, odds=2.0)])
    assert again["cap3"] == []
    assert conn.execute("SELECT count(*) FROM featured_picks").fetchone()[0] == 0
    assert conn.execute("SELECT prop_id FROM featured_shadow_picks").fetchone()[0] == 2


def test_daily_cap_applies_per_arm(conn):
    pool = [cand(i, i, i / 100) for i in range(1, 15)]
    assert len(S.record(conn, "2026-11-07", "21:00", NOW, candidates=pool)["cap3"]) == F.MAX_PER_DAY


def test_results_and_performance(conn):
    S.record(conn, "2026-11-07", "21:00", NOW, candidates=[cand(1, 1, 0.2, odds=2.5), cand(2, 2, 0.1)])
    conn.executemany("INSERT INTO prop_tracker VALUES (?,?,NULL)", [(1, "WON"), (2, "LOST")])
    perf = F.performance(S.picks_with_results(conn, "cap3"))
    assert perf["settled"] == 2 and perf["pnl"] == pytest.approx(0.5)


def test_milestone_sends_once_per_arm(tmp_path, monkeypatch, conn):
    import tennis_wc.publish.telegram as T
    import tennis_wc.store.db as db
    from contextlib import contextmanager

    S.record(conn, "2026-11-07", "21:00", NOW, candidates=[cand(1, 1, 0.2)])
    rows = [{"match_date": "2026-11-07", "result_status": "WON", "unit_profit": 1.0}] * 250

    @contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(db, "get_connection", fake_conn)
    monkeypatch.setattr(S, "picks_with_results", lambda c, arm: rows)
    sent = []
    monkeypatch.setattr(T, "notify", lambda msg, audience: sent.append((msg, audience)) or True)
    assert T.shadow_forward_milestones(tmp_path)["cap3"] == "ELIGIBLE_FOR_RELEASE_REVIEW"
    assert T.shadow_forward_milestones(tmp_path)["cap3"] is None
    assert len(sent) == 1 and sent[0][1] == "primary" and "cap3" in sent[0][0]
    assert "cap3:250" in json.loads((tmp_path / T.FORWARD_STATE).read_text())
