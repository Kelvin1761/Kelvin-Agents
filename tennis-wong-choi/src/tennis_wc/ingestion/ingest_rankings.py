from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from tennis_wc.config import get_settings
from tennis_wc.database.db import get_connection
from tennis_wc.database.ranking_reads import RankingReader, cached_rankings
from tennis_wc.ingestion.entity_mapping import PlayerIdentityConflict, existing_player_id, get_or_create_player
from tennis_wc.ingestion.name_matching import normalise_player_name
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now
from tennis_wc.providers import get_tennis_provider
from tennis_wc.ranking_dates import normalise_ranking_date, validate_ranking_rows


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
    rows = None
    try:
        rows = provider.fetch_rankings(tour, date)
        # Mock is an explicitly simulated calendar, not live ranking evidence.
        simulated = provider.provider_name == "mock"
        simulated_today = normalise_ranking_date(date) if simulated else None
        rows = validate_ranking_rows(
            rows, date, max_age_hours=None if simulated else get_settings().data_max_staleness_hours_rankings,
            today=datetime.fromisoformat(simulated_today).date() if simulated_today else None)
    except Exception as exc:
        _store_source_evidence(provider, tour, date, rejected_rows=rows, error=str(exc))
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
    capture_id = _store_source_evidence(provider, tour, date)
    if capture_id is not None and rows:
        # The PDF bytes are stored independently; link the normalized rows
        # to that immutable receipt without changing the provider's objects.
        rows = [{**row, "raw": {**row["raw"], "source_capture_raw_id": capture_id}}
                if isinstance(row.get("raw"), dict) and row["raw"].get("source") == "atp_official_numeric_pdf"
                else row for row in rows]
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
    seed_conn = get_connection()
    seed_reader = RankingReader(seed_conn)
    try:
        return _write_ranking_rows(provider, rows, raw_id, now, preflight, imported, held, tour, date, seed_reader)
    finally:
        seed_conn.close()


def _write_ranking_rows(provider, rows, raw_id, now, preflight, imported, held, tour, date, seed_reader):
    for index, row in enumerate(rows):
        try:
            if index in preflight:
                raise PlayerIdentityConflict(preflight[index])
            seed = _safe_rank_seed(provider.provider_name, row, seed_reader)
            # One player update and its history row are one transaction. If
            # the insert fails, do not leave a new mutable rank behind.
            with get_connection() as conn:
                player_id = get_or_create_player(
                    provider.provider_name,
                    row["player_id"],
                    row.get("player_name") or "Unknown Player",
                    row["tour"],
                    raw_id,
                    current_rank=row["rank"],
                    overall_elo=seed,
                    connection=conn,
                )
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
                        _ranking_origin(provider.provider_name, row),
                        raw_id,
                        now,
                    ),
                )
        except PlayerIdentityConflict as exc:
            held.append({"provider_player_id": row["player_id"], "player_name": row.get("player_name"),
                         "tour": row["tour"], "error": str(exc)})
            continue
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


def _ranking_origin(provider_name, row):
    raw = row.get("raw") or {}
    source = raw.get("source") if isinstance(raw, dict) else None
    # Preserve the actual publication namespace, so a fresh official PDF does
    # not overwrite a legacy misdated composite record for the same date.
    return source if source in {"atp_official_numeric_pdf", "ultimate_tennis_statistics", "sackmann_ranking",
                                "wta_ranked_players_api", "wta_numeric_pdf", "wta_rankings_html"} else provider_name


def _safe_rank_seed(provider_name, row, reader):
    """Initialize a prior; a routine rank refresh must preserve genuine Elo."""
    seed = _rank_seed_elo(row["rank"])
    pid = existing_player_id(reader.conn, provider_name, row["player_id"], row.get("player_name") or "Unknown Player", row["tour"])
    if pid is None:
        return seed
    player = reader.conn.execute("SELECT * FROM players WHERE id=?", (pid,)).fetchone()
    if player["overall_elo"] is None:
        return seed
    has_history = reader.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_elo_history'").fetchone()
    if has_history and reader.conn.execute(
            "SELECT 1 FROM player_elo_history WHERE player_id=? AND surface='' AND as_of_date<? LIMIT 1",
            (pid, row["ranking_date"])).fetchone():
        return None
    return seed if reader.unverified_seed(player, _rank_seed_elo) else None


def _store_source_evidence(provider, tour, requested, *, rejected_rows=None, error=None):
    captures = getattr(provider, "ranking_source_evidence", [])
    failures = getattr(provider, "ranking_source_failures", [])
    if not captures and not failures and rejected_rows is None:
        return
    return store_raw_response(provider.provider_name, "/rankings/source-evidence", {"tour": tour, "date": requested},
                       {"captures": captures, "failures": failures, "rejected_rows": rejected_rows, "error": error},
                       206 if error or failures else 200, "ranking_source_evidence", tour)


def _rank_seed_elo(rank: int | None) -> float | None:
    """
    Conservative fallback rating from live rank.

    `_safe_rank_seed` preserves established ratings and initializes only a
    missing rating or an explicitly unverified prior with no as-of history.
    This seed is a ranking prior, not independently measured Elo.
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
    with get_connection() as conn:
        rows = cached_rankings(conn, tour, date, max_age_hours=get_settings().data_max_staleness_hours_rankings,
                               today=datetime.now(timezone.utc).date())
        names = {r["id"]: dict(r) for r in conn.execute("SELECT id,name,tour FROM players")}
    if len(rows) > CACHED_RANKING_ROW_LIMIT:
        raise ValueError("ranking cache exceeds row safety limit; refusing partial cache")
    return [{"internal_player_id": int(row["player_id"]), "player_name": names[row["player_id"]]["name"],
             "tour": row["tour"], "ranking_date": row["ranking_date"], "rank": int(row["rank"]),
             "ranking_points": row["ranking_points"], "source_provider": row["source_provider"]}
            for row in sorted(rows, key=lambda r: (r["rank"], r["player_id"])) if row["player_id"] in names]


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
    return normalise_ranking_date(value)
