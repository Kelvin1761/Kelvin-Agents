from __future__ import annotations

from tennis_wc.props.evidence_contract import exclusion_reason, verified_contract_rows


def test_only_proven_named_player_totals_are_excluded_from_match_total_evidence():
    base={'id':1,'market_key':'total_match_games_12_5','feed_market_name':'Alex de Minaur Total Games'}
    assert exclusion_reason(base)=='named_player_total_priced_as_match_total'
    for name in ('Match Total Games','Total Games 22.5','Set 1 Total Games',None):
        assert exclusion_reason({**base,'feed_market_name':name}) is None
    assert exclusion_reason({**base,'market_key':'player_total_games_1_12_5'}) is None
    rows,audit=verified_contract_rows([base,{**base,'id':2,'feed_market_name':'Match Total Games'}])
    assert [r['id'] for r in rows]==[2]
    assert audit['policy']=='prop-contract-v1'
    assert audit['excluded'][0]['prop_id']==1
    assert base['market_key']=='total_match_games_12_5'


def test_ambiguous_legacy_total_games_without_feed_identity_remains_unverified():
    assert exclusion_reason({'market_key':'total_games','feed_market_name':None}) == 'legacy_match_total_contract_unverified'
    assert exclusion_reason({'market_key':'total_games','feed_market_name':'Match Total Games'}) is None


def test_current_match_total_keeps_the_bookmakers_contract_on_the_tracker(tmp_path,monkeypatch):
    import json
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.ingest_odds import _insert_market_odds
    from tennis_wc.props.daily import price_ace_props_for_date
    configure_test_db(tmp_path,monkeypatch);init_db()
    monkeypatch.setattr('tennis_wc.props.daily._match_prob_map',lambda conn,date:{1:.5})
    with get_connection() as c:
        for pid,name in ((1,'Player One'),(2,'Player Two')):
            c.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) VALUES (?,?,'ATP','test','now','now')",(pid,name))
        c.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at,start_time_utc) VALUES (1,'event','ATP','2026-06-01',1,1,2,'R1','test','now','now','2099-01-01T00:00:00Z')")
        _insert_market_odds(c,dict(event_id='event',bookmaker='Sportsbet',player_a_name='Player One',player_b_name='Player Two',markets=[
            dict(market_key='total_games',market_name='Match Total Games',selections=[
                dict(selection_name='Over 22.5',line=22.5,odds=1.9),
                dict(selection_name='Under 22.5',line=22.5,odds=1.9)])]),1,'sportsbet',1,'2026-06-01T08:00:00Z')
        price_ace_props_for_date(c,'2026-06-01',log=True)
        row=c.execute("SELECT * FROM prop_tracker WHERE market_key='total_games' AND side='over'").fetchone()
        assert row is not None
        assert row['feed_market_key']=='total_games'
        assert row['feed_market_name']=='Match Total Games'
        assert row['feed_selection_name']=='Over 22.5'
        assert json.loads(row['pricing_evidence_json'])['quote_status']=='OBSERVED'
        assert exclusion_reason(row) is None


def test_prop_subject_name_matching_declines_shared_first_names_and_other_full_names():
    from tennis_wc.props.daily import _resolve_player,_resolve_named_player
    from tennis_wc.ingestion.ingest_odds import selection_side_for
    meta={'player_a_id':1,'player_b_id':2,'a_name':'Alex de Minaur','b_name':'Alex Michelsen'}
    assert _resolve_player('Total Alex Aces 7.5',meta)==(None,'')
    assert _resolve_named_player('Alex Total Games','player_total_games',meta)==(None,'')
    assert _resolve_player('Total Alex Michelsen Aces 7.5',meta)==(2,'Alex Michelsen')
    assert _resolve_named_player('Alex Wong Total Games','player_total_games',meta)==(None,'')
    assert selection_side_for('Alex de Minaur','Jannik Sinner','Alex Wong') is None
    assert selection_side_for('Jack Draper','Jannik Sinner','J. Draper')=='player_a'
