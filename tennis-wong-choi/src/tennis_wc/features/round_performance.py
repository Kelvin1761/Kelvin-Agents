from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import avg, parse_date, rate, shrink_rate, utc_now
from tennis_wc.features.opponent_rank_buckets import get_opponent_rank_at_match_date


ROUND_MAP = {
    "final": "F",
    "atp 500 final": "F",
    "semi final": "SF",
    "semifinal": "SF",
    "semifinals": "SF",
    "quarter final": "QF",
    "quarterfinal": "QF",
    "quarterfinals": "QF",
    "round of 16": "R16",
    "r16": "R16",
    "round of 32": "R32",
    "r32": "R32",
    "round of 64": "R64",
    "r64": "R64",
    "round of 128": "R128",
    "r128": "R128",
    "qualifying": "QUALIFYING",
}


def normalise_round(raw_round: str) -> str:
    """
    Convert API round names to standard values.
    """
    return ROUND_MAP.get(raw_round.strip().lower(), "UNKNOWN")


def calculate_round_stats(
    player_id: int,
    round_name: str,
    tournament_level: str | None,
    surface: str | None,
    as_of_date: date,
    time_window: str,
) -> dict:
    """
    Calculate round-specific player performance.
    """
    round_code = normalise_round(round_name)
    start = "0001-01-01"
    if time_window == "LAST_52_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 364).isoformat()
    if time_window == "LAST_26_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 182).isoformat()

    query = """
        SELECT *
        FROM player_match_history
        WHERE player_id = ? AND match_date >= ? AND match_date < ?
    """
    params: list = [player_id, start, as_of_date.isoformat()]
    with get_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    rows = [row for row in rows if normalise_round(row["round"]) == round_code]
    if tournament_level:
        level_rows = [row for row in rows if row["tournament_level"] == tournament_level]
        rows = level_rows or rows
    if surface:
        surface_rows = [row for row in rows if (row.get("surface") or "").lower() == surface.lower()]
        rows = surface_rows or rows

    matches = len(rows)
    wins = sum(1 for row in rows if row["won"])
    raw_rate = rate(wins, matches)
    shrinked = shrink_rate(raw_rate, matches, 0.5) if raw_rate is not None else None
    ranks = [
        get_opponent_rank_at_match_date(row["opponent_id"], parse_date(row["match_date"]))
        for row in rows
    ]
    result = {
        "round": round_code,
        "matches": matches,
        "wins": wins,
        "losses": matches - wins,
        "win_rate": raw_rate,
        "shrinked_win_rate": shrinked,
        "avg_opponent_rank": avg(ranks),
        "avg_opponent_elo": avg(row.get("opponent_elo") for row in rows),
        "tiebreak_win_rate": rate(sum(1 for row in rows if row.get("tiebreak_won")), matches),
        "deciding_set_win_rate": rate(sum(1 for row in rows if row.get("deciding_set_won")), matches),
        "sample_size": matches,
        "warnings": ["low_sample"] if matches < 10 else [],
    }

    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO player_round_stats (
                player_id, tour, surface, round, tournament_level, time_window,
                matches, wins, losses, win_rate, shrinked_win_rate,
                avg_opponent_rank, avg_opponent_elo, tiebreak_win_rate,
                deciding_set_win_rate, calculated_at, created_at, updated_at
            )
            VALUES (?, COALESCE((SELECT tour FROM players WHERE id = ?), 'ATP'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, tour, surface, round, tournament_level, time_window) DO UPDATE SET
                matches = excluded.matches,
                wins = excluded.wins,
                losses = excluded.losses,
                win_rate = excluded.win_rate,
                shrinked_win_rate = excluded.shrinked_win_rate,
                avg_opponent_rank = excluded.avg_opponent_rank,
                avg_opponent_elo = excluded.avg_opponent_elo,
                tiebreak_win_rate = excluded.tiebreak_win_rate,
                deciding_set_win_rate = excluded.deciding_set_win_rate,
                calculated_at = excluded.calculated_at,
                updated_at = excluded.updated_at
            """,
            (
                player_id,
                player_id,
                surface,
                round_code,
                tournament_level,
                time_window,
                result["matches"],
                result["wins"],
                result["losses"],
                result["win_rate"],
                result["shrinked_win_rate"],
                result["avg_opponent_rank"],
                result["avg_opponent_elo"],
                result["tiebreak_win_rate"],
                result["deciding_set_win_rate"],
                now,
                now,
                now,
            ),
        )
    return result
