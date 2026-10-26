"""Recorded pre-match forecasts and outcomes for offline model measurements.

Never substitute a post-start rebuild for a forecast. Multiple providers of
one result are one observation; conflicting winners are not usable evidence.
"""
from __future__ import annotations

import json


def prematch_outcomes(conn, *, before: str | None = None,
                      since: str | None = None) -> list[dict]:
    """Earliest valid pre-start forecast per fixture, with one agreed outcome.

    ``before`` is also the knowledge cutoff: a prediction or result collected
    after that UTC day began cannot train a historical calibration. Missing or
    invalid start/write timestamps are excluded, rather than guessed from dates.
    """
    date_filter = ""
    params: list = []
    if before:
        date_filter += " AND m.match_date < ?"
        params.append(before)
    if since:
        date_filter += " AND m.match_date >= ?"
        params.append(since)
    forecast_filter = ""
    if before:
        forecast_filter = " AND julianday(p.created_at) < julianday(?)"
        params.append(before)
    forecasts = conn.execute(
        f"""
        WITH first_forecasts AS (
            SELECT x.match_id, MIN(x.id) AS prediction_id
            FROM predictions x JOIN matches m ON m.id=x.match_id
            WHERE x.selection_player_id IN (m.player_a_id,m.player_b_id)
              AND x.model_probability > 0 AND x.model_probability < 1
              AND julianday(x.created_at) < julianday(m.start_time_utc)
            GROUP BY x.match_id
        )
        SELECT m.id AS match_id, m.match_date, m.start_time_utc,
               m.player_a_id, m.player_b_id, m.tour, m.tournament_id, m.round,
               p.id AS prediction_id, p.created_at AS prediction_created_at,
               p.pricing_json,
               CASE WHEN p.selection_player_id = m.player_a_id
                    THEN p.model_probability ELSE 1.0-p.model_probability END AS model_p
        FROM first_forecasts f JOIN predictions p ON p.id=f.prediction_id
        JOIN matches m ON m.id=f.match_id
        WHERE m.player_a_id <> m.player_b_id {date_filter} {forecast_filter}
        ORDER BY m.match_date,m.id
        """, tuple(params),
    ).fetchall()
    result_filter = ""
    result_params: tuple = ()
    if before:
        result_filter = " AND julianday(created_at) < julianday(?)"
        result_params = (before,)
    results: dict[int, list] = {}
    for row in conn.execute(
        "SELECT id,match_id,winner_player_id,score_json,created_at "
        "FROM match_results WHERE winner_player_id IS NOT NULL"
        + result_filter + " ORDER BY id", result_params,
    ):
        results.setdefault(row["match_id"], []).append(row)
    out = []
    for forecast in forecasts:
        candidates = results.get(forecast["match_id"], [])
        winners = {row["winner_player_id"] for row in candidates}
        if len(winners) != 1:
            continue
        winner = next(iter(winners))
        if winner not in (forecast["player_a_id"], forecast["player_b_id"]):
            continue
        invalid = False
        for result in candidates:
            try:
                score = json.loads(result["score_json"] or "{}")
            except (TypeError, ValueError):
                invalid = True
                break
            if not isinstance(score, dict):
                invalid = True
                break
            a_sets, b_sets = score.get("player_a_sets"), score.get("player_b_sets")
            if (any(score.get(key) for key in ("retired", "walkover", "incomplete_scoreline"))
                    or (a_sets is not None and b_sets is not None and a_sets == b_sets)):
                invalid = True
                break
        if invalid:
            continue
        out.append({
            **dict(forecast), "winner_player_id": winner,
            "result_rows": [dict(row) for row in candidates],
        })
    return out


def earliest_match_odds(conn) -> dict[int, dict]:
    """One opening pair from MIN(id), only when captured before the start.

    Taking MIN(odds) independently per player manufactures a pair that may
    never have existed and can include in-running prices. No later fallback is
    allowed when the first snapshot itself is untimeable or post-start.
    """
    return {
        row["match_id"]: dict(row)
        for row in conn.execute(
            """
            SELECT o.* FROM odds_snapshots o JOIN matches m ON m.id=o.match_id
            WHERE o.id IN (SELECT MIN(id) FROM odds_snapshots GROUP BY match_id)
              AND julianday(o.fetched_at) < julianday(m.start_time_utc)
              AND o.player_a_odds > 1 AND o.player_b_odds > 1
            """
        )
    }
