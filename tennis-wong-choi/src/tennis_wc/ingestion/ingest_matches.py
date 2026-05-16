from __future__ import annotations

from datetime import date, timedelta

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.entity_mapping import get_internal_entity_id, get_or_create_player, upsert_tournament
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now
from tennis_wc.providers import get_tennis_provider


_PLAYER_CACHE: dict[tuple[str, str], int] = {}


def _ensure_player(provider_name: str, provider_player_id: str, raw_id: int, embedded: dict | None = None) -> int:
    cache_key = (provider_name, provider_player_id)
    if cache_key in _PLAYER_CACHE:
        return _PLAYER_CACHE[cache_key]
    if embedded and embedded.get("name"):
        player_id = get_or_create_player(
            provider_name,
            provider_player_id,
            embedded["name"],
            embedded.get("tour") or "ATP",
            raw_id,
            current_rank=embedded.get("current_rank"),
        )
        _PLAYER_CACHE[cache_key] = player_id
        return player_id

    provider = get_tennis_provider()
    profile = provider.fetch_player_profile(provider_player_id) or {}
    stats = provider.fetch_player_stats(provider_player_id) or {}
    player_raw_id = store_raw_response(
        provider_name,
        "/mock/player-stats",
        {"player_id": provider_player_id},
        {"profile": profile, "stats": stats},
        200,
        "player",
        provider_player_id,
    )
    player_id = get_or_create_player(
        provider_name,
        provider_player_id,
        profile.get("name") or "Unknown Player",
        profile.get("tour") or "ATP",
        player_raw_id,
        current_rank=profile.get("current_rank"),
        overall_elo=stats.get("overall_elo"),
        surface_elo=stats.get("surface_elo"),
    )
    _PLAYER_CACHE[cache_key] = player_id
    return player_id


def ingest_upcoming_matches(match_date: str) -> int:
    provider = get_tennis_provider()
    rows = provider.fetch_upcoming_matches(match_date)
    raw_id = store_raw_response(
        provider.provider_name,
        "/mock/upcoming-matches",
        {"date": match_date},
        rows,
        200,
        "match",
        match_date,
    )
    now = utc_now()
    count = 0
    for row in rows:
        player_a_id = _ensure_player(
            provider.provider_name,
            row["player_a_id"],
            raw_id,
            {"name": row.get("player_a_name"), "tour": row.get("tour"), "current_rank": row.get("player_a_current_rank")},
        )
        player_b_id = _ensure_player(
            provider.provider_name,
            row["player_b_id"],
            raw_id,
            {"name": row.get("player_b_name"), "tour": row.get("tour"), "current_rank": row.get("player_b_current_rank")},
        )
        tournament_id = upsert_tournament(
            provider.provider_name,
            row["tournament_id"],
            row.get("tournament_name") or row["tournament_id"],
            row["tour"],
            raw_id,
            row.get("tournament_level") or "UNKNOWN",
            row.get("surface"),
            row.get("indoor_outdoor"),
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO matches (
                    provider_match_id, market_event_id, tour, match_date, tournament_id,
                    player_a_id, player_b_id, round, source_provider, raw_response_id,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_provider, provider_match_id) DO UPDATE SET
                    market_event_id = excluded.market_event_id,
                    match_date = excluded.match_date,
                    tournament_id = excluded.tournament_id,
                    player_a_id = excluded.player_a_id,
                    player_b_id = excluded.player_b_id,
                    round = excluded.round,
                    raw_response_id = excluded.raw_response_id,
                    updated_at = excluded.updated_at
                """,
                (
                    row["id"],
                    row.get("market_event_id"),
                    row["tour"],
                    row.get("analysis_date") or row["match_date"],
                    tournament_id,
                    player_a_id,
                    player_b_id,
                    row["round"],
                    provider.provider_name,
                    raw_id,
                    now,
                    now,
                ),
            )
        count += 1
    return count


def ingest_historical_matches(start_date: str, end_date: str) -> int:
    provider = get_tennis_provider()
    rows = provider.fetch_historical_matches(start_date, end_date)
    raw_id = store_raw_response(
        provider.provider_name,
        "/mock/historical-matches",
        {"start_date": start_date, "end_date": end_date},
        rows,
        200,
        "match_history",
        None,
    )
    now = utc_now()
    count = 0
    for row in rows:
        player_id = _ensure_player(
            provider.provider_name,
            row["player_id"],
            raw_id,
            {"name": row.get("player_name"), "tour": row.get("tour"), "current_rank": row.get("player_current_rank")},
        )
        opponent_id = _ensure_player(
            provider.provider_name,
            row["opponent_id"],
            raw_id,
            {"name": row.get("opponent_name"), "tour": row.get("tour"), "current_rank": row.get("opponent_current_rank")},
        )
        upsert_tournament(
            provider.provider_name,
            row["tournament_id"],
            row["tournament_id"],
            row["tour"],
            raw_id,
            row.get("tournament_level", "UNKNOWN"),
            row.get("surface"),
            None,
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO player_match_history (
                    provider_match_id, player_id, opponent_id, tour, match_date, surface,
                    tournament_external_id, tournament_level, round, format, won,
                    opponent_elo, hold_rate, break_rate, first_serve_points_won_pct,
                    second_serve_points_won_pct, return_points_won_pct, tiebreak_won,
                    deciding_set_won, lost_first_set, comeback_after_losing_first_set,
                    source_provider, raw_response_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_provider, provider_match_id, player_id) DO UPDATE SET
                    won = excluded.won,
                    opponent_elo = excluded.opponent_elo,
                    raw_response_id = excluded.raw_response_id
                """,
                (
                    row["id"],
                    player_id,
                    opponent_id,
                    row["tour"],
                    row["match_date"],
                    row.get("surface"),
                    row["tournament_id"],
                    row.get("tournament_level", "UNKNOWN"),
                    row["round"],
                    row.get("format", "BO3"),
                    1 if row["won"] else 0,
                    row.get("opponent_elo"),
                    row.get("hold_rate"),
                    row.get("break_rate"),
                    row.get("first_serve_points_won_pct"),
                    row.get("second_serve_points_won_pct"),
                    row.get("return_points_won_pct"),
                    1 if row.get("tiebreak_won") else 0,
                    1 if row.get("deciding_set_won") else 0,
                    1 if row.get("lost_first_set") else 0,
                    1 if row.get("comeback_after_losing_first_set") else 0,
                    provider.provider_name,
                    raw_id,
                    now,
                ),
            )
        count += 1
    return count


def ingest_default_history(as_of_date: str) -> int:
    end = date.fromisoformat(as_of_date)
    start = end - timedelta(days=550)
    return ingest_historical_matches(start.isoformat(), as_of_date)
