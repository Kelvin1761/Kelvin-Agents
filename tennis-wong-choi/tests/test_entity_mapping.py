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
