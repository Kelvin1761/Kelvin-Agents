from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import avg, rate, shrink_rate, utc_now
from tennis_wc.features.opponent_rank_buckets import get_opponent_rank_at_match_date
from tennis_wc.features.common import parse_date


def _time_filter(as_of_date: date, time_window: str) -> tuple[str, str]:
    if time_window == "CAREER":
        return "0001-01-01", as_of_date.isoformat()
    days = 364 if time_window == "LAST_52_WEEKS" else 182
    return date.fromordinal(as_of_date.toordinal() - days).isoformat(), as_of_date.isoformat()


def _rows(player_id: int, tournament_level: str, surface: str | None, as_of_date: date, time_window: str) -> list[dict]:
    start, end = _time_filter(as_of_date, time_window)
    query = """
        SELECT *
        FROM player_match_history
        WHERE player_id = ? AND upper(tournament_level) = upper(?) AND match_date >= ? AND match_date < ?
    """
    params: list = [player_id, tournament_level, start, end]
    if surface:
        query += " AND lower(surface) = lower(?)"
        params.append(surface)
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def _summarise(rows: list[dict]) -> dict:
    matches = len(rows)
    wins = sum(1 for row in rows if row["won"])
    win_rate = rate(wins, matches)
    ranks = [
        get_opponent_rank_at_match_date(row["opponent_id"], parse_date(row["match_date"]))
        for row in rows
    ]
    return {
        "matches": matches,
        "wins": wins,
        "losses": matches - wins,
        "win_rate": win_rate,
        "hold_rate": avg(row.get("hold_rate") for row in rows),
        "break_rate": avg(row.get("break_rate") for row in rows),
        "first_serve_points_won_pct": avg(row.get("first_serve_points_won_pct") for row in rows),
        "second_serve_points_won_pct": avg(row.get("second_serve_points_won_pct") for row in rows),
        "return_points_won_pct": avg(row.get("return_points_won_pct") for row in rows),
        "tiebreak_win_rate": rate(sum(1 for row in rows if row.get("tiebreak_won")), matches),
        "deciding_set_win_rate": rate(sum(1 for row in rows if row.get("deciding_set_won")), matches),
        "avg_opponent_rank": avg(ranks),
        "avg_opponent_elo": avg(row.get("opponent_elo") for row in rows),
        "sample_size": matches,
    }


def calculate_tournament_level_stats(
    player_id: int,
    tournament_level: str,
    surface: str | None,
    as_of_date: date,
    time_window: str,
) -> dict:
    """
    Calculate player performance in tournament level before the match date.
    """
    if tournament_level == "UNKNOWN":
        return {
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "shrinked_win_rate": None,
            "sample_size": 0,
            "warnings": ["unknown_tournament_level"],
        }

    surface_rows = _rows(player_id, tournament_level, surface, as_of_date, time_window)
    all_surface_rows = _rows(player_id, tournament_level, None, as_of_date, time_window)
    selected_rows = surface_rows if len(surface_rows) >= 10 else all_surface_rows
    summary = _summarise(selected_rows)
    prior = _summarise(all_surface_rows)["win_rate"] or 0.5
    summary["shrinked_win_rate"] = (
        shrink_rate(summary["win_rate"], summary["sample_size"], prior)
        if summary["win_rate"] is not None
        else None
    )
    summary["warnings"] = []
    if len(surface_rows) < 10 and surface:
        summary["warnings"].append("surface_sample_below_10_blended_all_surface")
    if summary["sample_size"] < 10:
        summary["warnings"].append("low_sample")

    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO player_tournament_level_stats (
                player_id, tour, surface, tournament_level, time_window, matches,
                wins, losses, win_rate, shrinked_win_rate, hold_rate, break_rate,
                first_serve_points_won_pct, second_serve_points_won_pct,
                return_points_won_pct, tiebreak_win_rate, deciding_set_win_rate,
                avg_opponent_rank, avg_opponent_elo, calculated_at, created_at, updated_at
            )
            VALUES (?, COALESCE((SELECT tour FROM players WHERE id = ?), 'ATP'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, tour, surface, tournament_level, time_window) DO UPDATE SET
                matches = excluded.matches,
                wins = excluded.wins,
                losses = excluded.losses,
                win_rate = excluded.win_rate,
                shrinked_win_rate = excluded.shrinked_win_rate,
                hold_rate = excluded.hold_rate,
                break_rate = excluded.break_rate,
                first_serve_points_won_pct = excluded.first_serve_points_won_pct,
                second_serve_points_won_pct = excluded.second_serve_points_won_pct,
                return_points_won_pct = excluded.return_points_won_pct,
                tiebreak_win_rate = excluded.tiebreak_win_rate,
                deciding_set_win_rate = excluded.deciding_set_win_rate,
                avg_opponent_rank = excluded.avg_opponent_rank,
                avg_opponent_elo = excluded.avg_opponent_elo,
                calculated_at = excluded.calculated_at,
                updated_at = excluded.updated_at
            """,
            (
                player_id,
                player_id,
                surface,
                tournament_level,
                time_window,
                summary["matches"],
                summary["wins"],
                summary["losses"],
                summary["win_rate"],
                summary["shrinked_win_rate"],
                summary.get("hold_rate"),
                summary.get("break_rate"),
                summary.get("first_serve_points_won_pct"),
                summary.get("second_serve_points_won_pct"),
                summary.get("return_points_won_pct"),
                summary.get("tiebreak_win_rate"),
                summary.get("deciding_set_win_rate"),
                summary.get("avg_opponent_rank"),
                summary.get("avg_opponent_elo"),
                now,
                now,
                now,
            ),
        )
    return summary
