from __future__ import annotations

from tennis_wc.ingestion.raw_response_store import store_raw_response
from tennis_wc.providers import get_news_provider


def ingest_player_news(player_name: str, since_date: str | None = None) -> int:
    provider = get_news_provider()
    rows = provider.fetch_player_news(player_name, since_date)
    return store_raw_response(
        provider.provider_name,
        "/mock/player-news",
        {"player_name": player_name, "since_date": since_date},
        rows,
        200,
        "news",
        player_name,
    )
