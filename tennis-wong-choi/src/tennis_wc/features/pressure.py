from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import rate


def calculate_pressure_stats(player_id: int, surface: str | None, as_of_date: date, time_window: str) -> dict:
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
        _ensure_pressure_columns(conn)
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]

    bp_saved = _sum(rows, "break_points_saved")
    bp_faced = _sum(rows, "break_points_faced")
    bp_converted = _sum(rows, "break_points_converted")
    bp_chances = _sum(rows, "break_points_chances")
    tiebreak_rows = [row for row in rows if row.get("tiebreak_won") is not None]
    deciding_rows = [row for row in rows if row.get("deciding_set_won") is not None]
    comeback_rows = [row for row in rows if row.get("lost_first_set")]
    score_parts = [
        value
        for value in (
            rate(bp_saved, bp_faced),
            rate(bp_converted, bp_chances),
            rate(sum(1 for row in tiebreak_rows if row.get("tiebreak_won")), len(tiebreak_rows)),
            rate(sum(1 for row in deciding_rows if row.get("deciding_set_won")), len(deciding_rows)),
            rate(sum(1 for row in comeback_rows if row.get("comeback_after_losing_first_set")), len(comeback_rows)),
        )
        if value is not None
    ]
    return {
        "matches": len(rows),
        "break_points_saved": bp_saved,
        "break_points_faced": bp_faced,
        "break_point_save_rate": rate(bp_saved, bp_faced),
        "break_points_converted": bp_converted,
        "break_points_chances": bp_chances,
        "break_point_conversion_rate": rate(bp_converted, bp_chances),
        "tiebreak_win_rate": rate(sum(1 for row in tiebreak_rows if row.get("tiebreak_won")), len(tiebreak_rows)),
        "deciding_set_win_rate": rate(sum(1 for row in deciding_rows if row.get("deciding_set_won")), len(deciding_rows)),
        "comeback_after_losing_first_set_rate": rate(
            sum(1 for row in comeback_rows if row.get("comeback_after_losing_first_set")), len(comeback_rows)
        ),
        "pressure_score": sum(score_parts) / len(score_parts) if score_parts else None,
        "sample_size": len(rows),
        "warnings": ["low_sample"] if len(rows) < 10 else [],
    }


def _sum(rows: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) if values else None


def _ensure_pressure_columns(conn) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(player_match_history)").fetchall()}
    for name, ddl in {
        "break_points_saved": "ALTER TABLE player_match_history ADD COLUMN break_points_saved REAL",
        "break_points_faced": "ALTER TABLE player_match_history ADD COLUMN break_points_faced REAL",
        "break_points_converted": "ALTER TABLE player_match_history ADD COLUMN break_points_converted REAL",
        "break_points_chances": "ALTER TABLE player_match_history ADD COLUMN break_points_chances REAL",
    }.items():
        if name not in columns:
            conn.execute(ddl)
