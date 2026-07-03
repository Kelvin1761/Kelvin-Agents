from __future__ import annotations

import json
import re

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.raw_response_store import utc_now


def get_or_create_player(
    provider_name: str,
    provider_player_id: str,
    name: str,
    tour: str,
    raw_response_id: int,
    current_rank: int | None = None,
    overall_elo: float | None = None,
    surface_elo: dict | None = None,
) -> int:
    now = utc_now()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT internal_entity_id
            FROM provider_entities
            WHERE provider_name = ? AND entity_type = 'player' AND provider_entity_id = ?
            """,
            (provider_name, provider_player_id),
        ).fetchone()
        if row:
            player_id = int(row["internal_entity_id"])
            conn.execute(
                """
                UPDATE players
                SET name = ?, tour = ?, current_rank = COALESCE(?, current_rank),
                    overall_elo = COALESCE(?, overall_elo),
                    surface_elo_json = COALESCE(?, surface_elo_json),
                    raw_response_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    tour,
                    current_rank,
                    overall_elo,
                    json.dumps(surface_elo, sort_keys=True) if surface_elo else None,
                    raw_response_id,
                    now,
                    player_id,
                ),
            )
            return player_id

        matched_player = conn.execute(
            """
            SELECT id
            FROM players
            WHERE lower(name) = lower(?) AND tour = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (name, tour),
        ).fetchone()
        if matched_player:
            player_id = int(matched_player["id"])
            conn.execute(
                """
                UPDATE players
                SET current_rank = COALESCE(?, current_rank),
                    overall_elo = COALESCE(?, overall_elo),
                    surface_elo_json = COALESCE(?, surface_elo_json),
                    raw_response_id = COALESCE(?, raw_response_id),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    current_rank,
                    overall_elo,
                    json.dumps(surface_elo, sort_keys=True) if surface_elo else None,
                    raw_response_id,
                    now,
                    player_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO provider_entities (
                    provider_name, entity_type, provider_entity_id, internal_entity_id,
                    entity_name, confidence_score, created_at, updated_at
                )
                VALUES (?, 'player', ?, ?, ?, 0.92, ?, ?)
                ON CONFLICT(provider_name, entity_type, provider_entity_id) DO UPDATE SET
                    internal_entity_id = excluded.internal_entity_id,
                    entity_name = excluded.entity_name,
                    updated_at = excluded.updated_at
                """,
                (provider_name, provider_player_id, player_id, name, now, now),
            )
            return player_id

        cursor = conn.execute(
            """
            INSERT INTO players (
                name, tour, current_rank, overall_elo, surface_elo_json,
                source_provider, raw_response_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                tour,
                current_rank,
                overall_elo,
                json.dumps(surface_elo, sort_keys=True) if surface_elo else None,
                provider_name,
                raw_response_id,
                now,
                now,
            ),
        )
        player_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO provider_entities (
                provider_name, entity_type, provider_entity_id, internal_entity_id,
                entity_name, confidence_score, created_at, updated_at
            )
            VALUES (?, 'player', ?, ?, ?, 1.0, ?, ?)
            """,
            (provider_name, provider_player_id, player_id, name, now, now),
        )
        return player_id


def normalise_player_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def get_internal_entity_id(provider_name: str, entity_type: str, provider_entity_id: str) -> int | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT internal_entity_id
            FROM provider_entities
            WHERE provider_name = ? AND entity_type = ? AND provider_entity_id = ?
            """,
            (provider_name, entity_type, provider_entity_id),
        ).fetchone()
    return int(row["internal_entity_id"]) if row else None


def upsert_tournament(
    provider_name: str,
    external_id: str,
    name: str,
    tour: str,
    raw_response_id: int,
    level: str,
    surface: str | None,
    indoor_outdoor: str | None,
) -> int:
    now = utc_now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tournaments (name, tour, external_id, source_provider, raw_response_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_provider, external_id) DO UPDATE SET
                name = excluded.name,
                tour = excluded.tour,
                raw_response_id = excluded.raw_response_id,
                updated_at = excluded.updated_at
            RETURNING id
            """,
            (name, tour, external_id, provider_name, raw_response_id, now, now),
        )
        tournament_id = int(cursor.fetchone()["id"])
        conn.execute(
            """
            INSERT INTO tournament_levels (
                tournament_id, tour, level, surface, indoor_outdoor,
                source_provider, raw_response_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tournament_id, tour, source_provider) DO UPDATE SET
                level = COALESCE(NULLIF(excluded.level, 'UNKNOWN'), tournament_levels.level),
                surface = COALESCE(excluded.surface, tournament_levels.surface),
                indoor_outdoor = COALESCE(excluded.indoor_outdoor, tournament_levels.indoor_outdoor),
                raw_response_id = excluded.raw_response_id,
                updated_at = excluded.updated_at
            """,
            (tournament_id, tour, level, surface, indoor_outdoor, provider_name, raw_response_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO provider_entities (
                provider_name, entity_type, provider_entity_id, internal_entity_id,
                entity_name, confidence_score, created_at, updated_at
            )
            VALUES (?, 'tournament', ?, ?, ?, 1.0, ?, ?)
            ON CONFLICT(provider_name, entity_type, provider_entity_id) DO UPDATE SET
                internal_entity_id = excluded.internal_entity_id,
                entity_name = excluded.entity_name,
                updated_at = excluded.updated_at
            """,
            (provider_name, external_id, tournament_id, name, now, now),
        )
        return tournament_id
