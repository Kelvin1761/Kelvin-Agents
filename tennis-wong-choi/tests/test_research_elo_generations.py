"""Temporal and failure contracts for the memory-only generation experiment."""
from __future__ import annotations

import copy
import sqlite3
from unittest.mock import patch

import pytest

from tennis_wc import research_elo_generations as gen
from tennis_wc.modelling.elo_replay import replay_elo

BEFORE = '2001-05-31T23:59:59.999999Z'
FIRST = '2001-06-01T00:00:00Z'
SECOND = '2001-06-02T00:00:00Z'
THIRD = '2001-06-03T00:00:00Z'
EVENT = '2001-07-01'


def fixture_input():
    history = []
    games = [(1, 2, '01', 'hard'), (2, 3, '02', 'hard'),
             (3, 1, '03', 'clay'), (3, 2, '04', 'hard'),
             (2, 5, '04', None), (5, 3, '05', None)]
    for i, (winner, loser, day, surface) in enumerate(games):
        for role, player, opponent, won in [('winner', winner, loser, 1),
                                            ('loser', loser, winner, 0)]:
            history.append(dict(id=len(history)+1, source_provider='jeff_sackmann',
                                provider_match_id=f'm{i}-{role}', player_id=player,
                                opponent_id=opponent, won=won, match_date=f'2000-06-{day}',
                                surface=surface, history_status='ACTIVE', raw_response_id=10))
    return dict(history=history, players=[dict(id=i, name=f'P{i}') for i in range(1, 6)],
                winner_keys=[[r['source_provider'], r['provider_match_id'], r['player_id']]
                             for r in history if r['won']],
                mappings=[dict(provider='test', external_id='person-a', internal_id=1)],
                source_receipts=[dict(sha256='a'*64, captured_at='2000-06-10T00:00:00Z')])


def corrected(data):
    out = copy.deepcopy(data)
    for row in out['history'][:2]:
        for key in ('player_id', 'opponent_id'):
            if row[key] == 1:
                row[key] = 4
    out['winner_keys'][0][2] = 4
    out['mappings'][0]['internal_id'] = 4
    return out


def build_at(store, data, clock, activate=True):
    with patch.object(gen, 'utc_now', return_value=clock):
        gid = store.build(**data)
        if activate:
            store.activate(gid, reason='synthetic version test')
    return gid


@pytest.fixture
def store():
    instance = gen.ResearchEloGenerations()
    yield instance
    instance.conn.close()


def test_repair_switches_history_mapping_and_elo_together_at_actual_clock(store):
    data = fixture_input()
    old = build_at(store, data, FIRST)
    new = build_at(store, corrected(data), SECOND)
    assert store.snapshot_as_of(knowledge_at=BEFORE) is None
    assert store.rating_as_of(1, event_before=EVENT, knowledge_at=BEFORE) is None
    assert store.history_as_of(1, event_before=EVENT, knowledge_at=BEFORE) == []
    before = store.snapshot_as_of(knowledge_at='2001-06-01T23:59:59.999999Z')
    after = store.snapshot_as_of(knowledge_at=SECOND)
    assert before['generation_id'] == old and after['generation_id'] == new
    assert before['history'][0]['player_id'] == before['mappings'][0]['internal_id'] == 1
    assert after['history'][0]['player_id'] == after['mappings'][0]['internal_id'] == 4
    assert store.history_as_of(4, event_before=EVENT, knowledge_at=FIRST) == []
    assert len(store.history_as_of(4, event_before=EVENT, knowledge_at=SECOND)) == 1
    # A shared opponent's later rating changes too, not just the repaired identities.
    assert store.rating_as_of(3, event_before=EVENT, knowledge_at=FIRST) != store.rating_as_of(
        3, event_before=EVENT, knowledge_at=SECOND)
    assert after['qualification'] == gen.QUALIFICATION


def test_event_date_remains_strict_and_same_day_legacy_policy_is_preserved(store):
    build_at(store, fixture_input(), FIRST)
    assert store.history_as_of(1, event_before='2000-06-01', knowledge_at=FIRST) == []
    assert store.rating_as_of(1, event_before='2000-06-01', knowledge_at=FIRST) is None
    assert store.rating_as_of(1, event_before='2000-06-02', knowledge_at=FIRST) == 1500
    snapshot = store.snapshot_as_of(knowledge_at=FIRST)
    # Player 2 plays twice on June 4: first pre-match, last post-match.
    legacy = next(r for r in snapshot['legacy'] if r[:3] == [2, '2000-06-04', ''])
    shadow = next(r for r in snapshot['shadow_v2'] if r[:3] == [2, '2000-06-04', ''])
    assert legacy[4] == 2 and shadow[4] == 4
    assert store.rating_as_of(2, event_before='2000-06-05', knowledge_at=FIRST) == legacy[3]
    assert legacy[3] != shadow[3]


