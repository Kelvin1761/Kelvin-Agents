from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from tennis_wc.betting.clv import calculate_clv
from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.ingestion.name_matching import match_pair_score, same_player_name
from tennis_wc.providers import get_tennis_provider


def record_bet(prediction_id: int, odds: float, stake: float) -> int:
    _ensure_tracking_schema()
    prediction = _prediction(prediction_id)
    tier = _prediction_tier(prediction)
    now = utc_now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bet_ledger (
                prediction_id, match_id, selection_player_id, selection_name,
                market_key, market_name, tier, model_probability, edge, confidence,
                odds_taken, stake_units, status, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                prediction_id,
                prediction["match_id"],
                prediction["selection_player_id"],
                prediction["selection_name"],
                "match_winner",
                "Match Betting",
                tier,
                prediction["model_probability"],
                prediction["edge"],
                prediction["confidence"],
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
    _ensure_tracking_schema()
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
    update_clv_tracker_for_date(match_date)
    return count


def update_open_bets_clv() -> int:
    _ensure_tracking_schema()
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


def sync_clv_tracker_for_date(match_date: str) -> dict:
    _ensure_tracking_schema()
    now = utc_now()
    synced = 0
    with get_connection() as conn:
        predictions = conn.execute(
            """
            SELECT p.*, m.match_date, m.player_a_id, m.player_b_id
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            WHERE m.match_date = ?
              AND p.decision = 'BET'
              AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
            """,
            (match_date,),
        ).fetchall()
        for prediction in predictions:
            side = "player_a" if prediction["selection_player_id"] == prediction["player_a_id"] else "player_b"
            synced += _upsert_tracker(
                conn,
                {
                    "recommendation_type": "MATCH_PREDICTION",
                    "source_id": int(prediction["id"]),
                    "match_id": int(prediction["match_id"]),
                    "match_date": prediction["match_date"],
                    "selection_name": prediction["selection_name"],
                    "selection_side": side,
                    "market_key": "match_winner",
                    "market_name": "Match Betting",
                    "market_line": None,
                    "tier": _prediction_tier(dict(prediction)),
                    "model_probability": prediction["model_probability"],
                    "edge": prediction["edge"],
                    "confidence": prediction["confidence"],
                    "odds_taken": prediction["current_market_odds"],
                    "recorded_at": now,
                    "updated_at": now,
                },
            )

        market_predictions = conn.execute(
            """
            SELECT mp.*, m.match_date
            FROM market_predictions mp
            JOIN matches m ON m.id = mp.match_id
            WHERE m.match_date = ?
              AND (
                (mp.banker_eligible = 1 AND mp.market_key != 'match_winner')
                OR json_extract(mp.pricing_json, '$.tier') = 'HIGH_ODDS_VALUE'
                OR (mp.model_status = 'PROP_MODEL' AND COALESCE(mp.edge, 0) > 0)
                OR (
                    mp.model_status = 'DERIVED_MODEL'
                    AND mp.decision = 'MODEL_REVIEW'
                    AND COALESCE(mp.edge, 0) > 0
                    AND mp.market_key IN ('total_sets', 'both_players_to_win_a_set_yes_no', 'set_handicap', 'game_handicap', 'to_win_1st_set', 'winner_related')
                )
              )
            """,
            (match_date,),
        ).fetchall()
        for row in market_predictions:
            source_id = row["market_odds_snapshot_id"] if row["market_odds_snapshot_id"] is not None else row["id"]
            synced += _upsert_tracker(
                conn,
                {
                    "recommendation_type": "MARKET_LEG",
                    "source_id": int(source_id),
                    "match_id": int(row["match_id"]),
                    "match_date": row["match_date"],
                    "selection_name": row["selection_name"],
                    "selection_side": row["selection_side"],
                    "market_key": row["market_key"],
                    "market_name": row["market_name"],
                    "market_line": row["line"],
                    "tier": _market_prediction_tier(dict(row)),
                    "model_probability": row["model_probability"],
                    "edge": row["edge"],
                    "confidence": row["confidence"],
                    "odds_taken": row["odds"],
                    "recorded_at": now,
                    "updated_at": now,
                },
            )
        pruned = _prune_pending_tracker_duplicates(conn, match_date)
    updated_clv = update_clv_tracker_for_date(match_date)
    return {"synced": synced, "clv_updated": updated_clv, "duplicates_pruned": pruned}


def _prune_pending_tracker_duplicates(conn, match_date: str) -> int:
    rows = conn.execute(
        """
        SELECT id
        FROM clv_tracker
        WHERE match_date = ?
          AND result_status = 'PENDING'
          AND id NOT IN (
            SELECT MAX(id)
            FROM clv_tracker
            WHERE match_date = ?
              AND result_status = 'PENDING'
            GROUP BY recommendation_type, match_id, market_key, selection_name, COALESCE(market_line, -999999)
          )
        """,
        (match_date, match_date),
    ).fetchall()
    ids = [int(row["id"]) for row in rows]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"DELETE FROM clv_tracker WHERE id IN ({placeholders})", ids)
    return len(ids)


def sync_combo_tracker_for_date(match_date: str) -> dict:
    _ensure_tracking_schema()
    from tennis_wc.reports.daily_report import banker_combinations_for_date

    now = utc_now()
    combos = banker_combinations_for_date(match_date)
    synced = 0
    current_keys = {_combo_key(combo.get("legs") or []) for combo in combos if combo.get("legs")}
    with get_connection() as conn:
        if current_keys:
            placeholders = ",".join("?" for _ in current_keys)
            conn.execute(
                f"""
                DELETE FROM combo_tracker
                WHERE match_date = ?
                  AND result_status = 'PENDING'
                  AND combo_key NOT IN ({placeholders})
                """,
                (match_date, *sorted(current_keys)),
            )
        else:
            conn.execute("DELETE FROM combo_tracker WHERE match_date = ? AND result_status = 'PENDING'", (match_date,))
        for combo in combos:
            synced += _upsert_combo_tracker(conn, combo, match_date, now)
    return {"synced": synced, "source_combos": len(combos)}


def update_clv_tracker_for_date(match_date: str) -> int:
    _ensure_tracking_schema()
    now = utc_now()
    updated = 0
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM clv_tracker WHERE match_date = ?", (match_date,)).fetchall()
        for row in rows:
            closing_odds = _tracker_closing_odds(conn, dict(row))
            if closing_odds is None:
                continue
            clv = calculate_clv(float(row["odds_taken"]), float(closing_odds))
            conn.execute(
                "UPDATE clv_tracker SET closing_odds = ?, clv = ?, updated_at = ? WHERE id = ?",
                (closing_odds, clv, now, row["id"]),
            )
            updated += 1
    return updated


def fetch_results_for_date(match_date: str) -> dict:
    _ensure_tracking_schema()
    provider = get_tennis_provider()
    tennis_my_life = None
    try:
        lookup_dates = _result_lookup_dates(match_date)
        rows = []
        target_rows = []
        for lookup_date in lookup_dates:
            fetched = provider.fetch_historical_matches(lookup_date, lookup_date)
            if lookup_date == match_date:
                target_rows = fetched
            rows.extend(fetched)
    except Exception as exc:
        rows = []
        target_rows = []
        provider_error = str(exc)
    else:
        provider_error = None
    provider_name = getattr(provider, "provider_name", "unknown")
    imported = _store_result_rows(match_date, rows, provider_name)
    resolver = _resolve_pending_match_results(match_date, rows, provider_name)
    winners_seen = len([row for row in target_rows if row.get("won")])
    lookup_winners_seen = len([row for row in rows if row.get("won")])
    try:
        from tennis_wc.ingestion.ingest_tennismylife import ingest_tennismylife_results

        tennis_my_life = ingest_tennismylife_results(match_date)
    except Exception as exc:
        tennis_my_life = {"error": str(exc), "results_imported": 0}
    return {
        "provider": getattr(provider, "provider_name", "unknown"),
        "rows_seen": len(target_rows),
        "lookup_dates": lookup_dates if "lookup_dates" in locals() else [match_date],
        "lookup_rows_seen": len(rows),
        "winners_seen": winners_seen,
        "lookup_winners_seen": lookup_winners_seen,
        "imported": imported,
        "unmatched": max(0, winners_seen - min(imported, winners_seen)),
        "error": provider_error,
        "resolver": resolver,
        "tennismylife": tennis_my_life,
    }


def _result_lookup_dates(match_date: str) -> list[str]:
    from datetime import date, timedelta

    current = date.fromisoformat(match_date)
    return [(current + timedelta(days=offset)).isoformat() for offset in (0, -1, 1)]


