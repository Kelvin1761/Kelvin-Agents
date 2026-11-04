"""Source actor IDs, never initials, must own newly ingested TE history."""
from dataclasses import replace

import pytest

from test_tennisexplorer_history import _result, _setup as _history_setup, _Stub
from tennis_wc.database.db import get_connection
from tennis_wc.ingestion import ingest_tennisexplorer_history as corpus
from tennis_wc.identity.player_identity import ensure_identity_schema


SOURCE = 'https://www.tennisexplorer.com/player/bharadwaj-4e876/'


def _setup(tmp_path, monkeypatch):
    conn = _history_setup(tmp_path, monkeypatch)
    ensure_identity_schema(conn)
    conn.commit()
    return conn


def _player(conn, pid, name, tour='ATP', provider='sportsbet'):
    conn.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) "
                 "VALUES(?,?,?,?,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
                 (pid, name, tour, provider))


def _bind(conn, ref, pid, name, at='2026-01-01T00:00:00Z'):
    conn.execute("INSERT INTO provider_entities(provider_name,entity_type,provider_entity_id,"
                 "internal_entity_id,entity_name,confidence_score,created_at,updated_at) "
                 "VALUES('tennisexplorer','player',?,?,?,1,?,?)", (ref, pid, name, at, at))


def _lookup(conn, name='Bharadwaj S.', ref=SOURCE):
    return corpus._get_or_create_player(conn, name, 'ATP', [], source_actor_ref=ref)


def test_correct_book_tour_does_not_unlock_wrong_source_owner(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 21144, 'Siddharth Bharadwaj')
    conn.commit()
    result = replace(_result('ITF M15 Fixture', 'Bharadwaj S.', 'Example Opponent'),
                     player_a_source_ref=SOURCE)
    summary = corpus.ingest_tennisexplorer_history('2026-03-01', provider=_Stub({
        '2026-03-01': [result]}))
    assert summary['held_reasons'] == {'unbound_source_actor': 1}
    assert summary['rows'] == summary['players_created'] == 0
    with get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM provider_entities').fetchone()[0] == 0


def test_explicit_source_binding_precedes_wrong_global_alias(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 21144, 'Siddharth Bharadwaj')
    _player(conn, 32000, 'Shaurya Bharadwaj')
    _bind(conn, SOURCE, 32000, 'Bharadwaj Shaurya')
    conn.execute("INSERT INTO player_aliases(alias_norm,canonical_player_id,source,created_at) "
                 "VALUES('s bharadwaj',21144,'legacy','old')")
    assert _lookup(conn) == 32000
    assert _lookup(conn, ref=SOURCE.rstrip('/')) == 32000


def test_binding_full_name_conflict_is_not_hidden_by_same_initial(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 21144, 'Siddharth Bharadwaj')
    _bind(conn, SOURCE, 21144, 'Shaurya Bharadwaj')
    with pytest.raises(ValueError, match='source_binding_name_conflict'):
        _lookup(conn)


@pytest.mark.parametrize('at', ['2030-01-01T00:00:00Z', '2026-01-01', 'bad'])
def test_binding_clock_must_be_available_and_aware(tmp_path, monkeypatch, at):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, 'Shaurya Bharadwaj')
    _bind(conn, SOURCE, 1, 'Shaurya Bharadwaj', at=at)
    with pytest.raises(ValueError, match='source_binding_not_available'):
        _lookup(conn)


def test_source_binding_does_not_follow_a_later_merge(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, 'Shaurya Bharadwaj')
    _player(conn, 2, 'Siddharth Bharadwaj')
    _bind(conn, SOURCE, 1, 'Shaurya Bharadwaj')
    conn.execute('UPDATE players SET canonical_player_id=2 WHERE id=1')
    with pytest.raises(ValueError, match='source_binding_target_moved'):
        _lookup(conn)


def test_normalized_source_binding_collision_is_held(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, 'Shaurya Bharadwaj')
    _player(conn, 2, 'Siddharth Bharadwaj')
    _bind(conn, SOURCE, 1, 'Shaurya Bharadwaj')
    _bind(conn, SOURCE.rstrip('/'), 2, 'Siddharth Bharadwaj')
    with pytest.raises(ValueError, match='source_binding_collision'):
        _lookup(conn)


def test_legacy_te_spelling_without_source_key_is_not_proof(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, 'Bharadwaj S.', provider='tennisexplorer')
    with pytest.raises(ValueError, match='unbound_source_actor'):
        _lookup(conn)


@pytest.mark.parametrize('ref', [None, 'https://example.com/player/foo/',
                               SOURCE + '?annual=all', SOURCE + '#fragment'])
def test_source_key_must_be_an_official_individual_profile(tmp_path, monkeypatch, ref):
    conn = _setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='invalid_source_actor'):
        _lookup(conn, ref=ref)
    assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 0


def test_different_source_keys_with_identical_labels_are_distinct(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    a = _lookup(conn, name='Smith S.', ref='https://www.tennisexplorer.com/player/smith-a/')
    b = _lookup(conn, name='Smith S.', ref='https://www.tennisexplorer.com/player/smith-b/')
    assert a != b
    assert _lookup(conn, name='Smith S.', ref='https://www.tennisexplorer.com/player/smith-a') == a
    assert conn.execute('SELECT COUNT(*) FROM player_aliases').fetchone()[0] == 0


def test_identical_display_names_use_score_orientation_not_name_equality(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = replace(_result('ITF M15 Fixture', 'Smith S.', 'Smith S.'),
                     player_a_sets=0, player_b_sets=2,
                     sets=[{'player_a_games': 2, 'player_b_games': 6},
                           {'player_a_games': 3, 'player_b_games': 6}],
                     player_a_source_ref='https://www.tennisexplorer.com/player/smith-a/',
                     player_b_source_ref='https://www.tennisexplorer.com/player/smith-b/')
    summary = corpus.ingest_tennisexplorer_history('2026-03-01', provider=_Stub({
        '2026-03-01': [result]}))
    assert summary['matches'] == 1 and summary['rows'] == 2
    with get_connection() as conn:
        winner = conn.execute('SELECT player_id FROM player_match_history WHERE won=1').fetchone()[0]
        bound = conn.execute("SELECT internal_entity_id FROM provider_entities "
                             "WHERE provider_entity_id LIKE '%/smith-b/'").fetchone()[0]
        assert winner == bound


def test_full_display_name_alone_is_not_a_source_binding(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, 'Shaurya Bharadwaj')
    with pytest.raises(ValueError, match='unbound_source_actor'):
        _lookup(conn, name='Shaurya Bharadwaj')


def test_dangling_global_alias_is_held_without_minting_player(tmp_path, monkeypatch):
    conn = _setup(tmp_path, monkeypatch)
    conn.execute("INSERT INTO player_aliases(alias_norm,canonical_player_id,source,created_at) "
                 "VALUES('s bharadwaj',99999,'legacy','old')")
    with pytest.raises(ValueError, match='source_binding_target_missing'):
        _lookup(conn)
    assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0] == 0
