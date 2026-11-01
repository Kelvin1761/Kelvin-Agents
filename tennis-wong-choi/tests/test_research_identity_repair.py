"""Transactional identity split experiments cannot mutate a persistent DB."""
from copy import deepcopy
import json
import sqlite3

import pytest

from tennis_wc.database.migrations import SCHEMA
from tennis_wc.database.history_observations import ensure_history_schema
from tennis_wc import research_identity_repair as repair


@pytest.fixture
def conn(monkeypatch):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.execute('ALTER TABLE players ADD COLUMN canonical_player_id INTEGER')
    ensure_history_schema(c)
    for pid, name in [(1,'Wrong Person'), (2,'Other Player'), (3,'Right Player'), (4,'Fourth Player')]:
        c.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) VALUES (?,?,'ATP','test','2020-01-01','2020-01-01')",(pid,name))
    source = dict(tourney_id='2021-E',match_num=1,winner_id='R123',winner_name='Right Player',
                  loser_id='O123',loser_name='Other Player')
    c.execute("INSERT INTO raw_api_responses(id,provider_name,endpoint,request_url_hash,request_params_json,response_json,status_code,fetched_at,created_at) VALUES (1,'jeff_sackmann','season','hash','{}',?,200,'2021-01-10','2021-01-10')",(json.dumps([source]),))
    for hid, pid, opp, won, role in [(10,1,2,1,'winner'),(11,2,1,0,'loser')]:
        c.execute("""INSERT INTO player_match_history(id,provider_match_id,player_id,opponent_id,tour,
            match_date,surface,tournament_external_id,tournament_level,round,format,won,hold_rate,
            source_provider,raw_response_id,created_at) VALUES (?,?,?,?,'ATP','2021-01-01','Hard',
            '2021-E','A','R32','BO3',?,0.8,'jeff_sackmann',1,'2021-01-10T00:00:00Z')""",
            (hid,'ATP-2021-E-1-'+role,pid,opp,won))
    c.commit()
    monkeypatch.setattr(repair,'utc_now',lambda:'2026-11-01T10:00:00Z')
    # Existing upsert has its own import, but is explicitly given the new clock.
    yield c
    c.close()


def proposal(conn):
    return repair.propose_split(conn,[10,11],[3,2])


def histories(conn):
    return [dict(r) for r in conn.execute('SELECT * FROM player_match_history ORDER BY id')]


def test_dry_run_is_deterministic_and_read_only(conn):
    before = conn.total_changes
    p = proposal(conn)
    assert p == proposal(conn)
    assert conn.total_changes == before
    assert p['qualification'] == 'SOURCE_LABEL_POLICY_ONLY_NOT_LIVE_AUTHORITY'
    assert p['source_roles']['winner'] == dict(id='R123',name='Right Player')


def test_split_retires_both_sides_and_links_new_generation(conn):
    p = proposal(conn)
    result = repair.apply_split(conn,p)
    all_rows = histories(conn)
    assert len(all_rows) == 4
    assert [r['history_status'] for r in all_rows[:2]] == ['SUPERSEDED']*2
    a,b = all_rows[2:]
    assert (a['player_id'],a['opponent_id'],b['player_id'],b['opponent_id']) == (3,2,2,3)
    assert (a['supersedes_history_id'],b['supersedes_history_id']) == (10,11)
    assert a['canonical_event_key'] == b['canonical_event_key']
    assert a['created_at'] == b['created_at'] == result['observed_at'] == '2026-11-01T10:00:00Z'
    assert a['raw_response_id'] == b['raw_response_id'] == 1
    assert a['hold_rate'] == b['hold_rate'] == 0.8
    assert all_rows[0]['created_at'] == '2021-01-10T00:00:00Z'
    count = conn.total_changes
    assert repair.apply_split(conn,p) == result
    assert conn.total_changes == count


def test_rollback_is_idempotent_and_observations_are_append_only(conn):
    before = histories(conn)
    p = proposal(conn)
    repair.apply_split(conn,p)
    receipts_before = list(conn.execute('SELECT * FROM history_observations'))
    result = repair.rollback_split(conn,p['proposal_id'])
    after = histories(conn)
    assert after[:2] == before
    assert all(r['history_status']=='SUPERSEDED' for r in after[2:])
    assert list(conn.execute('SELECT * FROM history_observations ORDER BY id'))[:len(receipts_before)] == receipts_before
    changes = conn.total_changes
    assert repair.rollback_split(conn,p['proposal_id']) == result
    assert changes == conn.total_changes
    with pytest.raises(repair.RepairConflict,match='cannot be reapplied'):
        repair.apply_split(conn,p)
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):
        conn.execute('DELETE FROM history_observations')


