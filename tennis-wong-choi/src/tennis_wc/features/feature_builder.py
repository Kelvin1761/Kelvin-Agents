from __future__ import annotations

import json
from datetime import date
from typing import Any

from tennis_wc.database.db import get_connection
from tennis_wc.features.big_match import calculate_big_match_stats
from tennis_wc.features.bo_format import calculate_bo_format_stats, detect_match_format
from tennis_wc.features.common import datapoint, provenance, utc_now
from tennis_wc.features.data_quality import validate_data_freshness
from tennis_wc.features.head_to_head import calculate_head_to_head_stats
from tennis_wc.features.opponent_elo_buckets import calculate_player_elo_bucket_stats
from tennis_wc.features.opponent_rank_buckets import calculate_player_rank_bucket_stats
from tennis_wc.features.pressure import calculate_pressure_stats
from tennis_wc.features.round_performance import calculate_round_stats, normalise_round
from tennis_wc.features.surface_elo import get_surface_elo
from tennis_wc.features.tournament_level import calculate_tournament_level_stats


FEATURE_SET_VERSION = "stage3.v1"
RELIABLE_TOURNAMENT_METADATA_SOURCES = {
    "curated_tournament_metadata",
    "tennisdata_tournament_index",
    # Level/tour parsed from unambiguous circuit markers in Sportsbet's own
    # competition names ("... Challenger", "ITF ...", "UTR", "125K"). Level is
    # trustworthy; it never claims a surface (stored as NULL).
    "competition_name_heuristic",
    "bsd_tennis",
    "espn",
    "statsperform",
    "jeff_sackmann",
    "mock",
}


def _raw_meta(raw_response_id: int | None) -> dict:
    if raw_response_id is None:
        return {
            "source_provider": "missing",
            "source_endpoint": "missing",
            "source_timestamp": utc_now(),
            "raw_response_id": None,
            "warnings": ["missing_raw_response_id"],
        }
    with get_connection() as conn:
        row = conn.execute(
            "SELECT provider_name, endpoint, fetched_at FROM raw_api_responses WHERE id = ?",
            (raw_response_id,),
        ).fetchone()
    if not row:
        return {
            "source_provider": "missing",
            "source_endpoint": "missing",
            "source_timestamp": utc_now(),
            "raw_response_id": raw_response_id,
            "warnings": ["missing_raw_response"],
        }
    return provenance(row["provider_name"], row["endpoint"], row["fetched_at"], raw_response_id)


