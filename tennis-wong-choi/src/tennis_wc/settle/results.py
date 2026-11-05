"""Fetch match results into ``match_results``.

Sources, in order: the composite provider (ESPN) for the date and its two
neighbours, a resolver for fixtures still without a result, TennisMyLife and
TennisExplorer (ITF/low tiers). Each source's facts are stored as their own
rows; ``store.results`` decides when sources disagree.
"""
from __future__ import annotations

from tennis_wc.model.history import active_clause
import json
from datetime import date, timedelta
from tennis_wc.store.db import get_connection
from tennis_wc.model.features.common import utc_now
from tennis_wc.sources.name_matching import match_pair_score, same_player_name
from tennis_wc.sources.providers import get_tennis_provider


def fetch_results_for_date(match_date: str) -> dict:
    provider = get_tennis_provider()
    tennis_my_life = None
    try:
        lookup_dates = _result_lookup_dates(match_date)
        rows = []
        target_rows = []
        for lookup_date in lookup_dates:
            fetched = provider.fetch_historical_matches(lookup_date, lookup_date)
            if lookup_date == match_date:
                target_rows = fetched
            rows.extend(fetched)
    except Exception as exc:
        rows = []
        target_rows = []
        provider_error = str(exc)
    else:
        provider_error = None
    provider_name = getattr(provider, "provider_name", "unknown")
    imported = _store_result_rows(match_date, rows, provider_name)
    resolver = _resolve_pending_match_results(match_date, rows, provider_name)
    winners_seen = len([row for row in target_rows if row.get("won")])
    lookup_winners_seen = len([row for row in rows if row.get("won")])
    try:
        from tennis_wc.sources.ingest_tennismylife import ingest_tennismylife_results

        tennis_my_life = ingest_tennismylife_results(match_date)
    except Exception as exc:
        tennis_my_life = {"error": str(exc), "results_imported": 0}
    # ITF / UTR / Challenger: no other wired source publishes them, so without
    # this every prop on those tiers stays PENDING and never becomes evidence.
    try:
        from tennis_wc.sources.ingest_tennisexplorer import (
            ingest_tennisexplorer_results,
        )

        tennis_explorer = ingest_tennisexplorer_results(match_date)
    except Exception as exc:
        tennis_explorer = {"error": str(exc), "imported": 0}
    return {
        "provider": getattr(provider, "provider_name", "unknown"),
        "rows_seen": len(target_rows),
        "lookup_dates": lookup_dates if "lookup_dates" in locals() else [match_date],
        "lookup_rows_seen": len(rows),
        "winners_seen": winners_seen,
        "lookup_winners_seen": lookup_winners_seen,
        "imported": imported,
        "unmatched": max(0, winners_seen - min(imported, winners_seen)),
        "error": provider_error,
        "resolver": resolver,
        "tennismylife": tennis_my_life,
        "tennisexplorer": tennis_explorer,
    }


def _result_lookup_dates(match_date: str) -> list[str]:
    from datetime import date, timedelta

    current = date.fromisoformat(match_date)
    return [(current + timedelta(days=offset)).isoformat() for offset in (0, -1, 1)]


MIN_RESULT_MATCH_SCORE = 1.84


def _store_result_rows(match_date: str, rows: list[dict], provider_name: str) -> int:
    winners = [row for row in rows if row.get("won")]
    imported = 0
    now = utc_now()
    with get_connection() as conn:
        for row in winners:
            match = _match_by_names(conn, match_date, str(row.get("player_name") or ""), str(row.get("opponent_name") or ""))
            if not match:
                continue
            winner_player_id = match["player_a_id"] if same_player_name(row.get("player_name"), match["player_a_name"]) else match["player_b_id"]
            score_json = _result_score_json(row, dict(match))
            conn.execute(
                """
                INSERT INTO match_results (match_id, winner_player_id, score_json, source_provider, raw_response_id, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(match_id, source_provider) DO UPDATE SET
                    winner_player_id = excluded.winner_player_id,
                    score_json = COALESCE(excluded.score_json, match_results.score_json),
                    created_at = excluded.created_at
                """,
                (match["id"], winner_player_id, score_json, provider_name, now),
            )
            imported += 1
    return imported


