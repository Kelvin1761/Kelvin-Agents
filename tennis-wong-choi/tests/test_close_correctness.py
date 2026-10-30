"""Correctness fixes of 2026-10-14 (T0a/T0b/T0c). Every test runs on a temp DB.

T0a: the match-winner CLOSE is the last snapshot strictly before the start;
     no pre-start snapshot means a NULL close with a reason, never a newer
     (in-running) price.
T0b: degraded sources (rankings served from cache, history CSV 404) are no
     longer silent; the health line always prints the source-error count.
T0c: every evaluated prop gets its earliest pre-start price and pre-start close
     logged, without changing which props reach clv_tracker.
"""
from __future__ import annotations

import pytest

START = "2026-08-11T12:00:00Z"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db

    path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (1,'A','ATP','test','now','now'), (2,'B','ATP','test','now','now')"""
    )
    conn.commit()
    assert "tennis_wc_test.db" in str(path)
    return conn


def _match(conn, match_id: int, start: str | None = START, date: str = "2026-08-11"):
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (?,?,'ATP',?,1,1,2,'R1','test','now','now',?)""",
        (match_id, f"M{match_id}", date, start),
    )


def _odds(conn, match_id: int, fetched: str, a: float, b: float):
    conn.execute(
        """INSERT INTO odds_snapshots (event_id, match_id, bookmaker, market,
               player_a_odds, player_b_odds, source_provider, raw_response_id,
               fetched_at, created_at)
           VALUES (?, ?, 'sportsbet', 'h2h', ?, ?, 'sportsbet', 0, ?, ?)""",
        (f"E{match_id}", match_id, a, b, fetched, fetched),
    )


def _tracker(conn, match_id: int, odds_taken: float = 2.0, clv=None, closing=None):
    conn.execute(
        """INSERT INTO clv_tracker (recommendation_type, source_id, match_id, match_date,
               selection_name, selection_side, market_key, market_name, tier,
               odds_taken, closing_odds, clv, result_status, recorded_at, updated_at)
           VALUES ('MATCH_PREDICTION', ?, ?, '2026-08-11', 'A', 'player_a',
                   'match_winner', 'Match Betting', 'CORE', ?, ?, ?, 'PENDING',
                   '2026-08-11T00:00:00Z', '2026-08-11T00:00:00Z')""",
        (match_id, match_id, odds_taken, closing, clv),
    )


# ---------------------------------------------------------------- T0a


def test_match_winner_close_is_last_pre_start_snapshot(db):
    from tennis_wc.betting.ledger import fetch_closing_odds_for_date, get_connection

    _match(db, 1)
    _odds(db, 1, "2026-08-11T08:00:00Z", 2.10, 1.75)
    _odds(db, 1, "2026-08-11T11:59:00Z", 1.90, 1.95)   # the true close
    _odds(db, 1, "2026-08-11T13:30:00Z", 21.0, 1.01)   # in-running
    _tracker(db, 1, odds_taken=2.10)
    db.commit()

    assert fetch_closing_odds_for_date("2026-08-11") == 1
    conn = get_connection()
    close = conn.execute("SELECT * FROM closing_odds_snapshots WHERE match_id=1").fetchall()
    assert len(close) == 1
    assert close[0]["player_a_closing_odds"] == 1.90
    assert close[0]["fetched_at"] == "2026-08-11T11:59:00Z"
    assert close[0]["close_status"] == "PRE_START"
    row = conn.execute("SELECT closing_odds, clv FROM clv_tracker WHERE match_id=1").fetchone()
    assert row["closing_odds"] == 1.90, "took the in-running 21.00 as the close"
    assert row["clv"] == pytest.approx((2.10 - 1.90) / 1.90)


