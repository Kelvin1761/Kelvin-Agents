"""Prop settlement: log surfaced props, grade them vs actual outcomes, report ROI.

This is the load-bearing half of the "ship it, but validate live" plan. Because
prop ROI cannot yet be backtested (odds x outcome overlap is ~16 matches), every
prop the engine surfaces is recorded here as PENDING and graded after the match,
so real ROI accumulates from day one.

Actual total match aces are read from (in priority order):
  1. match_results.score_json player_a_aces + player_b_aces (live results feed)
  2. player_match_history paired rows for the same match (Sackmann backfill)
"""
from __future__ import annotations

import json

from tennis_wc.features.common import utc_now


def actual_total_aces(conn, match_id: int) -> float | None:
    """Actual total match aces for a match, or None if not yet settleable."""
    row = conn.execute(
        "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
        (match_id,),
    ).fetchone()
    if row and row["score_json"]:
        try:
            s = json.loads(row["score_json"])
            aa, ab = s.get("player_a_aces"), s.get("player_b_aces")
            if aa is not None and ab is not None:
                return float(aa) + float(ab)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    # fallback: paired player_match_history rows for this match's two players+date
    meta = conn.execute(
        "SELECT player_a_id, player_b_id, match_date FROM matches WHERE id = ?",
        (match_id,),
    ).fetchone()
    if not meta:
        return None
    day = (meta["match_date"] or "")[:10]
    rows = conn.execute(
        """
        SELECT player_id, ace_count FROM player_match_history
        WHERE ace_count IS NOT NULL AND substr(match_date,1,10) = ?
          AND player_id IN (?, ?) AND opponent_id IN (?, ?)
        """,
        (day, meta["player_a_id"], meta["player_b_id"], meta["player_a_id"], meta["player_b_id"]),
    ).fetchall()
    seen = {r["player_id"]: float(r["ace_count"]) for r in rows}
    if meta["player_a_id"] in seen and meta["player_b_id"] in seen:
        return seen[meta["player_a_id"]] + seen[meta["player_b_id"]]
    return None


def record_prop(conn, *, match_id: int, match_date: str, match_label: str,
                market_key: str, line: float, selection: str, decimal_odds: float,
                model_prob: float, market_prob_fair: float, blended_prob: float,
                edge: float, ev: float, predicted_mean: float,
                stake_units: float, is_value: bool) -> None:
    """Upsert a surfaced prop as PENDING (idempotent per match+market+line)."""
    prop_key = f"{match_id}|{market_key}|{selection}"
    now = utc_now()
    conn.execute(
        """
        INSERT INTO prop_tracker (
            prop_key, match_id, match_date, match_label, market_key, line, selection,
            decimal_odds, model_prob, market_prob_fair, blended_prob, edge, ev,
            predicted_mean, stake_units, is_value, result_status,
            profit_loss_units, actual_value, recorded_at, updated_at, settled_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING', NULL, NULL, ?, ?, NULL)
        ON CONFLICT(prop_key) DO UPDATE SET
            decimal_odds=excluded.decimal_odds, model_prob=excluded.model_prob,
            market_prob_fair=excluded.market_prob_fair, blended_prob=excluded.blended_prob,
            edge=excluded.edge, ev=excluded.ev, predicted_mean=excluded.predicted_mean,
            stake_units=excluded.stake_units, is_value=excluded.is_value,
            updated_at=excluded.updated_at
        WHERE prop_tracker.result_status = 'PENDING'
        """,
        (prop_key, match_id, match_date, match_label, market_key, line, selection,
         decimal_odds, model_prob, market_prob_fair, blended_prob, edge, ev,
         predicted_mean, stake_units, 1 if is_value else 0, now, now),
    )


def settle_props(conn) -> dict:
    """Grade all PENDING props whose match is now settleable. 'N+' wins if
    actual total aces >= line. Flat 1u accounting on stake_units."""
    pending = conn.execute(
        "SELECT * FROM prop_tracker WHERE result_status = 'PENDING'"
    ).fetchall()
    graded = 0
    for p in pending:
        actual = actual_total_aces(conn, p["match_id"])
        if actual is None:
            continue
        won = actual >= p["line"]
        stake = p["stake_units"] or 0.0
        pl = stake * (p["decimal_odds"] - 1.0) if won else -stake
        conn.execute(
            """
            UPDATE prop_tracker
               SET result_status = ?, actual_value = ?, profit_loss_units = ?,
                   settled_at = ?, updated_at = ?
             WHERE id = ?
            """,
            ("WIN" if won else "LOSS", actual, round(pl, 4), utc_now(), utc_now(), p["id"]),
        )
        graded += 1
    conn.commit()
    return {"graded": graded, "still_pending": len(pending) - graded}


def prop_roi_report(conn, value_only: bool = False) -> dict:
    """Realised ROI over settled props. value_only restricts to is_value picks."""
    where = "result_status IN ('WIN','LOSS')"
    if value_only:
        where += " AND is_value = 1"
    rows = conn.execute(f"SELECT * FROM prop_tracker WHERE {where}").fetchall()
    n = len(rows)
    if not n:
        return {"settled": 0, "wins": 0, "hit_rate": None, "staked": 0.0, "pnl": 0.0, "roi": None}
    wins = sum(1 for r in rows if r["result_status"] == "WIN")
    staked = sum((r["stake_units"] or 0.0) for r in rows)
    pnl = sum((r["profit_loss_units"] or 0.0) for r in rows)
    return {
        "settled": n, "wins": wins, "hit_rate": round(wins / n, 4),
        "staked": round(staked, 2), "pnl": round(pnl, 3),
        "roi": round(pnl / staked, 4) if staked else None,
    }
