from __future__ import annotations

import json
from collections import defaultdict

from tennis_wc.database.db import get_connection
from tennis_wc.features.elo import elo_probability
from tennis_wc.ingestion.ingest_sackmann import HISTORY_PROVIDERS
from tennis_wc.ingestion.ingest_tennisexplorer_history import (
    PROVIDER_NAME as TENNISEXPLORER_PROVIDER,
)
from tennis_wc.modelling.calibration import elo_k_factor
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now

# Elo reads more than the Sackmann files. Those publish ATP, ATP quali,
# Challenger and WTA and no ITF at all, which is why Elo reached 75.9% of tour
# fixtures and 1.2% of ITF ones while ITF is ~85% of the board we price. The
# TennisExplorer corpus exists to close exactly that gap.
ELO_PROVIDERS = (*HISTORY_PROVIDERS, TENNISEXPLORER_PROVIDER)

_PROVIDER_PLACEHOLDERS = ",".join("?" for _ in ELO_PROVIDERS)


def build_sackmann_elo(initial_rating: float = 1500.0, k_factor: float | None = None) -> dict:
    """
    Build deterministic Elo ratings from the stored match corpus.

    Reads every provider in ``ELO_PROVIDERS`` from player_match_history --
    the Sackmann/TennisMyLife files plus the TennisExplorer lower-tier corpus. Ratings
    are written back to players.overall_elo and players.surface_elo_json, and
    opponent pre-match Elo is backfilled into player_match_history.

    K is match-count-decayed (Sackmann-style) by default — the same curve used
    by the calibration scorer — so production ratings match what calibration
    validates. Pass a float ``k_factor`` to force a flat K.
    """
    with get_connection() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT source_provider, provider_match_id, player_id, opponent_id,
                       match_date, surface
                FROM player_match_history
                WHERE source_provider IN ({_PROVIDER_PLACEHOLDERS}) AND won = 1
                ORDER BY match_date, provider_match_id
                """,
                ELO_PROVIDERS,
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
    surface_matches: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    surfaces_seen: set[str] = set()

    def k_for(played: int) -> float:
        return float(k_factor) if k_factor is not None else elo_k_factor(played)

    with get_connection() as conn:
        from tennis_wc.history import elo_history

        elo_history.ensure_schema(conn)
        # The walk is already chronological, so the rating held at the top of
        # each iteration IS the pre-match rating. Capturing it here is what
        # makes an as-of lookup possible at all; without it the only rating
        # anyone can read is the final one, which contains every later result.
        history_rows: list[tuple] = []
        opponent_updates: list[tuple[str, str, float]] = []
        for row in rows:
            winner_id = int(row["player_id"])
            loser_id = int(row["opponent_id"])
            surface = _normalise_surface(row.get("surface"))

            winner_pre = overall[winner_id]
            loser_pre = overall[loser_id]
            match_date = row.get("match_date")
            history_rows.append(
                (winner_id, match_date, "", winner_pre, matches_by_player[winner_id])
            )
            history_rows.append(
                (loser_id, match_date, "", loser_pre, matches_by_player[loser_id])
            )
            winner_expected = elo_probability(winner_pre, loser_pre)
            k_winner = k_for(matches_by_player[winner_id])
            k_loser = k_for(matches_by_player[loser_id])
            overall[winner_id] = winner_pre + k_winner * (1 - winner_expected)
            overall[loser_id] = loser_pre + k_loser * (0 - (1 - winner_expected))

            winner_surface_pre = None
            loser_surface_pre = None
            if surface:
                surfaces_seen.add(surface)
                winner_surface_pre = surface_ratings[winner_id].get(surface, winner_pre)
                loser_surface_pre = surface_ratings[loser_id].get(surface, loser_pre)
                surface_expected = elo_probability(winner_surface_pre, loser_surface_pre)
                ks_winner = k_for(surface_matches[winner_id][surface])
                ks_loser = k_for(surface_matches[loser_id][surface])
                history_rows.append(
                    (winner_id, match_date, surface, winner_surface_pre,
                     surface_matches[winner_id][surface])
                )
                history_rows.append(
                    (loser_id, match_date, surface, loser_surface_pre,
                     surface_matches[loser_id][surface])
                )
                surface_ratings[winner_id][surface] = winner_surface_pre + ks_winner * (1 - surface_expected)
                surface_ratings[loser_id][surface] = loser_surface_pre + ks_loser * (0 - (1 - surface_expected))
                surface_matches[winner_id][surface] += 1
                surface_matches[loser_id][surface] += 1

            winner_match_id = row["provider_match_id"]
            loser_match_id = winner_match_id.removesuffix("-winner") + "-loser"
            provider = str(row["source_provider"])
            opponent_updates.append((provider, winner_match_id, loser_pre))
            opponent_updates.append((provider, loser_match_id, winner_pre))
            matches_by_player[winner_id] += 1
            matches_by_player[loser_id] += 1

        # The old loop issued two UPDATE statements per historical match. On
        # the production corpus that meant hundreds of thousands of Python to
        # SQLite round trips on every daily run, and it matched ids across ALL
        # providers, so a provider-local id collision could overwrite another
        # source's Elo. Stage provider-qualified values, then update the corpus
        # in one set operation.
        conn.execute(
            """CREATE TEMP TABLE IF NOT EXISTS _elo_opponent_updates (
                   source_provider TEXT NOT NULL,
                   provider_match_id TEXT NOT NULL,
                   opponent_elo REAL NOT NULL,
                   PRIMARY KEY (source_provider, provider_match_id)
               ) WITHOUT ROWID"""
        )
        conn.execute("DELETE FROM _elo_opponent_updates")
        conn.executemany(
            "INSERT OR REPLACE INTO _elo_opponent_updates "
            "(source_provider,provider_match_id,opponent_elo) VALUES (?,?,?)",
            opponent_updates,
        )
        conn.execute(
            """UPDATE player_match_history
               SET opponent_elo = (
                   SELECT staged.opponent_elo
                   FROM _elo_opponent_updates AS staged
                   WHERE staged.source_provider = player_match_history.source_provider
                     AND staged.provider_match_id = player_match_history.provider_match_id
               )
               WHERE EXISTS (
                   SELECT 1 FROM _elo_opponent_updates AS staged
                   WHERE staged.source_provider = player_match_history.source_provider
                     AND staged.provider_match_id = player_match_history.provider_match_id
               )"""
        )
        conn.execute("DROP TABLE _elo_opponent_updates")

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

        history_written = elo_history.record(conn, history_rows)

    return {
        "players_rated": len(overall),
        "elo_history_rows": history_written,
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