def test_missing_legacy_never_uses_current_or_shadow(store):
    build_at(store, fixture_input(), FIRST)
    assert store.rating_as_of(5, event_before='2000-06-04', knowledge_at=FIRST) is None
    assert store.rating_as_of(999, event_before=EVENT, knowledge_at=FIRST) is None
    overall = store.rating_as_of(1, event_before=EVENT, knowledge_at=FIRST)
    assert store.rating_as_of(1, event_before=EVENT, knowledge_at=FIRST, surface=' Grass ') == overall


def test_rollback_is_new_event_and_does_not_rewrite_intervening_knowledge(store):
    data = fixture_input()
    old = build_at(store, data, FIRST)
    new = build_at(store, corrected(data), SECOND)
    with patch.object(gen, 'utc_now', return_value=THIRD):
        store.activate(old, reason='rollback')
    assert store.snapshot_as_of(knowledge_at=FIRST)['generation_id'] == old
    assert store.snapshot_as_of(knowledge_at=SECOND)['generation_id'] == new
    assert store.snapshot_as_of(knowledge_at=THIRD)['generation_id'] == old
    assert store.conn.execute('SELECT COUNT(*) FROM research_elo_activations').fetchone()[0] == 3


def test_build_without_activation_is_invisible_and_identical_rebuild_is_idempotent(store):
    data = fixture_input()
    old = build_at(store, data, FIRST)
    new = build_at(store, corrected(data), SECOND, activate=False)
    assert new != old
    assert store.snapshot_as_of(knowledge_at=SECOND)['generation_id'] == old
    assert build_at(store, data, THIRD, activate=False) == old
    assert store.conn.execute('SELECT COUNT(*) FROM research_elo_generations').fetchone()[0] == 2


@pytest.mark.parametrize('change', ['source_reference', 'receipt', 'mapping'])
def test_refresh_cannot_reuse_earlier_generation_clock(store, change):
    data = fixture_input()
    old = build_at(store, data, FIRST)
    fresh = copy.deepcopy(data)
    if change == 'source_reference':
        fresh['history'][0]['source_match_ref'] = 'm0-winner'
    elif change == 'receipt':
        fresh['source_receipts'][0]['captured_at'] = SECOND
    else:
        fresh['mappings'][0]['external_id'] = 'source-renamed'
    new = build_at(store, fresh, SECOND)
    assert new != old
    assert store.snapshot_as_of(knowledge_at=FIRST)['generation_id'] == old
    assert store.snapshot_as_of(knowledge_at=SECOND)['available_at'].startswith('2001-06-02')


def test_caller_mutation_cannot_change_stored_facts_or_returned_snapshots(store):
    data = fixture_input()
    build_at(store, data, FIRST)
    data['history'][0]['player_id'] = 999
    snap = store.snapshot_as_of(knowledge_at=FIRST)
    snap['history'][0]['player_id'] = 888
    assert store.snapshot_as_of(knowledge_at=FIRST)['history'][0]['player_id'] == 1


@pytest.mark.parametrize('failure', ['calculation', 'insert', 'backward_clock'])
def test_failed_build_keeps_previous_generation_and_activation(store, failure):
    data = fixture_input()
    old = build_at(store, data, FIRST)
    if failure == 'insert':
        store.conn.execute('''CREATE TRIGGER fail_new_generation BEFORE INSERT ON
            research_elo_generations BEGIN SELECT RAISE(ABORT,'injected failure'); END''')
    with patch.object(gen, 'utc_now', side_effect=([SECOND, FIRST] if failure == 'backward_clock'
                                                 else lambda: SECOND)):
        if failure == 'calculation':
            with patch.object(gen, 'replay_elo', side_effect=ValueError('calculation failed')):
                with pytest.raises(ValueError):
                    store.build(**corrected(data))
        else:
            with pytest.raises((ValueError, sqlite3.IntegrityError)):
                store.build(**corrected(data))
    assert store.conn.execute('SELECT COUNT(*) FROM research_elo_generations').fetchone()[0] == 1
    assert store.snapshot_as_of(knowledge_at=SECOND)['generation_id'] == old


@pytest.mark.parametrize('table', ['research_elo_generations', 'research_elo_activations'])
@pytest.mark.parametrize('action', ['UPDATE', 'DELETE'])
def test_generation_and_activation_are_append_only(store, table, action):
    build_at(store, fixture_input(), FIRST)
    sql = f'UPDATE {table} SET id=id' if action == 'UPDATE' else f'DELETE FROM {table}'
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        store.conn.execute(sql)
    store.conn.rollback()
    assert store.snapshot_as_of(knowledge_at=FIRST) is not None


def test_rejects_disk_database_before_creating_any_generation_tables(tmp_path):
    with sqlite3.connect(tmp_path/'not-live.sqlite') as conn:
        with pytest.raises(ValueError, match='memory'):
            gen.ResearchEloGenerations(conn)
        assert conn.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0] == 0


