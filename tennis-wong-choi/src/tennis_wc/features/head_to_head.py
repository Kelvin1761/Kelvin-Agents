from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import rate


def calculate_head_to_head_stats(player_id: int, opponent_id: int, surface: str | None, as_of_date: date) -> dict:
    query = """
        SELECT *
        FROM player_match_history
        WHERE player_id = ?
          AND opponent_id = ?
          AND match_date < ?
    """
    params: list = [player_id, opponent_id, as_of_date.isoformat()]
    with get_connection() as conn:
        all_rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    surface_rows = [row for row in all_rows if surface and (row.get("surface") or "").lower() == surface.lower()]
    selected = surface_rows if len(surface_rows) >= 2 else all_rows
    wins = sum(1 for row in selected if row["won"])
    return {
        "matches": len(selected),
        "wins": wins,
        "losses": len(selected) - wins,
        "win_rate": rate(wins, len(selected)),
        "surface_matches": len(surface_rows),
        "all_surface_matches": len(all_rows),
        "sample_size": len(selected),
        "warnings": ["low_h2h_sample"] if len(selected) < 3 else [],
    }
