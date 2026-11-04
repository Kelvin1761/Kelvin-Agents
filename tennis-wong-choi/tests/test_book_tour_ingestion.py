"""Explicit source competition markers must reach provisional player rows."""
import pytest

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.ingestion.entity_mapping import PlayerIdentityConflict
from tennis_wc.ingestion.ingest_odds import _create_provisional_match_for_odds
from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_competition_meta


@pytest.mark.parametrize('competition,tour', [
    ('ITF Women Example Futures', 'WTA'),
    ("ITF Women's Example Futures", 'WTA'),
    ('ITF Men Example Futures', 'ATP'),
    ("ITF Men's Example Futures", 'ATP'),
    ('UTR Pro Series Women', 'WTA'),
    ('UTR Pro Series Men', 'ATP'),
    ('Example Ladies Challenger', 'WTA'),
])
def test_explicit_marker_reaches_early_stage(competition, tour):
    result = sportsbet_competition_meta(competition, '2026-11-04')
    assert result.tour == tour
    assert not result.is_mvp_supported
    assert result.surface is result.indoor_outdoor is None
    assert result.tournament_name == competition


@pytest.mark.parametrize('competition', [
    'ITF Example Futures', 'UTR Singles', 'Example City', '', None,
    'ITF Women Men Futures', 'ITF WTA ATP Futures',
    'ITF Women Doubles', 'ITF Men Doubles', 'Women Example City',
])
def test_no_single_supported_source_marker_stays_unknown(competition):
    assert sportsbet_competition_meta(competition, '2026-11-04').tour == 'UNKNOWN'


def _seed(tmp_path, monkeypatch, tour='UNKNOWN'):
    configure_test_db(tmp_path, monkeypatch)
    init_db()
    with get_connection() as conn:
        for pid, name in [(1, 'Source One'), (2, 'Source Two')]:
            conn.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) "
                         "VALUES(?,?,?,'sportsbet','before','before')", (pid, name, tour))
            conn.execute("INSERT INTO provider_entities(provider_name,entity_type,provider_entity_id,"
                         "internal_entity_id,entity_name,confidence_score,created_at,updated_at) "
                         "VALUES('sportsbet','player',?,?,?,1,'before','before')",
                         ('player-' + name.lower().replace(' ', '-'), pid, name))


def _row(competition='ITF Women Example Futures'):
    return dict(event_id='source-test-1', player_a_name='Source One',
                player_b_name='Source Two', competition=competition)


def test_existing_source_ids_are_retained_when_tour_becomes_known(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    mid = _create_provisional_match_for_odds('sportsbet', '2026-11-04', _row(), 1)
    with get_connection() as conn:
        assert [tuple(r) for r in conn.execute('SELECT id,tour FROM players ORDER BY id')] == [(1, 'WTA'), (2, 'WTA')]
        match = conn.execute('SELECT player_a_id,player_b_id,tour FROM matches WHERE id=?', (mid,)).fetchone()
        assert tuple(match) == (1, 2, 'WTA')
        assert conn.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] == 0


def test_conflicting_known_source_identity_is_rejected(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, 'ATP')
    with pytest.raises(PlayerIdentityConflict):
        _create_provisional_match_for_odds('sportsbet', '2026-11-04', _row(), 1)
    with get_connection() as conn:
        assert {r[0] for r in conn.execute('SELECT tour FROM players')} == {'ATP'}
        assert conn.execute('SELECT COUNT(*) FROM matches').fetchone()[0] == 0


def test_unknown_source_does_not_borrow_gender_from_player_names(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _create_provisional_match_for_odds('sportsbet', '2026-11-04', _row('ITF Example Futures'), 1)
    with get_connection() as conn:
        assert {r[0] for r in conn.execute('SELECT tour FROM players')} == {'UNKNOWN'}


def test_second_player_conflict_rolls_back_first_player(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    with get_connection() as conn:
        conn.execute("UPDATE players SET tour='ATP' WHERE id=2")
    with pytest.raises(PlayerIdentityConflict):
        _create_provisional_match_for_odds('sportsbet', '2026-11-04', _row(), 1)
    with get_connection() as conn:
        assert [r[0] for r in conn.execute('SELECT tour FROM players ORDER BY id')] == ['UNKNOWN', 'ATP']
        assert conn.execute('SELECT COUNT(*) FROM tournaments').fetchone()[0] == 0


def test_fixture_failure_rolls_back_all_provisional_metadata(tmp_path, monkeypatch):
    from tennis_wc.ingestion import ingest_odds
    _seed(tmp_path, monkeypatch)

    def fail_fixture(*args, **kwargs):
        raise RuntimeError('injected fixture failure')

    monkeypatch.setattr(ingest_odds, 'upsert_fixture', fail_fixture)
    with pytest.raises(RuntimeError, match='injected fixture failure'):
        _create_provisional_match_for_odds('sportsbet', '2026-11-04', _row(), 1)
    with get_connection() as conn:
        assert {r[0] for r in conn.execute('SELECT tour FROM players')} == {'UNKNOWN'}
        assert conn.execute('SELECT COUNT(*) FROM tournaments').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM matches').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM provider_entities').fetchone()[0] == 2
