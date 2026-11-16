import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import tennis_wc.select.featured as F
import tennis_wc.select.sharp_forward as SF
import tennis_wc.sources.betfair_prices as BF

# 21:05 Sydney (AEDT, UTC+11) on 2026-11-16
DECISION = datetime(2026, 11, 16, 10, 5, tzinfo=timezone.utc)
START = "2026-11-17T02:00:00Z"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, match_date TEXT, start_time_utc TEXT,
            player_a_id INTEGER, player_b_id INTEGER, fixture_status TEXT DEFAULT 'ACTIVE');
        CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, match_id INTEGER, bookmaker TEXT, market TEXT,
            player_a_odds REAL, player_b_odds REAL, fetched_at TEXT);
        CREATE TABLE match_results (match_id INTEGER, winner_player_id INTEGER, source_provider TEXT);
        INSERT INTO players VALUES (1, 'Tristan Schoolkate'), (2, 'Carl Emil Overbeck');
        INSERT INTO matches VALUES (10, '2026-11-17', '2026-11-17T02:00:00Z', 1, 2, 'ACTIVE');
    """)
    SF.ensure_schema(c)
    return c


def sb(conn, fetched, a, b, sid=None):
    conn.execute("INSERT INTO odds_snapshots (id, match_id, bookmaker, market, player_a_odds, player_b_odds, fetched_at) "
                 "VALUES (?, 10, 'Sportsbet', 'match_winner', ?, ?, ?)", (sid, a, b, BF.iso(fetched)))


def market(runners=("Carl Emil Overbeck", "Tristan Schoolkate"), start=START, mid="1.1"):
    return {"marketId": mid, "marketStartTime": start.replace("Z", ".000Z"), "event": {"name": "x"},
            "competition": {"name": "Sydney Challenger"},
            "runners": [{"selectionId": 100 + i, "runnerName": n, "sortPriority": i + 1} for i, n in enumerate(runners)]}


def book(mid, a_back, a_lay, b_back, b_lay, inplay=False):
    lad = lambda p: [{"price": p}] if p else []
    return {"marketId": mid, "status": "OPEN", "inplay": inplay, "isMarketDataDelayed": True,
            "runners": [{"selectionId": 100, "ex": {"availableToBack": lad(a_back), "availableToLay": lad(a_lay)}},
                        {"selectionId": 101, "ex": {"availableToBack": lad(b_back), "availableToLay": lad(b_lay)}}]}


def fake_rpc(markets, books):
    def rpc(method, params):
        return markets if method == "listMarketCatalogue" else [b for b in books if b["marketId"] in params["marketIds"]]
    return rpc


def test_doubles_are_skipped_and_unchanged_prices_extend_one_row(conn):
    m, d = market(), market(("A/B", "C/D"), mid="1.2")
    rpc = fake_rpc([m, d], [book("1.1", 2.5, 2.6, 1.6, 1.62)])
    BF.snapshot(conn, DECISION, rpc)
    out = BF.snapshot(conn, DECISION + timedelta(minutes=15), rpc)
    assert out == {"markets": 1, "new": 0, "unchanged": 1, "missing": 0}
    rows = conn.execute("SELECT fetched_at, last_seen_at FROM betfair_price_snapshots").fetchall()
    assert len(rows) == 1 and rows[0]["last_seen_at"] == BF.iso(DECISION + timedelta(minutes=15))


def test_fair_needs_a_tight_two_sided_book():
    assert BF.fair_a({"a_back": 2.0, "a_lay": 2.02, "b_back": 1.98, "b_lay": 2.0, "in_play": 0}) == pytest.approx(0.4975, abs=1e-3)
    assert BF.fair_a({"a_back": 2.0, "a_lay": 2.4, "b_back": 1.6, "b_lay": 1.62, "in_play": 0}) is None
    assert BF.fair_a({"a_back": 2.0, "a_lay": 2.02, "b_back": 1.98, "b_lay": 2.0, "in_play": 1}) is None


def test_decision_uses_21_00_snapshot_maps_swapped_runners_and_freezes(conn):
    sb(conn, DECISION - timedelta(hours=3), 2.9, 1.40)   # 18:05 Sydney: not a decision snapshot
    sb(conn, DECISION, 1.70, 2.20)                        # 21:05 Sydney: the decision
    # Betfair runner A is Overbeck (our B). Overbeck ~ 2.55 mid, Schoolkate ~1.61 mid.
    BF.snapshot(conn, DECISION, fake_rpc([market()], [book("1.1", 2.5, 2.6, 1.6, 1.62)]))
    assert SF.record(conn, DECISION + timedelta(minutes=10))["ready"] == 0  # tolerance window still open
    out = SF.record(conn, DECISION + timedelta(minutes=25))
    assert out["decided"] == 1 and out["bets"] == 1
    row = dict(conn.execute("SELECT * FROM sharp_forward_picks").fetchone())
    assert row["betfair_orientation"] == "swapped" and row["side"] == "a" and row["odds"] == 1.70
    assert row["p_a"] == pytest.approx((1 / 1.61) / (1 / 1.61 + 1 / 2.55), abs=1e-6)
    # Prices move later and Sportsbet re-quotes: the decision never changes.
    sb(conn, DECISION + timedelta(hours=1), 1.30, 3.50)
    BF.snapshot(conn, DECISION + timedelta(hours=1), fake_rpc([market()], [book("1.1", 4.0, 4.1, 1.3, 1.32)]))
    assert SF.record(conn, DECISION + timedelta(hours=2))["ready"] == 0
    assert conn.execute("SELECT COUNT(*), MAX(odds) FROM sharp_forward_picks").fetchone()[:] == (1, 1.70)


def test_no_edge_is_recorded_as_no_bet(conn):
    sb(conn, DECISION, 1.55, 2.30)
    BF.snapshot(conn, DECISION, fake_rpc([market()], [book("1.1", 2.5, 2.6, 1.6, 1.62)]))
    out = SF.record(conn, DECISION + timedelta(minutes=25))
    assert out == {"ready": 1, "no_market": 0, "no_price": 0, "decided": 1, "bets": 0}
    assert SF.decision_counts(conn) == {"decisions": 1, "bets": 0}


def test_settlement_clv_and_disagreeing_results(conn):
    sb(conn, DECISION, 1.70, 2.20)
    BF.snapshot(conn, DECISION, fake_rpc([market()], [book("1.1", 2.5, 2.6, 1.6, 1.62)]))
    SF.record(conn, DECISION + timedelta(minutes=25))
    BF.snapshot(conn, DECISION + timedelta(hours=5), fake_rpc([market()], [book("1.1", 3.0, 3.05, 1.48, 1.5)]))
    conn.execute("INSERT INTO match_results VALUES (10, 1, 'espn')")
    rows = SF.picks_with_results(conn)
    assert rows[0]["result_status"] == "WON" and rows[0]["unit_profit"] == pytest.approx(0.70)
    p_close = (1 / 1.49) / (1 / 1.49 + 1 / 3.025)
    assert rows[0]["clv"] == pytest.approx(1.70 * p_close - 1, abs=1e-6)
    conn.execute("INSERT INTO match_results VALUES (10, 2, 'tennisexplorer')")
    assert SF.picks_with_results(conn)[0]["result_status"] is None


def test_verdict_rules():
    base = {"settled": 1000, "ci_low": 0.01, "ci_high": 0.08}
    assert SF.verdict({**base, "settled": 299}) is None
    assert SF.verdict({**base, "settled": 300, "ci_low": -0.05}) == "INTERIM_CONTINUE"
    assert SF.verdict({**base, "settled": 300, "ci_low": -0.2, "ci_high": -0.01}) == "REJECT"
    assert SF.verdict(base) == "ELIGIBLE_FOR_RELEASE_REVIEW"
    assert SF.verdict({**base, "ci_low": -0.01}) == "NOT_PROVEN"


def test_milestone_sends_once(tmp_path, monkeypatch, conn):
    from contextlib import contextmanager

    import tennis_wc.publish.telegram as T
    import tennis_wc.store.db as db

    @contextmanager
    def fake_conn():
        yield conn

    rows = [{"result_status": "WON", "unit_profit": 1.0, "clv": 0.02}] * 300
    monkeypatch.setattr(db, "get_connection", fake_conn)
    monkeypatch.setattr(SF, "picks_with_results", lambda c: rows)
    sent = []
    monkeypatch.setattr(T, "notify", lambda text, audience="primary": sent.append(audience) or True)
    assert T.sharp_forward_milestone(tmp_path) == "INTERIM_CONTINUE"
    assert T.sharp_forward_milestone(tmp_path) is None
    assert sent == ["primary"]


def test_tick_reports_betfair_errors_without_dying(conn):
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "tennis_betfair_tick.py"
    spec = importlib.util.spec_from_file_location("tick", path)
    tick = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(tick)
    finally:
        sys.path.remove(str(path.parent))

    def boom(c):
        raise RuntimeError("no session")

    out = tick.run_tick(conn, snapshot=boom, record=lambda c: {"decided": 0})
    assert out["betfair_error"].startswith("RuntimeError") and out["decisions"] == {"decided": 0}


def test_loose_name_match_handles_trimmed_surnames():
    assert SF._orientation("Guiomar Maristany   Zuleta", "Martina Trevisan",
                           "Martina Trevisan", "Guiomar Maristany Zuleta De Reales") == "swapped"
    assert SF._orientation("Maria Garcia", "Gaia Maduzzi", "Maria Garcia Cid", "Anna Maduzzi") is None