def settle_bets_for_date(match_date: str, auto_refresh: bool = True) -> dict:
    _ensure_tracking_schema()
    refresh_summary = {}
    if auto_refresh:
        refresh_summary["results"] = fetch_results_for_date(match_date)
        refresh_summary["closing_odds_snapshots"] = fetch_closing_odds_for_date(match_date)
        refresh_summary["tracker"] = sync_clv_tracker_for_date(match_date)
        refresh_summary["combo_tracker"] = sync_combo_tracker_for_date(match_date)
    now = utc_now()
    settled = 0
    pending = 0
    with get_connection() as conn:
        bets = conn.execute(
            """
            SELECT b.*, r.winner_player_id
            FROM bet_ledger b
            JOIN matches m ON m.id = b.match_id
            LEFT JOIN match_results r ON r.id = (
                SELECT r2.id
                FROM match_results r2
                WHERE r2.match_id = b.match_id
                ORDER BY
                    CASE
                        WHEN json_extract(r2.score_json, '$.player_a_aces') IS NOT NULL
                         AND json_extract(r2.score_json, '$.player_b_aces') IS NOT NULL THEN 0
                        ELSE 1
                    END,
                    CASE WHEN r2.source_provider = 'tennismylife' THEN 0 ELSE 1 END,
                    r2.id DESC
                LIMIT 1
            )
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
    tracker_settlement = settle_clv_tracker_for_date(match_date)
    combo_settlement = settle_combo_tracker_for_date(match_date)
    return {
        "settled": settled,
        "pending_without_result": pending,
        "tracker_settlement": tracker_settlement,
        "combo_settlement": combo_settlement,
        "tier_roi": tier_roi_summary(),
        "auto_refresh": refresh_summary,
    }


def pending_settlement_dates(before_date: str, lookback_days: int = 30) -> list[str]:
    """Distinct past match dates that still hold PENDING tracker/ledger rows."""
    from datetime import date, timedelta

    _ensure_tracking_schema()
    cutoff = (date.fromisoformat(before_date) - timedelta(days=lookback_days)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT match_date FROM (
                SELECT match_date FROM clv_tracker WHERE result_status = 'PENDING'
                UNION SELECT match_date FROM combo_tracker WHERE result_status = 'PENDING'
                UNION SELECT match_date FROM prop_tracker WHERE result_status = 'PENDING'
                UNION SELECT m.match_date
                FROM bet_ledger b JOIN matches m ON m.id = b.match_id
                WHERE b.status = 'PENDING'
            )
            WHERE match_date < ? AND match_date >= ?
            ORDER BY match_date
            """,
            (before_date, cutoff),
        ).fetchall()
    return [row["match_date"] for row in rows]


def settle_pending_backlog(before_date: str, lookback_days: int = 30, max_dates: int = 10) -> dict:
    """Sweep past dates that still have PENDING rows: fetch results, sync and
    settle every tracker for each date, then grade props globally.

    run-daily calls this directly so settlement/recording no longer depends on
    the launchd wrapper being healthy — the 2026-06-19..07-08 tracker gap came
    from that coupling (scheduler died, so nothing synced or settled).
    """
    dates = pending_settlement_dates(before_date, lookback_days)
    summary: dict = {"dates": {}, "skipped_dates": dates[max_dates:]}
    for match_date in dates[:max_dates]:
        try:
            result = settle_bets_for_date(match_date)
            summary["dates"][match_date] = {
                "settled": result.get("settled"),
                "tracker_settled": (result.get("tracker_settlement") or {}).get("settled"),
                "combo_settled": (result.get("combo_settlement") or {}).get("settled"),
            }
        except Exception as exc:  # noqa: BLE001 - one bad date must not stop the sweep
            summary["dates"][match_date] = {"error": str(exc)}
    try:
        from tennis_wc.props.settlement import settle_props

        with get_connection() as conn:
            summary["props"] = settle_props(conn)
    except Exception as exc:  # noqa: BLE001
        summary["props"] = {"error": str(exc)}
    return summary


def settle_clv_tracker_for_date(match_date: str) -> dict:
    _ensure_tracking_schema()
    now = utc_now()
    settled = 0
    pending = 0
    unsupported = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.*, r.winner_player_id, r.score_json, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM clv_tracker c
            JOIN matches m ON m.id = c.match_id
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            LEFT JOIN match_results r ON r.id = (
                SELECT r2.id
                FROM match_results r2
                WHERE r2.match_id = c.match_id
                ORDER BY
                    CASE
                        WHEN json_extract(r2.score_json, '$.player_a_aces') IS NOT NULL
                         AND json_extract(r2.score_json, '$.player_b_aces') IS NOT NULL THEN 0
                        ELSE 1
                    END,
                    CASE WHEN r2.source_provider = 'tennismylife' THEN 0 ELSE 1 END,
                    r2.id DESC
                LIMIT 1
            )
            WHERE c.match_date = ?
              AND c.result_status = 'PENDING'
            """,
            (match_date,),
        ).fetchall()
        for row in rows:
            if row["winner_player_id"] is None:
                pending += 1
                continue
            won = _settle_market_leg(dict(row))
            if won is None:
                unsupported += 1
                continue
            status = "WON" if won else "LOST"
            profit = float(row["odds_taken"]) - 1 if won else -1.0
            conn.execute(
                """
                UPDATE clv_tracker
                SET result_status = ?, profit_loss_units = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, profit, now, row["id"]),
            )
            settled += 1
    return {"settled": settled, "pending_without_result": pending, "unsupported_market_results": unsupported}


def settle_combo_tracker_for_date(match_date: str) -> dict:
    _ensure_tracking_schema()
    now = utc_now()
    settled = 0
    pending = 0
    unsupported = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.*, r.winner_player_id, r.score_json, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM combo_tracker c
            JOIN matches m ON m.id = c.match_id
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            LEFT JOIN match_results r ON r.id = (
                SELECT r2.id
                FROM match_results r2
                WHERE r2.match_id = c.match_id
                ORDER BY
                    CASE
                        WHEN json_extract(r2.score_json, '$.player_a_aces') IS NOT NULL
                         AND json_extract(r2.score_json, '$.player_b_aces') IS NOT NULL THEN 0
                        ELSE 1
                    END,
                    CASE WHEN r2.source_provider = 'tennismylife' THEN 0 ELSE 1 END,
                    r2.id DESC
                LIMIT 1
            )
            WHERE c.match_date = ?
              AND c.result_status = 'PENDING'
            """,
            (match_date,),
        ).fetchall()
        for row in rows:
            legs = _combo_legs(row["legs_json"])
            if row["winner_player_id"] is None:
                pending += 1
                continue
            leg_results = [_settle_market_leg(_combo_leg_result_row(dict(row), leg)) for leg in legs]
            if not legs or any(result is None for result in leg_results):
                unsupported += 1
                continue
            won = all(bool(result) for result in leg_results)
            status = "WON" if won else "LOST"
            stake = float(row["stake_units"] or 0)
            profit = stake * (float(row["combo_odds"]) - 1) if won else -stake
            conn.execute(
                """
                UPDATE combo_tracker
                SET result_status = ?, profit_loss_units = ?, updated_at = ?, settled_at = ?
                WHERE id = ?
                """,
                (status, profit, now, now, row["id"]),
            )
            settled += 1
    return {"settled": settled, "pending_without_result": pending, "unsupported_market_results": unsupported}


def ledger_summary() -> dict:
    _ensure_tracking_schema()
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
        "by_tier": tier_roi_summary()["ledger_by_tier"],
        "clv_tracker": clv_tracker_summary(),
        "combo_tracker": combo_tracker_summary(),
    }


def clv_tracker_summary() -> dict:
    _ensure_tracking_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                   CASE
                       WHEN recommendation_type = 'MARKET_LEG' AND tier = 'VALUE_BANKER' THEN 'MARKET_TRIAL'
                       ELSE tier
                   END AS tier,
                   result_status,
                   COUNT(*) AS bets,
                   AVG(clv) AS avg_clv,
                   SUM(COALESCE(profit_loss_units, 0)) AS profit
            FROM clv_tracker
            WHERE NOT (
                recommendation_type = 'MARKET_LEG'
                AND tier IN ('MARKET_TRIAL', 'PROP_MODEL_REVIEW')
                AND COALESCE(edge, 0) <= 0
            )
            GROUP BY
                CASE
                    WHEN recommendation_type = 'MARKET_LEG' AND tier = 'VALUE_BANKER' THEN 'MARKET_TRIAL'
                    ELSE tier
                END,
                result_status
            ORDER BY tier, result_status
            """
        ).fetchall()
    return {"total_tracked": sum(int(row["bets"]) for row in rows), "by_tier_status": [dict(row) for row in rows]}


