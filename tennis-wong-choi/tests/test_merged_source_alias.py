"""A stale tour on a merged source row needs a complete, exact identity receipt."""
from __future__ import annotations

import sqlite3

import pytest

from conftest import configure_test_db
from tennis_wc.store.db import get_connection
from tennis_wc.store.migrations import init_db
from tennis_wc.sources.identity import ensure_identity_schema
from tennis_wc.sources import entity_mapping as mapping
from tennis_wc.sources.name_matching import normalise_player_name


def _seed(tmp_path, monkeypatch, *, name='Example Player', chained=False):
    path = configure_test_db(tmp_path, monkeypatch)
    init_db()
    with get_connection() as c:
        ensure_identity_schema(c)
        for pid, pname, tour in [(1, name, 'WTA'), (2, name, 'ATP'), (3, 'Different Person', 'ATP')]:
            c.execute('INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) '
                      'VALUES (?,?,?,?,?,?)', (pid, pname, tour, 'test', 'old', 'old'))
        if chained:
            c.execute('INSERT INTO players(id,name,tour,source_provider,created_at,updated_at,canonical_player_id) '
                      'VALUES (4,?,?,?,\'old\',\'old\',1)', (name, 'ATP', 'test'))
        c.execute('UPDATE players SET canonical_player_id=? WHERE id=2', (4 if chained else 1,))
        for old, target in ([(2, 4), (4, 1)] if chained else [(2, 1)]):
            c.execute('INSERT INTO player_merge_log(canonical_player_id,canonical_name,duplicate_id,duplicate_name,merged_at) '
                      'VALUES (?,?,?,?,?)', (target, name, old, name, '2026-11-04T00:00:00Z'))
        c.execute("INSERT INTO player_aliases(alias_norm,canonical_player_id,source) VALUES (?,1,'merge')",
                  (normalise_player_name(name),))
        c.execute("INSERT INTO provider_entities(provider_name,entity_type,provider_entity_id,internal_entity_id,entity_name,confidence_score,created_at,updated_at) "
                  "VALUES ('composite','player','espn-actor',2,?,1,'old','old')", (name,))
    return path


@pytest.mark.parametrize('chained', [False, True])
def test_proven_alias_reads_canonical_without_writes_then_ingests_to_it(tmp_path, monkeypatch, chained):
    _seed(tmp_path, monkeypatch, chained=chained)
    with get_connection() as c:
        before = [tuple(r) for r in c.execute('SELECT * FROM players ORDER BY id')]
        old = tuple(c.execute('SELECT * FROM players WHERE id=2').fetchone())
        assert mapping.existing_player_id(c, 'composite', 'espn-actor', 'Example Player', 'WTA') == 1
        assert c.total_changes == 0
        assert [tuple(r) for r in c.execute('SELECT * FROM players ORDER BY id')] == before
    assert mapping.get_or_create_player('composite', 'espn-actor', 'Example Player', 'WTA', 999, current_rank=20) == 1
    with get_connection() as c:
        assert tuple(c.execute('SELECT * FROM players WHERE id=2').fetchone()) == old
        assert c.execute('SELECT internal_entity_id FROM provider_entities').fetchone()[0] == 1
        assert tuple(c.execute('SELECT current_rank,raw_response_id FROM players WHERE id=1').fetchone()) == (20, 999)
        assert mapping.existing_player_id(c, 'composite', 'espn-actor', 'Example Player', 'WTA') == 1


