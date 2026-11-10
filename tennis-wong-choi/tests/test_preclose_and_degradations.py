"""Pre-start capture for 精選 matches, and degraded sources that must not be silent."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

START = "2026-08-11T12:00:00Z"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.store.db import get_connection
    from tennis_wc.store.migrations import init_db

    init_db()
    conn = get_connection()
    conn.execute("""INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
                    VALUES (1,'A','ATP','test','now','now'), (2,'B','ATP','test','now','now')""")
    conn.commit()
    return conn


def _match(conn, match_id: int, start: str | None = START, date: str = "2026-08-11"):
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (?,?,'ATP',?,1,1,2,'R1','test','now','now',?)""",
        (match_id, f"M{match_id}", date, start),
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




def _featured(conn, match_id):
    conn.execute("""INSERT INTO featured_picks (prop_id, match_id, match_date, rank, run_label, market_key,
                    selection, start_time_utc, odds, featured_at)
                    VALUES (?, ?, '2026-08-11', 1, '21:00', 'player_win_a_set_1', 'Yes', ?, 2.0, 'now')""",
                 (match_id, match_id, START))



def test_preclose_refresh_captures_featured_matches_only_and_never_the_card(db, monkeypatch):
    from tennis_wc.store.db import get_connection
    from tennis_wc.sources import ingest_odds
    from tennis_wc.pricing.quotes import rows_for_date

    _match(db, 7)                                     # start 12:00Z, featured
    _match(db, 8, start="2026-08-11T15:00:00Z")       # featured but outside the window
    _match(db, 9, start="2026-08-11T11:30:00Z")       # in window, not featured
    _featured(db, 7)
    _featured(db, 8)
    _market(db, 1, "2026-08-11T01:00:00Z", 2.20)
    db.commit()
    monkeypatch.setattr(ingest_odds, "_latest_sportsbet_event_refs", lambda d: [
        {"match_id": 7, "event_id": "E7", "event_url": "https://x/e7"},
        {"match_id": 9, "event_id": "E9", "event_url": "https://x/e9"},
    ])
    card_before = [tuple(r) for r in rows_for_date(get_connection(), "2026-08-11")]
    fetched = []

    def fetcher(ref, match_id):
        fetched.append((ref, match_id))
        return ingest_odds._store_preclose_event(_fake_page(match_id, 1.85, "2026-08-11T11:10:00Z"),
                                                 match_id, "sportsbet_scrape", 0)

    now = datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc)
    summary = ingest_odds.refresh_pre_start_markets("2026-08-11", now=now, fetcher=fetcher,
                                                    sleeper=lambda s: None)
    assert fetched == [("https://x/e7", 7)], "only featured matches inside the window"
    assert summary["refreshed"] == 1 and summary["failed"] == 0
    again = ingest_odds.refresh_pre_start_markets("2026-08-11", now=now.replace(minute=30),
                                                  fetcher=fetcher, sleeper=lambda s: None)
    assert again["already_captured"] == 1 and len(fetched) == 1
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM market_odds_snapshots").fetchone()[0] == 1
    assert [tuple(r) for r in rows_for_date(conn, "2026-08-11")] == card_before


def test_preclose_refresh_reports_missing_event_ref_and_respects_cap(db, monkeypatch):
    from tennis_wc.sources import ingest_odds

    for mid in (20, 21, 22):
        _match(db, mid)
        _featured(db, mid)
    db.commit()
    monkeypatch.setattr(ingest_odds, "_latest_sportsbet_event_refs", lambda d: [
        {"match_id": 21, "event_id": "E21", "event_url": "https://x/e21"},
        {"match_id": 22, "event_id": "E22", "event_url": "https://x/e22"},
    ])
    sleeps = []
    summary = ingest_odds.refresh_pre_start_markets(
        "2026-08-11", now=datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc),
        max_events=2, fetcher=lambda ref, mid: 1, sleeper=sleeps.append)
    assert summary["candidates"] == 3
    assert summary["no_event_ref"] == 1
    assert summary["refreshed"] == 1 and summary["deferred_by_cap"] == 1
    assert sleeps == []


def test_preclose_rejected_identity_is_not_reported_as_refreshed(db, monkeypatch):
    from tennis_wc.sources import ingest_odds

    _match(db, 20)
    _featured(db, 20)
    db.commit()
    monkeypatch.setattr(ingest_odds, "_latest_sportsbet_event_refs", lambda d: [
        {"match_id": 20, "event_id": "E20", "event_url": "https://x/e20"}])
    summary = ingest_odds.refresh_pre_start_markets(
        "2026-08-11", now=datetime(2026, 8, 11, 11, 0, tzinfo=timezone.utc),
        fetcher=lambda ref, mid: 0, sleeper=lambda s: None)
    assert summary["refreshed"] == 0 and summary["failed"] == 1
    assert summary["errors"][0]["error"] == "event_identity_rejected"