def combo_tracker_summary() -> dict:
    _ensure_tracking_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT tier, result_status, COUNT(*) AS combos,
                   SUM(stake_units) AS stake,
                   SUM(COALESCE(profit_loss_units, 0)) AS profit
            FROM combo_tracker
            GROUP BY tier, result_status
            ORDER BY tier, result_status
            """
        ).fetchall()
    return {"total_tracked": sum(int(row["combos"]) for row in rows), "by_tier_status": [dict(row) for row in rows]}


def tier_roi_summary() -> dict:
    _ensure_tracking_schema()
    with get_connection() as conn:
        ledger_rows = conn.execute(
            """
            SELECT COALESCE(tier, 'UNKNOWN') AS tier, COUNT(*) AS bets,
                   SUM(stake_units) AS stake,
                   SUM(COALESCE(profit_loss_units, 0)) AS profit,
                   AVG(clv) AS avg_clv
            FROM bet_ledger
            GROUP BY COALESCE(tier, 'UNKNOWN')
            ORDER BY tier
            """
        ).fetchall()
        tracker_rows = conn.execute(
            """
            SELECT
                   CASE
                       WHEN recommendation_type = 'MARKET_LEG' AND tier = 'VALUE_BANKER' THEN 'MARKET_TRIAL'
                       ELSE tier
                   END AS tier,
                   COUNT(*) AS tracked,
                   SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                   SUM(COALESCE(profit_loss_units, 0)) AS profit,
                   AVG(clv) AS avg_clv
            FROM clv_tracker
            WHERE NOT (
                recommendation_type = 'MARKET_LEG'
                AND tier IN ('MARKET_TRIAL', 'PROP_MODEL_REVIEW')
                AND COALESCE(edge, 0) <= 0
            )
            GROUP BY
                CASE
                    WHEN recommendation_type = 'MARKET_LEG' AND tier = 'VALUE_BANKER' THEN 'MARKET_TRIAL'
                    ELSE tier
                END
            ORDER BY tier
            """
        ).fetchall()
        combo_rows = conn.execute(
            """
            SELECT tier, COUNT(*) AS tracked,
                   SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                   SUM(stake_units) AS stake,
                   SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN stake_units ELSE 0 END) AS settled_stake,
                   SUM(COALESCE(profit_loss_units, 0)) AS profit
            FROM combo_tracker
            GROUP BY tier
            ORDER BY tier
            """
        ).fetchall()
    ledger = []
    for row in ledger_rows:
        stake = float(row["stake"] or 0)
        item = dict(row)
        item["roi"] = float(row["profit"] or 0) / stake if stake else None
        ledger.append(item)
    tracker = []
    for row in tracker_rows:
        settled = int(row["settled"] or 0)
        item = dict(row)
        item["flat_1u_roi"] = float(row["profit"] or 0) / settled if settled else None
        tracker.append(item)
    combos = []
    for row in combo_rows:
        stake = float(row["settled_stake"] or 0)
        item = dict(row)
        item["roi"] = float(row["profit"] or 0) / stake if stake else None
        combos.append(item)
    return {"ledger_by_tier": ledger, "tracker_by_tier": tracker, "combo_by_tier": combos}


def combo_roi_summary() -> dict:
    _ensure_tracking_schema()
    return {"combo_tracker": combo_tracker_summary(), "combo_by_tier": tier_roi_summary()["combo_by_tier"]}


MIN_SETTLEMENT_COVERAGE = 0.80
MIN_RESULT_MATCH_SCORE = 1.84


def tier_action_summary(min_samples: int = 30, min_coverage: float = MIN_SETTLEMENT_COVERAGE) -> dict:
    _ensure_tracking_schema()
    rows = _tier_action_rows()
    promote = []
    downgrade = []
    sample_building = []
    for row in rows:
        settled = int(row["settled"] or 0)
        tracked = int(row["tracked"] or 0)
        wins = int(row["wins"] or 0)
        profit = float(row["profit"] or 0)
        avg_clv = float(row["avg_clv"] or 0)
        roi = profit / settled if settled else None
        hit_rate = wins / settled if settled else None
        coverage_rate = settled / tracked if tracked else None
        item = {
            "tier": row["tier"],
            "market_key": row["market_key"],
            "tracked": tracked,
            "settled": settled,
            "coverage_rate": coverage_rate,
            "hit_rate": hit_rate,
            "roi": roi,
            "avg_clv": avg_clv if row["avg_clv"] is not None else None,
        }
        if settled < min_samples:
            sample_building.append(item | {"reason": "sample_building"})
        elif coverage_rate is not None and coverage_rate < min_coverage:
            sample_building.append(item | {"reason": "low_settlement_coverage"})
        elif row["tier"] == "VALUE_BANKER" and hit_rate is not None and hit_rate >= 0.58 and (roi or 0) > 0 and avg_clv > 0:
            promote.append(item | {"reason": "value_to_stable_value"})
        elif (roi or 0) < 0 or avg_clv < 0:
            downgrade.append(item | {"reason": "negative_roi_or_clv"})
    return {
        "min_samples": min_samples,
        "min_coverage": min_coverage,
        "promote_candidates": promote,
        "downgrade_warnings": downgrade,
        "sample_building": sample_building,
    }


def _tier_action_rows() -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                       CASE
                           WHEN recommendation_type = 'MARKET_LEG' AND tier = 'VALUE_BANKER' THEN 'MARKET_TRIAL'
                           ELSE tier
                       END AS tier,
                       market_key,
                       COUNT(*) AS tracked,
                       SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                       SUM(CASE WHEN result_status = 'WON' THEN 1 ELSE 0 END) AS wins,
                       AVG(clv) AS avg_clv,
                       SUM(COALESCE(profit_loss_units, 0)) AS profit
                FROM clv_tracker
                WHERE NOT (
                    recommendation_type = 'MARKET_LEG'
                    AND tier IN ('MARKET_TRIAL', 'PROP_MODEL_REVIEW')
                    AND COALESCE(edge, 0) <= 0
                )
                GROUP BY
                    CASE
                        WHEN recommendation_type = 'MARKET_LEG' AND tier = 'VALUE_BANKER' THEN 'MARKET_TRIAL'
                        ELSE tier
                    END,
                    market_key
                ORDER BY settled DESC, tracked DESC, tier, market_key
                """
            ).fetchall()
        ]


