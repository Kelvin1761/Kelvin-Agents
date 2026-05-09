from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import avg, parse_date, rate, utc_now
from tennis_wc.features.opponent_rank_buckets import get_opponent_rank_at_match_date
from tennis_wc.features.round_performance import normalise_round


def is_big_match(match: dict, opponent_rank: int | None, opponent_elo: float | None = None) -> bool:
    """
    Big match if Grand Slam, Masters/WTA 1000 QF+, any final, Top 10 opponent,
    both players Top 20 where data exists, or men's BO5.
    """
    level = match.get("tournament_level") or match.get("level")
    round_code = normalise_round(match.get("round", ""))
    player_rank = match.get("player_rank")
    return any(
        [
            level == "GRAND_SLAM",
            level in {"ATP_1000", "WTA_1000"} and round_code in {"QF", "SF", "F"},
            round_code == "F",
            opponent_rank is not None and opponent_rank <= 10,
            player_rank is not None and player_rank <= 20 and opponent_rank is not None and opponent_rank <= 20,
            match.get("format") == "BO5",
        ]
    )


def calculate_big_match_stats(
    player_id: int,
    surface: str | None,
    as_of_date: date,
    time_window: str,
) -> dict:
    start = "0001-01-01"
    if time_window == "LAST_52_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 364).isoformat()
    if time_window == "LAST_26_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 182).isoformat()
    query = "SELECT * FROM player_match_history WHERE player_id = ? AND match_date >= ? AND match_date < ?"
    params: list = [player_id, start, as_of_date.isoformat()]
    if surface:
        query += " AND lower(surface) = lower(?)"
        params.append(surface)
    with get_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    big_rows = []
    ranks = []
    for row in rows:
        rank = get_opponent_rank_at_match_date(row["opponent_id"], parse_date(row["match_date"]))
        if is_big_match(row, rank, row.get("opponent_elo")):
            big_rows.append(row)
            ranks.append(rank)
    matches = len(big_rows)
    wins = sum(1 for row in big_rows if row["won"])
    result = {
        "matches": matches,
        "wins": wins,
        "losses": matches - wins,
        "win_rate": rate(wins, matches),
        "avg_opponent_rank": avg(ranks),
        "avg_opponent_elo": avg(row.get("opponent_elo") for row in big_rows),
        "deciding_set_win_rate": rate(sum(1 for row in big_rows if row.get("deciding_set_won")), matches),
        "tiebreak_win_rate": rate(sum(1 for row in big_rows if row.get("tiebreak_won")), matches),
        "sample_size": matches,
        "warnings": ["low_sample"] if matches < 10 else [],
    }
    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO player_big_match_stats (
                player_id, tour, surface, time_window, matches, wins, losses,
                win_rate, avg_opponent_rank, avg_opponent_elo, deciding_set_win_rate,
                tiebreak_win_rate, calculated_at, created_at, updated_at
            )
            VALUES (?, COALESCE((SELECT tour FROM players WHERE id = ?), 'ATP'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, tour, surface, time_window) DO UPDATE SET
                matches = excluded.matches,
                wins = excluded.wins,
                losses = excluded.losses,
                win_rate = excluded.win_rate,
                avg_opponent_rank = excluded.avg_opponent_rank,
                avg_opponent_elo = excluded.avg_opponent_elo,
                deciding_set_win_rate = excluded.deciding_set_win_rate,
                tiebreak_win_rate = excluded.tiebreak_win_rate,
                calculated_at = excluded.calculated_at,
                updated_at = excluded.updated_at
            """,
            (
                player_id,
                player_id,
                surface,
                time_window,
                matches,
                wins,
                matches - wins,
                result["win_rate"],
                result["avg_opponent_rank"],
                result["avg_opponent_elo"],
                result["deciding_set_win_rate"],
                result["tiebreak_win_rate"],
                now,
                now,
                now,
            ),
        )
    return result
