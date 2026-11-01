from __future__ import annotations

from contextlib import closing
from datetime import date
import os
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from conftest import configure_test_db
from tennis_wc.database.db import get_connection, get_history_connection, get_history_scope
from tennis_wc.database.migrations import init_db
from tennis_wc.features.feature_builder import assemble_match_feature_snapshot, build_match_feature_snapshot
from tennis_wc.features.head_to_head import calculate_head_to_head_stats
from tennis_wc.research_elo_generations import utc_now
from tennis_wc import research_indexed_generations as indexed


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.ingestion.ingest_matches import ingest_default_history, ingest_upcoming_matches
    from tennis_wc.ingestion.ingest_odds import ingest_odds
    from tennis_wc.ingestion.ingest_rankings import ingest_rankings
    from tennis_wc.ingestion.ingest_tournaments import ingest_tournaments
    init_db()
    day = '2026-05-08'
    ingest_tournaments(day, day)
    ingest_rankings('ATP', day)
    ingest_default_history(day)
    ingest_upcoming_matches(day)
    ingest_odds(day)
    with closing(get_connection()) as c, c:
        match = dict(c.execute('SELECT * FROM matches LIMIT 1').fetchone())
        a, b = match['player_a_id'], match['player_b_id']
        target = c.execute('SELECT MAX(id)+1 FROM players').fetchone()[0]
        c.execute('INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) '
                  "VALUES (?,'Synthetic Target','ATP','mock','2000-01-01','2000-01-01')", (target,))
        for i, (winner, loser) in enumerate([(a,b),(b,a),(a,b)]):
            for role, player, opp, won in [('winner',winner,loser,1),('loser',loser,winner,0)]:
                c.execute('''INSERT INTO player_match_history
                    (provider_match_id,player_id,opponent_id,tour,match_date,surface,
                     tournament_external_id,tournament_level,round,format,won,source_provider,
                     raw_response_id,created_at) VALUES (?,?,?,'ATP',?,'hard','T','ATP250','R32',
                     'BO3',?,'jeff_sackmann',0,'2000-01-01')''',
                    (f'owned-{i}-{role}',player,opp,f'2026-04-0{i+1}',won))
    original = assemble_match_feature_snapshot(match['id'])[0]
    os.chmod(path, 0o400)
    yield dict(path=path, a=a, b=b, target=target, mid=match['id'], day=day,
               original=original, root=tmp_path)
    os.chmod(path, 0o600)


def build(data, name, amend=None):
    return indexed.build_public_snapshot(data['root']/name, source=data['path'],
        source_receipts=[dict(sha256='a'*64,captured_at='2000-01-01T00:00:00Z')], amend=amend)


def corrected(data):
    def amend(public):
        for row in public['player_match_history']:
            if row['provider_match_id'].startswith('owned-0-'):
                for k in ['player_id','opponent_id']:
                    if row[k] == data['a']:row[k] = data['target']
    return amend


def registry(data):
    return indexed.ShadowGenerationRegistry.create(data['root']/'registry.sqlite')


def activated_at(reg):
    with sqlite3.connect(reg.path) as c:
        return c.execute('SELECT MAX(observed_at) FROM activations').fetchone()[0]