def settlement_qa_for_date(match_date: str, result_health: dict | None = None) -> dict:
    _ensure_tracking_schema()
    tracker_items = []
    combo_items = []
    with get_connection() as conn:
        tracker_rows = conn.execute(
            """
            SELECT c.*, r.winner_player_id, r.score_json, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM clv_tracker c
            JOIN matches m ON m.id = c.match_id
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            LEFT JOIN match_results r ON r.id = (
                SELECT r2.id
                FROM match_results r2
                WHERE r2.match_id = c.match_id
                ORDER BY
                    CASE
                        WHEN json_extract(r2.score_json, '$.player_a_aces') IS NOT NULL
                         AND json_extract(r2.score_json, '$.player_b_aces') IS NOT NULL THEN 0
                        ELSE 1
                    END,
                    CASE WHEN r2.source_provider = 'tennismylife' THEN 0 ELSE 1 END,
                    r2.id DESC
                LIMIT 1
            )
            WHERE c.match_date = ?
            ORDER BY c.result_status, c.tier, c.market_key, c.selection_name
            """,
            (match_date,),
        ).fetchall()
        combo_rows = conn.execute(
            """
            SELECT c.*, r.winner_player_id, r.score_json, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM combo_tracker c
            JOIN matches m ON m.id = c.match_id
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            LEFT JOIN match_results r ON r.id = (
                SELECT r2.id
                FROM match_results r2
                WHERE r2.match_id = c.match_id
                ORDER BY
                    CASE
                        WHEN json_extract(r2.score_json, '$.player_a_aces') IS NOT NULL
                         AND json_extract(r2.score_json, '$.player_b_aces') IS NOT NULL THEN 0
                        ELSE 1
                    END,
                    CASE WHEN r2.source_provider = 'tennismylife' THEN 0 ELSE 1 END,
                    r2.id DESC
                LIMIT 1
            )
            WHERE c.match_date = ?
            ORDER BY c.result_status, c.tier, c.match_label
            """,
            (match_date,),
        ).fetchall()
    for row in tracker_rows:
        item = _tracker_qa_item(dict(row))
        if item:
            tracker_items.append(item)
    for row in combo_rows:
        item = _combo_qa_item(dict(row))
        if item:
            combo_items.append(item)
    reason_counts: dict[str, int] = {}
    for item in tracker_items + combo_items:
        reason = str(item.get("reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "date": match_date,
        "result_provider_health": result_health or {},
        "reason_counts": reason_counts,
        "tracker_items": tracker_items,
        "combo_items": combo_items,
    }


def _tracker_qa_item(row: dict) -> dict | None:
    status = str(row.get("result_status") or "")
    reason = None if status in {"WON", "LOST"} else _settlement_block_reason(row)
    if reason is None and status in {"WON", "LOST"}:
        return None
    return {
        "type": row.get("recommendation_type") or "tracker",
        "tier": row.get("tier"),
        "market_key": row.get("market_key"),
        "market_name": row.get("market_name"),
        "selection_name": row.get("selection_name"),
        "match": f"{row.get('player_a_name')} vs {row.get('player_b_name')}",
        "status": status,
        "reason": reason or status.lower(),
    }


def _combo_qa_item(row: dict) -> dict | None:
    status = str(row.get("result_status") or "")
    if status in {"WON", "LOST"}:
        return None
    if row.get("winner_player_id") is None:
        reason = "no_result"
    else:
        legs = _combo_legs(row.get("legs_json"))
        leg_reasons = [_settlement_block_reason(_combo_leg_result_row(dict(row), leg)) for leg in legs]
        reason = next((item for item in leg_reasons if item), "market_unsupported_or_parse_failed")
    return {
        "type": "combo",
        "tier": row.get("tier"),
        "market_key": "combo",
        "market_name": "Combo",
        "selection_name": row.get("match_label"),
        "match": row.get("match_label"),
        "status": status,
        "reason": reason,
    }


def _settlement_block_reason(row: dict) -> str | None:
    if row.get("winner_player_id") is None:
        return "no_result"
    market_key = str(row.get("market_key") or "")
    if market_key == "match_winner":
        if row.get("selection_side") not in {"player_a", "player_b"}:
            return "player_mapping_failed"
        return None
    score = _score_payload(row.get("score_json"))
    if not score:
        return "missing_scoreline"
    market_text = f"{market_key} {row.get('market_name') or ''}".lower()
    if "ace" in market_text or "double fault" in market_text or "double_fault" in market_text:
        prop = "aces" if "ace" in market_text else "double_faults"
        if _count_prop_value(row, score, prop) is None:
            return "missing_box_score"
        if _is_retired_score(score):
            return "retired_prop_settlement_policy_unknown"
    if _settle_market_leg(row) is None:
        return "market_unsupported_or_parse_failed"
    return None


def _write_settlement_qa_report(match_date: str, output_dir: Path, qa: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_date_prefix(match_date)} Tennis Settlement QA.txt"
    result_health = qa.get("result_provider_health") or {}
    tml = result_health.get("tennismylife") or {}
    resolver = result_health.get("resolver") or {}
    lines = [
        "Tennis Wong Choi 賽後結算 QA",
        f"日期：{match_date}",
        "",
        "## 賽果資料源狀態",
        "",
        f"主資料源：{result_health.get('provider', 'unknown')}｜讀到 rows：{result_health.get('rows_seen', 0)}｜查核 rows：{result_health.get('lookup_rows_seen', result_health.get('rows_seen', 0))}｜有 winner：{result_health.get('winners_seen', 0)}｜已匯入：{result_health.get('imported', 0)}｜未配對：{result_health.get('unmatched', 0)}",
        f"TennisMyLife：檔案 {tml.get('files', 0)}｜讀到 rows {tml.get('rows_seen', 0)}｜查核 rows {tml.get('lookup_rows_seen', tml.get('rows_seen', 0))}｜已匯入 {tml.get('results_imported', 0)}｜未配對 {tml.get('unmatched_rows', 0)}",
        f"Result resolver：event id tracked {resolver.get('event_id_tracked', 0)}｜event result 補入 {resolver.get('event_result_imported', 0)}｜provider rows 補入 {resolver.get('provider_rows_imported', 0)}｜local history 補入 {resolver.get('local_history_imported', 0)}",
        "",
        "## 未能結算 / 暫未支援原因",
        "",
    ]
    if qa.get("reason_counts"):
        for reason, count in sorted(qa["reason_counts"].items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {_hk_reason(reason)}：{count}")
    else:
        lines.append("- 無未結算或未支援項目。")
    lines.extend(["", "## Tracker 明細", ""])
    tracker_items = qa.get("tracker_items") or []
    if tracker_items:
        for item in tracker_items[:80]:
            lines.append(
                f"- {_hk_reason(item['reason'])}｜{item['type']}｜{item['tier']}｜{item['market_name']}: {item['selection_name']}｜{item['match']}"
            )
    else:
        lines.append("- 無 tracker QA 項目。")
    lines.extend(["", "## Combo 明細", ""])
    combo_items = qa.get("combo_items") or []
    if combo_items:
        for item in combo_items[:80]:
            lines.append(f"- {_hk_reason(item['reason'])}｜{item['tier']}｜{item['match']}")
    else:
        lines.append("- 無 combo QA 項目。")
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def _write_review_summary(
    match_date: str,
    output_dir: Path,
    settlement: dict,
    calibration: dict,
    market_validation: dict,
    aces_sanity: dict,
    ml_baseline: dict,
    settlement_qa: dict | None = None,
    tier_actions: dict | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_date_prefix(match_date)} Tennis Review Summary.txt"
    lines = [
        "Tennis Wong Choi 賽後檢討摘要",
        f"日期：{match_date}",
        "",
        "## 結算狀態",
        "",
        f"Bet ledger 已結算：{settlement.get('settled', 0)}｜待賽果：{settlement.get('pending_without_result', 0)}",
    ]
    tracker_settlement = settlement.get("tracker_settlement") or {}
    combo_settlement = settlement.get("combo_settlement") or {}
    auto_refresh = settlement.get("auto_refresh") or {}
    tracker_sync = auto_refresh.get("tracker") or {}
    result_health = auto_refresh.get("results") or {}
    tml = result_health.get("tennismylife") or {}
    resolver = result_health.get("resolver") or {}
    lines.extend(
        [
            f"CLV tracker 已結算：{tracker_settlement.get('settled', 0)}｜待賽果：{tracker_settlement.get('pending_without_result', 0)}｜暫未支援：{tracker_settlement.get('unsupported_market_results', 0)}",
            f"Combo tracker 已結算：{combo_settlement.get('settled', 0)}｜待賽果：{combo_settlement.get('pending_without_result', 0)}｜暫未支援：{combo_settlement.get('unsupported_market_results', 0)}",
            f"Tracker 同步：已同步 {tracker_sync.get('synced', 0)}｜CLV 已更新 {tracker_sync.get('clv_updated', 0)}｜重複項已清走 {tracker_sync.get('duplicates_pruned', 0)}",
            "",
            "## 賽果資料源狀態",
            "",
            f"主資料源：{result_health.get('provider', 'unknown')}｜rows {result_health.get('rows_seen', 0)}｜查核 rows {result_health.get('lookup_rows_seen', result_health.get('rows_seen', 0))}｜winner {result_health.get('winners_seen', 0)}｜已匯入 {result_health.get('imported', 0)}｜未配對 {result_health.get('unmatched', 0)}",
            f"TennisMyLife：檔案 {tml.get('files', 0)}｜rows {tml.get('rows_seen', 0)}｜查核 rows {tml.get('lookup_rows_seen', tml.get('rows_seen', 0))}｜已匯入 {tml.get('results_imported', 0)}｜未配對 {tml.get('unmatched_rows', 0)}",
            f"Result resolver：event id tracked {resolver.get('event_id_tracked', 0)}｜event result 補入 {resolver.get('event_result_imported', 0)}｜provider rows 補入 {resolver.get('provider_rows_imported', 0)}｜local history 補入 {resolver.get('local_history_imported', 0)}",
            "",
            "## 結算 QA",
            "",
            _qa_reason_summary(settlement_qa or {}),
            "",
            "## Tier ROI",
            "",
        ]
    )
    tier_summary = tier_roi_summary()
    lines.extend(_roi_rows("Tracker", tier_summary.get("tracker_by_tier") or [], "flat_1u_roi"))
    lines.extend(_roi_rows("Combo", tier_summary.get("combo_by_tier") or [], "roi"))
    lines.extend(
        [
            "",
            "## Calibration",
            "",
            f"已結算 tracked recommendations：{calibration.get('settled_tracked_recommendations', 0)}",
            f"建議：{calibration.get('recommendation') or calibration.get('warning') or calibration.get('note') or 'N/A'}",
            "",
            "## Market Validation",
            "",
        ]
    )
    for row in (market_validation.get("by_market") or [])[:12]:
        lines.append(
            f"- {row.get('market_key')}｜{row.get('tier')}｜已結算 {row.get('settled')}｜ROI {_pct(row.get('flat_1u_roi'))}｜CLV {_pct(row.get('avg_clv'))}｜{_hk_status(row.get('status'))}"
        )
    if not market_validation.get("by_market"):
        lines.append("- 暫時未有 market validation sample。")
    lines.extend(["", "## Tier 動作建議", ""])
    tier_actions = tier_actions or {}
    lines.extend(_tier_action_lines("可考慮升級", tier_actions.get("promote_candidates") or []))
    lines.extend(_tier_action_lines("降級警告", tier_actions.get("downgrade_warnings") or []))
    lines.extend(_tier_action_lines("仍在累積樣本", tier_actions.get("sample_building") or []))
    lines.extend(
        [
            "",
            "## Props / ML",
            "",
            f"Aces sanity check 已檢查：{aces_sanity.get('props_checked', 0)}",
            f"ML baseline：{ml_baseline.get('note') or ml_baseline.get('status') or ml_baseline.get('error') or 'N/A'}",
            "",
            "註：未有足夠 settled CLV/ROI 前，market 只應保留 review / trial，不應升入正式 banker。",
        ]
    )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def _qa_reason_summary(qa: dict) -> str:
    reason_counts = qa.get("reason_counts") or {}
    if not reason_counts:
        return "無未結算或未支援項目。"
    return "｜".join(f"{_hk_reason(reason)} {count}" for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0])))


def _tier_action_lines(title: str, rows: list[dict]) -> list[str]:
    lines = [f"{title}："]
    if not rows:
        lines.append("- 無")
        return lines
    for row in rows[:12]:
        lines.append(
            f"- {row.get('tier')}｜{row.get('market_key')}｜已結算 {row.get('settled')}｜命中率 {_pct(row.get('hit_rate'))}｜ROI {_pct(row.get('roi'))}｜CLV {_pct(row.get('avg_clv'))}｜{_hk_reason(row.get('reason'))}"
        )
    return lines