def _resolve_pending_match_results(match_date: str, rows: list[dict], provider_name: str) -> dict:
    """
    Fill match_results for tracked sportsbook fixtures that normal result import missed.

    This deliberately keeps strict pair matching. It is a resolver, not a guesser:
    provider rows, future event-level result APIs, and local history can only settle
    when both player names line up with the pending match pair.
    """
    event_summary = _resolve_pending_from_event_provider(match_date)
    provider_rows_imported = _resolve_pending_from_provider_rows(match_date, rows, provider_name)
    history_imported = _resolve_pending_from_player_history(match_date)
    return {
        "event_id_tracked": event_summary["event_id_tracked"],
        "event_result_imported": event_summary["event_result_imported"],
        "event_result_errors": event_summary["event_result_errors"],
        "provider_rows_imported": provider_rows_imported,
        "local_history_imported": history_imported,
    }


def _resolve_pending_from_event_provider(match_date: str) -> dict:
    matches = _pending_result_matches(match_date)
    event_id_tracked = len([row for row in matches if row["market_event_id"]])
    imported = 0
    errors = []
    try:
        from tennis_wc.sources.providers import get_odds_provider

        provider = get_odds_provider()
    except Exception as exc:
        return {
            "event_id_tracked": event_id_tracked,
            "event_result_imported": 0,
            "event_result_errors": [{"source": "odds_provider", "error": str(exc)}],
        }
    fetch_event_result = getattr(provider, "fetch_event_result", None)
    if not callable(fetch_event_result):
        return {"event_id_tracked": event_id_tracked, "event_result_imported": 0, "event_result_errors": []}

    from tennis_wc.store.markets import bookmaker_event_for_match

    with get_connection() as conn:
        event_refs = {row['id']: bookmaker_event_for_match(conn, row['id'], provider.provider_name)
                      for row in matches}
    event_id_tracked = sum(bool(ref) for ref in event_refs.values())
    for match in matches:
        event_id = event_refs[match['id']]
        if not event_id:
            continue
        try:
            result = fetch_event_result(str(event_id))
        except Exception as exc:
            errors.append({"event_id": str(event_id), "error": str(exc)})
            continue
        if not isinstance(result, dict) or not result.get("winner_name"):
            continue
        inserted = _insert_resolved_result_from_names(
            dict(match),
            result.get("winner_name"),
            result.get("loser_name") or _opponent_from_winner(dict(match), result.get("winner_name")),
            "sportsbook_event_resolver",
            {"source": "sportsbook_event_resolver", "event_id": str(event_id), "raw": result},
        )
        imported += inserted
    return {"event_id_tracked": event_id_tracked, "event_result_imported": imported, "event_result_errors": errors}


def _resolve_pending_from_provider_rows(match_date: str, rows: list[dict], provider_name: str) -> int:
    winners = [row for row in rows if row.get("won")]
    if not winners:
        return 0
    imported = 0
    for match in _pending_result_matches(match_date):
        best_row = None
        best_score = 0.0
        best_direction = None
        for row in winners:
            score, direction = match_pair_score(
                row.get("player_name"),
                row.get("opponent_name"),
                match["player_a_name"],
                match["player_b_name"],
            )
            if score > best_score:
                best_row = row
                best_score = score
                best_direction = direction
        if not best_row or best_score < MIN_RESULT_MATCH_SCORE:
            continue
        winner_name = match["player_a_name"] if best_direction == "direct" else match["player_b_name"]
        loser_name = match["player_b_name"] if best_direction == "direct" else match["player_a_name"]
        # Same scoreline parser the ordinary import uses, so a resolved match
        # can settle games/sets props and not just the match winner.
        scoreline_json = _result_score_json(best_row, dict(match))
        imported += _insert_resolved_result_from_names(
            dict(match),
            winner_name,
            loser_name,
            f"{provider_name}_resolver",
            {
                "source": f"{provider_name}_resolver",
                "score": round(best_score, 4),
                "provider_match_date": best_row.get("match_date"),
                "provider_match_id": best_row.get("id"),
            },
            json.loads(scoreline_json) if scoreline_json else None,
        )
    return imported


