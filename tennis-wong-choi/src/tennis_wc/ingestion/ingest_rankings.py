from __future__ import annotations

import math
from collections import defaultdict

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.entity_mapping import PlayerIdentityConflict, existing_player_id, get_or_create_player
from tennis_wc.ingestion.name_matching import normalise_player_name
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now
from tennis_wc.providers import get_tennis_provider


# tour -> details of the most recent call that served CACHED rankings instead of
# the provider's. Reset at the start of every call, so an entry means "the last
# ingest for this tour fell back". run-daily reads it to surface the fallback:
# returning len(cached) looked exactly like a successful pull, and the only
# trace was a 206 row in raw_api_responses nobody reads.
LAST_CACHE_FALLBACK: dict[str, dict] = {}


class RankingIdentityHoldError(RuntimeError):
    """Safe rows were ingested, but the source must still be reported partial."""

    def __init__(self, report: dict):
        self.report = report
        super().__init__(
            f"ranking identity holds: imported={report['imported_rows']} held={len(report['held'])} "
            f"raw_response_id={report['raw_response_id']} hold_response_id={report['hold_response_id']}; "
            f"first: {report['held'][0]['error']}"
        )


def rankings_cache_fallback(tour: str) -> dict | None:
    return LAST_CACHE_FALLBACK.get(tour)


def _ranking_identity_holds(provider_name: str, rows: list[dict]) -> dict[int, str]:
    """Hold all competing claims before either can overwrite a rank."""
    held: dict[int, str] = {}
    groups = defaultdict(list)
    with get_connection() as conn:
        for index, row in enumerate(rows):
            name = row.get("player_name") or "Unknown Player"
            try:
                player_id = existing_player_id(conn, provider_name, row["player_id"], name, row["tour"])
            except PlayerIdentityConflict as exc:
                held[index] = str(exc)
                continue
            scope = (str(row["tour"]).upper(), row["ranking_date"])
            groups[("provider_key", *scope, str(row["player_id"]))].append(index)
            groups[("name", *scope, normalise_player_name(name))].append(index)
            if player_id is not None:
                groups[("canonical", *scope, player_id)].append(index)
    for key, indices in groups.items():
        if len(indices) > 1:
            for index in indices:
                held[index] = f"ranking identity collision: {key[0]}={key[-1]!r}; source rows={indices}"
    return held


def ingest_rankings(tour: str, date: str | None = None) -> int:
    LAST_CACHE_FALLBACK.pop(tour, None)
    provider = get_tennis_provider()
    endpoint = "/rankings"
    status_code = 200
    raw_payload: dict | list
    try:
        rows = provider.fetch_rankings(tour, date)
    except Exception as exc:
        cached = _latest_cached_rankings(tour, date)
        if not cached:
            store_raw_response(
                provider.provider_name,
                endpoint,
                {"tour": tour, "date": date},
                {"error": str(exc), "fallback": "cache", "cached_rows": 0},
                503,
                "ranking",
                tour,
            )
            raise
        _refresh_current_ranks_from_cached_rows(cached)
        LAST_CACHE_FALLBACK[tour] = {
            "error": str(exc),
            "cached_rows": len(cached),
            "cached_latest_ranking_date": max(row["ranking_date"] for row in cached),
        }
        store_raw_response(
            provider.provider_name,
            "/cache/rankings",
            {"tour": tour, "date": date},
            {
                "error": str(exc),
                "fallback": "cache",
                "cached_rows": len(cached),
                "cached_latest_ranking_date": max(row["ranking_date"] for row in cached),
            },
            206,
            "ranking",
            tour,
        )
        return len(cached)
    if not rows:
        cached = _latest_cached_rankings(tour, date)
        if cached:
            _refresh_current_ranks_from_cached_rows(cached)
            LAST_CACHE_FALLBACK[tour] = {
                "error": "provider returned zero ranking rows",
                "cached_rows": len(cached),
                "cached_latest_ranking_date": max(row["ranking_date"] for row in cached),
            }
            store_raw_response(
                provider.provider_name,
                "/cache/rankings",
                {"tour": tour, "date": date},
                {
                    "error": "provider returned zero ranking rows",
                    "fallback": "cache",
                    "cached_rows": len(cached),
                    "cached_latest_ranking_date": max(row["ranking_date"] for row in cached),
                },
                206,
                "ranking",
                tour,
            )
            return len(cached)
        status_code = 204
        raw_payload = []
    else:
        raw_payload = rows
    raw_id = store_raw_response(
        provider.provider_name,
        endpoint,
        {"tour": tour, "date": date},
        raw_payload,
        status_code,
        "ranking",
        tour,
    )
    if not rows:
        return 0
    now = utc_now()
    held = []
    imported = 0
    preflight = _ranking_identity_holds(provider.provider_name, rows)
    for index, row in enumerate(rows):
        try:
            if index in preflight:
                raise PlayerIdentityConflict(preflight[index])
            player_id = get_or_create_player(
                provider.provider_name,
                row["player_id"],
                row.get("player_name") or "Unknown Player",
                row["tour"],
                raw_id,
                current_rank=row["rank"],
                overall_elo=_rank_seed_elo(row["rank"]),
            )
        except PlayerIdentityConflict as exc:
            held.append({"provider_player_id": row["player_id"], "player_name": row.get("player_name"),
                         "tour": row["tour"], "error": str(exc)})
            continue
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
        imported += 1
    if held:
        report = {"raw_response_id": raw_id, "imported_rows": imported,
                  "total_rows": len(rows), "held": held}
        report["hold_response_id"] = store_raw_response(
            provider.provider_name, "/rankings/identity-holds", {"tour": tour, "date": date},
            report, 206, "ranking_identity_hold", tour,
        )
        raise RankingIdentityHoldError(report)
    return len(rows)