def test_native_feature_helpers_pin_one_durable_version_and_rollback(seeded):
    d=seeded;source_hash=indexed.file_sha(d['path'])
    old=build(d,'old.sqlite');new=build(d,'new.sqlite',corrected(d))
    reg=registry(d);old_id=reg.register(Path(old['path']));new_id=reg.register(Path(new['path']))
    assert reg.register(Path(old['path']))==old_id
    reg.activate(old_id,reason='old');before=activated_at(reg)
    with reg.native_scope(knowledge_at=before):
        baseline=assemble_match_feature_snapshot(d['mid'])[0]
        old_count=calculate_head_to_head_stats(d['a'],d['b'],None,date.fromisoformat(d['day']))['matches']
        # A helper that closes its connection must not close the shared revision.
        get_history_connection().close()
        assert get_history_connection().execute('SELECT COUNT(*) FROM players').fetchone()[0]>0
    reg.activate(new_id,reason='counterfactual repair');after=activated_at(reg)
    with reg.native_scope(knowledge_at=after):
        candidate=assemble_match_feature_snapshot(d['mid'])[0]
        new_count=calculate_head_to_head_stats(d['a'],d['b'],None,date.fromisoformat(d['day']))['matches']
        assert new_count==old_count-1
        assert candidate['player_a']['overall_elo']['provenance']['revision_id']==new_id
        assert candidate['player_a']['head_to_head']['matches']['value']==new_count
        assert candidate['player_a']['fatigue']['provenance']['revision_id']==new_id
        assert candidate['shadow_backbone'] is not None
        assert candidate['data_quality']['is_valid'] is False
        assert candidate['data_quality']['score']==0
        assert candidate['feature_set_version'].endswith('+unqualified-generation')
    assert get_history_scope() is None
    with reg.native_scope(knowledge_at=before):
        assert assemble_match_feature_snapshot(d['mid'])[0]['player_a']['head_to_head']==baseline['player_a']['head_to_head']
    reg.activate(old_id,reason='rollback');rolled=activated_at(reg)
    with reg.native_scope(knowledge_at=rolled):
        assert get_history_scope()['revision_id']==old_id
    with reg.native_scope(knowledge_at=after):
        assert get_history_scope()['revision_id']==new_id
    assert indexed.file_sha(d['path'])==source_hash


def test_missing_version_never_falls_back_to_live_source(seeded):
    reg=registry(seeded)
    with pytest.raises(ValueError,match='no history generation'):
        with reg.native_scope(knowledge_at='2020-01-01T00:00:00Z'):
            assemble_match_feature_snapshot(seeded['mid'])
    assert get_history_scope() is None


def test_shadow_writes_are_refused_and_scope_restores_after_exception(seeded):
    d=seeded;result=build(d,'old.sqlite');reg=registry(d)
    gid=reg.register(Path(result['path']));reg.activate(gid,reason='test')
    with pytest.raises(ValueError,match='persist'):
        with reg.native_scope(knowledge_at=activated_at(reg)):
            build_match_feature_snapshot(d['mid'])
    assert get_history_scope() is None
    with reg.native_scope(knowledge_at=activated_at(reg)):
        with closing(get_connection()) as c:
            with pytest.raises(sqlite3.OperationalError):c.execute('UPDATE players SET name=name')
        with pytest.raises(sqlite3.OperationalError):
            get_history_connection().execute('UPDATE players SET name=name')
        with pytest.raises(ValueError,match='nested'):
            with reg.native_scope(knowledge_at=activated_at(reg)):pass
    assert get_history_scope() is None


def test_new_snapshot_has_no_private_payload_or_fixtures(seeded):
    info=build(seeded,'public.sqlite')
    with sqlite3.connect(info['path']) as c:
        for table in ['matches','odds_snapshots','raw_api_responses','predictions','bet_ledger',
                      'feature_snapshots','retained_payload_blobs']:
            assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0]>0
    assert Path(info['path']).stat().st_mode&0o222==0


def test_failed_build_cannot_register_or_change_active_version(seeded):
    d=seeded;old=build(d,'old.sqlite');reg=registry(d)
    gid=reg.register(Path(old['path']));reg.activate(gid,reason='old')
    def bad(public):public['players'][0]['unexpected_column']=1
    with pytest.raises(ValueError,match='unsupported'):
        build(d,'bad.sqlite',bad)
    with pytest.raises(ValueError,match='sealed'):
        reg.register(d['root']/'bad.sqlite')
    with reg.native_scope(knowledge_at=utc_now()):assert get_history_scope()['revision_id']==gid


def test_snapshot_tampering_is_detected(seeded):
    d=seeded;info=build(d,'old.sqlite');reg=registry(d);gid=reg.register(Path(info['path']))
    os.chmod(info['path'],0o600)
    with sqlite3.connect(info['path']) as c:c.execute("UPDATE players SET name='changed'")
    os.chmod(info['path'],0o400)
    with pytest.raises(ValueError,match='digest'):
        reg.activate(gid,reason='tampered')


def test_wrong_source_file_cannot_supply_portable_raw_ids(seeded,monkeypatch):
    d=seeded;info=build(d,'old.sqlite');reg=registry(d);gid=reg.register(Path(info['path']));reg.activate(gid,reason='old')
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+str(d['root']/'other.sqlite'))
    with pytest.raises(ValueError,match='configured'):
        with reg.native_scope(knowledge_at=utc_now()):pass
    assert get_history_scope() is None