def _resolve_pending_from_player_history(match_date: str) -> int:
    matches = _pending_result_matches(match_date)
    if not matches:
        return 0
    dates = _nearby_result_dates(match_date)
    placeholders = ",".join("?" for _ in dates)
    with get_connection() as conn:
        history_rows = conn.execute(
            f"""
            SELECT h.*, p.name AS player_name, op.name AS opponent_name
            FROM player_match_history h
            JOIN players p ON p.id = h.player_id
            JOIN players op ON op.id = h.opponent_id
            WHERE h.match_date IN ({placeholders})
              AND h.won = 1 AND {active_clause("h")}
            """,
            dates,
        ).fetchall()
    imported = 0
    for match in matches:
        best_row = None
        best_score = 0.0
        best_direction = None
        for row in history_rows:
            score, direction = match_pair_score(
                row["player_name"],
                row["opponent_name"],
                match["player_a_name"],
                match["player_b_name"],
            )
            if score > best_score:
                best_row = row
                best_score = score
                best_direction = direction
        if not best_row or best_score < MIN_RESULT_MATCH_SCORE:
            continue
        winner_name = match["player_a_name"] if best_direction == "direct" else match["player_b_name"]
        loser_name = match["player_b_name"] if best_direction == "direct" else match["player_a_name"]
        imported += _insert_resolved_result_from_names(
            dict(match),
            winner_name,
            loser_name,
            "local_history_resolver",
            {
                "source": "local_history_resolver",
                "score": round(best_score, 4),
                "history_match_date": best_row["match_date"],
                "history_provider": best_row["source_provider"],
                "history_provider_match_id": best_row["provider_match_id"],
            },
        )
    return imported


def _pending_result_matches(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT m.id, m.market_event_id, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM matches m
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            WHERE m.match_date = ?
              -- A winner-only row must not lock the match out of later
              -- resolution: the prop settlers need games/sets, so a result
              -- without a scoreline is unfinished work, not done work.
              AND NOT EXISTS (
                  SELECT 1 FROM match_results r
                  WHERE r.match_id = m.id
                    AND (
                        json_extract(r.score_json, '$.player_a_games') IS NOT NULL
                        OR json_extract(r.score_json, '$.player_a_sets') IS NOT NULL
                    )
              )
              AND EXISTS (SELECT 1 FROM prop_tracker p
                          WHERE p.match_id = m.id AND p.result_status = 'PENDING')
            """,
            (match_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def _insert_resolved_result_from_names(
    match: dict,
    winner_name: str | None,
    loser_name: str | None,
    source_provider: str,
    score_payload: dict,
    scoreline: dict | None = None,
) -> int:
    """Record a resolved result, with the scoreline when the source carries one.

    A winner alone settles nothing on the prop side: every games/sets/first-set
    settler in :mod:`tennis_wc.props.settlement` reads ``player_a_games``,
    ``player_a_sets`` or ``sets`` out of ``score_json``.  The resolver used to
    write provenance only, so a match it "resolved" still left its props
    PENDING for ever.  ``scoreline`` must already be oriented to this match's
    player_a/player_b (``_result_score_json`` does that by name).
    """
    score, direction = match_pair_score(winner_name, loser_name, match["player_a_name"], match["player_b_name"])
    if score < MIN_RESULT_MATCH_SCORE or direction not in {"direct", "swapped"}:
        return 0
    winner_player_id = match["player_a_id"] if direction == "direct" else match["player_b_id"]
    now = utc_now()
    payload = score_payload | {"resolver_pair_score": round(score, 4)}
    if scoreline:
        payload = scoreline | payload
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO match_results (match_id, winner_player_id, score_json, source_provider, raw_response_id, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            ON CONFLICT(match_id, source_provider) DO UPDATE SET
                winner_player_id = excluded.winner_player_id,
                score_json = COALESCE(excluded.score_json, match_results.score_json),
                created_at = excluded.created_at
            """,
            (match["id"], winner_player_id, json.dumps(payload, sort_keys=True), source_provider, now),
        )
    return 1


