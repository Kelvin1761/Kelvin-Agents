"""A current board cannot combine disappeared lines or different quote batches."""
from __future__ import annotations

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.ingestion.ingest_odds import _insert_market_odds
from tennis_wc.props.daily import _rows_for_date


def test_new_capture_retires_unobserved_lines_and_markets(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        for pid,name in [(1,'Player One'),(2,'Player Two')]:
            c.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) VALUES (?,?,'ATP','test','now','now')",(pid,name))
        c.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at) VALUES (1,'event','ATP','2026-06-01',1,1,2,'R1','test','now','now')")
        def total(line):
            return dict(market_key='total_games',market_name='Total Games',selections=[
                dict(selection_name='Over',line=line,odds=1.9),dict(selection_name='Under',line=line,odds=1.9)])
        row=dict(event_id='event',bookmaker='Sportsbet',player_a_name='Player One',player_b_name='Player Two')
        first_set=dict(market_key='first_set_winner',market_name='Set 1 Winner',selections=[
            dict(selection_name='Player One',odds=1.9),dict(selection_name='Player Two',odds=1.9)])
        _insert_market_odds(c,{**row,'markets':[total(22.5),first_set]},1,'sportsbet',1,'2026-06-01T08:00:00Z')
        assert len(_rows_for_date(c,'2026-06-01'))==4
        _insert_market_odds(c,{**row,'markets':[total(24.5)]},1,'sportsbet',2,'2026-06-01T09:00:00Z')
        live=_rows_for_date(c,'2026-06-01')
        assert len(live)==2 and {r['line'] for r in live}=={24.5}
        # Historical opening reader retains its original contract-first semantics.
        assert len(_rows_for_date(c,'2026-06-01',earliest_only=True))==6
        _insert_market_odds(c,{**row,'markets':[]},1,'sportsbet',3,'2026-06-01T10:00:00Z')
        assert _rows_for_date(c,'2026-06-01')==[]
        assert c.execute('SELECT COUNT(*) FROM market_odds_snapshots').fetchone()[0]==6


def test_different_books_never_share_a_devig_group():
    from tennis_wc.reports.daily_report import _group_market_rows
    base=dict(match_id=1,market_key='total_games',market_name='Total Games',line=22.5,source_provider='feed')
    grouped=_group_market_rows([{**base,'bookmaker':'Book A'},{**base,'bookmaker':'Book B'}])
    assert len(grouped)==2


def test_exact_player_names_with_shared_first_name_have_correct_sides():
    from tennis_wc.ingestion.ingest_odds import selection_side_for
    assert selection_side_for('Alex Michelsen','Alex de Minaur','Alex Michelsen')=='player_a'
    assert selection_side_for('Alex Michelsen','Alex de Minaur','Alex de Minaur')=='player_b'
    assert selection_side_for('Alex Michelsen','Alex de Minaur','Alex') is None


def test_empty_capture_cannot_resurrect_positional_prices(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        for pid,name in [(1,'Player One'),(2,'Player Two')]:
            c.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) VALUES (?,?,'ATP','test','now','now')",(pid,name))
        c.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at) VALUES (1,'event','ATP','2026-06-01',1,1,2,'R1','test','now','now')")
        row=dict(event_id='event',bookmaker='Sportsbet',player_a_name='Player One',player_b_name='Player Two',
                 player_a_odds=1.9,player_b_odds=1.9)
        _insert_market_odds(c,row,1,'sportsbet',1,'2026-06-01T08:00:00Z')
        c.execute("INSERT INTO odds_snapshots(event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,source_provider,raw_response_id,fetched_at,created_at) VALUES ('event',1,'Sportsbet','match_winner',1.9,1.9,'sportsbet',1,'2026-06-01T08:00:00Z','2026-06-01T08:00:00Z')")
        c.commit()
        from tennis_wc.features.feature_builder import _market
        assert _market(1)['mapping_status']['value']=='verified'
        _insert_market_odds(c,{**row,'markets':[],'player_a_odds':None,'player_b_odds':None},1,'sportsbet',2,'2026-06-01T09:00:00Z')
        c.commit()
        assert _market(1)=={}
        assert c.execute('SELECT COUNT(*) FROM odds_snapshots').fetchone()[0]==1


def test_preclose_capture_does_not_replace_the_current_live_batch(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        from tennis_wc.database.market_captures import record_market_capture,current_market_clause
        c.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at) VALUES (1,'event','ATP','2026-06-01',1,1,2,'R1','test','now','now')")
        c.execute("INSERT INTO market_odds_snapshots(event_id,match_id,bookmaker,market_key,market_name,selection_name,odds,source_provider,raw_response_id,fetched_at,created_at) VALUES ('event',1,'Sportsbet','test','Test','One',1.9,'sportsbet',1,'now','now')")
        row=dict(event_id='event',bookmaker='Sportsbet')
        record_market_capture(c,1,row,'sportsbet',1,'now','market_odds_snapshots')
        record_market_capture(c,1,row,'sportsbet',2,'later','preclose_market_odds_snapshots')
        assert c.execute(f'SELECT COUNT(*) FROM market_odds_snapshots mo WHERE {current_market_clause(c)}').fetchone()[0]==1


def test_bookmaker_event_never_uses_another_providers_fixture_id(tmp_path, monkeypatch):
    from tennis_wc.database.market_captures import bookmaker_event_for_match, record_market_capture
    configure_test_db(tmp_path, monkeypatch); init_db()
    with get_connection() as c:
        c.execute("INSERT INTO matches(id,provider_match_id,market_event_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at) VALUES (1,'fixture','espn-123','ATP','2026-06-01',1,1,2,'R1','composite','now','now')")
        assert bookmaker_event_for_match(c, 1, 'sportsbet') is None
        c.execute("INSERT INTO odds_snapshots(event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,source_provider,raw_response_id,fetched_at,created_at) VALUES ('sportsbet-456',1,'Sportsbet','match_winner',1.9,1.9,'sportsbet',1,'now','now')")
        assert bookmaker_event_for_match(c, 1, 'sportsbet') == 'sportsbet-456'
        record_market_capture(c, 1, dict(event_id='sportsbet-789'), 'sportsbet', 2, 'now', 'market_odds_snapshots')
        assert bookmaker_event_for_match(c, 1, 'sportsbet') == 'sportsbet-789'
        assert c.execute('SELECT market_event_id FROM matches WHERE id=1').fetchone()[0] == 'espn-123'