@pytest.mark.parametrize('mutation', ['history','target','raw','collision'])
def test_stale_proposal_is_rejected_without_additional_mutation(conn,mutation):
    p = proposal(conn)
    if mutation=='history':conn.execute('UPDATE player_match_history SET hold_rate=0.9 WHERE id=10')
    elif mutation=='target':conn.execute("UPDATE players SET name='Different Person' WHERE id=3")
    elif mutation=='raw':conn.execute("UPDATE raw_api_responses SET response_json='[]' WHERE id=1")
    else:
        row = histories(conn)[0];row.update(id=20,player_id=3,opponent_id=2,provider_match_id='different-key')
        conn.execute('INSERT INTO player_match_history('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
    before=histories(conn)
    observations=list(conn.execute('SELECT * FROM history_observations'))
    with pytest.raises(repair.RepairConflict):repair.apply_split(conn,p)
    assert histories(conn)==before
    assert list(conn.execute('SELECT * FROM history_observations'))==observations


def test_proposal_digest_cannot_be_changed(conn):
    p=deepcopy(proposal(conn));p['rows'][0]['hold_rate']=0.99
    with pytest.raises(repair.RepairConflict,match='digest'):repair.apply_split(conn,p)
    assert len(histories(conn))==2


@pytest.mark.parametrize('change', ['missing_side','extra_side','source_role','unknown_tour','merged_target','wrong_name','no_op','self_pair','duplicate_raw'])
def test_unqualified_pairs_are_held(conn,change):
    target=[3,2]
    if change=='missing_side':conn.execute('DELETE FROM player_match_history WHERE id=11')
    elif change=='extra_side':
        row=histories(conn)[0];row.update(id=20,player_id=4)
        conn.execute('INSERT INTO player_match_history('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
    elif change=='source_role':conn.execute("UPDATE player_match_history SET provider_match_id='ATP-2021-E-2-loser' WHERE id=11")
    elif change=='unknown_tour':conn.execute("UPDATE players SET tour='UNKNOWN' WHERE id=3")
    elif change=='merged_target':conn.execute('UPDATE players SET canonical_player_id=1 WHERE id=3')
    elif change=='wrong_name':conn.execute("UPDATE players SET name='Initial R' WHERE id=3")
    elif change=='no_op':target=[1,2]
    elif change=='self_pair':target=[3,3]
    else:
        body=json.loads(conn.execute('SELECT response_json FROM raw_api_responses WHERE id=1').fetchone()[0])
        conn.execute('UPDATE raw_api_responses SET response_json=? WHERE id=1',(json.dumps(body*2),))
    before=histories(conn)
    with pytest.raises(repair.RepairConflict):repair.propose_split(conn,[10,11],target)
    assert histories(conn)==before


def test_mid_apply_failure_rolls_back_all_rows_and_receipts(conn,monkeypatch):
    p=proposal(conn);before=histories(conn)
    real=repair.upsert_history_observation
    calls=[]
    def fail_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('simulated second-side failure')
        return real(*args,**kwargs)
    monkeypatch.setattr(repair,'upsert_history_observation',fail_second)
    with pytest.raises(RuntimeError,match='second-side'):repair.apply_split(conn,p)
    assert histories(conn)==before
    assert not list(conn.execute('SELECT * FROM history_observations'))


@pytest.mark.parametrize('which',['old','new'])
def test_rollback_refuses_concurrent_history_change(conn,which):
    p=proposal(conn);receipt=repair.apply_split(conn,p)
    hid=10 if which=='old' else receipt['new'][0]['id']
    conn.execute('UPDATE player_match_history SET opponent_elo=1234 WHERE id=?',(hid,))
    before=histories(conn)
    with pytest.raises(repair.RepairConflict,match='image'):repair.rollback_split(conn,p['proposal_id'])
    assert histories(conn)==before


def test_caller_transaction_is_not_committed(conn):
    p=proposal(conn)
    conn.execute('BEGIN')
    repair.apply_split(conn,p)
    assert conn.in_transaction
    conn.rollback()
    assert len(histories(conn))==2
    assert not list(conn.execute('SELECT * FROM history_observations'))


@pytest.mark.parametrize('api',['repeat_apply','rollback'])
@pytest.mark.parametrize('changed',['raw','target'])
def test_evidence_changes_after_apply_are_held(conn,api,changed):
    p=proposal(conn);repair.apply_split(conn,p)
    if changed=='raw':
        body=json.loads(conn.execute('SELECT response_json FROM raw_api_responses WHERE id=1').fetchone()[0])
        body[0]['extra']='new source fact'
        conn.execute('UPDATE raw_api_responses SET response_json=? WHERE id=1',(json.dumps(body),))
    else:conn.execute("UPDATE players SET updated_at='2026-11-02' WHERE id=3")
    before=histories(conn)
    with pytest.raises(repair.RepairConflict,match='evidence changed'):
        if api=='repeat_apply':repair.apply_split(conn,p)
        else:repair.rollback_split(conn,p['proposal_id'])
    assert histories(conn)==before


@pytest.mark.parametrize('kind',['file','attached','temporary'])
def test_persistent_or_temporary_disk_connections_rejected(tmp_path,kind):
    c=sqlite3.connect(str(tmp_path/'db.sqlite') if kind=='file' else ('' if kind=='temporary' else ':memory:'))
    c.row_factory=sqlite3.Row
    if kind=='attached':c.execute('ATTACH DATABASE ? AS external',(str(tmp_path/'attached.sqlite'),))
    with pytest.raises(repair.RepairConflict,match='memory'):
        repair.propose_split(c,[1,2],[3,4])
    assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[]
    c.close()