def _roi_rows(label: str, rows: list[dict], roi_key: str) -> list[str]:
    if not rows:
        return [f"{label}：暫時未有資料。"]
    lines = [f"{label}："]
    for row in rows:
        settled = row.get("settled", row.get("bets", 0))
        lines.append(
            f"- {row.get('tier')}｜已追蹤 {row.get('tracked', row.get('bets', 0))}｜已結算 {settled}｜ROI {_pct(row.get(roi_key))}｜CLV {_pct(row.get('avg_clv'))}"
        )
    return lines


def _hk_reason(reason) -> str:
    mapping = {
        "sample_building": "樣本仍在累積",
        "missing_box_score": "缺少 box score，未能結算 props",
        "no_result": "未搵到賽果",
        "market_unsupported_or_parse_failed": "市場暫未支援或解析失敗",
        "missing_scoreline": "缺少比分資料",
        "player_mapping_failed": "球員配對失敗",
        "retired_prop_settlement_policy_unknown": "退賽場 props 結算規則未確認",
    }
    return mapping.get(str(reason or ""), str(reason or "未分類"))


def _hk_status(status) -> str:
    mapping = {
        "KEEP_REVIEW": "繼續觀察",
        "SAMPLE_BUILDING": "樣本累積中",
        "PROMOTE_CANDIDATE": "可考慮升級",
        "DOWNGRADE_WARNING": "降級警告",
        "INSUFFICIENT_SAMPLE": "樣本不足",
        "CALIBRATED": "校準良好",
        "WATCH": "需要留意",
        "OVERCONFIDENT_OR_UNDERCONFIDENT": "校準偏差較大",
        "UNKNOWN": "未知",
    }
    return mapping.get(str(status or ""), str(status or "未知"))


def _pct(value) -> str:
    try:
        return f"{float(value) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _date_prefix(match_date: str) -> str:
    parts = str(match_date).split("-")
    if len(parts) >= 3:
        return f"{parts[1]}-{parts[2]}"
    return str(match_date)


def review_date(match_date: str) -> dict:
    settlement = settle_bets_for_date(match_date, auto_refresh=True)
    result_health = (settlement.get("auto_refresh") or {}).get("results") or {}
    settlement_qa = settlement_qa_for_date(match_date, result_health)
    tier_actions = tier_action_summary()
    try:
        from tennis_wc.modelling.ml_baseline import train_ml_baseline
        from tennis_wc.reports.calibration_report import banker_calibration_summary
        from tennis_wc.reports.daily_report import analysis_output_dir
        from tennis_wc.reports.market_validation_report import aces_prop_sanity_for_date, market_validation_summary

        output_dir = analysis_output_dir(match_date)
        calibration = banker_calibration_summary()
        market_validation = market_validation_summary()
        aces_sanity = aces_prop_sanity_for_date(match_date)
        ml_baseline = train_ml_baseline()
        qa_path = _write_settlement_qa_report(match_date, output_dir, settlement_qa)
        output_path = _write_review_summary(
            match_date,
            output_dir,
            settlement,
            calibration,
            market_validation,
            aces_sanity,
            ml_baseline,
            settlement_qa,
            tier_actions,
        )
    except Exception as exc:
        calibration = {"error": str(exc)}
        market_validation = {"error": str(exc)}
        aces_sanity = {"error": str(exc)}
        ml_baseline = {"error": str(exc)}
        qa_path = None
        output_path = None
    return {
        "date": match_date,
        "settlement": settlement,
        "settlement_qa": settlement_qa,
        "tier_roi": tier_roi_summary(),
        "combo_roi": combo_roi_summary(),
        "clv_tracker": clv_tracker_summary(),
        "combo_tracker": combo_tracker_summary(),
        "calibration": calibration,
        "market_validation": market_validation,
        "tier_actions": tier_actions,
        "aces_prop_sanity": aces_sanity,
        "ml_baseline": ml_baseline,
        "settlement_qa_report_path": str(qa_path) if qa_path else None,
        "review_report_path": str(output_path) if output_path else None,
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


def _prediction_tier(prediction: dict) -> str:
    payload = _json_payload(prediction.get("pricing_json"))
    filter_result = payload.get("filter", {})
    pricing = payload.get("pricing", {})
    confidence = int(prediction.get("confidence") or filter_result.get("confidence") or 0)
    edge = float(prediction.get("edge") or pricing.get("edge") or 0)
    probability = float(prediction.get("model_probability") or pricing.get("model_probability") or 0)
    odds = float(prediction.get("current_market_odds") or pricing.get("current_market_odds") or 0)
    if probability >= 0.68 and edge >= 0.05 and confidence >= 80 and odds <= 2.20 and _clv_history_allows_core("MATCH_PREDICTION"):
        return "CORE_BANKER"
    if probability >= 0.56 and edge >= 0.05 and confidence >= 68:
        if _stable_value_history_allows("MATCH_PREDICTION", "match_winner"):
            return "STABLE_VALUE_BANKER"
        return "VALUE_BANKER"
    if odds >= 2.5 and edge >= 0.08:
        return "HIGH_ODDS_VALUE"
    return "BET"


def _clv_history_allows_core(recommendation_type: str) -> bool:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(clv) AS samples, AVG(clv) AS avg_clv
                FROM clv_tracker
                WHERE tier = 'CORE_BANKER'
                  AND recommendation_type = ?
                  AND clv IS NOT NULL
                """,
                (recommendation_type,),
            ).fetchone()
    except Exception:
        return True
    samples = int(row["samples"] or 0) if row else 0
    if samples < 20:
        return True
    return float(row["avg_clv"] or 0) > 0


def _stable_value_history_allows(recommendation_type: str, market_key: str) -> bool:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                       SUM(CASE WHEN result_status = 'WON' THEN 1 ELSE 0 END) AS wins,
                       AVG(clv) AS avg_clv,
                       SUM(COALESCE(profit_loss_units, 0)) AS profit
                FROM clv_tracker
                WHERE tier = 'VALUE_BANKER'
                  AND recommendation_type = ?
                  AND market_key = ?
                  AND COALESCE(edge, 0) > 0
                """,
                (recommendation_type, market_key),
            ).fetchone()
    except Exception:
        return False
    settled = int(row["settled"] or 0) if row else 0
    if settled < 30:
        return False
    hit_rate = float(row["wins"] or 0) / settled
    roi = float(row["profit"] or 0) / settled
    avg_clv = float(row["avg_clv"] or 0)
    return hit_rate >= 0.58 and roi > 0 and avg_clv > 0


def _market_prediction_tier(row: dict) -> str:
    payload = _json_payload(row.get("pricing_json"))
    tier = payload.get("tier")
    if tier:
        return str(tier)
    if row.get("banker_eligible"):
        return "VALUE_BANKER"
    return "HIGH_ODDS_VALUE" if row.get("decision") == "NO_BET" else "ODDS_ONLY"


def _json_payload(raw: str | None) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _upsert_tracker(conn, data: dict) -> int:
    conn.execute(
        """
        INSERT INTO clv_tracker (
            recommendation_type, source_id, match_id, match_date, selection_name,
            selection_side, market_key, market_name, market_line, tier,
            model_probability, edge, confidence, odds_taken, result_status,
            recorded_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        ON CONFLICT(recommendation_type, source_id) DO UPDATE SET
            odds_taken = excluded.odds_taken,
            tier = excluded.tier,
            model_probability = excluded.model_probability,
            edge = excluded.edge,
            confidence = excluded.confidence,
            updated_at = excluded.updated_at
        """,
        (
            data["recommendation_type"],
            data["source_id"],
            data["match_id"],
            data["match_date"],
            data["selection_name"],
            data["selection_side"],
            data["market_key"],
            data["market_name"],
            data["market_line"],
            data["tier"],
            data["model_probability"],
            data["edge"],
            data["confidence"],
            data["odds_taken"],
            data["recorded_at"],
            data["updated_at"],
        ),
    )
    return 1


def _upsert_combo_tracker(conn, combo: dict, match_date: str, now: str) -> int:
    legs = combo.get("legs") or []
    if not legs:
        return 0
    match_id = int(legs[0]["match_id"])
    combo_key = _combo_key(legs)
    conn.execute(
        """
        INSERT INTO combo_tracker (
            combo_key, match_id, match_date, match_label, tier, legs_json,
            combo_odds, adjusted_confidence, adjusted_edge, stake_units,
            result_status, recorded_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        ON CONFLICT(combo_key) DO UPDATE SET
            tier = excluded.tier,
            legs_json = excluded.legs_json,
            combo_odds = excluded.combo_odds,
            adjusted_confidence = excluded.adjusted_confidence,
            adjusted_edge = excluded.adjusted_edge,
            stake_units = excluded.stake_units,
            updated_at = excluded.updated_at
        """,
        (
            combo_key,
            match_id,
            match_date,
            str(legs[0].get("match_label") or ""),
            str(combo.get("tier") or "UNKNOWN"),
            json.dumps([_combo_leg_payload(leg) for leg in legs], sort_keys=True),
            float(combo.get("combo_odds") or 0),
            int(combo.get("adjusted_confidence") or combo.get("min_confidence") or 0),
            float(combo.get("adjusted_edge") or combo.get("average_edge") or 0),
            float(combo.get("stake_units") or 0),
            now,
            now,
        ),
    )
    return 1


