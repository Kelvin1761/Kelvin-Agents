from __future__ import annotations

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.entity_mapping import get_or_create_player
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now
from tennis_wc.providers import get_tennis_provider


def ingest_rankings(tour: str, date: str | None = None) -> int:
    provider = get_tennis_provider()
    rows = provider.fetch_rankings(tour, date)
    raw_id = store_raw_response(
        provider.provider_name,
        "/mock/rankings",
        {"tour": tour, "date": date},
        rows,
        200,
        "ranking",
        tour,
    )
    now = utc_now()
    for row in rows:
        player_id = get_or_create_player(
            provider.provider_name,
            row["player_id"],
            row.get("player_name") or "Unknown Player",
            row["tour"],
            raw_id,
            current_rank=row["rank"],
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rankings_history (
                    player_id, ranking_date, tour, rank, ranking_points,
                    source_provider, raw_response_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, ranking_date, tour, source_provider) DO UPDATE SET
                    rank = excluded.rank,
                    ranking_points = excluded.ranking_points,
                    raw_response_id = excluded.raw_response_id
                """,
                (
                    player_id,
                    row["ranking_date"],
                    row["tour"],
                    row["rank"],
                    row.get("ranking_points"),
                    provider.provider_name,
                    raw_id,
                    now,
                ),
            )
    return len(rows)
