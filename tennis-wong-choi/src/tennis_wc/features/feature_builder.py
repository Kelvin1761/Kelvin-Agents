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
    # One connection for the whole payload, closed on the way out: the as-of
    # lookups below run per player per match, so a connection each would be
    # both slow and a handle leak.
    conn = get_connection()
    try:
        return _build_player_payload(
            conn, player_id, opponent_id, match_context, as_of_date
        )
    finally:
        conn.close()


def _build_player_payload(conn, player_id: int, opponent_id: int,
                          match_context: dict, as_of_date: date) -> dict:
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

    # As-of, not latest. players.overall_elo is one mutable number rewritten on
    # every rebuild with the rating computed over the WHOLE record, so reading
    # it while building a feature for a past match embeds that match's own
    # result. player_elo_history holds the rating as it stood before each date;
    # fall back to the mutable column only when no history exists for the
    # player, and mark the datapoint so the fallback is visible downstream.
    overall_elo, surface_elo, elo_as_of = _elo_as_of(conn, player_id, as_of_date, surface)
    if overall_elo is None:
        overall_elo = player["overall_elo"]
        surface_elo = get_surface_elo(player["surface_elo_json"], surface, overall_elo)
    elo_prov = _elo_provenance(player_prov, dict(player))
    if not elo_as_of and overall_elo is not None:
        elo_prov = {**elo_prov, "warnings": [*elo_prov.get("warnings", []), "elo_not_as_of"]}
    return {
        "id": datapoint(player_id, player_prov),
        "name": player["name"],
        "current_rank": datapoint(_rank_as_of(conn, player_id, as_of_date, player), player_prov),
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


def _elo_as_of(conn, player_id: int, as_of_date, surface: str | None):
    """(overall, surface, is_as_of) ratings recorded before ``as_of_date``."""
    from tennis_wc.history import elo_history

    stamp = as_of_date.isoformat() if hasattr(as_of_date, "isoformat") else str(as_of_date)
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_elo_history'"
    ).fetchone()
    if not exists:
        return None, None, False
    overall = elo_history.rating_as_of(conn, player_id, stamp)
    if overall is None:
        return None, None, False
    on_surface = elo_history.rating_as_of(
        conn, player_id, stamp, surface=(surface or "").strip().lower() or None
    )
    return overall, (on_surface if on_surface is not None else overall), True


# How stale a match may be and still accept `players.current_rank` as its
# as-of rank. Two days covers a card built the night before, plus the timezone
# spread between a tournament's local match date and a UTC ranking stamp.
CURRENT_RANK_FALLBACK_DAYS = 2


def _rank_as_of(conn, player_id: int, as_of_date, player) -> int | None:
    """Ranking published before the match, not the player's rank today.

    players.current_rank carries no as-of date at all, so every historical
    feature built from it used whatever the rank happened to be at build time.
    rankings_history has been populated all along (103,002 rows).

    2026-08-27: the unconditional fallback to `players.current_rank` was a
    look-ahead path, and lifting the ranking feed's 500-cap made it fire more
    often rather than less. Measured over the 5,748 player-sides on priced
    fixtures: 51.1% have a genuine as-of row, 29.9% have nothing, and **19.0%
    were being handed today's rank for a match already played** -- and that
    share grows with every improvement to `current_rank` coverage, which is the
    opposite of what a coverage fix should do.

    So the fallback now only applies to a match that has not meaningfully
    happened yet. A live card still gets a rank when the morning ranking
    refresh has not landed; a rebuilt historical snapshot gets None and says so,
    which is the honest input and the one the model should be graded on.
    """
    stamp = as_of_date.isoformat() if hasattr(as_of_date, "isoformat") else str(as_of_date)
    row = conn.execute(
        """
        SELECT rank FROM rankings_history
        WHERE player_id = ? AND ranking_date < ? AND rank IS NOT NULL
        ORDER BY ranking_date DESC LIMIT 1
        """,
        (player_id, stamp),
    ).fetchone()
    if row:
        return int(row[0])
    if not _is_effectively_now(stamp):
        return None
    return player["current_rank"]


def _is_effectively_now(stamp: str) -> bool:
    """Is this as-of date close enough to today that today's rank IS the as-of
    rank? Anything older is history, and history must not read a mutable
    column."""
    try:
        as_of = date.fromisoformat(str(stamp)[:10])
    except ValueError:
        return False
    return (date.today() - as_of).days <= CURRENT_RANK_FALLBACK_DAYS


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