def test_rankings_cache_fallback_is_reported(monkeypatch):
    from tennis_wc import run as cli
    from tennis_wc.sources import ingest_rankings as ir

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
    warnings = cli._degradations("rankings_wta", result)
    assert warnings and warnings[0]["warning"] == "rankings_cache_fallback"
    assert warnings[0]["cached_latest_ranking_date"] == "2026-10-06"
    # Not carried over to the other tour, nor to the next healthy call.
    assert cli._degradations("rankings_atp", result) == []




def test_history_404_is_recorded_and_surfaced(tmp_path, monkeypatch):
    from urllib.error import HTTPError

    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc import run as cli
    from tennis_wc.store.db import get_connection
    from tennis_wc.store.migrations import init_db
    from tennis_wc.sources import ingest_sackmann as sk

    init_db()

    def not_found(url):
        raise HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(sk, "_download_csv", not_found)
    tml = sk.ingest_tml_low_tier_history(2026, 2026)
    warnings = cli._degradations("history_lowtier", tml)
    assert len(warnings) == 3
    assert all(w["warning"] == "csv_not_found" for w in warnings)




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


# ---------------------------------------------------------------- hourly 精選 settlement

def _pending_prop(conn, prop_id, status="PENDING"):
    conn.execute(
        """INSERT INTO prop_tracker (id, prop_key, match_id, match_date, match_label, market_key, line,
               selection, decimal_odds, stake_units, is_value, result_status, recorded_at, updated_at)
           VALUES (?, ?, ?, '2026-08-11', 'A vs B', 'player_win_a_set_1', 0.5, 'Yes', 2.0, 1.0, 1, ?, 'now', 'now')""",
        (prop_id, f"k{prop_id}", prop_id, status),
    )


def test_settle_tick_only_fetches_when_a_featured_match_should_be_over(db, monkeypatch):
    from tennis_wc import run
    from tennis_wc.settle import props as settle_module

    _match(db, 7)                                               # 12:00Z, due at 14:00Z
    _match(db, 8, start="2026-08-11T13:30:00Z")                 # only 30 minutes in
    _match(db, 9, start="2026-08-10T20:00:00Z", date="2026-08-10")  # 18h ago: left to the daily runs
    _match(db, 10, start="2026-08-11T11:00:00Z")                # finished, but not featured
    for i in (7, 8, 9, 10):
        _pending_prop(db, i)
    for i in (7, 8, 9):
        _featured(db, i)
    db.commit()
    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    fetched = []

    def settle(conn, today=None):
        conn.execute("UPDATE prop_tracker SET result_status='WON' WHERE id=7")
        conn.commit()
        return {"graded": 1}

    monkeypatch.setattr(settle_module, "settle_props", settle)
    summary = run.settle_finished_featured(now, fetch=fetched.append)
    assert fetched == ["2026-08-11"]
    assert summary["due"] == 1 and summary["settled"] == 1 and summary["latest_date"] == "2026-08-11"

    # Nothing due any more: no fetch at all.
    again = run.settle_finished_featured(now, fetch=fetched.append)
    assert again["due"] == 0 and again["settled"] == 0 and fetched == ["2026-08-11"]


def test_settle_tick_follows_a_rescheduled_start_and_survives_a_failed_fetch(db, monkeypatch):
    from tennis_wc import run
    from tennis_wc.settle import props as settle_module

    _match(db, 7, start="2026-08-11T13:10:00Z", date="2026-08-12")  # pick frozen at 12:00Z, moved later
    _pending_prop(db, 7)
    _featured(db, 7)
    db.commit()
    monkeypatch.setattr(settle_module, "settle_props", lambda conn, today=None: {"graded": 0})
    early = run.settle_finished_featured(datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc), fetch=lambda d: None)
    assert early["due"] == 0, "50 minutes after the real start is too soon"

    def boom(day):
        raise RuntimeError("source down")

    late = run.settle_finished_featured(datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc), fetch=boom)
    assert late["due"] == 1 and late["settled"] == 0
    assert late["dates"] == ["2026-08-11", "2026-08-12"] and len(late["errors"]) == 2


def test_settle_tick_deploys_only_when_something_settled():
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "tennis_settle_tick.py"
    spec = importlib.util.spec_from_file_location("tennis_settle_tick_t", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    deployed = []

    def deploy(day):
        deployed.append(day)
        return {"status": "deployed"}

    quiet = module.run_tick(settle=lambda: {"due": 2, "settled": 0, "dates": ["2026-08-11"]}, deploy=deploy)
    assert deployed == [] and "dashboard" not in quiet
    done = module.run_tick(settle=lambda: {"due": 2, "settled": 1, "latest_date": "2026-08-11"}, deploy=deploy)
    assert deployed == ["2026-08-11"] and done["dashboard"] == {"status": "deployed"}
