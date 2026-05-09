from __future__ import annotations

from tennis_wc.betting.ledger import ledger_summary
from tennis_wc.database.db import get_connection


def prediction_summary() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT decision, COUNT(*) AS total, AVG(edge) AS avg_edge, AVG(stake_units) AS avg_stake
            FROM predictions
            GROUP BY decision
            ORDER BY decision
            """
        ).fetchall()
    return {
        "total_predictions": sum(int(row["total"]) for row in rows),
        "by_decision": [dict(row) for row in rows],
        "ledger": ledger_summary(),
        "note": "Calibration needs a larger settled sample.",
    }