def _latest_history_prov(player_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT r.provider_name, r.endpoint, r.fetched_at, r.id
            FROM player_match_history h
            JOIN raw_api_responses r ON r.id = h.raw_response_id
            WHERE h.player_id = ?
            ORDER BY r.fetched_at DESC
            LIMIT 1
            """,
            (player_id,),
        ).fetchone()
    if not row:
        return provenance("missing", "player_match_history", utc_now(), None, ["missing_player_history"])
    return provenance(row["provider_name"], row["endpoint"], row["fetched_at"], row["id"])


def _wrap_numeric_tree(value: Any, prov: dict) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return datapoint(value, prov)
    if isinstance(value, dict):
        warnings = value.get("warnings", [])
        wrapped = {}
        for key, val in value.items():
            if key == "warnings":
                continue
            next_prov = prov
            if warnings and key in {"matches", "sample_size"}:
                next_prov = prov | {"warnings": sorted(set([*prov.get("warnings", []), *warnings]))}
            wrapped[key] = _wrap_numeric_tree(val, next_prov)
        return wrapped
    if isinstance(value, list):
        return [_wrap_numeric_tree(item, prov) for item in value]
    return value


def _player_payload(player_id: int, opponent_id: int, match_context: dict, as_of_date: date) -> dict:
    with get_connection() as conn:
        player = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if player is None:
        raise ValueError(f"Player not found: {player_id}")

    player_prov = _raw_meta(player["raw_response_id"])
    history_prov = _latest_history_prov(player_id)
    surface = match_context["surface"]["value"]
    level = match_context["level"]["value"]
    round_name = match_context["round"]["value"]
    match_format = match_context["format"]["value"]

    rank_buckets = calculate_player_rank_bucket_stats(player_id, surface, as_of_date, "LAST_52_WEEKS")
    elo_buckets = calculate_player_elo_bucket_stats(player_id, surface, as_of_date, "LAST_52_WEEKS")
    tournament_level = calculate_tournament_level_stats(player_id, level, surface, as_of_date, "LAST_52_WEEKS")
    round_stats = calculate_round_stats(player_id, round_name, level, surface, as_of_date, "LAST_52_WEEKS")
    big_match = calculate_big_match_stats(player_id, surface, as_of_date, "LAST_52_WEEKS")
    bo_format = calculate_bo_format_stats(player_id, match_format, surface, as_of_date, "LAST_52_WEEKS")
    pressure = calculate_pressure_stats(player_id, surface, as_of_date, "LAST_52_WEEKS")
    h2h = calculate_head_to_head_stats(player_id, opponent_id, surface, as_of_date)
    rest_days = _rest_days(player_id, as_of_date)

    overall_elo = player["overall_elo"]
    surface_elo = get_surface_elo(player["surface_elo_json"], surface, overall_elo)
    elo_prov = _elo_provenance(player_prov, dict(player))
    return {
        "id": datapoint(player_id, player_prov),
        "name": player["name"],
        "current_rank": datapoint(player["current_rank"], player_prov),
        "overall_elo": datapoint(overall_elo, elo_prov),
        "surface_elo": datapoint(surface_elo, elo_prov),
        "serve_return": {
            "note": "Stage 3 placeholder until serve-return provider mapping is confirmed.",
            "provenance": history_prov,
        },
        "recent_form": {
            "note": "Stage 3 placeholder until form model is implemented.",
            "provenance": history_prov,
        },
        "opponent_rank_buckets": _wrap_numeric_tree(rank_buckets, history_prov),
        "opponent_elo_buckets": _wrap_numeric_tree(elo_buckets, history_prov),
        "tournament_level_stats": _wrap_numeric_tree(tournament_level, history_prov),
        "round_stats": _wrap_numeric_tree(round_stats, history_prov),
        "big_match_stats": _wrap_numeric_tree(big_match, history_prov),
        "bo_format_stats": _wrap_numeric_tree(bo_format, history_prov),
        "pressure_stats": _wrap_numeric_tree(pressure, history_prov),
        "head_to_head": _wrap_numeric_tree(h2h, history_prov),
        "fatigue": {"status": "KNOWN" if rest_days is not None else "UNKNOWN", "rest_days": datapoint(rest_days, history_prov), "provenance": history_prov},
        "injury": {"risk": "UNKNOWN", "provenance": history_prov},
    }


def _elo_provenance(player_prov: dict, player: dict) -> dict:
    has_rank_seed_shape = (
        player.get("overall_elo") is not None
        and player.get("current_rank") is not None
        and not player.get("surface_elo_json")
    )
    if player_prov.get("source_endpoint") != "/rankings" and not has_rank_seed_shape:
        return player_prov
    warnings = sorted(set([*player_prov.get("warnings", []), "rank_seed_elo"]))
    return player_prov | {"warnings": warnings}


def _rest_days(player_id: int, as_of_date: date) -> int | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(match_date) AS last_match_date
            FROM player_match_history
            WHERE player_id = ?
              AND match_date < ?
            """,
            (player_id, as_of_date.isoformat()),
        ).fetchone()
    if not row or not row["last_match_date"]:
        return None
    return max(0, (as_of_date - date.fromisoformat(row["last_match_date"])).days)


def _match_context(match: dict, tournament: dict, tournament_level: dict) -> dict:
    match_prov = _raw_meta(match["raw_response_id"])
    tournament_prov = _raw_meta(tournament_level["raw_response_id"])
    metadata_source = str(tournament_level.get("source_provider") or "")
    level = tournament_level["level"]
    surface = tournament_level["surface"]
    indoor_outdoor = tournament_level["indoor_outdoor"]
    if metadata_source not in RELIABLE_TOURNAMENT_METADATA_SOURCES:
        level = "UNKNOWN"
        surface = None
        indoor_outdoor = None
    base = {
        "tournament": datapoint(tournament["name"], tournament_prov),
        "tour": datapoint(match["tour"], match_prov),
        "level": datapoint(level, tournament_prov),
        "round": datapoint(normalise_round(match["round"]), match_prov),
        "surface": datapoint(surface, tournament_prov),
        "indoor_outdoor": datapoint(indoor_outdoor, tournament_prov),
        "match_date": datapoint(match["match_date"], match_prov),
    }
    base["format"] = datapoint(detect_match_format({"tour": match["tour"], "level": level}), tournament_prov)
    return base


