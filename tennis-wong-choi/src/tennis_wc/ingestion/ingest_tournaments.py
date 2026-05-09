from __future__ import annotations

from tennis_wc.ingestion.entity_mapping import upsert_tournament
from tennis_wc.ingestion.raw_response_store import store_raw_response
from tennis_wc.providers import get_tennis_provider


def ingest_tournaments(start_date: str, end_date: str) -> list[int]:
    provider = get_tennis_provider()
    rows = provider.fetch_tournaments(start_date, end_date)
    raw_id = store_raw_response(
        provider.provider_name,
        "/mock/tournaments",
        {"start_date": start_date, "end_date": end_date},
        rows,
        200,
        "tournament",
        None,
    )
    return [
        upsert_tournament(
            provider.provider_name,
            row["id"],
            row["name"],
            row["tour"],
            raw_id,
            row.get("level", "UNKNOWN"),
            row.get("surface"),
            row.get("indoor_outdoor"),
        )
        for row in rows
    ]