def test_rechecks_attached_database_before_every_operation(store, tmp_path):
    build_at(store, fixture_input(), FIRST)
    store.conn.execute('ATTACH DATABASE ? AS other', (str(tmp_path/'attached.sqlite'),))
    with pytest.raises(ValueError, match='memory'):
        store.snapshot_as_of(knowledge_at=FIRST)
    with pytest.raises(ValueError, match='memory'):
        store.build(**fixture_input())
    with pytest.raises(ValueError, match='memory'):
        store.activate(1, reason='should fail')


def test_rejects_caller_transaction_without_committing_it():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE caller (id INTEGER)')
    conn.execute('INSERT INTO caller VALUES (1)')
    with pytest.raises(ValueError, match='external connections'):
        gen.ResearchEloGenerations(conn)
    assert conn.in_transaction
    conn.rollback()
    assert conn.execute('SELECT COUNT(*) FROM caller').fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize('fault', ['missing_order', 'duplicate_order', 'wrong_order',
                                   'missing_player', 'duplicate_player', 'empty_receipts',
                                   'bad_hash', 'naive_clock', 'future_receipt', 'nan'])
def test_invalid_input_never_builds_or_activates(store, fault):
    data = fixture_input()
    if fault == 'missing_order':data['winner_keys'].pop()
    elif fault == 'duplicate_order':data['winner_keys'].append(data['winner_keys'][0])
    elif fault == 'wrong_order':data['winner_keys'].reverse()
    elif fault == 'missing_player':data['players'].pop()
    elif fault == 'duplicate_player':data['players'].append(data['players'][0])
    elif fault == 'empty_receipts':data['source_receipts'] = []
    elif fault == 'bad_hash':data['source_receipts'][0]['sha256'] = 'invalid'
    elif fault == 'naive_clock':data['source_receipts'][0]['captured_at'] = '2000-06-10'
    elif fault == 'future_receipt':data['source_receipts'][0]['captured_at'] = '2999-01-01T00:00:00Z'
    elif fault == 'nan':data['history'][0]['opponent_elo'] = float('nan')
    with pytest.raises(ValueError):
        build_at(store, data, FIRST)
    assert store.snapshot_as_of(knowledge_at=FIRST) is None
    assert store.conn.execute('SELECT COUNT(*) FROM research_elo_generations').fetchone()[0] == 0


def test_bad_activation_clock_or_unknown_generation_cannot_switch(store):
    old = build_at(store, fixture_input(), SECOND)
    with patch.object(gen, 'utc_now', return_value=FIRST):
        with pytest.raises(ValueError):store.activate(old, reason='backdated rollback')
    with pytest.raises(ValueError):store.activate(999, reason='missing')
    with pytest.raises(ValueError):store.activate(old, reason=' ')
    assert store.snapshot_as_of(knowledge_at=SECOND)['generation_id'] == old


def test_digest_corruption_is_detected_on_selection(store):
    build_at(store, fixture_input(), FIRST)
    store.conn.execute('DROP TRIGGER research_elo_generations_no_update')
    store.conn.execute("UPDATE research_elo_generations SET payload_json='{}'")
    store.conn.commit()
    with pytest.raises(ValueError, match='digest'):
        store.snapshot_as_of(knowledge_at=FIRST)


def test_calculator_handles_no_surface_and_fixed_k_without_mutating_inputs():
    rows = [r for r in fixture_input()['history'] if r['won']]
    untouched = copy.deepcopy(rows)
    result = replay_elo(rows, initial_rating=1400, k_factor=20)
    assert result.history_rows[0] == (1, '2000-06-01', '', 1400, 0)
    assert result.post_rows[0][3] == 1410
    assert rows == untouched
    assert result.surface_ratings[5] == {}


def test_unnamed_temporary_disk_connection_is_refused_even_with_memory_journal():
    conn = sqlite3.connect('')
    conn.execute('PRAGMA journal_mode=MEMORY')
    assert conn.execute('PRAGMA database_list').fetchone()[2] == ''
    with pytest.raises(ValueError, match='external connections'):
        gen.ResearchEloGenerations(conn)
    assert conn.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0] == 0
    conn.close()


def test_existing_store_will_not_commit_a_callers_unfinished_transaction(store):
    store.conn.execute('CREATE TABLE caller (id INTEGER)')
    store.conn.execute('INSERT INTO caller VALUES (1)')
    with pytest.raises(ValueError, match='transaction'):
        store.build(**fixture_input())
    with pytest.raises(ValueError, match='transaction'):
        store.snapshot_as_of(knowledge_at=FIRST)
    assert store.conn.in_transaction
    store.conn.rollback()
    assert store.conn.execute('SELECT COUNT(*) FROM caller').fetchone()[0] == 0