def test_no_pre_start_snapshot_records_null_close_and_clears_stale_clv(db):
    from tennis_wc.betting.ledger import fetch_closing_odds_for_date, get_connection

    _match(db, 2)
    _odds(db, 2, "2026-08-11T13:00:00Z", 5.0, 1.10)  # only a post-start price
    # A legacy close row and CLV computed from it, as the old code wrote them.
    db.execute(
        """INSERT INTO closing_odds_snapshots (match_id, event_id, bookmaker, market,
               player_a_closing_odds, player_b_closing_odds, source_provider,
               raw_response_id, fetched_at, created_at)
           VALUES (2,'E2','sportsbet','h2h',5.0,1.10,'sportsbet',0,
                   '2026-08-11T13:00:00Z','2026-08-12T00:00:00Z')"""
    )
    _tracker(db, 2, odds_taken=2.0, closing=5.0, clv=-0.6)
    db.commit()

    assert fetch_closing_odds_for_date("2026-08-11") == 1
    conn = get_connection()
    newest = conn.execute(
        "SELECT * FROM closing_odds_snapshots WHERE match_id=2 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert newest["player_a_closing_odds"] is None and newest["player_b_closing_odds"] is None
    assert newest["close_status"] == "NO_CLOSE"
    assert newest["close_reason"] == "no_pre_start_snapshot"
    row = conn.execute("SELECT closing_odds, clv FROM clv_tracker WHERE match_id=2").fetchone()
    assert row["closing_odds"] is None and row["clv"] is None, (
        "a CLV built on an in-running close must be cleared, not kept"
    )


def test_no_start_time_means_no_close(db):
    from tennis_wc.betting.ledger import fetch_closing_odds_for_date, get_connection

    _match(db, 3, start=None)
    _odds(db, 3, "2026-08-11T08:00:00Z", 2.0, 1.8)
    _tracker(db, 3)
    db.commit()

    fetch_closing_odds_for_date("2026-08-11")
    conn = get_connection()
    newest = conn.execute("SELECT * FROM closing_odds_snapshots WHERE match_id=3").fetchone()
    assert newest["close_reason"] == "no_start_time"
    assert newest["player_a_closing_odds"] is None
    assert conn.execute("SELECT clv FROM clv_tracker WHERE match_id=3").fetchone()["clv"] is None


def test_closing_fetch_is_idempotent(db):
    from tennis_wc.betting.ledger import fetch_closing_odds_for_date, get_connection

    _match(db, 4)
    _odds(db, 4, "2026-08-11T08:00:00Z", 2.0, 1.8)
    _match(db, 5)
    _odds(db, 5, "2026-08-11T13:00:00Z", 2.0, 1.8)
    db.commit()

    assert fetch_closing_odds_for_date("2026-08-11") == 2
    assert fetch_closing_odds_for_date("2026-08-11") == 0
    assert get_connection().execute(
        "SELECT COUNT(*) FROM closing_odds_snapshots"
    ).fetchone()[0] == 2


def test_legacy_post_start_close_row_is_ignored_by_readers(db):
    """Rows written before the fix have no status; the reader re-checks time."""
    from tennis_wc.betting.ledger import get_connection, update_clv_tracker_for_date

    _match(db, 6)
    for fetched, a in (("2026-08-11T10:00:00Z", 1.80), ("2026-08-11T14:00:00Z", 30.0)):
        db.execute(
            """INSERT INTO closing_odds_snapshots (match_id, event_id, bookmaker, market,
                   player_a_closing_odds, player_b_closing_odds, source_provider,
                   raw_response_id, fetched_at, created_at)
               VALUES (6,'E6','sportsbet','h2h',?,1.5,'sportsbet',0,?,?)""",
            (a, fetched, fetched),
        )
    _tracker(db, 6, odds_taken=2.0)
    db.commit()

    update_clv_tracker_for_date("2026-08-11")
    row = get_connection().execute("SELECT closing_odds FROM clv_tracker WHERE match_id=6").fetchone()
    assert row["closing_odds"] == 1.80


# ---------------------------------------------------------------- T0c


def _prop(conn, prop_id, *, is_value, stake, odds=2.0, feed=True, match_id=7):
    conn.execute(
        """INSERT INTO prop_tracker
           (id, prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            model_prob_raw, market_prob_fair, blended_prob, edge, ev, predicted_mean,
            stake_units, is_value, result_status, recorded_at, updated_at,
            feed_market_key, feed_market_name, feed_selection_name, feed_line)
           VALUES (?, ?, ?, '2026-08-11', 'A vs B', 'player_win_a_set_1', 0.5, 'Yes',
                   'over', 'player_win_set', 1, ?, 0.55, 0.56, 0.5, 0.54, 0.06, 0.1,
                   0.0, ?, ?, 'PENDING', '2026-08-11T00:00:00Z', '2026-08-11T00:00:00Z',
                   ?, ?, ?, NULL)""",
        (prop_id, f"k{prop_id}", match_id, odds, stake, is_value,
         "win_a_set" if feed else None,
         "To Win At Least One Set" if feed else None,
         f"Sel {prop_id}" if feed else None),
    )


def _market(conn, prop_id, fetched, odds, match_id=7):
    conn.execute(
        """INSERT INTO market_odds_snapshots
           (match_id, event_id, bookmaker, market_key, market_name, selection_name,
            line, odds, source_provider, raw_response_id, fetched_at, created_at)
           VALUES (?, 'E7', 'sportsbet', 'win_a_set', 'To Win At Least One Set',
                   ?, NULL, ?, 'sportsbet', 0, ?, ?)""",
        (match_id, f"Sel {prop_id}", odds, fetched, fetched),
    )


def test_every_evaluated_prop_gets_open_and_close_logged(db):
    from tennis_wc.betting.ledger import get_connection, sync_clv_tracker_for_date

    _match(db, 7)
    _prop(db, 1, is_value=1, stake=1.0)        # staked value bet
    _prop(db, 2, is_value=0, stake=0.0)        # evaluated, passed on
    _prop(db, 3, is_value=1, stake=0.0)        # value, unstaked
    _prop(db, 4, is_value=0, stake=0.0, feed=False)
    _prop(db, 5, is_value=0, stake=0.0)        # only an in-running price exists
    for pid in (1, 2, 3):
        _market(db, pid, "2026-08-11T01:00:00Z", 2.20)
        _market(db, pid, "2026-08-11T11:00:00Z", 1.80)
        _market(db, pid, "2026-08-11T13:00:00Z", 9.00)   # in-running
    _market(db, 5, "2026-08-11T13:00:00Z", 4.00)
    db.commit()

    before = [tuple(r) for r in get_connection().execute(
        "SELECT * FROM prop_tracker ORDER BY id").fetchall()]
    summary = sync_clv_tracker_for_date("2026-08-11")
    conn = get_connection()

    # Which props reach clv_tracker is unchanged: only the staked value bet.
    assert summary["props_synced"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM clv_tracker WHERE recommendation_type='PROP_RECOMMENDATION'"
    ).fetchone()[0] == 1
    after = [tuple(r) for r in conn.execute("SELECT * FROM prop_tracker ORDER BY id").fetchall()]
    assert before == after, "logging must not touch the bet decisions"

    log = {r["prop_id"]: r for r in conn.execute("SELECT * FROM prop_price_log").fetchall()}
    assert set(log) == {1, 2, 3, 4, 5}
    for pid in (1, 2, 3):
        assert log[pid]["earliest_pre_start_odds"] == 2.20
        assert log[pid]["close_pre_start_odds"] == 1.80
        assert log[pid]["pre_start_snapshots"] == 2
        assert log[pid]["status"] == "OK"
        assert log[pid]["clv_vs_close"] == pytest.approx((2.0 - 1.8) / 1.8)
    assert log[4]["status"] == "NO_CLOSE" and log[4]["reason"] == "no_feed_identity"
    assert log[5]["status"] == "NO_CLOSE" and log[5]["reason"] == "no_pre_start_snapshot"
    assert log[5]["close_pre_start_odds"] is None, "an in-running price is not a close"
    assert summary["prop_prices_logged"]["logged"] == 5
    assert summary["prop_prices_logged"]["with_close"] == 3

    # Idempotent: a second sync refreshes, never duplicates.
    sync_clv_tracker_for_date("2026-08-11")
    assert get_connection().execute("SELECT COUNT(*) FROM prop_price_log").fetchone()[0] == 5


def test_close_audit_migration_is_idempotent(db):
    from tennis_wc.database.migrations import ensure_close_audit_schema, init_db
    from tennis_wc.database.db import get_connection

    init_db()
    init_db()
    conn = get_connection()
    ensure_close_audit_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(closing_odds_snapshots)")}
    assert {"close_status", "close_reason"} <= cols


# ---------------------------------------------------------------- T0b


def test_rankings_cache_fallback_is_reported(monkeypatch):
    from tennis_wc import cli
    from tennis_wc.ingestion import ingest_rankings as ir

    class Broken:
        provider_name = "broken"

        def fetch_rankings(self, tour, date):
            raise RuntimeError("HTTP 503")

    monkeypatch.setattr(ir, "get_tennis_provider", lambda: Broken())
    monkeypatch.setattr(ir, "_latest_cached_rankings",
                        lambda tour, date: [{"ranking_date": "2026-10-06"}])
    monkeypatch.setattr(ir, "_refresh_current_ranks_from_cached_rows", lambda rows: None)
    monkeypatch.setattr(ir, "store_raw_response", lambda *a, **k: 1)

    result = ir.ingest_rankings("WTA", "2026-10-14")
    assert result == 1
    warnings = cli._stage_degradations("rankings_wta", result)
    assert warnings and warnings[0]["warning"] == "rankings_cache_fallback"
    assert warnings[0]["cached_latest_ranking_date"] == "2026-10-06"
    # Not carried over to the other tour, nor to the next healthy call.
    assert cli._stage_degradations("rankings_atp", result) == []


def test_history_404_is_recorded_and_surfaced(tmp_path, monkeypatch):
    from urllib.error import HTTPError

    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc import cli
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion import ingest_sackmann as sk

    init_db()

    def not_found(url):
        raise HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(sk, "_download_csv", not_found)
    out = sk.ingest_sackmann_history(2026, 2026, ["WTA"])
    assert out["errors"][0]["error"] == "csv_not_found"
    row = get_connection().execute(
        "SELECT status_code, entity_type FROM raw_api_responses WHERE provider_name='jeff_sackmann'"
    ).fetchone()
    assert row["status_code"] == 404
    # Its own entity_type, so retention never treats it as the newest CSV body.
    assert row["entity_type"] == "match_history_not_found"

    tml = sk.ingest_tml_low_tier_history(2026, 2026)
    warnings = cli._stage_degradations("history_lowtier", tml)
    assert len(warnings) == 3
    assert all(w["warning"] == "csv_not_found" for w in warnings)


def test_health_line_always_prints_source_errors(monkeypatch):
    from scripts import tennis_daily_schedule as sched

    monkeypatch.setattr(sched, "_prop_counts",
                        lambda _d: {"props": 0, "value": 0, "pending_older": 0})
    base = {
        "odds_coverage": {"fixtures": 50, "priced_matches": 45},
        "matches_analysed": 45,
        "readiness": {"severity": "ok", "horizon": "same_day"},
        "tracker_sync": {"clv": {}},
        "cloudflare_deploy": {"status": "deployed"},
    }
    quiet = sched.daily_health_line("2026-10-14", base)
    assert "來源錯誤 0" in quiet and "降級" not in quiet

    loud = sched.daily_health_line("2026-10-14", {
        **base,
        "source_errors": [{"source": "rankings_wta", "error": "x"},
                          {"source": "history", "error": "y"}],
        "source_warnings": [{"source": "rankings_atp", "warning": "rankings_cache_fallback"}],
    })
    assert "來源錯誤 2 (rankings_wta, history)" in loud
    assert "降級 1 (rankings_atp)" in loud


# ---------------------------------------------------------------- A: MARKET_LEG


def _market_snapshot(conn, match_id: int, fetched: str, odds: float,
                     key: str = "total_games", selection: str = "Over", line: float = 22.5):
    conn.execute(
        """INSERT INTO market_odds_snapshots (event_id, match_id, bookmaker, market_key,
               market_name, selection_name, selection_side, line, odds,
               source_provider, raw_response_id, fetched_at, created_at)
           VALUES (?, ?, 'sportsbet', ?, 'Total Games', ?, NULL, ?, ?, 'sportsbet', 0, ?, ?)""",
        (f"E{match_id}", match_id, key, selection, line, odds, fetched, fetched),
    )


def _leg(conn, match_id: int, odds_taken: float = 1.90, clv=None, closing=None):
    conn.execute(
        """INSERT INTO clv_tracker (recommendation_type, source_id, match_id, match_date,
               selection_name, selection_side, market_key, market_name, market_line,
               tier, odds_taken, closing_odds, clv, result_status, recorded_at, updated_at)
           VALUES ('MARKET_LEG', ?, ?, '2026-08-11', 'Over', NULL, 'total_games',
                   'our own label', 22.5, 'CORE', ?, ?, ?, 'PENDING',
                   '2026-08-11T00:00:00Z', '2026-08-11T00:00:00Z')""",
        (match_id, match_id, odds_taken, closing, clv),
    )


def test_market_leg_close_ignores_in_running_snapshot(db):
    from tennis_wc.betting.ledger import get_connection, update_clv_tracker_for_date

    _match(db, 30)
    _market_snapshot(db, 30, "2026-08-11T09:00:00Z", 1.95)
    _market_snapshot(db, 30, "2026-08-11T11:50:00Z", 1.80)  # the true close
    _market_snapshot(db, 30, "2026-08-11T12:40:00Z", 3.40)  # in-running
    _leg(db, 30, odds_taken=1.95)
    db.commit()

    update_clv_tracker_for_date("2026-08-11")
    row = get_connection().execute(
        "SELECT closing_odds, clv, close_reason FROM clv_tracker WHERE match_id=30"
    ).fetchone()
    assert row["closing_odds"] == 1.80, "MARKET_LEG close took the in-running price"
    assert row["clv"] == pytest.approx((1.95 - 1.80) / 1.80)
    assert row["close_reason"] is None


@pytest.mark.parametrize(
    "start,snapshot,reason",
    [
        (None, "2026-08-11T09:00:00Z", "no_start_time"),
        (START, "2026-08-11T12:30:00Z", "no_pre_start_snapshot"),
    ],
)
def test_market_leg_without_pre_start_close_is_null_with_reason(db, start, snapshot, reason):
    from tennis_wc.betting.ledger import get_connection, update_clv_tracker_for_date

    _match(db, 31, start=start)
    _market_snapshot(db, 31, snapshot, 2.60)
    _leg(db, 31, odds_taken=1.95, closing=2.60, clv=-0.25)  # legacy stale CLV
    db.commit()

    update_clv_tracker_for_date("2026-08-11")
    row = get_connection().execute(
        "SELECT closing_odds, clv, close_reason FROM clv_tracker WHERE match_id=31"
    ).fetchone()
    assert row["closing_odds"] is None and row["clv"] is None
    assert row["close_reason"] == reason


# ---------------------------------------------------------------- B: preclose capture


def _fake_page(match_id: int, odds: float, fetched: str) -> dict:
    return {
        "event_id": f"E{match_id}", "bookmaker": "sportsbet", "market": "match_winner",
        "player_a_name": "A", "player_b_name": "B",
        "player_a_odds": 1.70, "player_b_odds": 2.20, "timestamp": fetched,
        "markets": [{
            "market_key": "win_a_set", "market_name": "To Win At Least One Set",
            "selections": [{"selection_name": "Sel 1", "odds": odds}],
        }],
    }


def test_preclose_refresh_feeds_the_close_but_not_the_card(db, monkeypatch):
    from datetime import datetime, timezone

    from tennis_wc.betting.ledger import (
        _ensure_tracking_schema, get_connection, sync_clv_tracker_for_date,
    )
    from tennis_wc.ingestion import ingest_odds
    from tennis_wc.props.daily import _rows_for_date

    _match(db, 7)                                     # start 12:00Z
    _match(db, 8, start="2026-08-11T15:00:00Z")       # outside the window
    _match(db, 9, start="2026-08-11T11:30:00Z")       # in window, never evaluated
    _prop(db, 1, is_value=1, stake=1.0)
    _prop(db, 2, is_value=0, stake=0.0, match_id=8)
    _market(db, 1, "2026-08-11T01:00:00Z", 2.20)      # the only card-time price
    db.commit()
    _ensure_tracking_schema()
    monkeypatch.setattr(ingest_odds, "_latest_sportsbet_event_refs", lambda d: [
        {"match_id": 7, "event_id": "E7", "event_url": "https://x/e7"},
        {"match_id": 9, "event_id": "E9", "event_url": "https://x/e9"},
    ])
    card_before = [tuple(r) for r in _rows_for_date(get_connection(), "2026-08-11")]
    replay_before = [tuple(r) for r in _rows_for_date(get_connection(), "2026-08-11",
                                                      earliest_only=True)]
    fetched = []

    def fetcher(ref, match_id):
        fetched.append((ref, match_id))
        page = _fake_page(match_id, 1.85, "2026-08-11T11:10:00Z")
        return ingest_odds._store_preclose_event(page, match_id, "sportsbet_scrape", 0)

    now = datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc)
    summary = ingest_odds.refresh_pre_start_markets(
        "2026-08-11", now=now, fetcher=fetcher, sleeper=lambda s: None)
    assert fetched == [("https://x/e7", 7)], "only evaluated matches inside the window"
    assert summary["refreshed"] == 1 and summary["failed"] == 0

    # A second tick inside the same window does not fetch the page again.
    again = ingest_odds.refresh_pre_start_markets(
        "2026-08-11", now=now.replace(minute=30), fetcher=fetcher, sleeper=lambda s: None)
    assert again["already_captured"] == 1 and len(fetched) == 1

    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM market_odds_snapshots").fetchone()[0] == 1, (
        "the live table the card reads must be untouched")
    assert [tuple(r) for r in _rows_for_date(conn, "2026-08-11")] == card_before
    assert [tuple(r) for r in _rows_for_date(conn, "2026-08-11", earliest_only=True)] \
        == replay_before, "replay (earliest snapshot) must not see the preclose price"

    summary = sync_clv_tracker_for_date("2026-08-11")
    assert summary["prop_prices_logged"]["with_two_plus_pre_start"] == 1
    log = get_connection().execute(
        "SELECT * FROM prop_price_log WHERE prop_id = 1").fetchone()
    assert log["close_pre_start_odds"] == 1.85, "close must use the near-start capture"
    assert log["earliest_pre_start_odds"] == 2.20
    assert log["pre_start_snapshots"] == 2
    tracker = get_connection().execute(
        "SELECT closing_odds, clv FROM clv_tracker WHERE recommendation_type='PROP_RECOMMENDATION'"
    ).fetchone()
    assert tracker["closing_odds"] == 1.85
    assert tracker["clv"] == pytest.approx((2.0 - 1.85) / 1.85)