def _opponent_from_winner(match: dict, winner_name: str | None) -> str | None:
    if same_player_name(winner_name, match.get("player_a_name")):
        return match.get("player_b_name")
    if same_player_name(winner_name, match.get("player_b_name")):
        return match.get("player_a_name")
    return None


def _nearby_result_dates(match_date: str) -> list[str]:
    current = date.fromisoformat(match_date)
    return [(current + timedelta(days=offset)).isoformat() for offset in (0, -1, 1)]


def _result_score_json(row: dict, match: dict) -> str | None:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    payload = _score_from_bsd_raw(raw) or _score_from_espn_raw(raw, match)
    if not payload:
        return None
    return json.dumps(payload, sort_keys=True)


def _score_from_bsd_raw(raw: dict) -> dict | None:
    sets_detail = raw.get("sets_detail")
    if not isinstance(sets_detail, list) or not sets_detail:
        return None
    sets = []
    for item in sets_detail:
        if not isinstance(item, dict) or item.get("p1") is None or item.get("p2") is None:
            continue
        sets.append({"player_a_games": int(item["p1"]), "player_b_games": int(item["p2"])})
    if not sets:
        return None
    payload = _score_summary(sets, "bsd_sets_detail")
    payload.update(_bsd_stat_payload(raw))
    return payload


def _bsd_stat_payload(raw: dict) -> dict:
    return {
        "player_a_aces": _first_int(raw, ["p1_aces", "p1_ace", "player1_aces", "player1_ace", "home_aces"]),
        "player_b_aces": _first_int(raw, ["p2_aces", "p2_ace", "player2_aces", "player2_ace", "away_aces"]),
        "player_a_double_faults": _first_int(
            raw,
            ["p1_double_faults", "p1_double_fault", "p1_df", "player1_double_faults", "player1_df", "home_double_faults"],
        ),
        "player_b_double_faults": _first_int(
            raw,
            ["p2_double_faults", "p2_double_fault", "p2_df", "player2_double_faults", "player2_df", "away_double_faults"],
        ),
    }


def _first_int(raw: dict, keys: list[str]) -> int | None:
    for key in keys:
        number = _float_or_none(raw.get(key))
        if number is not None:
            return int(number)
    return None


def _score_from_espn_raw(raw: dict, match: dict) -> dict | None:
    competitors = raw.get("competitors")
    if not isinstance(competitors, list) or len(competitors) < 2:
        return None
    player_a = _espn_competitor_for_name(competitors, match.get("player_a_name"))
    player_b = _espn_competitor_for_name(competitors, match.get("player_b_name"))
    if not player_a or not player_b:
        return None
    a_lines = _espn_linescores(player_a)
    b_lines = _espn_linescores(player_b)
    sets = []
    if a_lines and b_lines and len(a_lines) == len(b_lines):
        sets = [{"player_a_games": int(a), "player_b_games": int(b)} for a, b in zip(a_lines, b_lines)]
    if sets:
        payload = _score_summary(sets, "espn_linescores")
        payload.update(_espn_stat_payload(player_a, player_b))
        return payload
    player_a_sets = _float_or_none(player_a.get("score"))
    player_b_sets = _float_or_none(player_b.get("score"))
    if player_a_sets is None or player_b_sets is None:
        return None
    payload = {
        "player_a_sets": int(player_a_sets),
        "player_b_sets": int(player_b_sets),
        "total_sets": int(player_a_sets + player_b_sets),
        "player_a_games": None,
        "player_b_games": None,
        "sets": [],
        "source": "espn_set_score",
    }
    payload.update(_espn_stat_payload(player_a, player_b))
    return payload


