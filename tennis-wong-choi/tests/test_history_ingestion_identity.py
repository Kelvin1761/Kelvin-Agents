from __future__ import annotations

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.ingestion.ingest_sackmann import _insert_history_pair


def match(ordinal='26',stage='QF',aces='7'):
    return {'tourney_id':'2026-319','match_num':ordinal,'tourney_level':'A',
            'surface':'Hard','best_of':'3','round':stage,'score':'6-4 6-4',
            'w_ace':aces,'l_ace':'3'}


def test_reused_source_ordinal_cannot_put_new_stats_on_the_old_opponent(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='tennismylife_history')
    _insert_history_pair('ATP',match(stage='SF',aces='13'),2,1,3,'2026-07-20','2026-07-24T00:00:00Z',provider='tennismylife_history')
    with get_connection() as c:
        old=c.execute('SELECT ace_count FROM player_match_history WHERE player_id=1 AND opponent_id=2').fetchone()
        assert old['ace_count']==7
        assert c.execute('SELECT COUNT(*) FROM player_match_history WHERE player_id=1').fetchone()[0]==2


def test_renumbered_same_knockout_event_does_not_create_another_match(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='tennismylife_history')
    _insert_history_pair('ATP',match(ordinal='25'),2,1,2,'2026-07-20','2026-07-24T00:00:00Z',provider='tennismylife_history')
    with get_connection() as c:
        assert c.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0]==2


def test_source_fact_revision_preserves_old_generation_and_observation(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='tennismylife_history')
    _insert_history_pair('ATP',match(aces='13'),2,1,2,'2026-07-20','2026-07-24T00:00:00Z',provider='tennismylife_history')
    with get_connection() as c:
        rows=c.execute('SELECT * FROM player_match_history WHERE player_id=1 ORDER BY id').fetchall()
        assert [(r['ace_count'],r['history_status']) for r in rows]==[(7,'SUPERSEDED'),(13,'ACTIVE')]
        assert rows[1]['supersedes_history_id']==rows[0]['id']
        assert c.execute("SELECT COUNT(*) FROM history_observations WHERE observation_kind='SUPERSEDED'").fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM history_observations').fetchone()[0]==4


def test_conflicting_facts_in_same_raw_response_are_refused(tmp_path,monkeypatch):
    import pytest
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='tennismylife_history')
    with pytest.raises(ValueError,match='conflicting facts'):
        _insert_history_pair('ATP',match(aces='13'),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='tennismylife_history')
    with get_connection() as c:
        assert c.execute('SELECT ace_count FROM player_match_history WHERE player_id=1').fetchone()[0]==7


def test_dated_correction_across_new_year_uses_tournament_identity(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-12-31','2027-01-02T00:00:00Z',provider='tennismylife_history')
    _insert_history_pair('ATP',match(),2,1,2,'2027-01-01','2027-01-03T00:00:00Z',provider='tennismylife_history')
    with get_connection() as c:
        rows=c.execute("SELECT * FROM player_match_history WHERE player_id=1 AND history_status='ACTIVE'").fetchall()
        assert len(rows)==1
        assert rows[0]['match_date']=='2027-01-01'


def test_elo_rebuild_keeps_source_order_after_internal_history_rekey(tmp_path,monkeypatch):
    from tennis_wc.modelling.elo_builder import build_sackmann_elo
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        for pid in (1,2,3):
            c.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) VALUES (?,?,'ATP','test','now','now')",(pid,str(pid)))
        for key,win,lose in [('a',1,2),('z',3,1)]:
            for role,pid,opp in [('winner',win,lose),('loser',lose,win)]:
                c.execute("""INSERT INTO player_match_history(provider_match_id,player_id,opponent_id,tour,
                    match_date,tournament_external_id,tournament_level,round,format,won,source_provider,
                    raw_response_id,created_at) VALUES (?,?,?,'ATP','2026-06-01','T','ATP_250','QF','BO3',?,'tennismylife_history',0,'now')""",
                    (key+'-'+role,pid,opp,int(role=='winner')))
    build_sackmann_elo()
    with get_connection() as c:
        before=[tuple(r) for r in c.execute('SELECT id,overall_elo,surface_elo_json FROM players ORDER BY id')]
        c.execute('UPDATE player_match_history SET source_match_ref=provider_match_id')
        c.execute("UPDATE player_match_history SET provider_match_id=CASE WHEN provider_match_id LIKE 'a-%' THEN 'hc1-zz-' ELSE 'hc1-aa-' END || CASE WHEN won=1 THEN 'winner' ELSE 'loser' END")
    with get_connection() as c:
        c.execute("""INSERT INTO player_match_history(provider_match_id,player_id,opponent_id,tour,
            match_date,tournament_external_id,tournament_level,round,format,won,source_provider,
            raw_response_id,created_at) VALUES ('self-winner',1,1,'ATP','2026-06-02','T','ATP_250','SF','BO3',1,'tennismylife_history',0,'now')""")
    build_sackmann_elo()
    with get_connection() as c:
        assert before==[tuple(r) for r in c.execute('SELECT id,overall_elo,surface_elo_json FROM players ORDER BY id')]


def test_cross_provider_dedup_cannot_identify_a_match_from_nearby_pair_alone(tmp_path,monkeypatch):
    from tennis_wc.ingestion.ingest_sackmann import _history_pair_exists
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='jeff_sackmann')
    assert not _history_pair_exists('jeff_sackmann',1,2,'2026-07-27')


def test_cross_provider_dedup_preserves_distinct_events_and_rounds(tmp_path,monkeypatch):
    from tennis_wc.ingestion.ingest_sackmann import _history_pair_exists
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,1,2,'2026-07-20','2026-07-22T00:00:00Z',provider='jeff_sackmann')
    event=match()
    assert _history_pair_exists('jeff_sackmann',1,2,'2026-08-02',tour='ATP',event=event)
    assert not _history_pair_exists('jeff_sackmann',1,2,'2026-07-27',tour='ATP',event={**event,'tourney_id':'2026-999'})
    assert not _history_pair_exists('jeff_sackmann',1,2,'2026-07-27',tour='ATP',event=match(stage='SF'))
    assert not _history_pair_exists('jeff_sackmann',1,2,'2026-07-27',tour='ATP',event={**event,'best_of':None})


def test_cross_provider_same_event_opposite_winner_fails_visibly(tmp_path,monkeypatch):
    import pytest
    from tennis_wc.ingestion.ingest_sackmann import _history_pair_exists
    configure_test_db(tmp_path,monkeypatch);init_db()
    _insert_history_pair('ATP',match(),1,2,1,'2026-07-20','2026-07-22T00:00:00Z',provider='jeff_sackmann')
    with pytest.raises(ValueError,match='cross-provider winner conflict'):
        _history_pair_exists('jeff_sackmann',1,2,'2026-07-27',tour='ATP',event=match())