def test_preclose_match_winner_capture_becomes_the_close(db):
    from tennis_wc.betting.ledger import (
        _ensure_tracking_schema, fetch_closing_odds_for_date, get_connection,
    )
    from tennis_wc.ingestion import ingest_odds

    _match(db, 1)
    _odds(db, 1, "2026-08-11T01:00:00Z", 2.10, 1.75)
    db.commit()
    _ensure_tracking_schema()
    ingest_odds._store_preclose_event(_fake_page(1, 1.9, "2026-08-11T11:20:00Z"),
                                      1, "sportsbet_scrape", 0)
    assert fetch_closing_odds_for_date("2026-08-11") == 1
    close = get_connection().execute(
        "SELECT * FROM closing_odds_snapshots WHERE match_id = 1").fetchone()
    assert close["fetched_at"] == "2026-08-11T11:20:00Z"
    assert (close["player_a_closing_odds"], close["player_b_closing_odds"]) == (1.70, 2.20)
    assert get_connection().execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0] == 1


def test_preclose_refresh_reports_missing_event_ref_and_respects_cap(db, monkeypatch):
    from datetime import datetime, timezone

    from tennis_wc.betting.ledger import _ensure_tracking_schema
    from tennis_wc.ingestion import ingest_odds

    for mid in (20, 21, 22):
        _match(db, mid)
        _prop(db, mid, is_value=0, stake=0.0, match_id=mid)
    db.commit()
    _ensure_tracking_schema()
    monkeypatch.setattr(ingest_odds, "_latest_sportsbet_event_refs", lambda d: [
        {"match_id": 21, "event_id": "E21", "event_url": "https://x/e21"},
        {"match_id": 22, "event_id": "E22", "event_url": "https://x/e22"},
    ])
    sleeps = []
    summary = ingest_odds.refresh_pre_start_markets(
        "2026-08-11", now=datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc),
        max_events=2, fetcher=lambda ref, mid: 1, sleeper=sleeps.append)
    assert summary["candidates"] == 3
    assert summary["no_event_ref"] == 1, "match 20 is not in the latest listing"
    assert summary["refreshed"] == 1 and summary["deferred_by_cap"] == 1
    assert sleeps == [], "no pause before the first real fetch"