def _combo_key(legs: list[dict]) -> str:
    match_id = legs[0].get("match_id") if legs else "unknown"
    leg_ids = sorted(str(leg.get("id") or _combo_leg_payload(leg)) for leg in legs)
    return f"{match_id}|" + "||".join(leg_ids)


def _combo_leg_payload(leg: dict) -> dict:
    return {
        "id": leg.get("id"),
        "match_id": leg.get("match_id"),
        "match_label": leg.get("match_label"),
        "market_key": leg.get("market_key"),
        "market_name": leg.get("market_name"),
        "selection_name": leg.get("selection_name"),
        "selection_side": leg.get("selection_side"),
        "line": leg.get("line"),
        "tier": leg.get("tier"),
        "odds": leg.get("odds"),
        "edge": leg.get("edge"),
        "confidence": leg.get("confidence"),
    }


def _combo_legs(raw: str | None) -> list[dict]:
    try:
        payload = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _combo_leg_result_row(result_row: dict, leg: dict) -> dict:
    row = dict(result_row)
    row.update(
        {
            "selection_name": leg.get("selection_name"),
            "selection_side": leg.get("selection_side"),
            "market_key": leg.get("market_key"),
            "market_name": leg.get("market_name"),
            "market_line": leg.get("line"),
        }
    )
    return row


def _settle_market_leg(row: dict) -> bool | None:
    market_key = str(row.get("market_key") or "")
    if market_key == "match_winner":
        winner_side = "player_a" if row.get("winner_player_id") == row.get("player_a_id") else "player_b"
        return row.get("selection_side") == winner_side

    score = _score_payload(row.get("score_json"))
    if not score:
        return None
    selection = str(row.get("selection_name") or "").lower()
    line = _float_or_none(row.get("market_line"))

    if market_key == "total_sets" or "total sets" in str(row.get("market_name") or "").lower():
        return _settle_total_sets(selection, line, score)
    if market_key == "both_players_to_win_a_set_yes_no" or "both players to win a set" in str(row.get("market_name") or "").lower():
        both = int(score.get("player_a_sets") or 0) > 0 and int(score.get("player_b_sets") or 0) > 0
        if "yes" in selection:
            return both
        if "no" in selection:
            return not both
        return None
    if _is_to_win_at_least_one_set_market(row):
        return _settle_to_win_at_least_one_set(row, score)
    if market_key in {"to_win_1st_set", "winner_related"} or _is_set_winner_market(row):
        return _settle_set_winner(row, score)
    if market_key == "set_handicap":
        return _settle_handicap(row, score, "sets")
    if market_key == "game_handicap":
        return _settle_handicap(row, score, "games")
    if market_key == "total_games" or ("total" in str(row.get("market_name") or "").lower() and "game" in str(row.get("market_name") or "").lower()):
        return _settle_total_games(row, selection, line, score)
    if "ace" in market_key or "ace" in str(row.get("market_name") or "").lower():
        return _settle_count_prop(row, score, "aces")
    if "double_fault" in market_key or "double fault" in str(row.get("market_name") or "").lower():
        return _settle_count_prop(row, score, "double_faults")
    return None


def _is_set_winner_market(row: dict) -> bool:
    text = f"{row.get('market_key') or ''} {row.get('market_name') or ''}".lower()
    return "set winner" in text or "win 1st set" in text or "to win 1st set" in text


def _is_to_win_at_least_one_set_market(row: dict) -> bool:
    text = f"{row.get('market_key') or ''} {row.get('market_name') or ''}".lower().replace("_", " ")
    return "to win at least one set" in text or "to win at least 1 set" in text


def _settle_to_win_at_least_one_set(row: dict, score: dict) -> bool | None:
    side = row.get("selection_side") or _selection_side_from_names(row)
    if side not in {"player_a", "player_b"}:
        return None
    selected_sets = score.get("player_a_sets") if side == "player_a" else score.get("player_b_sets")
    try:
        selected_sets = int(selected_sets)
    except (TypeError, ValueError):
        return None
    selection = str(row.get("selection_name") or "").lower().split()
    if not selection:
        return None
    if selection[-1] == "yes":
        return selected_sets > 0
    if selection[-1] == "no":
        return selected_sets == 0
    return None


def _settle_set_winner(row: dict, score: dict) -> bool | None:
    sets = score.get("sets")
    if not isinstance(sets, list) or not sets:
        return None
    set_index = _set_index(row)
    if set_index is None or set_index >= len(sets):
        return None
    set_score = sets[set_index]
    try:
        player_a_games = int(set_score["player_a_games"])
        player_b_games = int(set_score["player_b_games"])
    except (KeyError, TypeError, ValueError):
        return None
    if player_a_games == player_b_games:
        return None
    winning_side = "player_a" if player_a_games > player_b_games else "player_b"
    selection_side = row.get("selection_side") or _selection_side_from_names(row)
    if selection_side not in {"player_a", "player_b"}:
        return None
    return selection_side == winning_side


def _set_index(row: dict) -> int | None:
    text = f"{row.get('market_key') or ''} {row.get('market_name') or ''}".lower()
    if "2nd set" in text or "set 2" in text:
        return 1
    if "3rd set" in text or "set 3" in text:
        return 2
    if "4th set" in text or "set 4" in text:
        return 3
    if "5th set" in text or "set 5" in text:
        return 4
    if "1st set" in text or "set 1" in text or "to_win_1st_set" in text:
        return 0
    return 0


def _selection_side_from_names(row: dict) -> str | None:
    selection = row.get("selection_name")
    if _same_name(selection, row.get("player_a_name")):
        return "player_a"
    if _same_name(selection, row.get("player_b_name")):
        return "player_b"
    return None


def _settle_total_sets(selection: str, line: float | None, score: dict) -> bool | None:
    total_sets = int(score.get("total_sets") or 0)
    if total_sets <= 0:
        return None
    if line is not None:
        if "over" in selection:
            return total_sets > line
        if "under" in selection:
            return total_sets < line
    for value in (2, 3, 4, 5):
        if str(value) in selection:
            return total_sets == value
    return None


def _total_games_set_index(market_name: str) -> int | None:
    """Set index for a per-set total-games market, or None for the MATCH total.
    (The total_games market_key mixes 'Set 1/2 Total Games' with full-match
    totals; they must be settled against different game counts.)"""
    text = market_name.lower()
    if "set 1" in text or "1st set" in text:
        return 0
    if "set 2" in text or "2nd set" in text:
        return 1
    if "set 3" in text or "3rd set" in text:
        return 2
    if "set 4" in text or "4th set" in text:
        return 3
    if "set 5" in text or "5th set" in text:
        return 4
    return None


def _settle_total_games(row: dict, selection: str, line: float | None, score: dict) -> bool | None:
    if line is None or _is_retired_score(score):
        return None  # void / cannot settle a retired match's game total
    set_index = _total_games_set_index(str(row.get("market_name") or ""))
    if set_index is not None:
        sets = score.get("sets")
        if not isinstance(sets, list) or set_index >= len(sets):
            return None
        set_score = sets[set_index]
        a = set_score.get("player_a_games")
        b = set_score.get("player_b_games")
    else:
        a = score.get("player_a_games")
        b = score.get("player_b_games")
    if a is None or b is None:
        return None
    total_games = int(a) + int(b)
    if "over" in selection:
        return total_games > line
    if "under" in selection:
        return total_games < line
    return None


def _settle_handicap(row: dict, score: dict, unit: str) -> bool | None:
    line = _float_or_none(row.get("market_line"))
    side = row.get("selection_side")
    if line is None or side not in {"player_a", "player_b"}:
        return None
    if unit == "sets":
        player_a_value = float(score.get("player_a_sets") or 0)
        player_b_value = float(score.get("player_b_sets") or 0)
    else:
        player_a_value = float(score.get("player_a_games") or 0)
        player_b_value = float(score.get("player_b_games") or 0)
    selected = player_a_value if side == "player_a" else player_b_value
    opponent = player_b_value if side == "player_a" else player_a_value
    return selected + line > opponent


def _settle_count_prop(row: dict, score: dict, prop: str) -> bool | None:
    if _is_retired_score(score):
        return None
    line = _float_or_none(row.get("market_line"))
    if line is None:
        return None
    selection = str(row.get("selection_name") or "").lower()
    if "over" in selection:
        wants_over = True
    elif "under" in selection:
        wants_over = False
    else:
        return None
    value = _count_prop_value(row, score, prop)
    if value is None:
        return None
    return value > line if wants_over else value < line


def _count_prop_value(row: dict, score: dict, prop: str) -> float | None:
    market_text = _norm(f"{row.get('market_key') or ''} {row.get('market_name') or ''}")
    player_a_name = _norm(row.get("player_a_name"))
    player_b_name = _norm(row.get("player_b_name"))
    player_a_value = _float_or_none(score.get(f"player_a_{prop}"))
    player_b_value = _float_or_none(score.get(f"player_b_{prop}"))
    if player_a_value is None or player_b_value is None:
        return None
    if player_a_name and player_a_name in market_text:
        return player_a_value
    if player_b_name and player_b_name in market_text:
        return player_b_value
    if str(row.get("market_name") or "").lower().startswith("total "):
        return player_a_value + player_b_value
    return None


