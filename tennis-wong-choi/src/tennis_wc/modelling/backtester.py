from __future__ import annotations

import json

from tennis_wc.betting.ledger import ledger_summary
from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now


def run_backtest(start_date: str, end_date: str) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, m.match_date, tl.level, tl.surface, m.round
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN tournament_levels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour
            WHERE m.match_date BETWEEN ? AND ?
              AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
            """,
            (start_date, end_date),
        ).fetchall()
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "total_predictions": len(rows),
        "total_bets": sum(1 for row in rows if row["decision"] == "BET"),
        "watchlist": sum(1 for row in rows if row["decision"] == "WATCHLIST"),
        "no_bet": sum(1 for row in rows if row["decision"] == "NO_BET"),
        "average_edge": _avg(row["edge"] for row in rows),
        "ledger": ledger_summary(),
        "performance_by_tournament_level": _group(rows, "level"),
        "performance_by_round": _group(rows, "round"),
        "performance_by_surface": _group(rows, "surface"),
        "note": "ROI and win rate require settled bet ledger rows. Feature-bucket ROI starts after larger historical prediction sets exist.",
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO backtest_runs (start_date, end_date, summary_json, created_at) VALUES (?, ?, ?, ?)",
            (start_date, end_date, json.dumps(summary, sort_keys=True), utc_now()),
        )
    return summary


def _avg(values) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _group(rows, key: str) -> list[dict]:
    buckets: dict[str, list] = {}
    for row in rows:
        buckets.setdefault(str(row[key]), []).append(row)
    return [
        {
            key: bucket,
            "predictions": len(items),
            "bets": sum(1 for item in items if item["decision"] == "BET"),
            "average_edge": _avg(item["edge"] for item in items),
        }
        for bucket, items in sorted(buckets.items())
    ]