def test_registry_does_not_open_native_database_or_overwrite_files(seeded):
    with pytest.raises(ValueError,match='registry'):
        indexed.ShadowGenerationRegistry(seeded['path'])
    with pytest.raises((ValueError,FileExistsError)):
        indexed.ShadowGenerationRegistry.create(seeded['path'])
    os.chmod(seeded['path'],0o600)
    with pytest.raises(ValueError,match='frozen'):
        build(seeded,'cannot.sqlite')
    assert not (seeded['root']/'cannot.sqlite').exists()


def test_future_source_or_backdated_activation_cannot_enter_registry(seeded):
    d=seeded
    with pytest.raises(ValueError,match='future'):
        indexed.build_public_snapshot(d['root']/'future.sqlite',source=d['path'],
            source_receipts=[dict(sha256='a'*64,captured_at='2999-01-01T00:00:00Z')])
    info=build(d,'old.sqlite');reg=registry(d);gid=reg.register(Path(info['path']))
    with patch.object(indexed,'utc_now',return_value='2000-01-01T00:00:00Z'):
        with pytest.raises(ValueError,match='clock'):reg.activate(gid,reason='backdate')


def test_event_cutoff_never_falls_back_to_final_current_elo(seeded):
    from tennis_wc.features.feature_builder import _build_player_payload
    d=seeded;info=build(d,'old.sqlite');reg=registry(d)
    gid=reg.register(Path(info['path']));reg.activate(gid,reason='old')
    with reg.native_scope(knowledge_at=utc_now()):
        snapshot=assemble_match_feature_snapshot(d['mid'])[0]
        context=snapshot['match_context']
        assert get_history_connection().execute('SELECT overall_elo FROM players WHERE id=?',
                                                (d['a'],)).fetchone()[0] is not None
        payload=_build_player_payload(get_history_connection(),d['a'],d['b'],context,
                                      date(2026,4,1),persist_derived=False)
        assert payload['overall_elo']['value'] is None
        assert payload['surface_elo']['value'] is None


def test_file_replacement_and_inplace_source_changes_are_refused(seeded):
    d=seeded;info=build(d,'old.sqlite');reg=registry(d)
    gid=reg.register(Path(info['path']));reg.activate(gid,reason='old')
    os.chmod(d['path'],0o600)
    with sqlite3.connect(d['path']) as c:c.execute("UPDATE players SET name=name||' source changed'")
    os.chmod(d['path'],0o400)
    with pytest.raises(ValueError,match='replaced'):
        with reg.native_scope(knowledge_at=utc_now()):pass
    assert get_history_scope() is None


def test_readonly_baseline_scope_does_not_select_a_history_revision(seeded):
    from tennis_wc.database.db import readonly_source_scope
    d=seeded
    with readonly_source_scope(d['path']):
        assert get_history_scope() is None
        with closing(get_connection()) as c:
            assert c.execute('PRAGMA query_only').fetchone()[0]==1
            with pytest.raises(sqlite3.OperationalError):c.execute('UPDATE players SET name=name')
        assert assemble_match_feature_snapshot(d['mid'])[0]['feature_set_version']=='stage3.v1'
    with closing(get_connection()) as c:
        assert c.execute('PRAGMA query_only').fetchone()[0]==0


def test_writable_revision_or_source_is_never_used_as_immutable(seeded):
    d=seeded;info=build(d,'old.sqlite');reg=registry(d);gid=reg.register(Path(info['path']))
    os.chmod(info['path'],0o600)
    with pytest.raises(ValueError,match='sealed'):reg.activate(gid,reason='not immutable')
    os.chmod(info['path'],0o400);reg.activate(gid,reason='restored seal')
    os.chmod(d['path'],0o600)
    with pytest.raises(ValueError,match='frozen'):
        with reg.native_scope(knowledge_at=utc_now()):pass


def test_source_scope_cannot_change_inside_active_history_scope(seeded):
    from tennis_wc.database.db import readonly_source_scope
    d=seeded;info=build(d,'old.sqlite');reg=registry(d);gid=reg.register(Path(info['path']))
    reg.activate(gid,reason='old')
    with reg.native_scope(knowledge_at=utc_now()):
        with pytest.raises(ValueError,match='cannot change source'):
            with readonly_source_scope(d['path']):pass
        assert get_history_scope()['revision_id']==gid
    assert get_history_scope() is None


