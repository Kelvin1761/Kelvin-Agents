from __future__ import annotations

import json
from collections import defaultdict

from tennis_wc.database.db import get_connection
from tennis_wc.features.elo import elo_probability
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now


def build_sackmann_elo(initial_rating: float = 1500.0, k_factor: float = 32.0) -> dict:
    """
    Build deterministic Elo ratings from stored Jeff Sackmann match history.

    Uses only local API snapshots already stored in player_match_history. Ratings
    are written back to players.overall_elo and players.surface_elo_json, and
    opponent pre-match Elo is backfilled into player_match_history.
    """
    with get_connection() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT provider_match_id, player_id, opponent_id, match_date, surface
                FROM player_match_history
                WHERE source_provider = 'jeff_sackmann' AND won = 1
                ORDER BY match_date, provider_match_id
                """
            ).fetchall()
        ]

    raw_id = store_raw_response(
        "jeff_sackmann_elo",
        "local/player_match_history",
        {"initial_rating": initial_rating, "k_factor": k_factor, "winner_rows": len(rows)},
        {"summary": "Deterministic Elo calculated from stored Jeff Sackmann match snapshots."},
        200,
        "player_elo",
        "jeff_sackmann",
    )

    overall: dict[int, float] = defaultdict(lambda: initial_rating)
    surface_ratings: dict[int, dict[str, float]] = defaultdict(dict)
    matches_by_player: dict[int, int] = defaultdict(int)
    surfaces_seen: set[str] = set()

    with get_connection() as conn:
        for row in rows:
            winner_id = int(row["player_id"])
            loser_id = int(row["opponent_id"])
            surface = _normalise_surface(row.get("surface"))

            winner_pre = overall[winner_id]
            loser_pre = overall[loser_id]
            winner_expected = elo_probability(winner_pre, loser_pre)
            overall[winner_id] = winner_pre + k_factor * (1 - winner_expected)
            overall[loser_id] = loser_pre + k_factor * (0 - (1 - winner_expected))

            winner_surface_pre = None
            loser_surface_pre = None
            if surface:
                surfaces_seen.add(surface)
                winner_surface_pre = surface_ratings[winner_id].get(surface, winner_pre)
                loser_surface_pre = surface_ratings[loser_id].get(surface, loser_pre)
                surface_expected = elo_probability(winner_surface_pre, loser_surface_pre)
                surface_ratings[winner_id][surface] = winner_surface_pre + k_factor * (1 - surface_expected)
                surface_ratings[loser_id][surface] = loser_surface_pre + k_factor * (0 - (1 - surface_expected))

            winner_match_id = row["provider_match_id"]
            loser_match_id = winner_match_id.removesuffix("-winner") + "-loser"
            conn.execute(
                """
                UPDATE player_match_history
                SET opponent_elo = ?
                WHERE source_provider = 'jeff_sackmann' AND provider_match_id = ?
                """,
                (loser_pre, winner_match_id),
            )
            conn.execute(
                """
                UPDATE player_match_history
                SET opponent_elo = ?
                WHERE source_provider = 'jeff_sackmann' AND provider_match_id = ?
                """,
                (winner_pre, loser_match_id),
            )
            matches_by_player[winner_id] += 1
            matches_by_player[loser_id] += 1

        now = utc_now()
        for player_id, rating in overall.items():
            conn.execute(
                """
                UPDATE players
                SET overall_elo = ?,
                    surface_elo_json = ?,
                    raw_response_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    round(rating, 3),
                    json.dumps(
                        {key: round(value, 3) for key, value in sorted(surface_ratings[player_id].items())},
                        sort_keys=True,
                    ),
                    raw_id,
                    now,
                    player_id,
                ),
            )

    return {
        "players_rated": len(overall),
        "winner_rows_processed": len(rows),
        "surfaces": sorted(surfaces_seen),
        "raw_response_id": raw_id,
        "min_player_matches": min(matches_by_player.values()) if matches_by_player else 0,
        "max_player_matches": max(matches_by_player.values()) if matches_by_player else 0,
    }


def _normalise_surface(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().lower() or None