def _rank_seed_elo(rank: int | None) -> float | None:
    """
    Conservative fallback rating from live rank.

    True Sackmann Elo, when present, is still preferred because player updates use
    COALESCE and will not overwrite an existing Elo. This seed only prevents a
    fresh daily DB from treating ranked players as having no core rating at all.
    """
    try:
        parsed = int(rank) if rank is not None else None
    except (TypeError, ValueError):
        return None
    if not parsed or parsed < 1:
        return None
    return round(max(1400.0, min(2250.0, 2250.0 - 220.0 * math.log10(parsed))), 3)


# The third of three stacked 500-caps, and the one that actually decided which
# players carried a rank. Even with both feeds fetching the full ladder, this
# query handed `_refresh_current_ranks_from_cached_rows` only the top 500, so
# `players.current_rank` could never exceed 500 however deep the data went.
#
# There is no reason to bound it: one row per player per tour, and the whole
# ATP+WTA ladder is under 4,000 rows.
CACHED_RANKING_ROW_LIMIT = 10000


def _latest_cached_rankings(tour: str, date: str | None = None) -> list[dict]:
    cutoff = _normalise_date(date)
    with get_connection() as conn:
        params: list = [tour.upper()]
        where = ["rh.tour = ?"]
        if cutoff:
            where.append("rh.ranking_date <= ?")
            params.append(cutoff)
        rows = conn.execute(
            f"""
            WITH latest AS (
                SELECT rh.player_id, MAX(rh.ranking_date) AS ranking_date
                FROM rankings_history rh
                WHERE {' AND '.join(where)}
                GROUP BY rh.player_id
            )
            SELECT
                rh.player_id AS internal_player_id,
                p.name AS player_name,
                p.tour,
                rh.ranking_date,
                rh.rank,
                rh.ranking_points,
                rh.source_provider
            FROM rankings_history rh
            JOIN latest l
              ON l.player_id = rh.player_id
             AND l.ranking_date = rh.ranking_date
            JOIN players p ON p.id = rh.player_id
            ORDER BY rh.rank ASC
            LIMIT ?
            """,
            (*params, CACHED_RANKING_ROW_LIMIT),
        ).fetchall()
    return [
        {
            "internal_player_id": int(row["internal_player_id"]),
            "player_name": row["player_name"],
            "tour": row["tour"],
            "ranking_date": row["ranking_date"],
            "rank": int(row["rank"]),
            "ranking_points": row["ranking_points"],
            "source_provider": row["source_provider"],
        }
        for row in rows
    ]


def _refresh_current_ranks_from_cached_rows(rows: list[dict]) -> None:
    if not rows:
        return
    now = utc_now()
    with get_connection() as conn:
        for row in rows:
            conn.execute(
                """
                UPDATE players
                SET current_rank = ?, updated_at = ?
                WHERE id = ?
                """,
                (row["rank"], now, row["internal_player_id"]),
            )


def _normalise_date(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value
