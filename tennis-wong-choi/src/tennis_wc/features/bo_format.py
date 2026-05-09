from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import parse_date, rate, utc_now
from tennis_wc.features.opponent_rank_buckets import get_opponent_rank_at_match_date


def detect_match_format(match: dict) -> str:
    """
    Return BO3 or BO5. BO5 applies to men's Grand Slam main draw singles.
    """
    if match.get("tour") == "ATP" and match.get("level") == "GRAND_SLAM":
        return "BO5"
    return "BO3"


def calculate_bo_format_stats(
    player_id: int,
    format: str,
    surface: str | None,
    as_of_date: date,
    time_window: str,
) -> dict:
    if format == "BO5":
        with get_connection() as conn:
            tour = conn.execute("SELECT tour FROM players WHERE id = ?", (player_id,)).fetchone()
        if tour and tour["tour"] == "WTA":
            return {"format": "BO5", "value": None, "warnings": ["bo5_not_applicable_wta"]}

    start = "0001-01-01"
    if time_window == "LAST_52_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 364).isoformat()
    if time_window == "LAST_26_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 182).isoformat()
    query = "SELECT * FROM player_match_history WHERE player_id = ? AND format = ? AND match_date >= ? AND match_date < ?"
    params: list = [player_id, format, start, as_of_date.isoformat()]
    if surface:
        query += " AND lower(surface) = lower(?)"
        params.append(surface)
    with get_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    matches = len(rows)
    wins = sum(1 for row in rows if row["won"])
    top50_rows = [
        row
        for row in rows
        if (get_opponent_rank_at_match_date(row["opponent_id"], parse_date(row["match_date"])) or 9999) <= 50
    ]
    deciding_rows = [row for row in rows if row.get("deciding_set_won") is not None]
    comeback_rows = [row for row in rows if row.get("lost_first_set")]
    result = {
        "format": format,
        "matches": matches,
        "wins": wins,
        "losses": matches - wins,
        "win_rate": rate(wins, matches),
        "vs_top_50_matches": len(top50_rows),
        "vs_top_50_wins": sum(1 for row in top50_rows if row["won"]),
        "vs_top_50_win_rate": rate(sum(1 for row in top50_rows if row["won"]), len(top50_rows)),
        "deciding_set_matches": len(deciding_rows),
        "deciding_set_wins": sum(1 for row in deciding_rows if row.get("deciding_set_won")),
        "deciding_set_win_rate": rate(sum(1 for row in deciding_rows if row.get("deciding_set_won")), len(deciding_rows)),
        "comeback_after_losing_first_set_matches": len(comeback_rows),
        "comeback_after_losing_first_set_wins": sum(1 for row in comeback_rows if row.get("comeback_after_losing_first_set")),
        "comeback_after_losing_first_set_rate": rate(
            sum(1 for row in comeback_rows if row.get("comeback_after_losing_first_set")), len(comeback_rows)
        ),
        "warnings": ["low_sample"] if matches < 10 else [],
    }
    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO player_bo_format_stats (
                player_id, tour, surface, format, time_window, matches, wins, losses,
                win_rate, vs_top_50_matches, vs_top_50_wins, vs_top_50_win_rate,
                deciding_set_matches, deciding_set_wins, deciding_set_win_rate,
                comeback_after_losing_first_set_matches, comeback_after_losing_first_set_wins,
                comeback_after_losing_first_set_rate, calculated_at, created_at, updated_at
            )
            VALUES (?, COALESCE((SELECT tour FROM players WHERE id = ?), 'ATP'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, tour, surface, format, time_window) DO UPDATE SET
                matches = excluded.matches,
                wins = excluded.wins,
                losses = excluded.losses,
                win_rate = excluded.win_rate,
                vs_top_50_matches = excluded.vs_top_50_matches,
                vs_top_50_wins = excluded.vs_top_50_wins,
                vs_top_50_win_rate = excluded.vs_top_50_win_rate,
                deciding_set_matches = excluded.deciding_set_matches,
                deciding_set_wins = excluded.deciding_set_wins,
                deciding_set_win_rate = excluded.deciding_set_win_rate,
                comeback_after_losing_first_set_matches = excluded.comeback_after_losing_first_set_matches,
                comeback_after_losing_first_set_wins = excluded.comeback_after_losing_first_set_wins,
                comeback_after_losing_first_set_rate = excluded.comeback_after_losing_first_set_rate,
                calculated_at = excluded.calculated_at,
                updated_at = excluded.updated_at
            """,
            (
                player_id,
                player_id,
                surface,
                format,
                time_window,
                result["matches"],
                result["wins"],
                result["losses"],
                result["win_rate"],
                result["vs_top_50_matches"],
                result["vs_top_50_wins"],
                result["vs_top_50_win_rate"],
                result["deciding_set_matches"],
                result["deciding_set_wins"],
                result["deciding_set_win_rate"],
                result["comeback_after_losing_first_set_matches"],
                result["comeback_after_losing_first_set_wins"],
                result["comeback_after_losing_first_set_rate"],
                now,
                now,
                now,
            ),
        )
    return result