@pytest.mark.parametrize('corrupt', [
    'missing_log', 'latest_log', 'old_log_name', 'target_log_name', 'missing_time', 'invalid_time',
    'missing_alias', 'manual_alias', 'wrong_alias', 'source_name', 'old_name',
    'target_name', 'target_tour', 'cycle', 'dangling', 'missing_second_log',
    'middle_name', 'initial', 'no_merge_schema',
])
def test_unproven_merge_still_rejects_without_renaming_or_rebinding(tmp_path, monkeypatch, corrupt):
    name = 'E. Player' if corrupt == 'initial' else 'Example Player'
    _seed(tmp_path, monkeypatch, name=name, chained=corrupt == 'missing_second_log')
    sql = {
        'missing_log': 'DELETE FROM player_merge_log',
        'latest_log': "INSERT INTO player_merge_log(canonical_player_id,canonical_name,duplicate_id,duplicate_name,merged_at) VALUES (3,'Example Player',2,'Example Player','later')",
        'old_log_name': "UPDATE player_merge_log SET duplicate_name='Different Person'",
        'target_log_name': "UPDATE player_merge_log SET canonical_name='Different Person'",
        'missing_time': 'UPDATE player_merge_log SET merged_at=NULL',
        'invalid_time': "UPDATE player_merge_log SET merged_at='not-a-timestamp'",
        'missing_alias': 'DELETE FROM player_aliases',
        'manual_alias': "UPDATE player_aliases SET source='manual'",
        'wrong_alias': 'UPDATE player_aliases SET canonical_player_id=3',
        'source_name': "UPDATE provider_entities SET entity_name='Different Person'",
        'old_name': "UPDATE players SET name='Different Person' WHERE id=2",
        'target_name': "UPDATE players SET name='Different Person' WHERE id=1",
        'target_tour': "UPDATE players SET tour='ATP' WHERE id=1",
        'cycle': 'UPDATE players SET canonical_player_id=2 WHERE id=1',
        'dangling': 'UPDATE players SET canonical_player_id=999 WHERE id=2',
        'missing_second_log': 'DELETE FROM player_merge_log WHERE duplicate_id=4',
        'middle_name': "UPDATE players SET name='Example Middle Player' WHERE id=1",
        'initial': 'SELECT 1',
        'no_merge_schema': 'DROP TABLE player_merge_log',
    }[corrupt]
    with get_connection() as c:
        c.execute(sql)
        if corrupt == 'cycle':
            c.execute("INSERT INTO player_merge_log(canonical_player_id,canonical_name,duplicate_id,duplicate_name,merged_at) VALUES (2,'Example Player',1,'Example Player','2026-11-04T00:00:00Z')")
        before_players = [tuple(r) for r in c.execute('SELECT * FROM players ORDER BY id')]
        before_aliases = [tuple(r) for r in c.execute('SELECT * FROM provider_entities ORDER BY id')]
        with pytest.raises(mapping.PlayerIdentityConflict):
            mapping.existing_player_id(c, 'composite', 'espn-actor', name, 'WTA')
    with pytest.raises(mapping.PlayerIdentityConflict):
        mapping.get_or_create_player('composite', 'espn-actor', name, 'WTA', 999, current_rank=1)
    with get_connection() as c:
        assert [tuple(r) for r in c.execute('SELECT * FROM players ORDER BY id')] == before_players
        assert [tuple(r) for r in c.execute('SELECT * FROM provider_entities ORDER BY id')] == before_aliases


