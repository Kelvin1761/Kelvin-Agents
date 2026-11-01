from __future__ import annotations

import json

from tennis_wc.database.db import get_connection
from tennis_wc.database.history_observations import history_active_clause
from tennis_wc.ingestion.ingest_sackmann import HISTORY_PROVIDERS
from tennis_wc.ingestion.ingest_tennisexplorer_history import (
    PROVIDER_NAME as TENNISEXPLORER_PROVIDER,
)
from tennis_wc.modelling.elo_replay import replay_elo
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now

# Elo reads more than the Sackmann files. Those publish ATP, ATP quali,
# Challenger and WTA and no ITF at all, which is why Elo reached 75.9% of tour
# fixtures and 1.2% of ITF ones while ITF is ~85% of the board we price. The
# TennisExplorer corpus exists to close exactly that gap.
ELO_PROVIDERS = (*HISTORY_PROVIDERS, TENNISEXPLORER_PROVIDER)

_PROVIDER_PLACEHOLDERS = ",".join("?" for _ in ELO_PROVIDERS)


def read_elo_inputs(conn) -> list[dict]:
    """The production eligibility and SQL order, without writing anything."""
    history_columns = {r["name"] for r in conn.execute("PRAGMA table_info(player_match_history)")}
    source_order = ("COALESCE(source_match_ref,provider_match_id)"
                    if "source_match_ref" in history_columns else "provider_match_id")
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT source_provider, provider_match_id, player_id, opponent_id,
                   match_date, surface
            FROM player_match_history
            WHERE source_provider IN ({_PROVIDER_PLACEHOLDERS}) AND won = 1
              AND {history_active_clause(conn)}
            ORDER BY match_date, {source_order}
            """,
            ELO_PROVIDERS,
        ).fetchall()
    ]


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
        rows = read_elo_inputs(conn)

    raw_id = store_raw_response(
        "jeff_sackmann_elo",
        "local/player_match_history",
        {"initial_rating": initial_rating, "k_factor": k_factor, "winner_rows": len(rows)},
        {"summary": "Deterministic Elo calculated from stored Jeff Sackmann match snapshots."},
        200,
        "player_elo",
        "jeff_sackmann",
    )

    calculated = replay_elo(rows, initial_rating, k_factor)
    overall = calculated.overall
    surface_ratings = calculated.surface_ratings
    matches_by_player = calculated.matches_by_player
    surfaces_seen = calculated.surfaces_seen
    history_rows = calculated.history_rows
    post_rows = calculated.post_rows
    opponent_updates = calculated.opponent_updates

    with get_connection() as conn:
        from tennis_wc.history import elo_history

        elo_history.ensure_schema(conn)
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
        # Shadow only (EXP-20261009-01). Inside a savepoint so a failure here
        # rolls back v2 alone and can never cost production its daily Elo.
        try:
            conn.execute("SAVEPOINT elo_shadow_v2")
            shadow_written = elo_history.replace_post_match(conn, post_rows)
            conn.execute("RELEASE SAVEPOINT elo_shadow_v2")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT elo_shadow_v2")
            conn.execute("RELEASE SAVEPOINT elo_shadow_v2")
            shadow_written = 0

    return {
        "players_rated": len(overall),
        "elo_history_rows": history_written,
        "elo_history_v2_rows": shadow_written,
        "winner_rows_processed": len(rows),
        "surfaces": sorted(surfaces_seen),
        "raw_response_id": raw_id,
        "min_player_matches": min(matches_by_player.values()) if matches_by_player else 0,
        "max_player_matches": max(matches_by_player.values()) if matches_by_player else 0,
    }
