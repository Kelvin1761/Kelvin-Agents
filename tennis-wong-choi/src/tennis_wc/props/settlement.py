"""Prop settlement + results review.

Load-bearing half of the "ship it, validate live" plan: log every surfaced prop,
grade vs actual outcomes, and REVIEW performance two ways:

  1. Segmented ROI (by market / side / value-flag) -- needs bets to settle.
  2. Model-vs-market SCORECARD (Brier + log-loss + calibration table) -- needs
     only outcomes, so it tells us WHO is right (our model or the book) far
     sooner than ROI can, directly resolving the "book too tight vs model too
     low" question the ace over-pricing raised.

Outcomes:
  * match total aces  -> match_results.score_json (a+b), else paired history.
  * single-player aces -> that player's ace_count (score_json side, else history).
Win rule (works for both integer 'N+' and '.5' O/U lines):
  side 'over'  wins if actual >= line ;  side 'under' wins if actual < line.
"""
from __future__ import annotations

import json
import math

from tennis_wc.features.common import utc_now


def actual_total_aces(conn, match_id: int) -> float | None:
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
    meta = conn.execute(
        "SELECT player_a_id, player_b_id, match_date FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not meta:
        return None
    a = _history_aces(conn, match_id, meta["player_a_id"])
    b = _history_aces(conn, match_id, meta["player_b_id"])
    return (a + b) if (a is not None and b is not None) else None


def actual_player_aces(conn, match_id: int, player_id: int) -> float | None:
    """Actual aces for one player in a match."""
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if meta:
        row = conn.execute(
            "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()
        if row and row["score_json"]:
            try:
                s = json.loads(row["score_json"])
                if player_id == meta["player_a_id"] and s.get("player_a_aces") is not None:
                    return float(s["player_a_aces"])
                if player_id == meta["player_b_id"] and s.get("player_b_aces") is not None:
                    return float(s["player_b_aces"])
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
    return _history_aces(conn, match_id, player_id)


def _history_aces(conn, match_id: int, player_id: int) -> float | None:
    meta = conn.execute("SELECT match_date FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not meta:
        return None
    row = conn.execute(
        "SELECT ace_count FROM player_match_history "
        "WHERE player_id = ? AND ace_count IS NOT NULL AND substr(match_date,1,10) = ? LIMIT 1",
        (player_id, (meta["match_date"] or "")[:10]),
    ).fetchone()
    return float(row["ace_count"]) if row else None


def record_prop(conn, *, match_id: int, match_date: str, match_label: str,
                market_key: str, line: float, selection: str, side: str,
                prop_scope: str, subject_player_id: int | None, decimal_odds: float,
                model_prob: float, market_prob_fair: float, blended_prob: float,
                edge: float, ev: float, predicted_mean: float,
                stake_units: float, is_value: bool) -> None:
    """Upsert a surfaced prop as PENDING (idempotent per match+market+selection).
    model_prob / market_prob_fair are the probabilities OF THIS SIDE."""
    prop_key = f"{match_id}|{market_key}|{selection}"
    now = utc_now()
    conn.execute(
        """
        INSERT INTO prop_tracker (
            prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            market_prob_fair, blended_prob, edge, ev, predicted_mean, stake_units,
            is_value, result_status, profit_loss_units, actual_value,
            recorded_at, updated_at, settled_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING', NULL, NULL, ?, ?, NULL)
        ON CONFLICT(prop_key) DO UPDATE SET
            decimal_odds=excluded.decimal_odds, model_prob=excluded.model_prob,
            market_prob_fair=excluded.market_prob_fair, blended_prob=excluded.blended_prob,
            edge=excluded.edge, ev=excluded.ev, predicted_mean=excluded.predicted_mean,
            stake_units=excluded.stake_units, is_value=excluded.is_value,
            updated_at=excluded.updated_at
        WHERE prop_tracker.result_status = 'PENDING'
        """,
        (prop_key, match_id, match_date, match_label, market_key, line, selection,
         side, prop_scope, subject_player_id, decimal_odds, model_prob,
         market_prob_fair, blended_prob, edge, ev, predicted_mean, stake_units,
         1 if is_value else 0, now, now),
    )


def _actual_for(conn, p) -> float | None:
    if (p["prop_scope"] or "match") == "match":
        return actual_total_aces(conn, p["match_id"])
    return actual_player_aces(conn, p["match_id"], p["subject_player_id"])


def settle_props(conn) -> dict:
    pending = conn.execute("SELECT * FROM prop_tracker WHERE result_status = 'PENDING'").fetchall()
    graded = 0
    for p in pending:
        actual = _actual_for(conn, p)
        if actual is None:
            continue
        won = actual >= p["line"] if (p["side"] or "over") == "over" else actual < p["line"]
        stake = p["stake_units"] or 0.0
        pl = stake * (p["decimal_odds"] - 1.0) if won else -stake
        conn.execute(
            "UPDATE prop_tracker SET result_status=?, actual_value=?, profit_loss_units=?, "
            "settled_at=?, updated_at=? WHERE id=?",
            ("WIN" if won else "LOSS", actual, round(pl, 4), utc_now(), utc_now(), p["id"]),
        )
        graded += 1
    conn.commit()
    return {"graded": graded, "still_pending": len(pending) - graded}


# --------------------------------------------------------------------------- #
# Review 1: segmented ROI
# --------------------------------------------------------------------------- #
def prop_roi_report(conn, value_only: bool = True) -> dict:
    """Realised ROI over settled BET props (is_value), segmented by market family
    and side. value_only=False includes scorecard-only (stake 0) rows too."""
    where = "result_status IN ('WIN','LOSS') AND stake_units > 0"
    if value_only:
        where += " AND is_value = 1"
    rows = conn.execute(f"SELECT * FROM prop_tracker WHERE {where}").fetchall()

    def agg(rs):
        n = len(rs)
        if not n:
            return {"settled": 0, "wins": 0, "hit_rate": None, "staked": 0.0, "pnl": 0.0, "roi": None}
        wins = sum(1 for r in rs if r["result_status"] == "WIN")
        staked = sum((r["stake_units"] or 0.0) for r in rs)
        pnl = sum((r["profit_loss_units"] or 0.0) for r in rs)
        return {"settled": n, "wins": wins, "hit_rate": round(wins / n, 4),
                "staked": round(staked, 2), "pnl": round(pnl, 3),
                "roi": round(pnl / staked, 4) if staked else None}

    def family(mk: str) -> str:
        if mk.startswith("total_aces") or mk == "total_aces_in_the_match":
            return "match_total_aces"
        if "_aces" in mk:
            return "player_aces"
        return mk

    by_side, by_family = {}, {}
    for r in rows:
        by_side.setdefault(r["side"] or "over", []).append(r)
        by_family.setdefault(family(r["market_key"]), []).append(r)
    return {
        "overall": agg(rows),
        "by_side": {k: agg(v) for k, v in by_side.items()},
        "by_family": {k: agg(v) for k, v in by_family.items()},
    }


# --------------------------------------------------------------------------- #
# Review 2: model-vs-market scorecard (needs only outcomes, not bets)
# --------------------------------------------------------------------------- #
def model_vs_market_scorecard(conn) -> dict:
    """On every settled prop, compare the MODEL's probability of the recorded
    side vs the MARKET's de-vigged probability, via Brier + log-loss. Lower is
    better. If the model beats the market, our edge is real; if the market wins,
    the model is the weak link (as with match-winner). Also a calibration table:
    predicted-prob bucket vs realised hit."""
    rows = conn.execute(
        "SELECT model_prob, market_prob_fair, result_status FROM prop_tracker "
        "WHERE result_status IN ('WIN','LOSS') AND model_prob IS NOT NULL AND market_prob_fair IS NOT NULL"
    ).fetchall()
    n = len(rows)
    if not n:
        return {"settled": 0, "model": None, "market": None, "verdict": "no settled props yet",
                "calibration": []}

    def clamp(p):
        return min(1 - 1e-9, max(1e-9, p))

    m_brier = mk_brier = m_ll = mk_ll = 0.0
    cal = {}
    for r in rows:
        y = 1.0 if r["result_status"] == "WIN" else 0.0
        mp, kp = clamp(r["model_prob"]), clamp(r["market_prob_fair"])
        m_brier += (mp - y) ** 2
        mk_brier += (kp - y) ** 2
        m_ll += -(y * math.log(mp) + (1 - y) * math.log(1 - mp))
        mk_ll += -(y * math.log(kp) + (1 - y) * math.log(1 - kp))
        b = round(mp * 10) / 10
        cal.setdefault(b, [0.0, 0, 0])
        cal[b][0] += mp; cal[b][1] += int(y); cal[b][2] += 1
    model = {"brier": round(m_brier / n, 4), "log_loss": round(m_ll / n, 4)}
    market = {"brier": round(mk_brier / n, 4), "log_loss": round(mk_ll / n, 4)}
    if model["brier"] < market["brier"] - 0.005:
        verdict = "MODEL beats market (edge plausibly real) — keep validating"
    elif market["brier"] < model["brier"] - 0.005:
        verdict = "MARKET beats model (model is the weak link, like match-winner)"
    else:
        verdict = "model ≈ market (no clear edge either way)"
    calibration = [
        {"pred": round(s / c, 3), "realised": round(w / c, 3), "n": c}
        for b, (s, w, c) in sorted(cal.items()) if c >= 5
    ]
    return {"settled": n, "model": model, "market": market, "verdict": verdict,
            "calibration": calibration}