def _normalise_name(value: str | None) -> str:
    return " ".join(str(value or "").lower().strip().split())


def _market(match_id: int) -> dict:
    with get_connection() as conn:
        match = conn.execute(
            """
            SELECT p1.name AS player_a_name, p2.name AS player_b_name
            FROM matches m
            JOIN players p1 ON p1.id = m.player_a_id
            JOIN players p2 ON p2.id = m.player_b_id
            WHERE m.id = ?
            """,
            (match_id,),
        ).fetchone()
        odds_rows = conn.execute(
            """
            SELECT *
            FROM market_odds_snapshots
            WHERE match_id = ?
              AND market_key = 'match_winner'
              AND id IN (
                  SELECT MAX(id)
                  FROM market_odds_snapshots
                  WHERE match_id = ?
                    AND market_key = 'match_winner'
                  GROUP BY selection_name, COALESCE(line, -999999)
              )
            ORDER BY id DESC
            """,
            (match_id, match_id),
        ).fetchall()
    if not odds_rows:
        return _legacy_positional_market(match_id)
    if match is None:
        prov = _raw_meta(odds_rows[0]["raw_response_id"])
        return {"errors": ["odds_selection_mapping_failed"], "timestamp": datapoint(odds_rows[0]["fetched_at"], prov)}

    player_a_name = match["player_a_name"]
    player_b_name = match["player_b_name"]
    player_a_key = _normalise_name(player_a_name)
    player_b_key = _normalise_name(player_b_name)
    player_a_row = None
    player_b_row = None
    for row in odds_rows:
        selection_key = _normalise_name(row["selection_name"])
        if selection_key == player_a_key:
            player_a_row = row
        elif selection_key == player_b_key:
            player_b_row = row

    prov = _raw_meta(odds_rows[0]["raw_response_id"])
    if player_a_row is None or player_b_row is None:
        return {
            "bookmaker": datapoint(odds_rows[0]["bookmaker"], prov),
            "market": datapoint("match_winner", prov),
            "timestamp": datapoint(odds_rows[0]["fetched_at"], prov),
            "mapping_status": datapoint("failed", prov),
            "errors": ["odds_selection_mapping_failed"],
            "available_selections": [row["selection_name"] for row in odds_rows],
        }

    return {
        "bookmaker": datapoint(player_a_row["bookmaker"], prov),
        "market": datapoint("match_winner", prov),
        "player_a_odds": datapoint(player_a_row["odds"], prov),
        "player_b_odds": datapoint(player_b_row["odds"], prov),
        "player_a_open_odds": datapoint(None, prov),
        "player_b_open_odds": datapoint(None, prov),
        "player_a_selection_name": datapoint(player_a_row["selection_name"], prov),
        "player_b_selection_name": datapoint(player_b_row["selection_name"], prov),
        "timestamp": datapoint(max(player_a_row["fetched_at"], player_b_row["fetched_at"]), prov),
        "mapping_status": datapoint("verified", prov),
        "errors": [],
    }