def _norm(value: str | None) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def _score_payload(raw: str | None) -> dict | None:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_retired_score(score: dict | None) -> bool:
    if not isinstance(score, dict):
        return False
    return bool(score.get("retired"))


def _tracker_closing_odds(conn, row: dict) -> float | None:
    if row["market_key"] == "match_winner":
        closing = conn.execute(
            """
            SELECT *
            FROM closing_odds_snapshots
            WHERE match_id = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (row["match_id"],),
        ).fetchone()
        if not closing:
            return None
        value = closing["player_a_closing_odds"] if row["selection_side"] == "player_a" else closing["player_b_closing_odds"]
        return float(value) if value is not None else None
    market = conn.execute(
        """
        SELECT odds
        FROM market_odds_snapshots
        WHERE match_id = ?
          AND market_key = ?
          AND lower(trim(selection_name)) = lower(trim(?))
          AND COALESCE(line, -999999) = COALESCE(?, -999999)
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (row["match_id"], row["market_key"], row["selection_name"], row["market_line"]),
    ).fetchone()
    return float(market["odds"]) if market and market["odds"] is not None else None


def _store_result_rows(match_date: str, rows: list[dict], provider_name: str) -> int:
    winners = [row for row in rows if row.get("won")]
    imported = 0
    now = utc_now()
    with get_connection() as conn:
        for row in winners:
            match = _match_by_names(conn, match_date, str(row.get("player_name") or ""), str(row.get("opponent_name") or ""))
            if not match:
                continue
            winner_player_id = match["player_a_id"] if same_player_name(row.get("player_name"), match["player_a_name"]) else match["player_b_id"]
            score_json = _result_score_json(row, dict(match))
            conn.execute(
                """
                INSERT INTO match_results (match_id, winner_player_id, score_json, source_provider, raw_response_id, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(match_id, source_provider) DO UPDATE SET
                    winner_player_id = excluded.winner_player_id,
                    score_json = COALESCE(excluded.score_json, match_results.score_json),
                    created_at = excluded.created_at
                """,
                (match["id"], winner_player_id, score_json, provider_name, now),
            )
            imported += 1
    return imported


def _resolve_pending_match_results(match_date: str, rows: list[dict], provider_name: str) -> dict:
    """
    Fill match_results for tracked sportsbook fixtures that normal result import missed.

    This deliberately keeps strict pair matching. It is a resolver, not a guesser:
    provider rows, future event-level result APIs, and local history can only settle
    when both player names line up with the pending match pair.
    """
    _ensure_tracking_schema()
    event_summary = _resolve_pending_from_event_provider(match_date)
    provider_rows_imported = _resolve_pending_from_provider_rows(match_date, rows, provider_name)
    history_imported = _resolve_pending_from_player_history(match_date)
    return {
        "event_id_tracked": event_summary["event_id_tracked"],
        "event_result_imported": event_summary["event_result_imported"],
        "event_result_errors": event_summary["event_result_errors"],
        "provider_rows_imported": provider_rows_imported,
        "local_history_imported": history_imported,
    }


def _resolve_pending_from_event_provider(match_date: str) -> dict:
    matches = _pending_result_matches(match_date)
    event_id_tracked = len([row for row in matches if row["market_event_id"]])
    imported = 0
    errors = []
    try:
        from tennis_wc.providers import get_odds_provider

        provider = get_odds_provider()
    except Exception as exc:
        return {
            "event_id_tracked": event_id_tracked,
            "event_result_imported": 0,
            "event_result_errors": [{"source": "odds_provider", "error": str(exc)}],
        }
    fetch_event_result = getattr(provider, "fetch_event_result", None)
    if not callable(fetch_event_result):
        return {"event_id_tracked": event_id_tracked, "event_result_imported": 0, "event_result_errors": []}

    for match in matches:
        event_id = match["market_event_id"]
        if not event_id:
            continue
        try:
            result = fetch_event_result(str(event_id))
        except Exception as exc:
            errors.append({"event_id": str(event_id), "error": str(exc)})
            continue
        if not isinstance(result, dict) or not result.get("winner_name"):
            continue
        inserted = _insert_resolved_result_from_names(
            dict(match),
            result.get("winner_name"),
            result.get("loser_name") or _opponent_from_winner(dict(match), result.get("winner_name")),
            "sportsbook_event_resolver",
            {"source": "sportsbook_event_resolver", "event_id": str(event_id), "raw": result},
        )
        imported += inserted
    return {"event_id_tracked": event_id_tracked, "event_result_imported": imported, "event_result_errors": errors}


def _resolve_pending_from_provider_rows(match_date: str, rows: list[dict], provider_name: str) -> int:
    winners = [row for row in rows if row.get("won")]
    if not winners:
        return 0
    imported = 0
    for match in _pending_result_matches(match_date):
        best_row = None
        best_score = 0.0
        best_direction = None
        for row in winners:
            score, direction = match_pair_score(
                row.get("player_name"),
                row.get("opponent_name"),
                match["player_a_name"],
                match["player_b_name"],
            )
            if score > best_score:
                best_row = row
                best_score = score
                best_direction = direction
        if not best_row or best_score < MIN_RESULT_MATCH_SCORE:
            continue
        winner_name = match["player_a_name"] if best_direction == "direct" else match["player_b_name"]
        loser_name = match["player_b_name"] if best_direction == "direct" else match["player_a_name"]
        imported += _insert_resolved_result_from_names(
            dict(match),
            winner_name,
            loser_name,
            f"{provider_name}_resolver",
            {
                "source": f"{provider_name}_resolver",
                "score": round(best_score, 4),
                "provider_match_date": best_row.get("match_date"),
                "provider_match_id": best_row.get("id"),
            },
        )
    return imported


def _resolve_pending_from_player_history(match_date: str) -> int:
    matches = _pending_result_matches(match_date)
    if not matches:
        return 0
    dates = _nearby_result_dates(match_date)
    placeholders = ",".join("?" for _ in dates)
    with get_connection() as conn:
        history_rows = conn.execute(
            f"""
            SELECT h.*, p.name AS player_name, op.name AS opponent_name
            FROM player_match_history h
            JOIN players p ON p.id = h.player_id
            JOIN players op ON op.id = h.opponent_id
            WHERE h.match_date IN ({placeholders})
              AND h.won = 1
            """,
            dates,
        ).fetchall()
    imported = 0
    for match in matches:
        best_row = None
        best_score = 0.0
        best_direction = None
        for row in history_rows:
            score, direction = match_pair_score(
                row["player_name"],
                row["opponent_name"],
                match["player_a_name"],
                match["player_b_name"],
            )
            if score > best_score:
                best_row = row
                best_score = score
                best_direction = direction
        if not best_row or best_score < MIN_RESULT_MATCH_SCORE:
            continue
        winner_name = match["player_a_name"] if best_direction == "direct" else match["player_b_name"]
        loser_name = match["player_b_name"] if best_direction == "direct" else match["player_a_name"]
        imported += _insert_resolved_result_from_names(
            dict(match),
            winner_name,
            loser_name,
            "local_history_resolver",
            {
                "source": "local_history_resolver",
                "score": round(best_score, 4),
                "history_match_date": best_row["match_date"],
                "history_provider": best_row["source_provider"],
                "history_provider_match_id": best_row["provider_match_id"],
            },
        )
    return imported


def _pending_result_matches(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT m.id, m.market_event_id, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM matches m
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            WHERE m.match_date = ?
              AND NOT EXISTS (
                  SELECT 1 FROM match_results r WHERE r.match_id = m.id
              )
              AND (
                  EXISTS (SELECT 1 FROM clv_tracker c WHERE c.match_id = m.id AND c.result_status = 'PENDING')
                  OR EXISTS (SELECT 1 FROM combo_tracker co WHERE co.match_id = m.id AND co.result_status = 'PENDING')
                  OR EXISTS (SELECT 1 FROM bet_ledger b WHERE b.match_id = m.id AND b.status = 'PENDING')
              )
            """,
            (match_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def _insert_resolved_result_from_names(
    match: dict,
    winner_name: str | None,
    loser_name: str | None,
    source_provider: str,
    score_payload: dict,
) -> int:
    score, direction = match_pair_score(winner_name, loser_name, match["player_a_name"], match["player_b_name"])
    if score < MIN_RESULT_MATCH_SCORE or direction not in {"direct", "swapped"}:
        return 0
    winner_player_id = match["player_a_id"] if direction == "direct" else match["player_b_id"]
    now = utc_now()
    payload = score_payload | {"resolver_pair_score": round(score, 4)}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO match_results (match_id, winner_player_id, score_json, source_provider, raw_response_id, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            ON CONFLICT(match_id, source_provider) DO UPDATE SET
                winner_player_id = excluded.winner_player_id,
                score_json = COALESCE(excluded.score_json, match_results.score_json),
                created_at = excluded.created_at
            """,
            (match["id"], winner_player_id, json.dumps(payload, sort_keys=True), source_provider, now),
        )
    return 1