def test_missing_registry_is_not_silently_recreated_on_write(seeded):
    d=seeded;info=build(d,'old.sqlite');reg=registry(d);reg.path.unlink()
    with pytest.raises(sqlite3.OperationalError):reg.register(Path(info['path']))
    assert not reg.path.exists()


def test_registry_replacement_cannot_modify_foreign_database(seeded):
    d=seeded;reg=registry(d)
    reg.path.unlink()
    with sqlite3.connect(reg.path) as c:c.execute('CREATE TABLE foreign_data (value TEXT)')
    info=build(d,'old.sqlite')
    with pytest.raises(ValueError,match='replaced'):reg.register(Path(info['path']))
    with sqlite3.connect(reg.path) as c:
        assert c.execute('SELECT COUNT(*) FROM sqlite_master WHERE name="revisions"').fetchone()[0]==0


def profile_rows(public, data):
    import copy
    base=next(r for r in public['player_match_history'] if r['provider_match_id']=='owned-0-winner')
    first=max(r['id'] for r in public['player_match_history'])+1
    rows=[]
    for i in range(6):
        winner,loser=(data['a'],data['b']) if i%2==0 else (data['b'],data['a'])
        for role,player,opponent,won in [('winner',winner,loser,1),('loser',loser,winner,0)]:
            row=copy.deepcopy(base)
            row.update(id=first+len(rows),provider_match_id=f'owned-{i}-{role}',
                       player_id=player,opponent_id=opponent,won=won,
                       match_date=f'2026-04-0{i+1}',hold_rate=.65,break_rate=.3,
                       first_serve_points_won_pct=.6,second_serve_points_won_pct=.5,
                       return_points_won_pct=.4,ace_count=2,double_fault_count=1,
                       service_games_played=10,source_match_ref=None,canonical_event_key=None)
            if i==0 and player==data['a']:
                row.update(hold_rate=.95,ace_count=10,double_fault_count=8)
            rows.append(row)
    public['player_match_history']=rows


def test_serve_aces_double_faults_and_games_pin_caller_connection_to_same_revision(seeded):
    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.ace_model import player_ace_profile
    from tennis_wc.props.player_model import count_profile
    from tennis_wc.props.games_model import combined_hold
    d=seeded
    def baseline(public):profile_rows(public,d)
    def candidate(public):profile_rows(public,d);corrected(d)(public)
    old=build(d,'profile-old.sqlite',baseline);new=build(d,'profile-new.sqlite',candidate)
    reg=registry(d);old_id=reg.register(Path(old['path']));new_id=reg.register(Path(new['path']))
    def read():
        with closing(get_connection()) as source_conn:
            return (serve_return_profile(source_conn,d['a'],d['day']),
                    player_ace_profile(source_conn,d['a'],d['day'],'hard'),
                    count_profile(source_conn,d['a'],d['day'],'double_fault_count'),
                    combined_hold(source_conn,d['a'],d['b'],d['day']))
    reg.activate(old_id,reason='six controlled games')
    with reg.native_scope(knowledge_at=utc_now()):before=read()
    reg.activate(new_id,reason='first controlled perspective belongs to target')
    with reg.native_scope(knowledge_at=utc_now()):
        after=read()
        foreign=sqlite3.connect(':memory:')
        try:
            for call in [lambda:serve_return_profile(foreign,d['a'],d['day']),
                         lambda:player_ace_profile(foreign,d['a'],d['day'],'hard'),
                         lambda:count_profile(foreign,d['a'],d['day'],'double_fault_count'),
                         lambda:combined_hold(foreign,d['a'],d['b'],d['day'])]:
                with pytest.raises(ValueError,match='different source'):call()
        finally:foreign.close()
    assert before[0].matches==6 and after[0].matches==5
    assert before[1].n==6 and after[1].n==5
    assert before[2].n==6 and after[2].n==5
    assert before[3]==pytest.approx(1.35)
    assert after[3]==pytest.approx(1.30)
    assert set(after[0].history_ids)<set(before[0].history_ids)
    assert set(after[1].history_ids)<set(before[1].history_ids)