def test_concurrent_alias_change_is_preserved_and_target_update_aborted(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    original = mapping._existing_player_choice

    def race(c, *args):
        result = original(c, *args)
        with sqlite3.connect(path) as other:
            other.execute("UPDATE provider_entities SET internal_entity_id=3,entity_name='Different Person'")
        return result

    monkeypatch.setattr(mapping, '_existing_player_choice', race)
    with pytest.raises(mapping.PlayerIdentityConflict, match='alias changed during resolution'):
        mapping.get_or_create_player('composite', 'espn-actor', 'Example Player', 'WTA', 999, current_rank=1)
    with get_connection() as c:
        assert tuple(c.execute('SELECT internal_entity_id,entity_name FROM provider_entities').fetchone()) == (3, 'Different Person')
        assert tuple(c.execute('SELECT current_rank,raw_response_id FROM players WHERE id=1').fetchone()) == (None, None)


@pytest.mark.parametrize('mutation', [
    "UPDATE players SET name='Different Person' WHERE id=1",
    "UPDATE player_merge_log SET merged_at=NULL",
])
def test_concurrent_identity_receipt_change_prevents_rebind(tmp_path, monkeypatch, mutation):
    path = _seed(tmp_path, monkeypatch)
    original = mapping._existing_player_choice

    def race(c, *args):
        result = original(c, *args)
        with sqlite3.connect(path) as other:
            other.execute(mutation)
        return result

    monkeypatch.setattr(mapping, '_existing_player_choice', race)
    with pytest.raises(mapping.PlayerIdentityConflict, match='merge receipt changed'):
        mapping.get_or_create_player('composite', 'espn-actor', 'Example Player', 'WTA', 999)
    with get_connection() as c:
        assert c.execute('SELECT internal_entity_id FROM provider_entities').fetchone()[0] == 2
        assert c.execute('SELECT raw_response_id FROM players WHERE id=1').fetchone()[0] is None
        if 'SET name' in mutation:
            assert c.execute('SELECT name FROM players WHERE id=1').fetchone()[0] == 'Different Person'
        else:
            assert c.execute('SELECT merged_at FROM player_merge_log').fetchone()[0] is None


@pytest.mark.parametrize('has_receipt', [True, False])
def test_real_history_ingress_uses_canonical_pair_or_holds_it(tmp_path, monkeypatch, has_receipt):
    from types import SimpleNamespace
    from tennis_wc.sources import ingest_matches

    _seed(tmp_path, monkeypatch)
    with get_connection() as c:
        c.execute("UPDATE players SET tour='WTA',name='Opposing Player' WHERE id=3")
        if not has_receipt:
            c.execute('DELETE FROM player_merge_log')
    common = dict(tour='WTA', match_date='2026-11-04', tournament_id='example-2026',
                  tournament_level='WTA_250', round='R1', format='BO3', surface='Hard')
    rows = [dict(common, id='source-winner', player_id='espn-actor', player_name='Example Player',
                 opponent_id='opponent', opponent_name='Opposing Player', won=True, hold_rate=.75),
            dict(common, id='source-loser', player_id='opponent', player_name='Opposing Player',
                 opponent_id='espn-actor', opponent_name='Example Player', won=False, hold_rate=.55)]
    monkeypatch.setattr(ingest_matches, 'get_tennis_provider', lambda: SimpleNamespace(
        provider_name='composite', fetch_historical_matches=lambda start, end: rows))
    assert ingest_matches.ingest_historical_matches('2026-11-04', '2026-11-04') == (2 if has_receipt else 0)
    with get_connection() as c:
        saved = [tuple(r) for r in c.execute('SELECT player_id,opponent_id,won,hold_rate FROM player_match_history ORDER BY player_id')]
        assert saved == ([(1, 3, 1, .75), (3, 1, 0, .55)] if has_receipt else [])
        assert c.execute('SELECT tour FROM players WHERE id=2').fetchone()[0] == 'ATP'
        assert c.execute("SELECT internal_entity_id FROM provider_entities WHERE provider_entity_id='espn-actor'").fetchone()[0] == (1 if has_receipt else 2)



def test_caller_can_catch_failed_revalidation_without_committing_partial_rebind(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    original = mapping._proven_merged_source_target
    calls = 0

    def reject_second_check(c, *args):
        nonlocal calls
        calls += 1
        return original(c, *args) if calls == 1 else None

    monkeypatch.setattr(mapping, '_proven_merged_source_target', reject_second_check)
    with get_connection() as c:
        c.execute('UPDATE players SET current_rank=100 WHERE id=3')
        with pytest.raises(mapping.PlayerIdentityConflict, match='merge receipt changed'):
            mapping.get_or_create_player('composite', 'espn-actor', 'Example Player', 'WTA', 999, connection=c)
        assert c.execute('SELECT internal_entity_id FROM provider_entities').fetchone()[0] == 2
        assert c.execute('SELECT raw_response_id FROM players WHERE id=1').fetchone()[0] is None
    with get_connection() as c:
        assert c.execute('SELECT current_rank FROM players WHERE id=3').fetchone()[0] == 100
        assert c.execute('SELECT internal_entity_id FROM provider_entities').fetchone()[0] == 2
