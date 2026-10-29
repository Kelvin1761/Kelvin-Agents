from __future__ import annotations

import pytest

from conftest import configure_test_db


def _seed_player(conn, player_id: int, name: str, tour: str = "ATP") -> None:
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (player_id, name, tour, "test", "now", "now"),
    )


def test_placeholder_player_identity_is_rejected(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_or_create_player

    init_db()
    with pytest.raises(ValueError, match="placeholder player identity"):
        get_or_create_player("composite", "None", "Unknown Player", "ATP", 0)
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0


def test_existing_provider_alias_rebinds_to_history_rich_canonical_player(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_or_create_player

    init_db()
    with get_connection() as conn:
        _seed_player(conn, 1, "Taylor Fritz")
        _seed_player(conn, 2, "Taylor Fritz")
        for index in range(5):
            conn.execute(
                """INSERT INTO player_match_history
                   (provider_match_id, player_id, opponent_id, tour, match_date,
                    tournament_external_id, tournament_level, round, format, won,
                    source_provider, raw_response_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"H{index}", 1, 99, "ATP", f"2025-01-{index + 1:02d}",
                 "T", "ATP250", "R1", "BO3", 1, "history", 0, "now"),
            )
        conn.execute(
            """INSERT INTO provider_entities
               (provider_name, entity_type, provider_entity_id, internal_entity_id,
                entity_name, confidence_score, created_at, updated_at)
               VALUES ('composite','player','fritz',2,'Taylor Fritz',1,'now','now')"""
        )
        conn.commit()

    resolved = get_or_create_player(
        "composite", "fritz", "Taylor Fritz", "ATP", 0, current_rank=4
    )
    assert resolved == 1
    with get_connection() as conn:
        mapped = conn.execute(
            "SELECT internal_entity_id FROM provider_entities "
            "WHERE provider_name='composite' AND provider_entity_id='fritz'"
        ).fetchone()[0]
        assert mapped == 1


def test_reused_player_alias_cannot_rename_existing_history(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    init_db()
    first=get_or_create_player('feed','same-key','Taylor Fritz','ATP',0)
    with pytest.raises(ValueError,match='identity changed'):
        get_or_create_player('feed','same-key','Rinky Hijikata','ATP',0)
    with get_connection() as conn:
        assert conn.execute('SELECT name FROM players WHERE id=?',(first,)).fetchone()[0]=='Taylor Fritz'
        assert conn.execute('SELECT COUNT(*) FROM players').fetchone()[0]==1


def test_same_initial_full_names_are_not_one_player(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.entity_mapping import get_or_create_player
    init_db()
    get_or_create_player('feed','key','Tim Smith','ATP',0)
    with pytest.raises(ValueError,match='identity changed'):
        get_or_create_player('feed','key','Taylor Smith','ATP',0)


@pytest.mark.parametrize("target_name,target_tour", [("Toby Samuel", "ATP"), ("Stefan Kozlov", "WTA")])
@pytest.mark.parametrize("known_key", [True, False])
def test_merged_target_must_agree_and_rejected_write_rolls_back(tmp_path, monkeypatch, target_name, target_tour, known_key):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.ingestion.entity_mapping import PlayerIdentityConflict, get_or_create_player

    init_db()
    with get_connection() as conn:
        ensure_identity_schema(conn)
        _seed_player(conn, 1, target_name, target_tour)
        _seed_player(conn, 2, "Stefan Kozlov")
        conn.execute("UPDATE players SET canonical_player_id=1, current_rank=200 WHERE id=2")
        if known_key:
            conn.execute("INSERT INTO provider_entities (provider_name,entity_type,provider_entity_id,internal_entity_id,entity_name,confidence_score,created_at,updated_at) VALUES ('feed','player','KE64',2,'Stefan Kozlov',1,'now','now')")
        before_players = [dict(r) for r in conn.execute("SELECT * FROM players ORDER BY id")]
        before_keys = [dict(r) for r in conn.execute("SELECT * FROM provider_entities ORDER BY id")]
    with pytest.raises(PlayerIdentityConflict, match="canonical player identity changed"):
        get_or_create_player("feed", "KE64", "Stefan Kozlov", "ATP", 999, current_rank=3, overall_elo=2000)
    with get_connection() as conn:
        assert [dict(r) for r in conn.execute("SELECT * FROM players ORDER BY id")] == before_players
        assert [dict(r) for r in conn.execute("SELECT * FROM provider_entities ORDER BY id")] == before_keys


@pytest.mark.parametrize("target", [999, 2])
def test_missing_or_cyclic_merge_target_is_not_returned(tmp_path, monkeypatch, target):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.ingestion.entity_mapping import PlayerIdentityConflict, get_or_create_player

    init_db()
    with get_connection() as conn:
        ensure_identity_schema(conn)
        _seed_player(conn, 2, "Stefan Kozlov")
        conn.execute("UPDATE players SET canonical_player_id=? WHERE id=2", (target,))
    with pytest.raises(PlayerIdentityConflict, match="canonical player identity changed"):
        get_or_create_player("feed", "KE64", "Stefan Kozlov", "ATP", 0)


def test_valid_merge_chain_still_resolves(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.ingestion.entity_mapping import get_or_create_player

    init_db()
    with get_connection() as conn:
        ensure_identity_schema(conn)
        for pid in (1, 2, 3):
            _seed_player(conn, pid, "Stefan Kozlov")
        conn.execute("UPDATE players SET canonical_player_id=2 WHERE id=3")
        conn.execute("UPDATE players SET canonical_player_id=1 WHERE id=2")
        conn.execute("INSERT INTO provider_entities (provider_name,entity_type,provider_entity_id,internal_entity_id,entity_name,confidence_score,created_at,updated_at) VALUES ('feed','player','KE64',3,'Stefan Kozlov',1,'now','now')")
    assert get_or_create_player("feed", "KE64", "Stefan Kozlov", "ATP", 0) == 1


@pytest.mark.parametrize("incoming,canonical,accept", [
    ("Taylor Harry Fritz", "Taylor Fritz", True),
    ("Felipe Meligeni Rodrigues Alves", "Felipe Meligeni Alves", True),
    ("Alan Sau Franco", "Alan Raul Sau Franco", True),
    ("Tim Smith", "Taylor Smith", False),
    ("John Patrick Smith", "John Peter Smith", False),
    ("Juan Manuel Cerundolo", "Francisco Cerundolo", False),
])
def test_merge_target_middle_names_are_constrained(tmp_path, monkeypatch, incoming, canonical, accept):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.ingestion.entity_mapping import PlayerIdentityConflict, get_or_create_player

    init_db()
    with get_connection() as conn:
        ensure_identity_schema(conn)
        _seed_player(conn, 1, canonical)
        _seed_player(conn, 2, incoming)
        conn.execute("UPDATE players SET canonical_player_id=1 WHERE id=2")
        conn.execute("INSERT INTO provider_entities (provider_name,entity_type,provider_entity_id,internal_entity_id,entity_name,confidence_score,created_at,updated_at) VALUES ('feed','player','key',2,?,1,'now','now')", (incoming,))
    if accept:
        assert get_or_create_player("feed", "key", incoming, "ATP", 0) == 1
    else:
        with pytest.raises(PlayerIdentityConflict):
            get_or_create_player("feed", "key", incoming, "ATP", 0)