def _score_summary(sets: list[dict], source: str) -> dict:
    player_a_sets = sum(1 for item in sets if int(item["player_a_games"]) > int(item["player_b_games"]))
    player_b_sets = sum(1 for item in sets if int(item["player_b_games"]) > int(item["player_a_games"]))
    payload = {
        "player_a_sets": player_a_sets,
        "player_b_sets": player_b_sets,
        "total_sets": player_a_sets + player_b_sets,
        "player_a_games": sum(int(item["player_a_games"]) for item in sets),
        "player_b_games": sum(int(item["player_b_games"]) for item in sets),
        "sets": sets,
        "source": source,
    }
    # A completed match cannot end level on sets. ESPN reports a retirement or
    # an abandoned match with both players on one set and no marker, and those
    # were stored as finished: 9 such results survived at this source after the
    # TennisMyLife side was fixed. Settlement voids on the flag rather than
    # grading a scoreline that never happened.
    if player_a_sets == player_b_sets:
        payload["retired"] = True
        payload["incomplete_scoreline"] = True
    return payload


def _espn_competitor_for_name(competitors: list[dict], name: str | None) -> dict | None:
    for competitor in competitors:
        athlete = competitor.get("athlete") or {}
        if same_player_name(athlete.get("displayName"), name) or same_player_name(athlete.get("shortName"), name):
            return competitor
    return None


def _espn_stat_payload(player_a: dict, player_b: dict) -> dict:
    return {
        "player_a_aces": _espn_stat_value(player_a, {"aces", "ace"}),
        "player_b_aces": _espn_stat_value(player_b, {"aces", "ace"}),
        "player_a_double_faults": _espn_stat_value(player_a, {"double faults", "double_faults", "doublefaults"}),
        "player_b_double_faults": _espn_stat_value(player_b, {"double faults", "double_faults", "doublefaults"}),
    }


def _espn_stat_value(competitor: dict, names: set[str]) -> int | None:
    stats = competitor.get("statistics") or competitor.get("stats") or []
    if not isinstance(stats, list):
        return None
    for item in stats:
        if not isinstance(item, dict):
            continue
        label = str(item.get("name") or item.get("displayName") or item.get("label") or "").lower().replace("_", " ")
        if label in names:
            value = item.get("value", item.get("displayValue"))
            number = _float_or_none(value)
            return int(number) if number is not None else None
    return None


def _espn_linescores(competitor: dict) -> list[int]:
    rows = competitor.get("linescores")
    if not isinstance(rows, list):
        return []
    values = []
    for row in rows:
        value = row.get("value") if isinstance(row, dict) else None
        if value is None and isinstance(row, dict):
            value = row.get("displayValue")
        number = _float_or_none(value)
        if number is None:
            return []
        values.append(int(number))
    return values


def _match_by_names(conn, match_date: str, player_name: str, opponent_name: str):
    rows = conn.execute(
        """
        SELECT m.id, m.player_a_id, m.player_b_id, pa.name AS player_a_name, pb.name AS player_b_name
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.match_date = ?
        """,
        (match_date,),
    ).fetchall()
    best_row = None
    best_score = 0.0
    for row in rows:
        score, _direction = match_pair_score(player_name, opponent_name, row["player_a_name"], row["player_b_name"])
        if score > best_score:
            best_row = row
            best_score = score
    if best_score < MIN_RESULT_MATCH_SCORE:
        return None
    return best_row


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