def test_preclose_rejected_identity_is_not_reported_as_refreshed(db, monkeypatch):
    from datetime import datetime, timezone
    from tennis_wc.betting.ledger import _ensure_tracking_schema
    from tennis_wc.ingestion import ingest_odds
    _match(db, 20)
    _prop(db, 20, is_value=0, stake=0.0, match_id=20)
    db.commit()
    _ensure_tracking_schema()
    monkeypatch.setattr(ingest_odds, "_latest_sportsbet_event_refs", lambda d: [
        {"match_id": 20, "event_id": "E20", "event_url": "https://x/e20"}])
    summary = ingest_odds.refresh_pre_start_markets(
        "2026-08-11", now=datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc),
        fetcher=lambda ref, mid: 0, sleeper=lambda s: None)
    assert summary["refreshed"] == 0 and summary["failed"] == 1
    assert summary["errors"][0]["error"] == "event_identity_rejected"


def test_preclose_tick_covers_today_and_tomorrow():
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "tennis_preclose_refresh.py"
    spec = importlib.util.spec_from_file_location("tennis_preclose_refresh_t", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    seen = []

    def refresh(match_date):
        seen.append(match_date)
        if match_date.endswith("15"):
            raise RuntimeError("boom")
        return {"refreshed": 2, "failed": 0}

    summary = module.run_tick("2026-10-14", refresh=refresh)
    assert seen == ["2026-10-14", "2026-10-15"]
    assert summary["refreshed"] == 2 and summary["failed"] == 1