def _opponent_from_winner(match: dict, winner_name: str | None) -> str | None:
    if same_player_name(winner_name, match.get("player_a_name")):
        return match.get("player_b_name")
    if same_player_name(winner_name, match.get("player_b_name")):
        return match.get("player_a_name")
    return None


def _nearby_result_dates(match_date: str) -> list[str]:
    current = date.fromisoformat(match_date)
    return [(current + timedelta(days=offset)).isoformat() for offset in (0, -1, 1)]


def _result_score_json(row: dict, match: dict) -> str | None:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    payload = _score_from_bsd_raw(raw) or _score_from_espn_raw(raw, match)
    if not payload:
        return None
    return json.dumps(payload, sort_keys=True)


def _score_from_bsd_raw(raw: dict) -> dict | None:
    sets_detail = raw.get("sets_detail")
    if not isinstance(sets_detail, list) or not sets_detail:
        return None
    sets = []
    for item in sets_detail:
        if not isinstance(item, dict) or item.get("p1") is None or item.get("p2") is None:
            continue
        sets.append({"player_a_games": int(item["p1"]), "player_b_games": int(item["p2"])})
    if not sets:
        return None
    payload = _score_summary(sets, "bsd_sets_detail")
    payload.update(_bsd_stat_payload(raw))
    return payload


def _bsd_stat_payload(raw: dict) -> dict:
    return {
        "player_a_aces": _first_int(raw, ["p1_aces", "p1_ace", "player1_aces", "player1_ace", "home_aces"]),
        "player_b_aces": _first_int(raw, ["p2_aces", "p2_ace", "player2_aces", "player2_ace", "away_aces"]),
        "player_a_double_faults": _first_int(
            raw,
            ["p1_double_faults", "p1_double_fault", "p1_df", "player1_double_faults", "player1_df", "home_double_faults"],
        ),
        "player_b_double_faults": _first_int(
            raw,
            ["p2_double_faults", "p2_double_fault", "p2_df", "player2_double_faults", "player2_df", "away_double_faults"],
        ),
    }


def _first_int(raw: dict, keys: list[str]) -> int | None:
    for key in keys:
        number = _float_or_none(raw.get(key))
        if number is not None:
            return int(number)
    return None


def _score_from_espn_raw(raw: dict, match: dict) -> dict | None:
    competitors = raw.get("competitors")
    if not isinstance(competitors, list) or len(competitors) < 2:
        return None
    player_a = _espn_competitor_for_name(competitors, match.get("player_a_name"))
    player_b = _espn_competitor_for_name(competitors, match.get("player_b_name"))
    if not player_a or not player_b:
        return None
    a_lines = _espn_linescores(player_a)
    b_lines = _espn_linescores(player_b)
    sets = []
    if a_lines and b_lines and len(a_lines) == len(b_lines):
        sets = [{"player_a_games": int(a), "player_b_games": int(b)} for a, b in zip(a_lines, b_lines)]
    if sets:
        payload = _score_summary(sets, "espn_linescores")
        payload.update(_espn_stat_payload(player_a, player_b))
        return payload
    player_a_sets = _float_or_none(player_a.get("score"))
    player_b_sets = _float_or_none(player_b.get("score"))
    if player_a_sets is None or player_b_sets is None:
        return None
    payload = {
        "player_a_sets": int(player_a_sets),
        "player_b_sets": int(player_b_sets),
        "total_sets": int(player_a_sets + player_b_sets),
        "player_a_games": None,
        "player_b_games": None,
        "sets": [],
        "source": "espn_set_score",
    }
    payload.update(_espn_stat_payload(player_a, player_b))
    return payload


def _score_summary(sets: list[dict], source: str) -> dict:
    player_a_sets = sum(1 for item in sets if int(item["player_a_games"]) > int(item["player_b_games"]))
    player_b_sets = sum(1 for item in sets if int(item["player_b_games"]) > int(item["player_a_games"]))
    return {
        "player_a_sets": player_a_sets,
        "player_b_sets": player_b_sets,
        "total_sets": player_a_sets + player_b_sets,
        "player_a_games": sum(int(item["player_a_games"]) for item in sets),
        "player_b_games": sum(int(item["player_b_games"]) for item in sets),
        "sets": sets,
        "source": source,
    }


def _espn_competitor_for_name(competitors: list[dict], name: str | None) -> dict | None:
    for competitor in competitors:
        athlete = competitor.get("athlete") or {}
        if same_player_name(athlete.get("displayName"), name) or same_player_name(athlete.get("shortName"), name):
            return competitor
    return None


def _espn_stat_payload(player_a: dict, player_b: dict) -> dict:
    return {
        "player_a_aces": _espn_stat_value(player_a, {"aces", "ace"}),
        "player_b_aces": _espn_stat_value(player_b, {"aces", "ace"}),
        "player_a_double_faults": _espn_stat_value(player_a, {"double faults", "double_faults", "doublefaults"}),
        "player_b_double_faults": _espn_stat_value(player_b, {"double faults", "double_faults", "doublefaults"}),
    }


def _espn_stat_value(competitor: dict, names: set[str]) -> int | None:
    stats = competitor.get("statistics") or competitor.get("stats") or []
    if not isinstance(stats, list):
        return None
    for item in stats:
        if not isinstance(item, dict):
            continue
        label = str(item.get("name") or item.get("displayName") or item.get("label") or "").lower().replace("_", " ")
        if label in names:
            value = item.get("value", item.get("displayValue"))
            number = _float_or_none(value)
            return int(number) if number is not None else None
    return None


def _espn_linescores(competitor: dict) -> list[int]:
    rows = competitor.get("linescores")
    if not isinstance(rows, list):
        return []
    values = []
    for row in rows:
        value = row.get("value") if isinstance(row, dict) else None
        if value is None and isinstance(row, dict):
            value = row.get("displayValue")
        number = _float_or_none(value)
        if number is None:
            return []
        values.append(int(number))
    return values


def _match_by_names(conn, match_date: str, player_name: str, opponent_name: str):
    rows = conn.execute(
        """
        SELECT m.id, m.player_a_id, m.player_b_id, pa.name AS player_a_name, pb.name AS player_b_name
        FROM matches m
        JOIN players pa ON pa.id = m.player_a_id
        JOIN players pb ON pb.id = m.player_b_id
        WHERE m.match_date = ?
        """,
        (match_date,),
    ).fetchall()
    best_row = None
    best_score = 0.0
    for row in rows:
        score, _direction = match_pair_score(player_name, opponent_name, row["player_a_name"], row["player_b_name"])
        if score > best_score:
            best_row = row
            best_score = score
    if best_score < MIN_RESULT_MATCH_SCORE:
        return None
    return best_row


def _same_name(left: str | None, right: str | None) -> bool:
    return same_player_name(left, right)


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ensure_tracking_schema() -> None:
    with get_connection() as conn:
        ledger_columns = {row["name"] for row in conn.execute("PRAGMA table_info(bet_ledger)").fetchall()}
        for name, ddl in {
            "market_key": "ALTER TABLE bet_ledger ADD COLUMN market_key TEXT",
            "market_name": "ALTER TABLE bet_ledger ADD COLUMN market_name TEXT",
            "tier": "ALTER TABLE bet_ledger ADD COLUMN tier TEXT",
            "model_probability": "ALTER TABLE bet_ledger ADD COLUMN model_probability REAL",
            "edge": "ALTER TABLE bet_ledger ADD COLUMN edge REAL",
            "confidence": "ALTER TABLE bet_ledger ADD COLUMN confidence INTEGER",
        }.items():
            if name not in ledger_columns:
                conn.execute(ddl)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clv_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                selection_side TEXT,
                market_key TEXT NOT NULL,
                market_name TEXT NOT NULL,
                market_line REAL,
                tier TEXT NOT NULL,
                model_probability REAL,
                edge REAL,
                confidence INTEGER,
                odds_taken REAL NOT NULL,
                closing_odds REAL,
                clv REAL,
                result_status TEXT NOT NULL,
                profit_loss_units REAL,
                recorded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(recommendation_type, source_id)
            )
            """
        )
        tracker_columns = {row["name"] for row in conn.execute("PRAGMA table_info(clv_tracker)").fetchall()}
        if "market_line" not in tracker_columns:
            conn.execute("ALTER TABLE clv_tracker ADD COLUMN market_line REAL")
        result_columns = {row["name"] for row in conn.execute("PRAGMA table_info(match_results)").fetchall()}
        if "score_json" not in result_columns:
            conn.execute("ALTER TABLE match_results ADD COLUMN score_json TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS combo_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combo_key TEXT NOT NULL,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                match_label TEXT NOT NULL,
                tier TEXT NOT NULL,
                legs_json TEXT NOT NULL,
                combo_odds REAL NOT NULL,
                adjusted_confidence INTEGER,
                adjusted_edge REAL,
                stake_units REAL NOT NULL,
                result_status TEXT NOT NULL,
                profit_loss_units REAL,
                recorded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                settled_at TEXT,
                UNIQUE(combo_key)
            )
            """
        )