def _legacy_positional_market(match_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM odds_snapshots
            WHERE match_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
            """,
            (match_id,),
        ).fetchone()
    if not row:
        return {}
    prov = _raw_meta(row["raw_response_id"])
    return {
        "bookmaker": datapoint(row["bookmaker"], prov),
        "market": datapoint(row["market"], prov),
        "player_a_odds": datapoint(row["player_a_odds"], prov),
        "player_b_odds": datapoint(row["player_b_odds"], prov),
        "player_a_open_odds": datapoint(row["player_a_open_odds"], prov),
        "player_b_open_odds": datapoint(row["player_b_open_odds"], prov),
        "timestamp": datapoint(row["fetched_at"], prov),
        "mapping_status": datapoint("legacy_positional_fallback", prov),
        "errors": [],
    }


def assemble_match_feature_snapshot(match_id: int) -> tuple[dict, dict]:
    """
    Build the complete two-player feature snapshot WITHOUT persisting it.

    Returns (snapshot, tournament_level_row) so callers that want to persist can
    reuse the same assembly. This is read-only and safe to call repeatedly
    (e.g. from backtests) because it never writes to feature_snapshots.
    """
    with get_connection() as conn:
        match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not match:
            raise ValueError(f"Match not found: {match_id}")
        tournament = conn.execute("SELECT * FROM tournaments WHERE id = ?", (match["tournament_id"],)).fetchone()
        tournament_level = conn.execute(
            """
            SELECT * FROM tournament_levels
            WHERE tournament_id = ? AND tour = ?
            ORDER BY
                (source_provider = 'curated_tournament_metadata') DESC,
                (level != 'UNKNOWN' AND level != '未確認') DESC,
                (surface IS NOT NULL) DESC,
                id DESC
            LIMIT 1
            """,
            (match["tournament_id"], match["tour"]),
        ).fetchone()
    if tournament is None or tournament_level is None:
        raise ValueError(f"Tournament metadata missing for match {match_id}")

    match_dict = dict(match)
    context = _match_context(match_dict, dict(tournament), dict(tournament_level))
    as_of_date = date.fromisoformat(match["match_date"])
    snapshot = {
        "match_id": datapoint(match_id, _raw_meta(match["raw_response_id"])),
        "feature_set_version": FEATURE_SET_VERSION,
        "match_context": context,
        "player_a": _player_payload(match["player_a_id"], match["player_b_id"], context, as_of_date),
        "player_b": _player_payload(match["player_b_id"], match["player_a_id"], context, as_of_date),
        "market": _market(match_id),
        "entity_mapping_complete": True,
    }
    quality = validate_data_freshness(snapshot)
    snapshot["data_quality"] = quality
    snapshot["provenance"] = {
        "match_raw_response_id": match["raw_response_id"],
        "tournament_raw_response_id": tournament_level["raw_response_id"],
    }
    return snapshot, dict(tournament_level)


def build_match_feature_snapshot(match_id: int) -> dict:
    """
    Build complete feature set for both players.
    Store feature snapshots in database and return structured JSON.
    """
    snapshot, _tournament_level = assemble_match_feature_snapshot(match_id)
    quality = snapshot["data_quality"]

    now = utc_now()
    with get_connection() as conn:
        for player_key in ("player_a", "player_b"):
            player_payload = snapshot[player_key]
            player_id = player_payload["id"]["value"]
            conn.execute(
                """
                INSERT INTO feature_snapshots (
                    match_id, player_id, feature_set_version, features_json,
                    provenance_json, data_quality_score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    player_id,
                    FEATURE_SET_VERSION,
                    json.dumps(player_payload, sort_keys=True),
                    json.dumps(snapshot["provenance"], sort_keys=True),
                    quality["score"],
                    now,
                ),
            )
    return snapshot


def build_feature_snapshots_for_date(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM matches WHERE match_date = ?", (match_date,)).fetchall()
    return [build_match_feature_snapshot(int(row["id"])) for row in rows]


def build_sportsbet_feature_snapshots_for_date(match_date: str) -> list[dict]:
    from tennis_wc.ingestion.confirmed_metadata import is_doubles_competition

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT m.id, t.name AS tournament_name
            FROM matches m
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN odds_snapshots o ON o.match_id = m.id
            WHERE m.match_date = ?
              AND o.source_provider = 'sportsbet'
            ORDER BY m.id
            """,
            (match_date,),
        ).fetchall()
    # Doubles events must never enter the singles pipeline: the "players" are
    # pair labels with no Elo/history, so every downstream read is junk (130
    # doubles matches had produced 257 junk predictions before this filter).
    return [
        build_match_feature_snapshot(int(row["id"]))
        for row in rows
        if not is_doubles_competition(row["tournament_name"])
    ]
