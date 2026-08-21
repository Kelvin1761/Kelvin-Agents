"""Build a lower-tier match corpus from the TennisExplorer scoreboard.

``ingest_tennisexplorer`` settles fixtures we already hold.  This writes the
history the models learn from, including matches between players we have never
priced -- which is the whole point.  Elo is built from ``player_match_history``,
that table is fed by the Sackmann/TennisMyLife files, and those publish ATP,
ATP quali, Challenger and WTA and **no ITF at all** (checked against the live
manifest: 171 files, zero matching itf or futures).  So Elo covers 75.9% of
tour fixtures and 1.2% of ITF ones while ITF is ~85% of the board we price.

Every player is resolved through :mod:`tennis_wc.identity.player_identity`
before anything is created, because creating a player per spelling is exactly
how 864 duplicate identities happened the first time.
"""
from __future__ import annotations

from datetime import date, timedelta

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.identity import player_identity
from tennis_wc.ingestion.name_matching import normalise_player_name
from tennis_wc.ingestion.raw_response_store import store_raw_response
from tennis_wc.providers.tennisexplorer_provider import (
    ParsedResult,
    TennisExplorerResultsProvider,
)

PROVIDER_NAME = "tennisexplorer"


def _tier_of(tournament_name: str | None) -> str:
    name = str(tournament_name or "").upper()
    if "ITF" in name or "FUTURES" in name:
        return "ITF"
    if "UTR" in name:
        return "UTR"
    if "CHALLENGER" in name:
        return "CHALLENGER"
    return "TOUR"


def _tour_of(tournament_name: str | None, tour_hint: str | None) -> str:
    if tour_hint:
        return str(tour_hint).upper()
    name = str(tournament_name or "").upper()
    if any(token in name for token in (" W15", " W35", " W50", " W75", " W100", "WTA")):
        return "WTA"
    return "ATP"


def _date_range(start_date: str, end_date: str) -> list[str]:
    first = date.fromisoformat(start_date)
    last = date.fromisoformat(end_date)
    if last < first:
        first, last = last, first
    return [
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    ]


def _get_or_create_player(conn, name: str, tour: str, created: list) -> int | None:
    """Canonical id for ``name``, creating a player only as a last resort."""
    if not name or player_identity.is_placeholder(name):
        return None
    existing = player_identity.resolve_player_id(conn, name, tour)
    if existing is not None:
        return existing
    now = utc_now()
    cursor = conn.execute(
        "INSERT INTO players (name, tour, source_provider, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, tour, PROVIDER_NAME, now, now),
    )
    player_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT OR IGNORE INTO player_aliases "
        "(alias_norm, canonical_player_id, source, created_at) VALUES (?, ?, ?, ?)",
        (normalise_player_name(name), player_id, PROVIDER_NAME, now),
    )
    created.append(player_id)
    return player_id


def _store_history(conn, match_date: str, results: list[ParsedResult], raw_id: int) -> dict:
    counts = {"matches": 0, "rows": 0, "players_created": 0, "skipped": 0}
    created: list[int] = []
    now = utc_now()
    for result in results:
        winner_name = result.winner_name
        loser_name = (
            result.player_b_name if winner_name == result.player_a_name
            else result.player_a_name
        )
        if not winner_name or not loser_name:
            counts["skipped"] += 1
            continue
        tier = _tier_of(result.tournament_name)
        tour = _tour_of(result.tournament_name, getattr(result, "tour", None))
        winner_id = _get_or_create_player(conn, winner_name, tour, created)
        loser_id = _get_or_create_player(conn, loser_name, tour, created)
        if winner_id is None or loser_id is None or winner_id == loser_id:
            counts["skipped"] += 1
            continue
        payload = result.score_payload()
        # Deterministic id so a re-run updates rather than duplicates.
        base = (
            f"te-{match_date}-"
            f"{normalise_player_name(winner_name).replace(' ', '')}-"
            f"{normalise_player_name(loser_name).replace(' ', '')}"
        )
        for provider_match_id, player_id, opponent_id, won in (
            (f"{base}-winner", winner_id, loser_id, 1),
            (f"{base}-loser", loser_id, winner_id, 0),
        ):
            conn.execute(
                """
                INSERT INTO player_match_history
                    (provider_match_id, player_id, opponent_id, tour, match_date,
                     tournament_external_id, tournament_level, round, format, won,
                     source_provider, raw_response_id, created_at, surface)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_provider, provider_match_id, player_id) DO UPDATE SET
                    player_id = excluded.player_id,
                    opponent_id = excluded.opponent_id,
                    won = excluded.won
                """,
                (
                    provider_match_id, player_id, opponent_id, tour, match_date,
                    result.tournament_name, tier, "R",
                    "BO3", won, PROVIDER_NAME, raw_id, now, None,
                ),
            )
            counts["rows"] += 1
        # A retirement still decides a winner, so it counts for Elo; the games
        # are what cannot be trusted, and those are not stored here.
        counts["matches"] += 1
    counts["players_created"] = len(set(created))
    return counts


def ingest_tennisexplorer_history(
    start_date: str, end_date: str | None = None, provider=None, log=None
) -> dict:
    """Walk the scoreboard day by day and store both sides of every match."""
    provider = provider or TennisExplorerResultsProvider()
    summary = {
        "dates": 0, "matches": 0, "rows": 0, "players_created": 0,
        "skipped": 0, "parse_skipped": 0, "errors": [],
    }
    raw_id = store_raw_response(
        PROVIDER_NAME,
        "tennisexplorer/results",
        {"start_date": start_date, "end_date": end_date or start_date},
        {"summary": "Lower-tier match corpus for Elo; ATP/WTA files carry no ITF."},
        200,
        "match_history",
        PROVIDER_NAME,
    )
    with get_connection() as conn:
        player_identity.ensure_identity_schema(conn)
        for match_date in _date_range(start_date, end_date or start_date):
            try:
                results, parse_skipped = provider.fetch_results_for_date(match_date)
            except Exception as exc:  # one bad day must not end the corpus build
                summary["errors"].append({"date": match_date, "error": str(exc)})
                continue
            counts = _store_history(conn, match_date, results, raw_id)
            conn.commit()
            summary["dates"] += 1
            summary["parse_skipped"] += parse_skipped
            for key in ("matches", "rows", "players_created", "skipped"):
                summary[key] += counts[key]
            if log:
                log(f"{match_date}: {counts['matches']} matches, "
                    f"{counts['players_created']} new players")
    return summary
