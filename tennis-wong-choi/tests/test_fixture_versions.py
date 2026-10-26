"""A reused provider key must not move old forecasts/results to new players."""
from __future__ import annotations

import pytest

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.ingestion import ingest_matches, ingest_odds


@pytest.fixture
def fixture_feed(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    init_db()
    class Feed:
        provider_name = 'mock'
        rows = []
        def fetch_upcoming_matches(self, day):
            return self.rows
    feed = Feed()
    monkeypatch.setattr(ingest_matches, 'get_tennis_provider', lambda: feed)
    return feed


def fixture_row(a='11', b='1', day='2026-10-26'):
    names={'11':'Stefanos Tsitsipas','1':'Taylor Fritz','35':'Rinky Hijikata'}
    return dict(id='185138',market_event_id='185138',tour='ATP',match_date=day,
                tournament_id='23-2026',tournament_name='Basel',round='R1',
                player_a_id=a,player_b_id=b,player_a_name=names[a],player_b_name=names[b],
                start_time_utc=f'{day}T12:00:00Z')


def test_reused_key_preserves_old_pair_and_result(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    with get_connection() as c:
        old=dict(c.execute('SELECT * FROM matches').fetchone())
        c.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (?,?,'test','2026-10-26T15:00:00Z')",(old['id'],old['player_a_id']))
    fixture_feed.rows=[fixture_row('35','1','2026-10-27')]
    assert ingest_matches.ingest_upcoming_matches('2026-10-27')==1
    with get_connection() as c:
        kept=dict(c.execute('SELECT * FROM matches WHERE id=?',(old['id'],)).fetchone())
        assert (kept['player_a_id'],kept['player_b_id'],kept['match_date'])==(old['player_a_id'],old['player_b_id'],old['match_date'])
        current=dict(c.execute("SELECT * FROM matches WHERE provider_match_id='185138'").fetchone())
        assert current['id']!=old['id']
        assert kept['fixture_status']=='SUPERSEDED' and kept['market_event_id'] is None
        assert current['supersedes_match_id']==old['id']
        assert c.execute('SELECT match_id FROM match_results').fetchone()[0]==old['id']
    # Repeated refresh must update the current generation, not create duplicates.
    ingest_matches.ingest_upcoming_matches('2026-10-27')
    with get_connection() as c:
        assert c.execute('SELECT COUNT(*) FROM matches').fetchone()[0]==2


def test_swapped_source_order_keeps_positional_meaning(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    with get_connection() as c:
        old=dict(c.execute('SELECT * FROM matches').fetchone())
    fixture_feed.rows=[fixture_row('1','11')]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    with get_connection() as c:
        now=dict(c.execute('SELECT * FROM matches').fetchone())
        assert (now['player_a_id'],now['player_b_id'])==(old['player_a_id'],old['player_b_id'])
        assert c.execute('SELECT COUNT(*) FROM matches').fetchone()[0]==1
        assert now['start_time_utc']=='2026-10-26T12:00:00Z'


def test_resulted_same_pair_on_new_date_is_new_generation(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    with get_connection() as c:
        old=dict(c.execute('SELECT * FROM matches').fetchone())
        c.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (?,?,'test','2026-10-26T15:00:00Z')",(old['id'],old['player_a_id']))
    fixture_feed.rows=[fixture_row(day='2026-11-01')]
    ingest_matches.ingest_upcoming_matches('2026-11-01')
    with get_connection() as c:
        assert c.execute('SELECT match_date FROM matches WHERE id=?',(old['id'],)).fetchone()[0]=='2026-10-26'
        assert c.execute('SELECT COUNT(*) FROM matches').fetchone()[0]==2


@pytest.mark.parametrize('preclose',[False,True])
def test_event_odds_mismatched_pair_is_quarantined(fixture_feed,monkeypatch,preclose):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    class Book:
        provider_name='sportsbet'
        def fetch_event_odds(self,*args):
            return dict(event_id='185138',player_a_name='Rinky Hijikata',player_b_name='Taylor Fritz',
                        bookmaker='Sportsbet',market='match_winner',player_a_odds=2.1,player_b_odds=1.8)
    monkeypatch.setattr(ingest_odds,'get_odds_provider',lambda: Book())
    with get_connection() as c:
        mid=c.execute('SELECT id FROM matches').fetchone()[0]
    assert ingest_odds.ingest_event_odds('185138',mid,preclose=preclose)==0
    with get_connection() as c:
        assert c.execute('SELECT fixture_status FROM matches WHERE id=?',(mid,)).fetchone()[0]=='DISPUTED'
        assert c.execute('SELECT COUNT(*) FROM odds_snapshots').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM market_odds_snapshots').fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM fixture_observations WHERE observation_kind='EVENT_PAIR_CONFLICT'").fetchone()[0]==1
    from tennis_wc.features.feature_builder import assemble_match_feature_snapshot
    with pytest.raises(ValueError,match='identity disputed'):
        assemble_match_feature_snapshot(mid)


def test_new_generation_does_not_enter_old_daily_feature_population(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    fixture_feed.rows=[fixture_row('35','1','2026-10-27')]
    ingest_matches.ingest_upcoming_matches('2026-10-27')
    from tennis_wc.features.feature_builder import build_feature_snapshots_for_date
    assert build_feature_snapshots_for_date('2026-10-26')==[]


def test_delisting_keeps_price_history_and_returning_pair_can_reactivate(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    with get_connection() as c:
        c.execute("UPDATE matches SET source_provider='sportsbet'")
        mid=c.execute('SELECT id FROM matches').fetchone()[0]
        c.execute("INSERT INTO odds_snapshots(event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,source_provider,raw_response_id,fetched_at,created_at) VALUES ('185138',?,'book','match_winner',1.9,1.9,'sportsbet',0,'now','now')",(mid,))
    ingest_odds._prune_stale_sportsbet_odds_for_date('sportsbet','2026-10-26',{'other-event'})
    with get_connection() as c:
        assert c.execute('SELECT COUNT(*) FROM odds_snapshots').fetchone()[0]==1
        m=dict(c.execute('SELECT * FROM matches').fetchone())
        assert m['fixture_status']=='NOT_LISTED'
        from tennis_wc.ingestion.fixture_versions import upsert_fixture
        upsert_fixture(c,m,'later')
        assert c.execute('SELECT fixture_status FROM matches').fetchone()[0]=='ACTIVE'


def test_legacy_audit_can_quarantine_but_never_guess_old_players(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    from tennis_wc.ingestion.raw_response_store import store_raw_response
    raw=store_raw_response('mock','upcoming',{},[fixture_row('35','1','2026-10-27')],200,'match','day')
    from tennis_wc.database.fixture_audit import audit_fixture_versions,quarantine_plan
    with get_connection() as c:
        mid=c.execute('SELECT id FROM matches').fetchone()[0]
        c.execute('DELETE FROM fixture_observations')  # emulate the legacy writer
        c.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (?,1,'test','2000-01-01T00:00:00Z')",(mid,))
        c.execute('UPDATE matches SET raw_response_id=? WHERE id=?',(raw,mid))
        report=audit_fixture_versions(c)
        assert report['legacy_identity_cases']==1
        pair=tuple(c.execute('SELECT player_a_id,player_b_id FROM matches').fetchone())
        assert quarantine_plan(c,report,'now')==1
        assert tuple(c.execute('SELECT player_a_id,player_b_id FROM matches').fetchone())==pair
        assert c.execute('SELECT fixture_status FROM matches').fetchone()[0]=='DISPUTED'
        assert quarantine_plan(c,report,'later')==0
        c.execute("UPDATE matches SET match_date='2099-01-01'")
        with pytest.raises(ValueError,match='stale identity audit plan'):
            quarantine_plan(c,report,'later')


def test_prediction_store_freezes_pair_and_refuses_inactive_fixture(fixture_feed):
    import json
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    from tennis_wc.modelling.prediction_store import store_prediction
    filters=dict(decision='NO_BET',stake_units=0,confidence=0,risk='HIGH')
    pid=store_prediction(1,'test',{},filters)
    with get_connection() as c:
        evidence=json.loads(c.execute('SELECT pricing_json FROM predictions WHERE id=?',(pid,)).fetchone()[0])['fixture_at_prediction']
        assert evidence['start_time_utc']=='2026-10-26T12:00:00Z'
        c.execute("UPDATE matches SET fixture_status='DISPUTED'")
    with pytest.raises(ValueError,match='Inactive fixture identity'):
        store_prediction(1,'test',{},filters)


def test_ambiguous_name_only_odds_do_not_choose_first_fixture(fixture_feed):
    fixture_feed.rows=[fixture_row()]
    ingest_matches.ingest_upcoming_matches('2026-10-26')
    with get_connection() as c:
        m=dict(c.execute('SELECT * FROM matches').fetchone())
        from tennis_wc.ingestion.fixture_versions import upsert_fixture
        upsert_fixture(c,{**m,'source_provider':'another','provider_match_id':'another','market_event_id':'another'},'now')
        row=dict(event_id='unmapped',player_a_name='Stefanos Tsitsipas',player_b_name='Taylor Fritz')
        assert ingest_odds._resolve_odds_fixture(c,row,'2026-10-26',provider_name='sportsbet')==(None,True)


def test_provisional_book_event_reuse_creates_new_pair_version(fixture_feed):
    row=dict(event_id='book-1',player_a_name='Stefanos Tsitsipas',player_b_name='Taylor Fritz',competition='ATP Basel')
    first=ingest_odds._create_provisional_match_for_odds('sportsbet','2026-10-26',row,0)
    with get_connection() as c:
        original=tuple(c.execute('SELECT player_a_id,player_b_id FROM matches WHERE id=?',(first,)).fetchone())
    second=ingest_odds._create_provisional_match_for_odds('sportsbet','2026-10-27',{**row,'player_a_name':'Rinky Hijikata'},0)
    assert second!=first
    with get_connection() as c:
        assert tuple(c.execute('SELECT player_a_id,player_b_id FROM matches WHERE id=?',(first,)).fetchone())==original
        assert c.execute('SELECT supersedes_match_id FROM matches WHERE id=?',(second,)).fetchone()[0]==first
