from __future__ import annotations

from tennis_wc.betting.clv import calculate_clv
from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now


def record_bet(prediction_id: int, odds: float, stake: float) -> int:
    prediction = _prediction(prediction_id)
    now = utc_now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bet_ledger (
                prediction_id, match_id, selection_player_id, selection_name,
                odds_taken, stake_units, status, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                prediction_id,
                prediction["match_id"],
                prediction["selection_player_id"],
                prediction["selection_name"],
                odds,
                stake,
                now,
            ),
        )
        return int(cursor.lastrowid)


def fetch_closing_odds_for_date(match_date: str) -> int:
    """
    Stage 7 MVP stores latest available odds as closing odds.
    Real providers should replace this with market-close snapshots.
    """
    now = utc_now()
    with get_connection() as conn:
        matches = conn.execute("SELECT id, market_event_id FROM matches WHERE match_date = ?", (match_date,)).fetchall()
        count = 0
        for match in matches:
            odds = conn.execute(
                """
                SELECT *
                FROM odds_snapshots
                WHERE match_id = ?
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (match["id"],),
            ).fetchone()
            if not odds:
                continue
            conn.execute(
                """
                INSERT INTO closing_odds_snapshots (
                    match_id, event_id, bookmaker, market, player_a_closing_odds,
                    player_b_closing_odds, source_provider, raw_response_id,
                    fetched_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match["id"],
                    odds["event_id"],
                    odds["bookmaker"],
                    odds["market"],
                    odds["player_a_odds"],
                    odds["player_b_odds"],
                    odds["source_provider"],
                    odds["raw_response_id"],
                    odds["fetched_at"],
                    now,
                ),
            )
            count += 1
    update_open_bets_clv()
    return count


def update_open_bets_clv() -> int:
    with get_connection() as conn:
        bets = conn.execute("SELECT * FROM bet_ledger WHERE status = 'PENDING'").fetchall()
        count = 0
        for bet in bets:
            prediction = _prediction(bet["prediction_id"])
            closing = conn.execute(
                """
                SELECT *
                FROM closing_odds_snapshots
                WHERE match_id = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (bet["match_id"],),
            ).fetchone()
            if not closing:
                continue
            closing_odds = (
                closing["player_a_closing_odds"]
                if _selection_side(prediction) == "player_a"
                else closing["player_b_closing_odds"]
            )
            clv = calculate_clv(float(bet["odds_taken"]), float(closing_odds))
            conn.execute(
                "UPDATE bet_ledger SET closing_odds = ?, clv = ? WHERE id = ?",
                (closing_odds, clv, bet["id"]),
            )
            count += 1
    return count


def settle_bets_for_date(match_date: str) -> dict:
    now = utc_now()
    settled = 0
    pending = 0
    with get_connection() as conn:
        bets = conn.execute(
            """
            SELECT b.*, r.winner_player_id
            FROM bet_ledger b
            JOIN matches m ON m.id = b.match_id
            LEFT JOIN match_results r ON r.match_id = b.match_id
            WHERE m.match_date = ? AND b.status = 'PENDING'
            """,
            (match_date,),
        ).fetchall()
        for bet in bets:
            if bet["winner_player_id"] is None:
                pending += 1
                continue
            won = bet["selection_player_id"] == bet["winner_player_id"]
            status = "WON" if won else "LOST"
            profit = bet["stake_units"] * (bet["odds_taken"] - 1) if won else -bet["stake_units"]
            conn.execute(
                """
                UPDATE bet_ledger
                SET status = ?, profit_loss_units = ?, settled_at = ?
                WHERE id = ?
                """,
                (status, profit, now, bet["id"]),
            )
            settled += 1
    return {"settled": settled, "pending_without_result": pending}


def ledger_summary() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS bets, SUM(stake_units) AS stake,
                   SUM(COALESCE(profit_loss_units, 0)) AS profit,
                   AVG(clv) AS avg_clv
            FROM bet_ledger
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
    by_status = [dict(row) for row in rows]
    total_profit = sum(float(row["profit"] or 0) for row in by_status)
    total_stake = sum(float(row["stake"] or 0) for row in by_status)
    return {
        "total_bets": sum(int(row["bets"]) for row in by_status),
        "total_stake_units": total_stake,
        "profit_loss_units": total_profit,
        "roi": total_profit / total_stake if total_stake else None,
        "by_status": by_status,
    }


def _prediction(prediction_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    if not row:
        raise ValueError(f"Prediction not found: {prediction_id}")
    return dict(row)


def _selection_side(prediction: dict) -> str:
    with get_connection() as conn:
        match = conn.execute("SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (prediction["match_id"],)).fetchone()
    if prediction["selection_player_id"] == match["player_a_id"]:
        return "player_a"
    return "player_b"
