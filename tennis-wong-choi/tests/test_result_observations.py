"""Overwriting result.created_at cannot erase when a label became known."""
from __future__ import annotations

import sqlite3

import pytest

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.database.result_observations import results_known_before


@pytest.fixture
def conn(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch)
    init_db()
    c=get_connection()
    c.execute("INSERT INTO matches(provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at) VALUES ('event','ATP','2026-01-01',1,1,2,'R1','test','now','now')")
    yield c
    c.close()


def test_duplicate_refresh_does_not_erase_first_observation(conn):
    conn.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (1,1,'feed','2000-01-01')")
    observed=conn.execute('SELECT observed_at FROM result_observations').fetchone()[0]
    assert observed>'2026-01-01'  # claimed old created_at cannot backdate arrival
    conn.execute("UPDATE match_results SET created_at='2099-01-01'")
    assert conn.execute('SELECT COUNT(*) FROM result_observations').fetchone()[0]==1
    assert results_known_before(conn,'2026-01-02')==[]
    assert results_known_before(conn,'2098-01-01')[0]['winner_player_id']==1


def test_correction_and_deletion_are_preserved(conn):
    conn.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (1,1,'feed','now')")
    conn.execute('UPDATE match_results SET winner_player_id=2')
    assert [r[0] for r in conn.execute('SELECT winner_player_id FROM result_observations ORDER BY id')]==[1,2]
    assert results_known_before(conn,'2099-01-01')[0]['winner_player_id']==2
    conn.execute('DELETE FROM match_results')
    assert results_known_before(conn,'2099-01-01')==[]
    assert conn.execute('SELECT COUNT(*) FROM result_observations').fetchone()[0]==3
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):
        conn.execute('DELETE FROM result_observations')


def test_legacy_seed_is_not_a_historical_availability_claim(conn):
    conn.execute('DROP TRIGGER result_observe_insert')
    conn.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (1,1,'feed','2000-01-01')")
    conn.commit()
    from tennis_wc.database.result_observations import ensure_result_observations
    ensure_result_observations(conn)
    row=conn.execute('SELECT * FROM result_observations').fetchone()
    assert row['observation_kind']=='LEGACY_SEED'
    assert results_known_before(conn,'2026-01-02')==[]
    assert len(results_known_before(conn,'2099-01-01'))==1