def _sportsbet_priced_matches(conn, match_date: str) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
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
    ]


def build_sportsbet_feature_snapshots_for_date(
    match_date: str, skipped: list[dict] | None = None
) -> list[dict]:
    """Build snapshots for every Sportsbet-priced SINGLES match on a date.

    Each match is isolated: a match that cannot be assembled is recorded and
    skipped, never allowed to end the loop. This used to be a bare list
    comprehension, so the FIRST match whose tournament metadata was missing
    raised out of the whole call and silently dropped every remaining match for
    that date -- with no error surfaced anywhere, the report just showed a
    smaller "已分析" count. Pass `skipped` to collect the per-match reasons.
    """
    from tennis_wc.ingestion.confirmed_metadata import is_doubles_competition

    with get_connection() as conn:
        rows = _sportsbet_priced_matches(conn, match_date)

    log = skipped if skipped is not None else []
    snapshots: list[dict] = []
    for row in rows:
        match_id = int(row["id"])
        # Doubles events must never enter the singles pipeline: the "players" are
        # pair labels with no Elo/history, so every downstream read is junk (130
        # doubles matches had produced 257 junk predictions before this filter).
        if is_doubles_competition(row["tournament_name"]):
            log.append({"match_id": match_id, "tournament": row["tournament_name"],
                        "reason": "doubles_competition"})
            continue
        try:
            snapshots.append(build_match_feature_snapshot(match_id))
        except Exception as exc:  # one bad match must not blind us to the rest
            log.append({"match_id": match_id, "tournament": row["tournament_name"],
                        "reason": f"{type(exc).__name__}: {exc}"})
    return snapshots


# The two populations, and why the readiness gate may only see one of them.
#
# Fixtures arrive from two places that do not overlap. `matches.source_provider
# = 'sportsbet'` is a row Sportsbet itself listed -- it is in the book by
# definition. `'composite'` is the ESPN fixture feed, which publishes full draws
# days ahead and covers tournaments Sportsbet never opens a market on at all
# (ITF qualifying, UTR, college events).
#
# Dividing sportsbet-priced matches by the UNION of the two answers a question
# nobody asked: "what share of every fixture on earth does Sportsbet price?"
# On 2026-08-24 that number was 34% and blocked the card, twice, through both
# recovery attempts -- because ESPN had loaded 64 US Open QUALIFYING fixtures
# that Sportsbet had no market for. Sportsbet's own book that morning was
# 53/81 = 65%, a perfectly ordinary day. Measured over 2026-07-28..08-25 the
# union ratio dips under the 35% gate on four dates, three of which had a
# healthy book; the book-scoped ratio is 52-100% on every date that had one.
#
# So `fixtures` stays the full calendar count -- the health line reports it and
# it is the honest answer to "how much tennis is on today" -- and the gate
# reads `book_fixtures`, which counts only what Sportsbet listed. A day where
# Sportsbet lists nothing at all still lands on the zero-fixtures branch, which
# is the outage the gate exists to catch.
_BOOK_SCOPE_SQL = """
                  AND (
                        m.source_provider = 'sportsbet'
                        OR EXISTS (
                            SELECT 1 FROM odds_snapshots o
                            WHERE o.match_id = m.id AND o.source_provider = 'sportsbet'
                        )
                  )
"""

_PRICED_SCOPE_SQL = """
                  AND EXISTS (
                        SELECT 1 FROM odds_snapshots o
                        WHERE o.match_id = m.id AND o.source_provider = 'sportsbet'
                  )
"""


def _distinct_fixture_count(conn, match_date: str, extra_where: str = "") -> int:
    """Fixtures on a date, deduplicated the one way the whole module dedupes.

    Two providers describing the same match are one fixture, and a row whose
    "players" are placeholders is not a fixture at all. Counting the numerator
    with `COUNT(DISTINCT match_id)` while the denominator deduped by player pair
    could put the ratio above 1.0; both go through here now.
    """
    return int(conn.execute(
        f"""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT
                    m.tour,
                    CASE
                        WHEN lower(pa.name) <= lower(pb.name)
                        THEN lower(pa.name) || '|' || lower(pb.name)
                        ELSE lower(pb.name) || '|' || lower(pa.name)
                    END AS player_pair
                FROM matches m
                JOIN players pa ON pa.id = m.player_a_id
                JOIN players pb ON pb.id = m.player_b_id
                WHERE m.match_date = ?
                  AND m.player_a_id != m.player_b_id
                  AND lower(trim(pa.name)) NOT IN ('unknown player', 'unknown', 'tbd', 'none', 'null', '')
                  AND lower(trim(pb.name)) NOT IN ('unknown player', 'unknown', 'tbd', 'none', 'null', '')
                  {extra_where}
            )
        """,
        (match_date,),
    ).fetchone()[0] or 0)


