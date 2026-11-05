"""A wrong event must not become an opening or a substitute close."""
from __future__ import annotations

import json

import pytest

from conftest import configure_test_db
from tennis_wc.store.db import get_connection
from tennis_wc.store.migrations import init_db
from tennis_wc.store.odds_source_reads import OddsSourceReader
from tennis_wc.pricing.quotes import rows_for_date as _rows_for_date


@pytest.fixture
def conn(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    init_db()
    with get_connection() as c:
        c.execute("""INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,
                     player_a_id,player_b_id,round,source_provider,created_at,updated_at,start_time_utc)
                     VALUES (1,'m','ATP','2026-06-01',1,1,2,'R1','test','now','now','2026-06-01T12:00:00Z')""")
        yield c


def receipt(conn, raw_id, returned, *, ref="https://sportsbet.com.au/tennis/a-b-123", endpoint="/event-odds", provider="sportsbet"):
    conn.execute("""INSERT INTO raw_api_responses(id,provider_name,endpoint,request_url_hash,
                    request_params_json,response_json,status_code,fetched_at,created_at)
                    VALUES (?,?,?,?,?,?,200,'now','now')""",
                 (raw_id, provider, endpoint, "h", json.dumps({"event_id": ref}), json.dumps(returned)))


def market(conn, raw_id, odds, when):
    conn.execute("""INSERT INTO market_odds_snapshots(event_id,match_id,bookmaker,market_key,
                    market_name,selection_name,line,odds,source_provider,raw_response_id,fetched_at,created_at)
                    VALUES ('123',1,'Sportsbet','total_games','Total Games','Over',22.5,?,'sportsbet',?,?,?)""",
                 (odds, raw_id, when, when))


def test_wrong_event_quote_is_dropped_and_verified_one_kept(conn):
    receipt(conn, 1, {"event_id": "999"})
    receipt(conn, 2, {"event_id": "123"})
    market(conn, 1, 2.1, "2026-06-01T08:00:00Z")
    market(conn, 2, 1.8, "2026-06-01T09:00:00Z")
    assert [r["odds"] for r in _rows_for_date(conn, "2026-06-01")] == [1.8]
    assert conn.execute("SELECT COUNT(*) FROM market_odds_snapshots").fetchone()[0] == 2


def test_current_bad_batch_is_not_replaced_by_older_quote(conn):
    receipt(conn, 1, {"event_id": "123"})
    receipt(conn, 2, {"event_id": "999"})
    market(conn, 1, 2.1, "2026-06-01T08:00:00Z")
    market(conn, 2, 1.8, "2026-06-01T09:00:00Z")
    assert _rows_for_date(conn, "2026-06-01") == []




def test_unverifiable_and_out_of_scope_receipts_are_explicit(conn):
    receipt(conn, 1, {})
    receipt(conn, 2, {"event_id": "999"}, ref="opaque-123")
    receipt(conn, 3, {"event_id": "999"}, provider="other")
    reader = OddsSourceReader(conn)
    assert reader.assess(1) == ("unverified_response", True)
    assert reader.assess(2) == ("unverified_reference_namespace", False)
    assert reader.assess(3) == ("outside_direct_event_scope", False)
    assert reader.assess(9000) == ("unverified_missing_receipt", False)
