from __future__ import annotations

import json
from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now


def run_backtest(start_date: str, end_date: str) -> dict:
    start_day,end_day=date.fromisoformat(start_date),date.fromisoformat(end_date)
    if start_day > end_day:
        raise ValueError("start_date must not be after end_date")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, m.match_date, tl.level, tl.surface, m.round
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            LEFT JOIN tournament_levels tl ON tl.id = (
                SELECT MAX(x.id) FROM tournament_levels x
                WHERE x.tournament_id=m.tournament_id AND x.tour=m.tour
            )
            WHERE m.match_date BETWEEN ? AND ?
              AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
            """,
            (start_date, end_date),
        ).fetchall()
        ledger_rows = conn.execute(
            """
            SELECT b.status, COUNT(*) AS bets, SUM(b.stake_units) AS stake,
                   SUM(COALESCE(b.profit_loss_units,0)) AS profit
            FROM bet_ledger b JOIN matches m ON m.id=b.match_id
            WHERE m.match_date BETWEEN ? AND ?
            GROUP BY b.status ORDER BY b.status
            """, (start_date,end_date),
        ).fetchall()
    settled_stake = sum(float(row["stake"] or 0) for row in ledger_rows
                        if row["status"] in {"WON", "LOST"})
    profit = sum(float(row["profit"] or 0) for row in ledger_rows
                 if row["status"] in {"WON", "LOST"})
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "total_predictions": len(rows),
        "total_bets": sum(1 for row in rows if row["decision"] == "BET"),
        "watchlist": sum(1 for row in rows if row["decision"] == "WATCHLIST"),
        "no_bet": sum(1 for row in rows if row["decision"] == "NO_BET"),
        "average_edge": _avg(row["edge"] for row in rows),
        "ledger": {
            "total_bets": sum(int(row["bets"]) for row in ledger_rows),
            "total_stake_units": sum(float(row["stake"] or 0) for row in ledger_rows),
            "settled_stake_units": settled_stake,
            "profit_loss_units": profit,
            "roi": profit / settled_stake if settled_stake else None,
            "by_status": [dict(row) for row in ledger_rows],
        },
        "performance_by_tournament_level": _group(rows, "level"),
        "performance_by_round": _group(rows, "round"),
        "performance_by_surface": _group(rows, "surface"),
        "note": "Prediction counts describe stored latest forecasts, including rebuilds; they are not point-in-time model evidence. Ledger ROI uses only recorded WON/LOST bets in this date range and is not a simulated strategy return.",
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
