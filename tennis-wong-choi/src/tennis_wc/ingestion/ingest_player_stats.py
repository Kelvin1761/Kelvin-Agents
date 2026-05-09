from __future__ import annotations

from tennis_wc.ingestion.entity_mapping import get_or_create_player
from tennis_wc.ingestion.raw_response_store import store_raw_response
from tennis_wc.providers import get_tennis_provider


def ingest_player_stats(player_id: str) -> int:
    provider = get_tennis_provider()
    profile = provider.fetch_player_profile(player_id)
    stats = provider.fetch_player_stats(player_id)
    raw_id = store_raw_response(
        provider.provider_name,
        "/mock/player-stats",
        {"player_id": player_id},
        {"profile": profile, "stats": stats},
        200,
        "player",
        player_id,
    )
    return get_or_create_player(
        provider.provider_name,
        player_id,
        profile["name"],
        profile["tour"],
        raw_id,
        overall_elo=stats.get("overall_elo"),
        surface_elo=stats.get("surface_elo"),
    )