def odds_coverage_for_date(match_date: str) -> dict:
    """How much of the day's fixture list Sportsbet has actually priced.

    A run can look healthy while pricing almost nothing. The 20:00 scheduled job
    analyses TOMORROW, and Sportsbet has not opened most of tomorrow's book at
    that hour, so on 2026-07-29 the report was built from 2 priced matches out of
    102 fixtures (2%) and still counted as a successful run -- the retry gate only
    fired on "zero matches" or "all snapshots invalid". Exposing the ratio lets
    the scheduler tell "quiet betting day" apart from "the book was not open yet".

    Returns both scopes: `fixtures`/`priced_ratio` over the whole calendar for
    display, and `book_fixtures`/`book_priced_ratio` over Sportsbet's own book
    for the gate. See `_BOOK_SCOPE_SQL` for why they must not be the same number.
    """
    with get_connection() as conn:
        fixtures = _distinct_fixture_count(conn, match_date)
        book_fixtures = _distinct_fixture_count(conn, match_date, _BOOK_SCOPE_SQL)
        priced = _distinct_fixture_count(conn, match_date, _PRICED_SCOPE_SQL)
        latest = conn.execute(
            """
            SELECT MAX(o.fetched_at) FROM odds_snapshots o
            JOIN matches m ON m.id = o.match_id
            WHERE m.match_date = ? AND o.source_provider = 'sportsbet'
            """,
            (match_date,),
        ).fetchone()[0]
    return {
        "fixtures": int(fixtures or 0),
        "priced_matches": int(priced or 0),
        "priced_ratio": round((priced or 0) / fixtures, 4) if fixtures else None,
        "book_fixtures": int(book_fixtures or 0),
        "book_priced_ratio": (
            round((priced or 0) / book_fixtures, 4) if book_fixtures else None
        ),
        "latest_scrape": latest,
    }


def feature_build_coverage(match_date: str) -> dict:
    """Read-only: how many Sportsbet-priced matches actually reached the model.

    Exists because the gap was invisible. On 2026-07-25 the report said "已分析 38
    場" while 60 matches had Sportsbet odds -- including all 22 of an ATP 500
    (Washington), which produced 2 feature snapshots and 0 predictions. Nothing
    in any output mentioned the other 20 matches. This surfaces the drop so it
    can never be silent again.
    """
    from tennis_wc.ingestion.confirmed_metadata import is_doubles_competition

    with get_connection() as conn:
        rows = _sportsbet_priced_matches(conn, match_date)
        with_features = {
            int(r["match_id"])
            for r in conn.execute(
                """
                SELECT DISTINCT f.match_id FROM feature_snapshots f
                JOIN matches m ON m.id = f.match_id WHERE m.match_date = ?
                """,
                (match_date,),
            ).fetchall()
        }
        with_predictions = {
            int(r["match_id"])
            for r in conn.execute(
                """
                SELECT DISTINCT p.match_id FROM predictions p
                JOIN matches m ON m.id = p.match_id WHERE m.match_date = ?
                """,
                (match_date,),
            ).fetchall()
        }
    singles = [r for r in rows if not is_doubles_competition(r["tournament_name"])]
    missing = [r for r in singles if int(r["id"]) not in with_features]
    by_tournament: dict[str, int] = {}
    for row in missing:
        name = str(row["tournament_name"] or "unknown")
        by_tournament[name] = by_tournament.get(name, 0) + 1
    return {
        "priced_matches": len(rows),
        "singles_candidates": len(singles),
        "doubles_excluded": len(rows) - len(singles),
        "with_features": sum(1 for r in singles if int(r["id"]) in with_features),
        "with_predictions": sum(1 for r in singles if int(r["id"]) in with_predictions),
        "missing_features": len(missing),
        "missing_by_tournament": dict(
            sorted(by_tournament.items(), key=lambda kv: -kv[1])
        ),
    }
