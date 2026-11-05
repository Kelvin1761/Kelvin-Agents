"""The ledger: one ``prop_tracker`` row per priced prop side.

A row is upserted only while PENDING, and a post-start write never replaces a
pre-match price (``is_point_in_time`` is stamped at write and only downgrades).
"""
from __future__ import annotations

from datetime import datetime

POINT_IN_TIME, POST_START, UNVERIFIABLE = 1, 0, None


def classify_point_in_time(recorded_at: str | None, start_time_utc: str | None) -> int | None:
    """1 if recorded before the start, 0 after, None if either time is unusable."""
    if not start_time_utc or not recorded_at:
        return UNVERIFIABLE
    try:
        captured = datetime.fromisoformat(str(recorded_at).replace("Z", "+00:00"))
        start = datetime.fromisoformat(str(start_time_utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return UNVERIFIABLE
    if captured.tzinfo is None or start.tzinfo is None:
        return UNVERIFIABLE
    return POINT_IN_TIME if captured < start else POST_START


def record_rows(conn, rows: list[dict], now: str) -> int:
    """Upsert priced rows (from ``pricing.props.price_date``); returns rows written."""
    written = 0
    for row in rows:
        fixture = conn.execute("SELECT player_a_id, player_b_id, fixture_status, start_time_utc "
                               "FROM matches WHERE id=?", (row["match_id"],)).fetchone()
        if fixture is None:
            raise ValueError(f"Prop fixture not found: {row['match_id']}")
        if fixture["player_a_id"] == fixture["player_b_id"]:
            raise ValueError(f"Prop fixture lists the same player twice: {row['match_id']}")
        if row["subject_player_id"] is not None and row["subject_player_id"] not in (
                fixture["player_a_id"], fixture["player_b_id"]):
            raise ValueError(f"Prop subject is outside fixture: {row['match_id']}/{row['subject_player_id']}")
        if fixture["fixture_status"] != "ACTIVE":
            raise ValueError(f"Prop fixture is inactive: {row['match_id']}")
        point_in_time = classify_point_in_time(now, fixture["start_time_utc"])
        conn.execute("""
            INSERT INTO prop_tracker (
                prop_key, match_id, match_date, match_label, market_key, line, selection,
                side, prop_scope, subject_player_id, decimal_odds, model_prob,
                model_prob_raw, temper_strength,
                market_prob_fair, blended_prob, edge, ev, predicted_mean, stake_units,
                is_value, result_status, profit_loss_units, actual_value,
                recorded_at, updated_at, settled_at,
                feed_market_key, feed_market_name, feed_selection_name, feed_line,
                is_point_in_time, pricing_evidence_json, priced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',NULL,NULL,?,?,NULL,?,?,?,?,?,?,?)
            ON CONFLICT(prop_key) DO UPDATE SET
                pricing_evidence_json=excluded.pricing_evidence_json, priced_at=excluded.priced_at,
                decimal_odds=excluded.decimal_odds, model_prob=excluded.model_prob,
                model_prob_raw=excluded.model_prob_raw, temper_strength=excluded.temper_strength,
                market_prob_fair=excluded.market_prob_fair, blended_prob=excluded.blended_prob,
                edge=excluded.edge, ev=excluded.ev, predicted_mean=excluded.predicted_mean,
                stake_units=excluded.stake_units, is_value=excluded.is_value,
                updated_at=excluded.updated_at,
                feed_market_key=COALESCE(excluded.feed_market_key, prop_tracker.feed_market_key),
                feed_market_name=COALESCE(excluded.feed_market_name, prop_tracker.feed_market_name),
                feed_selection_name=COALESCE(excluded.feed_selection_name, prop_tracker.feed_selection_name),
                feed_line=COALESCE(excluded.feed_line, prop_tracker.feed_line),
                is_point_in_time=CASE
                    WHEN excluded.is_point_in_time IS NULL OR prop_tracker.is_point_in_time IS NULL THEN NULL
                    ELSE MIN(excluded.is_point_in_time, prop_tracker.is_point_in_time) END
            WHERE prop_tracker.result_status = 'PENDING'
              AND NOT (prop_tracker.is_point_in_time = 1 AND excluded.is_point_in_time = 0)
            """, (
            f"{row['match_id']}|{row['market_key']}|{row['selection']}", row["match_id"],
            row["match_date"], row["match_label"], row["market_key"], row["line"], row["selection"],
            row["side"], row["prop_scope"], row["subject_player_id"], row["decimal_odds"],
            row["model_prob"], row["model_prob_raw"], row["temper_strength"],
            row["market_prob_fair"], row["blended_prob"], row["edge"], row["ev"],
            row["predicted_mean"], row["stake_units"], 1 if row["is_value"] else 0, now, now,
            row["feed_market_key"], row["feed_market_name"], row["feed_selection_name"],
            row["feed_line"], point_in_time, row["pricing_evidence_json"], now))
        written += 1
    conn.commit()
    return written
