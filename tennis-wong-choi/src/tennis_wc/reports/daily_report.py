from __future__ import annotations

from itertools import combinations
import json
import math
import re
from pathlib import Path

from tennis_wc.betting import combos as combo_engine
from tennis_wc.betting.combos import Leg
from tennis_wc.betting.segment_risk import apply_segment_risk as _apply_segment_risk
from tennis_wc.betting.segment_risk import segment_risk as _segment_risk
from tennis_wc.betting.staking import kelly_stake_units
from tennis_wc.config import get_settings
from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.features.market import implied_probability
from tennis_wc.modelling import market_models
from tennis_wc.modelling import set_distribution
from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_competition_meta


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def latest_predictions_for_date(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH BestLevels AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY tournament_id, tour 
                           ORDER BY (source_provider = 'curated_tournament_metadata') DESC, (level != 'UNKNOWN' AND level != '未確認') DESC, (surface IS NOT NULL) DESC, id DESC
                       ) as rn
                FROM tournament_levels
            )
            SELECT
                p.*,
                m.match_date,
                m.round,
                m.tour,
                t.name AS tournament_name,
                tl.level,
                tl.surface,
                tl.source_provider AS metadata_source,
                pa.name AS player_a_name,
                pb.name AS player_b_name,
                (
                    SELECT mo.selection_side
                    FROM market_odds_snapshots mo
                    WHERE mo.match_id = m.id
                      AND mo.market_key = 'match_winner'
                      AND lower(trim(mo.selection_name)) = lower(trim(p.selection_name))
                    ORDER BY mo.id DESC
                    LIMIT 1
                ) AS mapped_selection_side,
                (
                    SELECT mo.odds
                    FROM market_odds_snapshots mo
                    WHERE mo.match_id = m.id
                      AND mo.market_key = 'match_winner'
                      AND lower(trim(mo.selection_name)) = lower(trim(p.selection_name))
                    ORDER BY mo.id DESC
                    LIMIT 1
                ) AS mapped_selection_odds
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN BestLevels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour AND tl.rn = 1
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            WHERE m.match_date = ?
              AND EXISTS (
                SELECT 1
                FROM odds_snapshots o
                WHERE o.match_id = m.id
                  AND o.source_provider = 'sportsbet'
              )
              AND p.id IN (
                SELECT MAX(id)
                FROM predictions
                GROUP BY match_id
              )
            ORDER BY p.decision, p.edge DESC
            """,
            (match_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def analysis_output_dir(match_date: str) -> Path:
    return PROJECT_ROOT / f"{match_date} Tennis Analysis"


def generate_daily_report(match_date: str, output_dir: str | Path | None = None) -> Path:
    rows = latest_predictions_for_date(match_date)
    source_status = source_status_for_date(match_date)
    unanalysed = unanalysed_sportsbet_rows(match_date)
    output_dir = Path(output_dir) if output_dir is not None else analysis_output_dir(match_date)
    output_path = output_dir / "Tennis_Daily_Report.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_daily_report(match_date, rows, source_status, unanalysed), encoding="utf-8")
    refresh_market_predictions(match_date, rows)
    export_market_odds_report(match_date, output_dir)
    export_banker_report(match_date, output_dir, banker_market_predictions_for_date(match_date))
    # Grade any now-settleable ace props (live-validation of the prop engine).
    try:
        from tennis_wc.props.settlement import settle_props
        settle_props(get_connection())
    except Exception:
        pass
    return output_path


def export_banker_report(match_date: str, output_dir: str | Path | None = None, rows: list[dict] | None = None) -> Path:
    output_dir = Path(output_dir) if output_dir is not None else analysis_output_dir(match_date)
    output_path = output_dir / f"{_report_date_prefix(match_date)} Tennis Banker Report.txt"
    legacy_path = output_dir / "Tennis_Banker_Report.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = rows if rows is not None else banker_market_predictions_for_date(match_date)
    content = render_banker_report(match_date, rows)
    output_path.write_text(content, encoding="utf-8")
    legacy_path.write_text(content, encoding="utf-8")
    return output_path


def _report_date_prefix(match_date: str) -> str:
    parts = str(match_date).split("-")
    if len(parts) >= 3:
        return f"{parts[1]}-{parts[2]}"
    return str(match_date)


def export_market_odds_report(match_date: str, output_dir: str | Path | None = None) -> Path:
    output_dir = Path(output_dir) if output_dir is not None else analysis_output_dir(match_date)
    output_path = output_dir / "Tennis_Market_Odds.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_market_odds_report(match_date), encoding="utf-8")
    return output_path


def source_status_for_date(match_date: str) -> dict:
    with get_connection() as conn:
        latest_run_errors = conn.execute(
            """
            SELECT response_json
            FROM raw_api_responses
            WHERE provider_name = 'tennis_wc_pipeline'
              AND entity_type = 'run_daily_source_errors'
              AND entity_external_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        latest_raw = conn.execute(
            """
            SELECT id
            FROM raw_api_responses
            WHERE entity_type = 'odds'
              AND entity_external_id = ?
              AND provider_name = 'sportsbet'
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        raw_id = int(latest_raw["id"]) if latest_raw else None
        sportsbet = conn.execute(
            """
            SELECT COUNT(*) AS odds_rows, COUNT(match_id) AS linked_rows, MAX(fetched_at) AS latest_fetch
            FROM odds_snapshots
            WHERE source_provider = 'sportsbet' AND raw_response_id = ?
            """,
            (raw_id,),
        ).fetchone()
        bsd_error = conn.execute(
            """
            SELECT response_json
            FROM raw_api_responses
            WHERE provider_name = 'bsd_tennis' AND status_code >= 400
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        market_count = conn.execute(
            """
            SELECT COUNT(*) AS rows, COUNT(DISTINCT market_key) AS markets
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            WHERE m.match_date = ?
              AND mo.id IN (
                SELECT MAX(mo2.id)
                FROM market_odds_snapshots mo2
                JOIN matches m2 ON m2.id = mo2.match_id
                WHERE m2.match_date = ?
                GROUP BY mo2.match_id, mo2.market_key, mo2.market_name, mo2.selection_name, COALESCE(mo2.line, -999999)
              )
            """,
            (match_date, match_date),
        ).fetchone()
        ranking_status = {
            tour: conn.execute(
                """
                SELECT status_code, response_json, fetched_at
                FROM raw_api_responses
                WHERE entity_type = 'ranking'
                  AND entity_external_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (tour,),
            ).fetchone()
            for tour in ("ATP", "WTA")
        }
    # The run-daily record is either a bare list (legacy) or {"mode", "errors"}.
    run_mode = None
    run_errors: list = []
    if latest_run_errors:
        payload = json.loads(latest_run_errors["response_json"])
        if isinstance(payload, dict):
            run_mode = payload.get("mode")
            run_errors = payload.get("errors") or []
        else:
            run_errors = payload
    return {
        "sportsbet_odds_rows": int(sportsbet["odds_rows"] or 0),
        "sportsbet_linked_rows": int(sportsbet["linked_rows"] or 0),
        "sportsbet_latest_fetch": sportsbet["latest_fetch"],
        "bsd_fixture_status": _bsd_status(bsd_error["response_json"] if bsd_error else None),
        "fixture_note": "Sportsbet odds-backed provisional fixtures enabled; unconfirmed competitions remain NO_BET.",
        "history_source": "Jeff Sackmann ATP/WTA snapshots + local Elo cache",
        "ranking_source_note": _ranking_source_note(ranking_status),
        "market_odds_note": f"{int(market_count['rows'] or 0)} selections across {int(market_count['markets'] or 0)} market types. Non-match-winner markets are review-only.",
        "run_mode": run_mode,
        "latest_run_errors": run_errors,
    }


def clear_pipeline_source_errors(match_date: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM raw_api_responses
            WHERE provider_name = 'tennis_wc_pipeline'
              AND entity_type = 'run_daily_source_errors'
              AND entity_external_id = ?
            """,
            (match_date,),
        )


def _ranking_source_note(rows: dict) -> str:
    parts = []
    for tour in ("ATP", "WTA"):
        row = rows.get(tour)
        if not row:
            parts.append(f"{tour}: no recent ranking refresh record")
            continue
        status = int(row["status_code"])
        if status == 206:
            payload = json.loads(row["response_json"])
            latest = payload.get("cached_latest_ranking_date") or "unknown"
            count = payload.get("cached_rows") or 0
            parts.append(f"{tour}: cached fallback ({count} rows, latest {latest})")
        elif status >= 400:
            parts.append(f"{tour}: refresh failed ({status})")
        elif status == 204:
            parts.append(f"{tour}: live refresh returned no rows")
        else:
            payload = json.loads(row["response_json"])
            if isinstance(payload, list) and payload:
                latest = max(str(item.get("ranking_date") or "") for item in payload) or "unknown"
                source = (payload[0].get("raw") or {}).get("source") or "provider"
                parts.append(f"{tour}: live refresh OK ({len(payload)} rows, latest {latest}, {source})")
            else:
                parts.append(f"{tour}: live refresh OK")
    return "; ".join(parts)


def unanalysed_sportsbet_rows(match_date: str) -> list[dict]:
    with get_connection() as conn:
        raw_rows = conn.execute(
            """
            SELECT response_json
            FROM raw_api_responses
            WHERE entity_type = 'odds'
              AND entity_external_id = ?
              AND provider_name = 'sportsbet'
            ORDER BY id DESC
            LIMIT 1
            """,
            (match_date,),
        ).fetchone()
        linked = {
            row["event_id"]
            for row in conn.execute(
                "SELECT DISTINCT event_id FROM odds_snapshots WHERE match_id IS NOT NULL"
            ).fetchall()
        }
    if not raw_rows:
        return []
    rows = json.loads(raw_rows["response_json"])
    unanalysed = []
    for row in rows:
        if str(row.get("event_id")) in linked:
            continue
        meta = sportsbet_competition_meta(row.get("competition"))
        unanalysed.append(
            {
                "competition": row.get("competition") or "UNKNOWN",
                "match": f"{row.get('player_a_name')} v {row.get('player_b_name')}",
                "reason": meta.reason or "not_linked_to_feature_snapshot",
                "event_url": row.get("event_url"),
            }
        )
    return unanalysed


def refresh_market_predictions(match_date: str, rows: list[dict] | None = None) -> None:
    _ensure_market_predictions_table()
    rows = rows if rows is not None else latest_predictions_for_date(match_date)
    prediction_by_match = {int(row["match_id"]): row for row in rows}
    market_rows = _market_odds_base_rows(match_date)
    grouped = _group_market_rows(market_rows)
    now = utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM market_predictions
            WHERE match_id IN (
                SELECT id FROM matches WHERE match_date = ?
            )
            """,
            (match_date,),
        )
        for key, group_rows in grouped.items():
            no_vig_by_row = _no_vig_probabilities(group_rows)
            for row in group_rows:
                prediction = _price_market_selection(row, prediction_by_match.get(int(row["match_id"])), no_vig_by_row.get(int(row["id"])))
                conn.execute(
                    """
                    INSERT INTO market_predictions (
                        match_id, market_odds_snapshot_id, market_key, market_name,
                        selection_name, selection_side, line, odds, model_status,
                        model_probability, no_vig_market_probability, edge,
                        minimum_acceptable_odds, decision, banker_eligible,
                        confidence, risk, reason, pricing_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["match_id"],
                        row["id"],
                        row["market_key"],
                        row["market_name"],
                        row["selection_name"],
                        row["selection_side"],
                        row["line"],
                        row["odds"],
                        prediction["model_status"],
                        prediction["model_probability"],
                        prediction["no_vig_market_probability"],
                        prediction["edge"],
                        prediction["minimum_acceptable_odds"],
                        prediction["decision"],
                        1 if prediction["banker_eligible"] else 0,
                        prediction["confidence"],
                        prediction["risk"],
                        prediction["reason"],
                        json.dumps(prediction, sort_keys=True),
                        now,
                    ),
                )


def banker_market_predictions_for_date(match_date: str) -> list[dict]:
    _ensure_market_predictions_table()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                mp.*,
                t.name AS tournament_name,
                p1.name AS player_a_name,
                p2.name AS player_b_name
            FROM market_predictions mp
            JOIN matches m ON m.id = mp.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            JOIN players p1 ON p1.id = m.player_a_id
            JOIN players p2 ON p2.id = m.player_b_id
            WHERE m.match_date = ?
            ORDER BY mp.match_id, mp.market_key, mp.line, mp.selection_name
            """,
            (match_date,),
        ).fetchall()
    return [dict(row) for row in rows]


def _ensure_market_predictions_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                market_odds_snapshot_id INTEGER,
                market_key TEXT NOT NULL,
                market_name TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                selection_side TEXT,
                line REAL,
                odds REAL NOT NULL,
                model_status TEXT NOT NULL,
                model_probability REAL,
                no_vig_market_probability REAL,
                edge REAL,
                minimum_acceptable_odds REAL,
                decision TEXT NOT NULL,
                banker_eligible INTEGER NOT NULL,
                confidence INTEGER NOT NULL,
                risk TEXT NOT NULL,
                reason TEXT,
                pricing_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _market_odds_base_rows(match_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH BestLevels AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY tournament_id, tour
                           ORDER BY (source_provider = 'curated_tournament_metadata') DESC, (level != 'UNKNOWN' AND level != '未確認') DESC, (surface IS NOT NULL) DESC, id DESC
                       ) AS rn
                FROM tournament_levels
            )
            SELECT
                mo.*,
                t.name AS tournament_name,
                tl.level AS tournament_level,
                tl.surface AS tournament_surface,
                p1.name AS player_a_name,
                p2.name AS player_b_name
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            LEFT JOIN BestLevels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour AND tl.rn = 1
            JOIN players p1 ON p1.id = m.player_a_id
            JOIN players p2 ON p2.id = m.player_b_id
            WHERE m.match_date = ?
              AND mo.id IN (
                SELECT MAX(mo2.id)
                FROM market_odds_snapshots mo2
                JOIN matches m2 ON m2.id = mo2.match_id
                WHERE m2.match_date = ?
                GROUP BY mo2.match_id, mo2.market_key, mo2.market_name, mo2.selection_name, COALESCE(mo2.line, -999999)
              )
            ORDER BY t.name, p1.name, p2.name, mo.market_key, mo.market_name, mo.line, mo.selection_name
            """,
            (match_date, match_date),
        ).fetchall()
    return [dict(row) for row in rows]


def _group_market_rows(rows: list[dict]) -> dict[tuple, list[dict]]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["match_id"], row["market_key"], row["market_name"], row["line"])
        grouped.setdefault(key, []).append(row)
    return grouped


def _no_vig_probabilities(rows: list[dict]) -> dict[int, float]:
    """Proportional de-vig across a group of mutually exclusive selections.

    Was 2-way only, which left every multiway market (e.g. full-match Set
    Betting: 4 outcomes) with no fair price -> edge None -> never shadow
    tracked. For 2 selections this is identical to remove_vig_two_way."""
    if len(rows) < 2:
        return {}
    implied = [implied_probability(float(row["odds"])) for row in rows]
    total = sum(implied)
    if total <= 0:
        return {}
    return {int(row["id"]): imp / total for row, imp in zip(rows, implied)}


def _price_market_selection(row: dict, prediction_row: dict | None, no_vig_probability: float | None) -> dict:
    unsupported = {
        "model_status": "ODDS_ONLY",
        "model_probability": None,
        "no_vig_market_probability": no_vig_probability,
        "edge": None,
        "minimum_acceptable_odds": None,
        "decision": "UNSUPPORTED_FOR_BANKER",
        "banker_eligible": False,
        "confidence": 0,
        "risk": "High",
        "reason": "unsupported_player_props_model_not_built",
    }
    if row["market_key"] != "match_winner":
        if prediction_row is None:
            return unsupported | {"reason": "missing_match_winner_prediction"}
        if prediction_row.get("decision") != "BET":
            return unsupported | {"model_status": "UNSUPPORTED_FOR_BANKER", "reason": "original_prediction_failed_safety_gate"}
        derived = _derived_market_probability(row, prediction_row, no_vig_probability)
        if derived is None:
            prop = _ace_market_probability(row)
            if prop is None:
                return unsupported
            return _market_decision(row, prediction_row, prop["probability"], no_vig_probability, "PROP_MODEL", prop["reason"])
        return _market_decision(row, prediction_row, derived["probability"], no_vig_probability, "DERIVED_MODEL", derived["reason"])
    if prediction_row is None:
        return unsupported | {"reason": "missing_match_winner_prediction"}
    if not _match_winner_mapping_verified(row):
        return unsupported | {"model_status": "UNSUPPORTED_FOR_BANKER", "reason": "odds_selection_mapping_failed"}

    payload = _pricing_payload(prediction_row)
    model = payload.get("pricing", {}).get("model", {})
    selection_side = _selection_side_for_market_row(row)
    if selection_side == "player_a":
        model_probability = model.get("player_a_probability")
    elif selection_side == "player_b":
        model_probability = model.get("player_b_probability")
    else:
        model_probability = None
    if model_probability is None or no_vig_probability is None:
        return unsupported | {"model_status": "UNSUPPORTED_FOR_BANKER", "reason": "missing_model_or_market_probability"}
    if _same_name(str(row.get("selection_name") or ""), str(prediction_row.get("selection_name") or "")) and prediction_row.get("decision") != "BET":
        return unsupported | {
            "model_status": "MODELLED",
            "model_probability": round(float(model_probability), 6),
            "no_vig_market_probability": round(float(no_vig_probability), 6),
            "edge": round(float(model_probability) - float(no_vig_probability), 6),
            "minimum_acceptable_odds": None,
            "decision": "NO_BET",
            "banker_eligible": False,
            "confidence": int(prediction_row.get("confidence") or 0),
            "risk": "High",
            "reason": "original_prediction_failed_safety_gate",
        }

    return _market_decision(row, prediction_row, float(model_probability), no_vig_probability, "MODELLED", "match_winner_model")


def _market_decision(
    row: dict,
    prediction_row: dict,
    model_probability: float,
    no_vig_probability: float | None,
    model_status: str,
    model_reason: str,
) -> dict:
    if no_vig_probability is None:
        return {
            "model_status": "UNSUPPORTED_FOR_BANKER",
            "model_probability": round(model_probability, 6),
            "no_vig_market_probability": None,
            "edge": None,
            "minimum_acceptable_odds": None,
            "decision": "UNSUPPORTED_FOR_BANKER",
            "banker_eligible": False,
            "confidence": int(prediction_row.get("confidence") or 0),
            "risk": "High",
            "reason": "missing_model_or_market_probability",
        }
    edge = model_probability - float(no_vig_probability)
    min_edge = get_settings().min_edge_match_winner
    minimum_acceptable = round(1 / max(model_probability - min_edge, 0.01), 4)
    odds = float(row["odds"])
    base_confidence = int(prediction_row.get("confidence") or 0)
    # Cap the edge contribution (see bet_filter: perceived edge has no backtested
    # predictive value, so it must not inflate confidence; base_confidence is
    # already edge-aware, so this avoids double-counting a worthless signal).
    confidence = max(0, min(100, int(base_confidence + min(max(edge, 0), 0.10) * 100)))
    if model_status == "PROP_MODEL":
        return {
            "model_status": model_status,
            "model_probability": round(model_probability, 6),
            "no_vig_market_probability": round(float(no_vig_probability), 6),
            "edge": round(edge, 6),
            "minimum_acceptable_odds": minimum_acceptable,
            "decision": "MODEL_REVIEW",
            "banker_eligible": False,
            "confidence": confidence,
            "risk": "Medium",
            "reason": "ace_prop_model_review",
            "tier": "PROP_MODEL_REVIEW",
            "reason_score": _reason_score(model_probability, edge, odds, confidence, model_status),
        }
    upgrade_gate = _market_upgrade_gate(str(row.get("market_key") or ""), model_status)
    if not upgrade_gate["banker_allowed"]:
        return {
            "model_status": model_status,
            "model_probability": round(model_probability, 6),
            "no_vig_market_probability": round(float(no_vig_probability), 6),
            "edge": round(edge, 6),
            "minimum_acceptable_odds": minimum_acceptable,
            "decision": "MODEL_REVIEW",
            "banker_eligible": False,
            "confidence": confidence,
            "risk": "Medium",
            "reason": upgrade_gate["reason"],
            "tier": upgrade_gate["tier"],
            "reason_score": _reason_score(model_probability, edge, odds, confidence, model_status),
        }
    tier = _banker_tier(model_probability, edge, odds, confidence, model_status)
    if tier == "CORE_BANKER" and not upgrade_gate["core_allowed"]:
        tier = "VALUE_BANKER"
    if tier == "CORE_BANKER" and not _clv_history_allows_core(model_status):
        tier = "VALUE_BANKER"
    if tier == "VALUE_BANKER" and _stable_value_history_allows(model_status, str(row.get("market_key") or "")):
        tier = "STABLE_VALUE_BANKER"
    downgrade_reason = _tier_downgrade_reason(tier, model_status, str(row.get("market_key") or ""), model_probability)
    if downgrade_reason:
        return {
            "model_status": model_status,
            "model_probability": round(model_probability, 6),
            "no_vig_market_probability": round(float(no_vig_probability), 6),
            "edge": round(edge, 6),
            "minimum_acceptable_odds": minimum_acceptable,
            "decision": "MODEL_REVIEW",
            "banker_eligible": False,
            "confidence": confidence,
            "risk": "High",
            "reason": downgrade_reason,
            "tier": f"{tier}_REVIEW",
            "reason_score": _reason_score(model_probability, edge, odds, confidence, model_status),
        }
    decision = "BET" if tier in {"CORE_BANKER", "STABLE_VALUE_BANKER", "VALUE_BANKER"} and odds >= minimum_acceptable else "NO_BET"
    reason = _banker_reason(model_reason, tier, model_probability, edge, odds, confidence, odds >= minimum_acceptable)
    risk = "Low" if tier in {"CORE_BANKER", "STABLE_VALUE_BANKER"} else ("Medium" if tier in {"VALUE_BANKER", "NEAR_BANKER_WATCH"} or decision == "BET" else "High")
    return {
        "model_status": model_status,
        "model_probability": round(model_probability, 6),
        "no_vig_market_probability": round(float(no_vig_probability), 6),
        "edge": round(edge, 6),
        "minimum_acceptable_odds": minimum_acceptable,
        "decision": decision,
        "banker_eligible": decision == "BET" and tier in {"CORE_BANKER", "STABLE_VALUE_BANKER", "VALUE_BANKER"},
        "confidence": confidence,
        "risk": risk,
        "reason": reason,
        "tier": tier,
        "reason_score": _reason_score(model_probability, edge, odds, confidence, model_status),
    }


def _derived_market_probability(row: dict, prediction_row: dict, no_vig_probability: float | None) -> dict | None:
    payload = _pricing_payload(prediction_row)
    model = payload.get("pricing", {}).get("model", {})
    p_a = model.get("player_a_probability")
    p_b = model.get("player_b_probability")
    if p_a is None or p_b is None:
        return None
    p_a = float(p_a)
    p_b = float(p_b)
    key = str(row.get("market_key") or "")
    name = str(row.get("market_name") or "").lower()
    selection = str(row.get("selection_name") or "")
    line = row.get("line")

    if key in {"to_win_1st_set", "winner_related"} or "set winner" in name:
        side = _selection_side_for_market_row(row)
        if side in {"player_a", "player_b"}:
            base = p_a if side == "player_a" else p_b
            # Empirical set-distribution table (68,876 BO3 matches) replaced the
            # old hand-picked 0.78 compression — holdout Brier win (2026-07-12).
            return {"probability": _clamp_probability(set_distribution.first_set_win_probability(base)), "reason": "derived_set_winner_from_set_distribution"}

    if _is_to_win_at_least_one_set_market(key, name):
        side = _selection_side_for_market_row(row)
        is_yes = _selection_is_yes_no(selection)
        if side in {"player_a", "player_b"} and is_yes is not None:
            base = p_a if side == "player_a" else p_b
            probability = set_distribution.win_at_least_one_set_probability(base)
            if not is_yes:
                probability = 1 - probability
            return {"probability": _clamp_probability(probability), "reason": "derived_at_least_one_set_from_set_distribution"}

    set_betting = _set_betting_probability(row, p_a, p_b)
    if set_betting is not None:
        return set_betting

    if key == "game_handicap":
        side = _selection_side_for_market_row(row)
        if side in {"player_a", "player_b"} and line is not None:
            context = _match_games_context(int(row["match_id"]))
            if context is not None:
                base = p_a if side == "player_a" else p_b
                probability = market_models.game_handicap_cover_probability(
                    float(line), base >= 0.5, context["hold_a"], context["hold_b"], p_a, context["best_of"]
                )
                return {"probability": _clamp_probability(probability), "reason": "derived_game_handicap_from_hold_rates"}

    if key in {"game_handicap", "set_handicap"}:
        side = _selection_side_for_market_row(row)
        if side in {"player_a", "player_b"} and line is not None:
            base = p_a if side == "player_a" else p_b
            line_value = float(line)
            if line_value < 0:
                probability = base - min(abs(line_value) * 0.035, 0.22)
            else:
                probability = base + min(abs(line_value) * 0.025, 0.18)
            return {"probability": _clamp_probability(probability), "reason": "derived_handicap_from_match_model"}

    if key == "total_games" or ("total" in name and "game" in name):
        is_over = _selection_is_yes_or_over(selection)
        if is_over is not None and line is not None:
            context = _match_games_context(int(row["match_id"]))
            if context is not None:
                set_index = _total_games_set_index(name)
                if set_index is not None:
                    # Per-set total games (e.g. "Set 1 Total Games O/U 9.5").
                    expected = market_models.expected_games_per_set(context["hold_a"], context["hold_b"])
                    over = market_models.set_total_games_over_probability(float(line), expected)
                    reason = "derived_set_total_games_from_hold_rates"
                else:
                    expected = market_models.expected_total_games(
                        context["hold_a"], context["hold_b"], p_a, context["best_of"]
                    )
                    over = market_models.total_games_over_probability(float(line), expected, context["best_of"])
                    reason = "derived_total_games_from_hold_rates"
                probability = over if is_over else 1 - over
                return {"probability": _clamp_probability(probability), "reason": reason}

    if key in {"total_sets", "both_players_to_win_a_set_yes_no"} or "both players to win a set" in name:
        line_value = float(line) if line is not None else 2.5
        if line_value < 3.5:
            # BO3: P(over 2.5 sets) = P(goes three) from the empirical set
            # distribution — the old competitiveness heuristic said up to 62%
            # three-setters for coin-flips; reality is ~38% (straight sets are
            # far more common than independence or the heuristic assumed).
            over_probability = _clamp_probability(set_distribution.three_sets_probability(p_a), 0.05, 0.60)
            is_yes_or_over = _selection_is_yes_or_over(selection)
            if is_yes_or_over is not None:
                probability = over_probability if is_yes_or_over else 1 - over_probability
                return {"probability": _clamp_probability(probability), "reason": "derived_total_sets_from_set_distribution"}
        competitiveness = 1 - abs(p_a - p_b)
        if line_value >= 4.5:
            over_probability = _clamp_probability(0.06 + competitiveness * 0.22, 0.04, 0.34)
        elif line_value >= 3.5:
            over_probability = _clamp_probability(0.16 + competitiveness * 0.34, 0.10, 0.56)
        else:
            over_probability = _clamp_probability(0.20 + competitiveness * 0.42, 0.12, 0.72)
        is_yes_or_over = _selection_is_yes_or_over(selection)
        if is_yes_or_over is not None:
            probability = over_probability if is_yes_or_over else 1 - over_probability
            return {"probability": _clamp_probability(probability), "reason": "derived_total_sets_from_competitiveness"}

    return None


def _ace_market_probability(row: dict) -> dict | None:
    key = str(row.get("market_key") or "").lower()
    name = str(row.get("market_name") or "").lower()
    if "ace" not in key and "ace" not in name:
        return None
    line = row.get("line")
    if line is None:
        return None
    selection = str(row.get("selection_name") or "")
    is_over = _selection_is_yes_or_over(selection)
    if is_over is None:
        return None
    match_id = int(row["match_id"])
    player_id = _ace_market_player_id(row)
    mean = _historical_ace_mean(match_id, player_id)
    if mean is None:
        return None
    over_probability = 1 - _poisson_cdf(int(math.floor(float(line))), mean)
    probability = over_probability if is_over else 1 - over_probability
    return {"probability": _clamp_probability(probability, 0.02, 0.98), "reason": "ace_prop_model_review"}


def _ace_market_player_id(row: dict) -> int | None:
    market = f"{row.get('market_key') or ''} {row.get('market_name') or ''}".lower()
    player_a = str(row.get("player_a_name") or "")
    player_b = str(row.get("player_b_name") or "")
    with get_connection() as conn:
        match = conn.execute("SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (row["match_id"],)).fetchone()
    if _same_name(player_a, market) or _same_name(player_a.replace("-", " "), market):
        return int(match["player_a_id"])
    if _same_name(player_b, market) or _same_name(player_b.replace("-", " "), market):
        return int(match["player_b_id"])
    if player_a.lower() in market:
        return int(match["player_a_id"])
    if player_b.lower() in market:
        return int(match["player_b_id"])
    return None


def _historical_ace_mean(match_id: int, player_id: int | None) -> float | None:
    with get_connection() as conn:
        if not _has_history_prop_columns(conn):
            return None
        match = conn.execute("SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)).fetchone()
        if player_id is None:
            rows = conn.execute(
                """
                SELECT ace_count
                FROM player_match_history
                WHERE player_id IN (?, ?)
                  AND ace_count IS NOT NULL
                ORDER BY match_date DESC
                LIMIT 40
                """,
                (match["player_a_id"], match["player_b_id"]),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ace_count
                FROM player_match_history
                WHERE player_id = ?
                  AND ace_count IS NOT NULL
                ORDER BY match_date DESC
                LIMIT 25
                """,
                (player_id,),
            ).fetchall()
    values = [float(row["ace_count"]) for row in rows if row["ace_count"] is not None]
    if len(values) < 10:
        return None
    context = _match_games_context(match_id)
    tour = context["tour"] if context else None
    best_of = context["best_of"] if context else 3
    # Shrink toward the tour population mean (avoids over-confident means from
    # short histories) and scale for best-of-5.
    per_player = market_models.shrunk_ace_mean(values, tour, best_of)
    if per_player is None:
        return None
    if player_id is None:
        # total-match aces = both players serving.
        return max(0.1, per_player * 2)
    return per_player


def _has_history_prop_columns(conn) -> bool:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(player_match_history)").fetchall()}
    return "ace_count" in columns


def _poisson_cdf(k: int, mean: float) -> float:
    total = 0.0
    for i in range(max(0, k) + 1):
        total += math.exp(-mean) * mean**i / math.factorial(i)
    return max(0.0, min(1.0, total))


def _selection_is_yes_or_over(selection: str) -> bool | None:
    lowered = selection.lower()
    if "over" in lowered or lowered in {"yes", "3 sets", "4 sets", "5 sets"}:
        return True
    if "under" in lowered or lowered == "no":
        return False
    return None


def _selection_is_yes_no(selection: str) -> bool | None:
    tokens = str(selection or "").lower().split()
    if not tokens:
        return None
    if tokens[-1] == "yes":
        return True
    if tokens[-1] == "no":
        return False
    return None


def _is_to_win_at_least_one_set_market(market_key: str, market_name: str) -> bool:
    text = f"{market_key} {market_name}".lower().replace("_", " ")
    return "to win at least one set" in text or "to win at least 1 set" in text


# NOTE: the old hand-picked _win_at_least_one_set_probability heuristic was
# replaced by set_distribution.win_at_least_one_set_probability (2026-07-12).

_SET_BETTING_SCORE_RE = re.compile(r"\s+2-([01])\s*$")


def _set_betting_probability(row: dict, p_a: float, p_b: float) -> dict | None:
    """Full-match Set Betting (correct set score, BO3): '<Player> 2-0'/'2-1'.

    Priced from the empirical set-outcome distribution. Returns None for the
    other selections sharing the set_betting key (per-set correct GAME scores,
    BO5 3-x selections) — those stay unpriced/unrecorded."""
    if str(row.get("market_name") or "").strip().lower() != "set betting":
        return None
    selection = str(row.get("selection_name") or "")
    m = _SET_BETTING_SCORE_RE.search(selection)
    if not m:
        return None
    sets_lost = int(m.group(1))
    name = selection[: m.start()].strip()
    if _same_name(name, str(row.get("player_a_name") or "")):
        p_side = p_a
    elif _same_name(name, str(row.get("player_b_name") or "")):
        p_side = p_b
    else:
        return None
    probability = set_distribution.set_score_probability(p_side, sets_lost)
    if probability is None:
        return None
    return {
        "probability": _clamp_probability(probability, 0.02, 0.90),
        "reason": "derived_set_betting_from_set_distribution",
    }


def _banker_tier(probability: float, edge: float, odds: float, confidence: int, model_status: str) -> str:
    effective_probability = max(0.0, probability - _calibration_safety_margin(probability))
    if model_status == "DERIVED_MODEL":
        if effective_probability >= 0.68 and edge >= 0.06 and confidence >= 80 and odds <= 2.20:
            return "CORE_BANKER"
        if effective_probability >= 0.64 and edge >= 0.06 and confidence >= 74 and odds <= 2.8:
            return "VALUE_BANKER"
        if effective_probability >= 0.62 and edge >= 0.05 and confidence >= 76 and odds <= 2.60:
            return "NEAR_BANKER_WATCH"
        if odds >= 2.5 and edge >= 0.10:
            return "HIGH_ODDS_VALUE"
        return "NO_BET"
    if effective_probability >= 0.68 and edge >= 0.05 and confidence >= 80 and odds <= 2.20:
        return "CORE_BANKER"
    if effective_probability >= 0.56 and edge >= 0.05 and confidence >= 68:
        return "VALUE_BANKER"
    if effective_probability >= 0.62 and edge >= 0.035 and confidence >= 72 and odds <= 2.40:
        return "NEAR_BANKER_WATCH"
    if odds >= 2.5 and edge >= 0.08:
        return "HIGH_ODDS_VALUE"
    return "NO_BET"


def _calibration_safety_margin(probability: float) -> float:
    try:
        from tennis_wc.reports.calibration_report import banker_probability_safety_margin

        return banker_probability_safety_margin(probability)
    except Exception:
        return 0.0


def _market_upgrade_gate(market_key: str, model_status: str) -> dict:
    if model_status == "MODELLED":
        return {"banker_allowed": True, "core_allowed": True, "tier": "MODELLED", "reason": "modelled_market"}
    if model_status != "DERIVED_MODEL":
        return {"banker_allowed": False, "core_allowed": False, "tier": "MODEL_REVIEW", "reason": "model_not_ready_for_banker"}
    if not _settlement_supported_market_key(market_key):
        return {
            "banker_allowed": False,
            "core_allowed": False,
            "tier": "SETTLEMENT_NOT_SUPPORTED",
            "reason": "settlement_not_supported_for_market",
        }
    history = _market_validation_history(market_key)
    if history["settled"] < 20:
        return {
            "banker_allowed": False,
            "core_allowed": False,
            "tier": "MARKET_TRIAL",
            "reason": "settlement_supported_sample_building",
        }
    # CLV blocks only when NEGATIVE. Our "closing odds" are the last Sportsbet
    # scrape, so when a line never moves CLV is exactly 0.0 — that is "no line
    # movement information", not adverse evidence; requiring strictly-positive
    # CLV made graduation depend on noise (total_sets sat at ROI +18% with
    # avg_clv 0.0 and could never pass). ROI on settled shadow picks is the
    # real gate.
    if (history["avg_clv"] or 0) < 0 or (history["roi"] or 0) < 0:
        return {
            "banker_allowed": False,
            "core_allowed": False,
            "tier": "MARKET_REVIEW",
            "reason": "market_validation_not_positive_yet",
        }
    return {
        "banker_allowed": True,
        "core_allowed": history["settled"] >= 50,
        "tier": "VALIDATED_DERIVED_MARKET",
        "reason": "market_validation_positive",
    }


def _settlement_supported_market_keys() -> set[str]:
    # set_betting: only full-match "Set Betting" rows are ever PRICED (the
    # per-set correct-game-score rows sharing the key get no model probability,
    # so they never enter the shadow tracker), and those settle from
    # score_json set counts.
    return {"total_sets", "both_players_to_win_a_set_yes_no", "set_handicap", "game_handicap", "total_games", "to_win_1st_set", "winner_related", "set_betting"}


def _total_games_set_index(market_name: str) -> int | None:
    """Set index for a per-set total-games market, or None for the MATCH total.
    The total_games market_key mixes 'Set 1/2 Total Games' with full-match
    totals; they must be priced against per-set vs whole-match game counts."""
    text = market_name.lower()
    for token, idx in (("set 1", 0), ("1st set", 0), ("set 2", 1), ("2nd set", 1),
                       ("set 3", 2), ("3rd set", 2), ("set 4", 3), ("set 5", 4)):
        if token in text:
            return idx
    return None


def _match_games_context(match_id: int) -> dict | None:
    """Average hold rates for each player + match format, for the games models.
    Returns None if hold history is unavailable for either player."""
    with get_connection() as conn:
        match = conn.execute(
            "SELECT player_a_id, player_b_id, tour, tournament_id FROM matches WHERE id = ?",
            (match_id,),
        ).fetchone()
        if not match:
            return None

        def avg_hold(player_id: int) -> float | None:
            row = conn.execute(
                """
                SELECT AVG(hold_rate) AS h
                FROM player_match_history
                WHERE player_id = ? AND hold_rate IS NOT NULL
                """,
                (player_id,),
            ).fetchone()
            return float(row["h"]) if row and row["h"] is not None else None

        hold_a = avg_hold(int(match["player_a_id"]))
        hold_b = avg_hold(int(match["player_b_id"]))
        level_row = conn.execute(
            "SELECT level FROM tournament_levels WHERE tournament_id = ? AND tour = ? LIMIT 1",
            (match["tournament_id"], match["tour"]),
        ).fetchone()
    if hold_a is None or hold_b is None:
        return None
    # Only ATP Grand Slam main draw is best-of-5; everything else is best-of-3.
    level = str(level_row["level"] or "").upper() if level_row else ""
    best_of = 5 if str(match["tour"] or "").upper() == "ATP" and "GRAND_SLAM" in level else 3
    return {"hold_a": hold_a, "hold_b": hold_b, "best_of": best_of, "tour": match["tour"]}


def _settlement_supported_market_key(market_key: str) -> bool:
    return market_key in _settlement_supported_market_keys() or _is_to_win_at_least_one_set_market(market_key, "")


def _market_validation_history(market_key: str) -> dict:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS tracked,
                       SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                       AVG(clv) AS avg_clv,
                       SUM(COALESCE(profit_loss_units, 0)) AS profit
                FROM clv_tracker
                WHERE recommendation_type = 'MARKET_LEG'
                  AND market_key = ?
                  AND COALESCE(edge, 0) > 0
                """,
                (market_key,),
            ).fetchone()
    except Exception:
        return {"tracked": 0, "settled": 0, "avg_clv": None, "roi": None}
    settled = int(row["settled"] or 0) if row else 0
    profit = float(row["profit"] or 0) if row else 0.0
    return {
        "tracked": int(row["tracked"] or 0) if row else 0,
        "settled": settled,
        "avg_clv": float(row["avg_clv"]) if row and row["avg_clv"] is not None else None,
        "roi": profit / settled if settled else None,
    }


def _clv_history_allows_core(model_status: str) -> bool:
    tier = "CORE_BANKER"
    recommendation_type = "MARKET_LEG" if model_status == "DERIVED_MODEL" else "MATCH_PREDICTION"
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(clv) AS samples, AVG(clv) AS avg_clv
                FROM clv_tracker
                WHERE tier = ?
                  AND recommendation_type = ?
                  AND clv IS NOT NULL
                """,
                (tier, recommendation_type),
            ).fetchone()
    except Exception:
        return True
    samples = int(row["samples"] or 0) if row else 0
    if samples < 20:
        return True
    return float(row["avg_clv"] or 0) > 0


def _stable_value_history_allows(model_status: str, market_key: str) -> bool:
    recommendation_type = "MARKET_LEG" if model_status == "DERIVED_MODEL" else "MATCH_PREDICTION"
    market_key = market_key or "match_winner"
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS tracked,
                       SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
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


def _tier_downgrade_reason(tier: str, model_status: str, market_key: str, probability: float) -> str | None:
    if tier not in {"CORE_BANKER", "STABLE_VALUE_BANKER", "VALUE_BANKER"}:
        return None
    recommendation_type = "MARKET_LEG" if model_status == "DERIVED_MODEL" else "MATCH_PREDICTION"
    market_key = market_key or "match_winner"
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                       AVG(clv) AS avg_clv,
                       SUM(COALESCE(profit_loss_units, 0)) AS profit
                FROM clv_tracker
                WHERE tier = ?
                  AND recommendation_type = ?
                  AND market_key = ?
                  AND COALESCE(edge, 0) > 0
                """,
                (tier, recommendation_type, market_key),
            ).fetchone()
    except Exception:
        row = None
    settled = int(row["settled"] or 0) if row else 0
    if settled >= 30:
        roi = float(row["profit"] or 0) / settled
        avg_clv = float(row["avg_clv"] or 0)
        if roi < 0:
            return "tier_downgraded_negative_roi"
        if avg_clv < 0:
            return "tier_downgraded_negative_clv"
    if _calibration_safety_margin(probability) >= 0.08:
        return "tier_downgraded_calibration_overconfident"
    return None


def _banker_reason(
    model_reason: str,
    tier: str,
    probability: float,
    edge: float,
    odds: float,
    confidence: int,
    odds_above_minimum: bool,
) -> str:
    if not odds_above_minimum:
        return "current_odds_below_minimum_acceptable_odds"
    if tier == "CORE_BANKER":
        return f"core_banker:{model_reason}:prob={probability:.3f}:edge={edge:.3f}:confidence={confidence}:odds={odds:.2f}"
    if tier == "STABLE_VALUE_BANKER":
        return f"stable_value_banker:{model_reason}:prob={probability:.3f}:edge={edge:.3f}:confidence={confidence}:odds={odds:.2f}"
    if tier == "VALUE_BANKER":
        return f"value_banker:{model_reason}:prob={probability:.3f}:edge={edge:.3f}:confidence={confidence}:odds={odds:.2f}"
    if tier == "NEAR_BANKER_WATCH":
        return f"near_banker_watch:{model_reason}:prob={probability:.3f}:edge={edge:.3f}:confidence={confidence}:odds={odds:.2f}"
    if tier == "HIGH_ODDS_VALUE":
        return f"high_odds_value_not_banker:{model_reason}:prob={probability:.3f}:edge={edge:.3f}:confidence={confidence}:odds={odds:.2f}"
    return "below_banker_threshold"


def _reason_score(probability: float, edge: float, odds: float, confidence: int, model_status: str) -> int:
    score = int(probability * 45 + max(edge, 0) * 250 + confidence * 0.35)
    if model_status == "DERIVED_MODEL":
        score -= 8
    if odds >= 3.0 and probability < 0.56:
        score -= 12
    return max(0, min(100, score))


def _clamp_probability(value: float, low: float = 0.05, high: float = 0.95) -> float:
    return max(low, min(high, value))


def _match_winner_mapping_verified(row: dict) -> bool:
    selection = str(row.get("selection_name") or "")
    return _same_name(selection, str(row.get("player_a_name") or "")) or _same_name(selection, str(row.get("player_b_name") or ""))


def _selection_side_for_market_row(row: dict) -> str | None:
    selection = str(row.get("selection_name") or "")
    player_a = str(row.get("player_a_name") or "")
    player_b = str(row.get("player_b_name") or "")
    if _same_name(selection, player_a):
        return "player_a"
    if _same_name(selection, player_b):
        return "player_b"
    selection_key = " ".join(selection.lower().split())
    player_a_key = " ".join(player_a.lower().split())
    player_b_key = " ".join(player_b.lower().split())
    if player_a_key and player_a_key in selection_key:
        return "player_a"
    if player_b_key and player_b_key in selection_key:
        return "player_b"
    return None


def _mode_status_line(run_mode: str | None) -> str:
    if run_mode == "live_full":
        return "- Mode：LIVE_FULL（今次跑 live 抓取：fixtures + 全市場 + metadata backfill）"
    if run_mode == "mvp_snapshot":
        return "- Mode：SNAPSHOT_MODE（使用最近已保存嘅 Sportsbet / local snapshot；唔扮 live odds）"
    return "- Mode：未知（report 找唔到今次 run 嘅 mode 記錄）"


def render_daily_report(match_date: str, rows: list[dict], source_status: dict | None = None, unanalysed: list[dict] | None = None) -> str:
    bets = [row for row in rows if row["decision"] == "BET"]
    watchlist = [row for row in rows if row["decision"] == "WATCHLIST"]
    no_bets = [row for row in rows if row["decision"] == "NO_BET"]
    source_status = source_status or {}
    unanalysed = unanalysed or []
    lines = [
        "Tennis Wong Choi 每日分析報告",
        f"日期：{match_date}",
        "",
        f"已分析賽事：{len(rows)}",
        f"建議投注：{len(bets)}",
        f"觀察名單：{len(watchlist)}",
        f"不下注：{len(no_bets)}",
        f"未能進入分析賽事：{len(unanalysed)}",
        "",
        "## 數據源狀態",
        "",
        f"- Sportsbet odds rows：{source_status.get('sportsbet_odds_rows', 0)}",
        f"- 已配對 / 已建 provisional fixture：{source_status.get('sportsbet_linked_rows', 0)}",
        f"- Sportsbet 最新抓取時間：{source_status.get('sportsbet_latest_fetch') or 'N/A'}",
        "- Bankroll：100u virtual bankroll；1 unit = $1；注碼用 tenth-Kelly，1u 起跳、最大 5u",
        _mode_status_line(source_status.get("run_mode")),
        f"- Tennis fixture source：{source_status.get('bsd_fixture_status') or 'N/A'}",
        f"- Fixture 補齊策略：{source_status.get('fixture_note') or 'N/A'}",
        f"- Ranking refresh：{source_status.get('ranking_source_note') or 'N/A'}",
        f"- 歷史數據 / Elo：{source_status.get('history_source') or 'N/A'}",
        f"- 多市場 odds：{source_status.get('market_odds_note') or 'N/A'}",
        "",
    ]
    metadata_gap_lines = _metadata_gap_summary_lines(rows)
    if metadata_gap_lines:
        lines.extend(["## 資料缺口摘要", "", *metadata_gap_lines, ""])
    run_errors = source_status.get("latest_run_errors") or []
    if run_errors:
        lines.extend(
            [
                "## 今次 full run 警告",
                "",
                "今次 live API refresh 未完整成功；以下報告只可作 debug / pipeline 檢查，唔應作真實下注清單。",
            ]
        )
        for error in run_errors:
            lines.append(f"- {_source_label(str(error.get('source')))}：{_source_error_label(str(error.get('error')))}")
        lines.append("")
    lines.extend(
        [
            "## 下注候選一覽",
            "",
            *_bet_summary_lines(bets),
            "",
            "## 下注詳情（只列 BET）",
            "",
            "說明：模型勝率＝有效因素喺 logit 空間以 Elo 為骨幹合併；注碼＝tenth-Kelly（1u 起跳、最大 5u）。",
            "",
        ]
    )
    if not bets:
        lines.extend(["暫時未有通過所有 hard rule 嘅 BET。", ""])
    for idx, row in enumerate(bets, start=1):
        payload = json.loads(row["pricing_json"])
        pricing = payload["pricing"]
        filter_result = payload["filter"]
        match_label = _match_label(row)
        lines.extend(
            [
                f"### BET {idx}｜{match_label}",
                "",
                f"賽事：{_display_label(row['tournament_name'])}（ID {row['match_id']}）",
                *_match_context_report_lines(row),
                f"市場：Match Winner｜選擇：{_display_label(row['selection_name'])}",
                f"現價 {_fmt(row['current_market_odds'])}（最低可接受 {_fmt(row['minimum_acceptable_odds'])}）｜模型勝率 {_pct(row['model_probability'])}｜公平價 {_fmt(row['fair_odds'])}",
                f"去水市場勝率 {_pct(row['no_vig_market_probability'])}｜Edge {_pct(row['edge'], signed=True)}｜信心 {row['confidence']}｜風險 {row['risk']}",
                f"建議注碼：{_stake_label(row['stake_units'], row['decision'])}",
                "",
                "分析：",
            ]
        )
        components = pricing.get("model", {}).get("components", [])
        lines.extend(_model_explanation_lines(row, pricing, components))
        red_flags = _report_red_flags(filter_result)
        if red_flags:
            lines.append("紅旗：" + "；".join(red_flags))
        lines.extend(["", ""])

    # Watchlist: one compact line each (no full cards).
    if watchlist:
        lines.extend(["## 觀察名單", ""])
        for row in watchlist:
            lines.append(
                f"- {_display_label(row['selection_name'])}｜{_match_label(row)}｜現價 {_fmt(row['current_market_odds'])}｜"
                f"模型 {_pct(row['model_probability'])}｜Edge {_pct(row['edge'], signed=True)}"
            )
        lines.append("")

    # NO_BET: a single collapsed count + a compact table, not 90+ full cards.
    if no_bets:
        lines.extend(_no_bet_summary_lines(no_bets))

    if unanalysed:
        lines.extend(["## 未分析 / 資料不足", ""])
        for row in unanalysed:
            lines.append(f"- {_display_label(row['competition'])}｜{_display_label(row['match'])}｜{_hk_reason(row['reason'])}")
            if row.get("event_url"):
                lines.append(f"  URL：{row['event_url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _match_context_report_lines(row: dict) -> list[str]:
    lines: list[str] = []
    missing: list[str] = []
    context_fields = (
        ("級別", row.get("level")),
        ("圈數", row.get("round")),
        ("場地", row.get("surface")),
    )
    for label, value in context_fields:
        if _is_confirmed_context_value(value):
            lines.append(f"{label}：{_display_label(value)}")
        else:
            missing.append(label)
    return lines


def _is_confirmed_context_value(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.upper() not in {"UNKNOWN", "N/A"} and text != "未確認"


def _metadata_gap_summary_lines(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    fields = (("級別", "level"), ("圈數", "round"), ("場地", "surface"))
    lines = []
    for label, key in fields:
        if key in {"level", "surface"}:
            missing = sum(
                1
                for row in rows
                if row.get("metadata_source") not in {"curated_tournament_metadata", "tennisdata_tournament_index"}
                or not _is_confirmed_context_value(row.get(key))
            )
        else:
            missing = sum(1 for row in rows if not _is_confirmed_context_value(row.get(key)))
        if missing:
            lines.append(f"- {label} 未有可靠 metadata：{missing}/{len(rows)} 場")
    if lines:
        lines.append("- 呢啲欄位會影響 tournament / round / surface context；未有可靠來源前唔應該用 heuristic 當正式資料。")
    return lines


_TIER_BLURB = {
    # 穩膽 tier retired from the model-edge combo engine (Phase 3, 2026-07-12):
    # its odds/hit band was unsatisfiable for favourites and model-edge parlays
    # backtest negative anyway. The 穩膽 slot is the chalk chain section above
    # (穩膽大熱串), which is tracked and settles in combo_tracker.
    combo_engine.TIER_BANKER: (
        "組合1 穩膽",
        "呢欄已由「🎯 穩膽大熱串」取代（見上面）——市場大熱 ≤1.20 平注串，唔靠模型 edge；"
        "模型 edge 組合經回測證實砌唔出高命中低賠組合。",
    ),
    combo_engine.TIER_VALUE: ("組合2 價值膽（僅供參考）", "命中中等、賠率 ~2.5-5.5。"),
    combo_engine.TIER_HIGH: ("組合3 高倍率（僅供參考）", "長賠 5+。"),
    combo_engine.TIER_BOMB: ("組合X 火藥庫（僅供參考）", "穩腳 + 高 edge 爆冷腳，長賠。"),
}

# The long-odds match-winner tiers are demoted to reference-only: a 15,299-bet
# walk-forward backtest (2022-24 vs de-vigged close) shows they bleed and get
# WORSE with more edge -- value(2.5-5.5) −5.4% hit 28%, high(5+) −32% hit 8%,
# high@edge≥20% −39%. The model's edge is anti-predictive at long odds. Shown for
# context, NOT recommended; profit path is the prop unders/overs (which beat the
# market on the live scorecard).
_DEMOTED_TIERS = {combo_engine.TIER_VALUE, combo_engine.TIER_HIGH, combo_engine.TIER_BOMB}
_DEMOTED_TIER_WARNING = (
    "⛔ 僅供參考，唔建議落：回測（15,299 注 vs 收盤）證實 match-winner 長賠 edge 係反指標 —— "
    "價值膽 −5.4%（命中 28%）、高倍率 −32%（命中 8%），而且 edge 越大輸得越勁。"
    "想要「高賠率但長期企得住」，請睇上面嘅 🎾 Prop / 🎯 Prop 串（唯一喺記分卡贏市場嘅結構）。"
)


def _leg_risk_map(match_date: str) -> dict[int, tuple[str, str]]:
    """{match_id: (tour, level)} for the date, for segment-risk classification."""
    out: dict[int, tuple[str, str]] = {}
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT m.id AS match_id, m.tour,
                   (SELECT tl.level FROM tournament_levels tl
                    WHERE tl.tournament_id = m.tournament_id AND tl.tour = m.tour
                    ORDER BY (tl.level NOT IN ('UNKNOWN','未確認')) DESC, tl.id DESC LIMIT 1) AS level
            FROM matches m
            WHERE m.match_date = ?
            """,
            (match_date,),
        ).fetchall()
    for row in rows:
        out[int(row["match_id"])] = (row["tour"], row["level"])
    return out


def _match_winner_bet_legs(match_date: str) -> list[Leg]:
    """
    Match-winner combo legs sourced from the AUTHORITATIVE singles `predictions`
    table (decision == BET — i.e. cleared the half-Kelly +EV bet filter). This
    decouples combos from the separate market-path match-winner gate, which uses
    different thresholds and can desync (e.g. after an odds re-scrape).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.match_id, p.selection_name, p.selection_player_id,
                   p.current_market_odds, p.model_probability, p.no_vig_market_probability,
                   p.edge, p.confidence, p.pricing_json,
                   m.player_a_id, m.player_b_id, pa.name AS player_a_name, pb.name AS player_b_name
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            WHERE m.match_date = ?
              AND p.decision = 'BET'
              AND p.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
            """,
            (match_date,),
        ).fetchall()
    risk_map = _leg_risk_map(match_date)
    legs: list[Leg] = []
    for row in rows:
        try:
            odds = float(row["current_market_odds"])
            prob = float(row["model_probability"])
        except (TypeError, ValueError):
            continue
        if odds < 1.01 or not (0.0 < prob < 1.0):
            continue
        edge = float(row["edge"] or 0.0)
        nv = row["no_vig_market_probability"]
        nv = float(nv) if nv is not None else None
        # Same validation-driven sanity gate as the market pool.
        if edge > 0.30:
            continue
        if nv is not None and prob >= 0.55 and nv <= 0.42:
            continue
        # prob/edge from the predictions table are ALREADY segment-shrunk at
        # pricing time. Only derive the display label here — re-applying the
        # shrink would double-count it.
        tour, level = risk_map.get(int(row["match_id"]), (None, None))
        risk_label, _ = _segment_risk(tour, level)
        side = "player_a" if row["selection_player_id"] == row["player_a_id"] else "player_b"
        factors: dict[str, float] = {}
        try:
            comps = json.loads(row["pricing_json"]).get("pricing", {}).get("model", {}).get("components", [])
            for comp in comps:
                if comp.get("active", True) and comp.get("name") is not None:
                    p = float(comp.get("probability") or 0.5)
                    factors[comp["name"]] = p if side != "player_b" else 1.0 - p
        except (TypeError, ValueError, KeyError):
            pass
        legs.append(
            Leg(
                leg_id=f"{int(row['match_id'])}|match_winner|{row['selection_name']}|None",
                match_id=int(row["match_id"]),
                match_label=f"{_display_label(row['player_a_name'])} vs {_display_label(row['player_b_name'])}",
                selection_name=_display_label(row["selection_name"]),
                market_key="match_winner",
                market_name="Match Betting",
                selection_side=side,
                line=None,
                decimal_odds=odds,
                model_probability=prob,
                no_vig_probability=nv,
                edge=edge,
                confidence=int(row["confidence"] or 0),
                factors=factors,
                validated=True,
                risk_label=risk_label,
            )
        )
    return legs


def _dedup_legs(legs: list[Leg]) -> list[Leg]:
    """Keep the first Leg per leg_id (authoritative singles win over market rows)."""
    seen: set[str] = set()
    out: list[Leg] = []
    for leg in legs:
        if leg.leg_id in seen:
            continue
        seen.add(leg.leg_id)
        out.append(leg)
    return out


def _build_combo_tiers(match_date: str, rows: list[dict]) -> tuple[dict, list]:
    factor_map = _combo_factor_map(rows)
    risk_map = _leg_risk_map(match_date)
    # Match-winner legs come from the authoritative singles (`predictions`); other
    # validated legs come from the market predictions. Dedup so a match-winner
    # leg isn't double-counted if it also appears as a BET market row.
    legs = _dedup_legs(_match_winner_bet_legs(match_date) + _combo_leg_pool(rows, factor_map, risk_map=risk_map))
    return combo_engine.build_combinations(legs, max_legs=3), legs


def _build_trial_combos(match_date: str, rows: list[dict]) -> list[dict]:
    """Combos that use at least one modelled-but-unvalidated market leg (the
    opened markets). Clearly flagged — these let the user see extra combinations
    from the new markets without pretending they are proven."""
    factor_map = _combo_factor_map(rows)
    risk_map = _leg_risk_map(match_date)
    legs = _dedup_legs(_match_winner_bet_legs(match_date) + _combo_leg_pool(rows, factor_map, include_trial=True, risk_map=risk_map))
    if not any(not leg.validated for leg in legs):
        return []
    result = combo_engine.build_combinations(legs, max_legs=3, per_tier=4)
    trial: list[dict] = []
    seen: set = set()
    for tier in combo_engine._TIER_ORDER:
        for combo in result["tiers"].get(tier) or []:
            if combo_engine.combo_is_validated(combo):
                continue  # already shown as a core combo
            if combo["leg_ids"] in seen:
                continue
            seen.add(combo["leg_ids"])
            trial.append(combo)
    trial.sort(key=lambda c: -c["combo_ev"])
    return trial[:4]


def render_banker_report(match_date: str, rows: list[dict]) -> str:
    result, legs = _build_combo_tiers(match_date, rows)
    tiers = result["tiers"]
    total = sum(len(section) for section in tiers.values())
    combo_min_odds = min(_TIER_ODDS_FLOORS) if legs else None

    market_keys = {str(r.get("market_key") or "") for r in rows}
    # STRATEGY (2026-07-04): player props are the primary play. A 15,299-bet
    # backtest showed the match-winner model's edge is anti-predictive at real
    # odds (value −5.4% / high −32%), so match-winner is NO LONGER a standalone
    # value bet -- it is used only as a STABLE combo leg (short-priced favourites
    # in the 大熱串, or a strong-fav anchor). Props lead; match-winner is reference.
    lines = [
        "Tennis Wong Choi 每日 Banker / Combo Report",
        f"日期：{match_date}",
        "",
        "## 🎯 策略重心：Player Props（match-winner 只作穩定組合腳）",
        "",
        "回測結論：match-winner 模型 edge 係反指標（價值 −5.4%、高倍率 −32%，edge 越大越蝕），唔再做主打。",
        "主打 = 下面嘅 🎾 Prop + 🎯 Prop 串（唯一喺記分卡贏緊市場嘅結構）。",
        "match-winner 淨係喺『穩膽大熱串』（市場大熱 ≤1.20）或做強熱 anchor 先用，只作穩定組合腳，唔再單獨當 value 落。",
        "",
    ]
    # PRIMARY: player props + prop parlays + live scorecard.
    lines.extend(_ace_prop_lines(match_date))
    # Stable match-winner legs: chalk favourites (≤1.20) parlayed -- the one
    # match-winner structure that does not bleed. This is "match-winner as a
    # stable combo leg" in practice.
    lines.extend(_chalk_combo_lines(rows))
    # ---- reference zone: match-winner edge combos (demoted, backtest-negative) ----
    lines.extend([
        "────────── 以下：match-winner 參考區（回測長期蝕，只作組合腳 / 觀察，唔建議單獨追）──────────",
        "",
    ])
    if legs:
        lines.extend(_anchor_single_lines(legs))
        lines.extend(_slate_concentration_lines(legs, result))
    if market_keys and market_keys <= {"match_winner", ""}:
        lines.extend(
            [
                "⚠️ 今日只抓到 match-winner 賠率，未有多市場數據（總局數 / 讓局 / 贏盤等）。",
                "   多市場 enrichment 未跑或失敗 → 組合只可來自 match-winner，試注組合會冇。",
                "   要有更多組合，請喺 live 模式跑 `run-daily`（會自動 enrich-event-markets），唔好用 --mvp-snapshot。",
                "",
            ]
        )
    if total == 0:
        if legs:
            # We have qualifying picks but no combo cleared a tier band. The most
            # common reason: the legs are short-priced favourites whose combined
            # odds fall below the combo floor (~1.9) — i.e. worth betting as
            # singles, not as a parlay. Say so and surface the singles.
            lines.append(
                f"今日有 {len(legs)} 個合格單腳，但夾唔出抵砌嘅組合"
                f"（可砌嘅 +EV 組合得 {result['candidate_count']} 個，合併賠率多數低過組合下限 {combo_min_odds}，"
                "即係兩隻大熱夾埋都唔夠賠率，倒不如當單注落）。"
            )
            lines.extend(["", *_qualifying_singles_lines(legs)])
        else:
            lines.append("今日無合格單腳（冇 match-winner BET、亦無已驗證市場），亦無組合；建議唔落。")
    else:
        for tier in combo_engine._TIER_ORDER:
            section = tiers.get(tier) or []
            title, blurb = _TIER_BLURB[tier]
            lines.extend([f"## {title}", "", blurb, ""])
            if tier in _DEMOTED_TIERS:
                lines.extend([_DEMOTED_TIER_WARNING, ""])
            if not section:
                lines.extend(["（今日無合資格組合）", ""])
                continue
            for idx, combo in enumerate(section, start=1):
                lines.extend(_render_combo_card(combo, idx))
        # Also surface any qualifying single that didn't end up in a shown combo.
        lines.extend(_qualifying_singles_lines(legs))

    # Trial combos from the opened (modelled-but-unvalidated) markets.
    trial = _build_trial_combos(match_date, rows)
    if trial:
        lines.extend(
            [
                "## 試注組合（未驗證市場）",
                "",
                "以下組合含「已建模但未經結算驗證」嘅市場（總局數 / 讓局 / 贏盤等）。模型未證實長期 +EV，"
                "宜當試注；落注前自己用即時盤口同判斷再核。",
                "",
            ]
        )
        for idx, combo in enumerate(trial, start=1):
            lines.extend(_render_combo_card(combo, idx, trial=True))
    return "\n".join(lines).rstrip() + "\n"


# Minimum combo odds across the four tiers (a 2-leg parlay below this is treated
# as "bet the singles instead").
_TIER_ODDS_FLOORS = (1.9, 2.5, 5.0, 5.0)


# Model probability at/above which a single is a true favourite that can serve
# as a low-variance "banker" anchor (a hit-rate play, not a value play).
_ANCHOR_MIN_PROB = 0.60


def _anchor_single_lines(legs: list) -> list[str]:
    """Report-only '今日最穩' anchor: the single strongest favourite among the
    qualified legs, shown at its real (short) odds and clearly framed as a
    hit-rate play, NOT a +EV value bet. This gives a stable main pick on the
    (common) days when no +EV banker COMBO can form, without faking combo math.
    If no >=60% favourite qualifies, say so honestly instead of forcing one."""
    lines = ["## 今日最穩單注（低波動 anchor）", ""]
    favourites = [leg for leg in legs if leg.model_probability >= _ANCHOR_MIN_PROB]
    if not favourites:
        lines.extend(
            [
                "今日合格腳全部係接近五五波或細冷（無 ≥60% 大熱腳），冇適合做 anchor 嘅穩膽。",
                "唔好為咗「有膽」而硬揀一隻無把握嘅腳 —— 寧願今日唔落穩膽。",
                "",
            ]
        )
        return lines
    anchor = max(favourites, key=lambda leg: (leg.model_probability, leg.confidence))
    factors = _combo_leg_factor_line(anchor)
    suffix = f"｜支持：{factors}" if factors else ""
    risk = f"｜{anchor.risk_label}" if anchor.risk_label else ""
    lines.extend(
        [
            f"- {anchor.selection_name} @ {_fmt(anchor.decimal_odds)}（{anchor.match_label}）{risk}｜"
            f"模型 {_pct(anchor.model_probability)}｜Edge {_pct(anchor.edge, signed=True)}{suffix}",
            "⚠ 呢個係「博命中率」嘅 anchor：賠率低、贏粒糖；唔係厚 value。做你今日嘅定心主腳，平注 / 細注即可，唔好大注追。",
            "",
        ]
    )
    return lines


def _slate_concentration_lines(legs: list, result: dict) -> list[str]:
    """Surface the leg-concentration / thin-slate fragility that makes a string
    of combos collapse together when one shared leg loses (the 06-21 'all
    missed' experience), and explain why the daily BET count can exceed the
    combo leg count (high-edge artifacts are deliberately held out of combos)."""
    leg_count = result.get("leg_count", len(legs))
    lines: list[str] = []
    if 0 < leg_count <= 3:
        lines.extend(
            [
                f"⚠ 薄牌警告：今日得 {leg_count} 隻合格腳。所有組合大量共用呢幾隻腳 —— "
                f"你實際係 {leg_count} 個獨立倉位，唔係 {result.get('candidate_count', 0)} 條獨立優勢。"
                "一隻腳輸，多數組合會一齊冚（呢個就係 06-21 全失手嘅主因：唔好當佢哋係幾條互相獨立嘅注）。",
                "",
            ]
        )
    lines.extend(
        [
            "ℹ 單注數 vs 組合腳數：模型 edge 過大（>30%）或模型同市場分歧過闊嘅單注，"
            "會被組合引擎當低可靠度 artifact（多數係排名 fallback Elo 估出嚟）剔走，唔會入組合。"
            "所以每日報告嘅「建議投注」可能多過呢度嘅合格腳 —— 嗰啲被剔嘅，建議當細注 / 觀察，唔好疊大注。",
            "",
        ]
    )
    return lines


# Chalk-combo banker: the ONE tennis combo structure that does NOT bleed vs the
# closing line. Parlay short-odds MARKET favourites (favourite-longshot bias --
# heavy chalk is mildly underpriced); different matches are independent so there
# is no correlation haircut. Re-verified 2026-07-03 (ATP+WTA 2022-24, 20,180
# matches, Pinnacle close, DISJOINT deployable chains): 2-leg hit 81% ROI +0.3%,
# 3-leg hit 74% ROI +0.8% (with Elo veto ~+0.7-0.8%); per-year noisy
# (+4.6%/-0.8%/-1.5%), i.e. ~breakeven vs the sharp close -- versus -8..-25% for
# model-edge parlays. Cutoffs above 1.20 go negative (1.25 -1.0%, 1.30 -3.3%).
# We require a genuine tour-level model price (model_probability above the 0.50
# 'no-opinion' default AND confidence >= the bet floor) so we never parlay
# ITF/quali junk the model cannot price. NOT an edge play -- requiring model
# edge here LOSES; the model only vetoes favourites it disagrees with and
# screens out low-data junk.
_CHALK_MIN_ODDS = 1.05
_CHALK_MAX_ODDS = 1.20
_CHALK_MIN_MODEL_PROB = 0.52
_CHALK_MIN_CONFIDENCE = 65
_CHALK_FLAT_STAKE_U = 1.0
# The chalk backtest (tennis-data seasons) covers TOUR-LEVEL events only. Now
# that Phase 2 lets ITF/Challenger matches score above the quality floor, keep
# them out of the chalk chains until their own tracker record proves the
# favourite-longshot edge exists down there too.
_CHALK_EXCLUDED_COMPETITION_RE = re.compile(
    r"\b(challenger|itf|futures|utr|doubles)\b", re.IGNORECASE
)


def _chalk_combo_legs(rows: list[dict]) -> list[dict]:
    """One qualifying chalk favourite per match (highest model prob)."""
    best: dict[int, dict] = {}
    for r in rows:
        if str(r.get("market_key") or "") != "match_winner":
            continue
        if _CHALK_EXCLUDED_COMPETITION_RE.search(str(r.get("tournament_name") or "")):
            continue
        odds, mp = r.get("odds"), r.get("model_probability")
        if odds is None or mp is None:
            continue
        if not (_CHALK_MIN_ODDS <= float(odds) <= _CHALK_MAX_ODDS):
            continue
        if float(mp) <= _CHALK_MIN_MODEL_PROB or int(r.get("confidence") or 0) < _CHALK_MIN_CONFIDENCE:
            continue
        mid = int(r["match_id"])
        if mid not in best or float(mp) > float(best[mid]["model_probability"]):
            best[mid] = r
    return list(best.values())


def _chalk_combo_dicts(rows: list[dict]) -> list[dict]:
    """Deployable DISJOINT chalk chains for the combo tracker（tier 穩膽大熱串）.

    The report section shows ranked (overlapping) candidate parlays; the
    tracker records only the greedy disjoint chains — 3-leg first, then a
    2-leg from the remainder — matching the structure the backtest validated,
    at the flat stake. This gives the headline 穩膽 recommendation a settled
    track record instead of being report-only."""
    legs = _chalk_combo_legs(rows)
    if len(legs) < 2:
        return []
    legs.sort(key=lambda r: -float(r["model_probability"]))
    chains: list[list[dict]] = []
    i = 0
    while len(legs) - i >= 3:
        chains.append(legs[i : i + 3])
        i += 3
    if len(legs) - i == 2:
        chains.append(legs[i : i + 2])
    out: list[dict] = []
    for grp in chains:
        odds = hit = 1.0
        leg_dicts: list[dict] = []
        for r in grp:
            odds *= float(r["odds"])
            hit *= float(r["model_probability"])
            leg_dicts.append(
                {
                    "id": r.get("id"),
                    "match_id": r.get("match_id"),
                    "match_label": r.get("match_label"),
                    "market_key": r.get("market_key"),
                    "market_name": r.get("market_name"),
                    "selection_name": r.get("selection_name"),
                    "selection_side": r.get("selection_side"),
                    "line": r.get("line"),
                    "tier": "穩膽大熱串",
                    "odds": r.get("odds"),
                    "edge": r.get("edge"),
                    "confidence": r.get("confidence"),
                }
            )
        out.append(
            {
                "legs": leg_dicts,
                "tier": "穩膽大熱串",
                "combo_odds": round(odds, 4),
                "adjusted_hit_probability": round(hit, 4),
                "average_edge": None,
                "adjusted_edge": None,
                "min_confidence": min(int(r.get("confidence") or 0) for r in grp),
                "adjusted_confidence": min(int(r.get("confidence") or 0) for r in grp),
                "stake_units": _CHALK_FLAT_STAKE_U,
            }
        )
    return out


def _chalk_combo_lines(rows: list[dict]) -> list[str]:
    legs = _chalk_combo_legs(rows)
    lines = [
        "## 🎯 穩膽大熱串（市場大熱 ≤1.20｜回測唯一唔蝕入肉嘅組合結構）",
        "",
        "原理：串市場大熱（賠率 ≤1.20），食 favourite-longshot bias（大熱被輕微低估）；唔同場互相獨立，冇相關性折讓。",
        "回測（2022-24 vs Pinnacle 收盤、可落盤嘅不重疊串法）：2 腳命中 81% ROI +0.3%、3 腳命中 74% ROI +0.8%；逐年有波動（+4.6%/−0.8%/−1.5%）。",
        "⇒ 期望值大約打和，唔係印錢機；但對比模型 edge 串（每腳 −8% 起，串埋蝕更快）係唯一企得住嘅串法。價格好過收盤先落，價差就係你嘅真 edge。",
        "平注；唔靠模型 edge（要 edge 反而蝕），模型淨係用嚟剔走佢唔同意嘅大熱 + 隔走低數據 junk。",
        "",
    ]
    if len(legs) < 2:
        if len(legs) == 1:
            r = legs[0]
            lines.append(
                f"今日得 1 隻合資格大熱：{_display_label(r['selection_name'])} @ {_fmt(r['odds'])}"
                f"（模型 {_pct(r['model_probability'])}），唔夠砌串；可當單注穩膽平注。"
            )
        else:
            lines.append("今日無合資格 ≤1.20 大熱（要 tour 級、模型有真實評分、信心 ≥65）；薄牌日唔好硬砌。")
        lines.append("")
        return lines
    legs.sort(key=lambda r: -float(r["model_probability"]))

    def combo_block(size: int, top_n: int) -> list[str]:
        out: list[str] = []
        shown = 0
        for grp in combinations(legs, size):
            odds = hit = mkt = 1.0
            for r in grp:
                odds *= float(r["odds"])
                hit *= float(r["model_probability"])
                mkt *= float(r.get("no_vig_market_probability") or r["model_probability"])
            out.append(f"### {size} 腳大熱串｜Odds {_fmt(round(odds, 3))}｜建議 {_CHALK_FLAT_STAKE_U:g}u（平注）")
            out.append(f"模型命中：{_pct(hit)}｜市場隱含命中：{_pct(mkt)}")
            for r in grp:
                out.append(f"- {_display_label(r['selection_name'])} @ {_fmt(r['odds'])}（模型 {_pct(r['model_probability'])}）")
            out.append("")
            shown += 1
            if shown >= top_n:
                break
        return out

    lines.extend(combo_block(2, 3))
    if len(legs) >= 3:
        lines.extend(combo_block(3, 2))
    lines.append("⚠ +EV 係對 Pinnacle 收盤計；Sportsbet 大熱價通常較差，逐隻腳格價，唔夠收盤價就唔好落。賠率薄、靠量同紀律。")
    lines.append("")
    return lines


def _ace_prop_lines(match_date: str) -> list[str]:
    """NBA-style player-prop section: match-total AND single-player ACES on the
    soft Sportsbet book, priced by the calibrated ace model. Two-way markets are
    de-vigged exactly and BOTH sides priced, so we can back the UNDER (fade) where
    the model sees value. Honest by design: +EV flagged only within the calibrated
    range (never longshot extrapolation), ROI stated as unverified, and a live
    model-vs-market scorecard shows who is actually right as results settle."""
    try:
        from tennis_wc.props.daily import price_ace_props_for_date
        from tennis_wc.props.settlement import (
            settle_props, prop_roi_report, model_vs_market_scorecard,
        )
        from tennis_wc.props import calibration
        conn = get_connection()
        settle_props(conn)  # grade anything now settleable before we review
        boards = price_ace_props_for_date(conn, match_date, log=True)
        _ev_note = calibration.strength_note(calibration.current_strength(conn), conn)
    except Exception as exc:  # never let an experimental section break the report
        return ["## 🎾 球員 Prop：Aces（實驗中）", "", f"（Prop 引擎今日無法產生：{exc}）", ""]
    lines = [
        "## 🎾 球員 Prop：Aces（NBA 式 soft-market，實驗中・上線驗證緊）",
        "",
        "學 NBA 打 prop：只用 soft book（Sportsbet），模型經歷史校準（P(over) 係實測頻率）。",
        "兩邊盤（Over/Under X.5）已精確去水，兩邊都定價 → 可以夾 under（模型認為 aces 會少過條線嗰邊）。",
        "ℹ️ WTA aces 暫時只做定價展示、唔出 value 注：冇可結算嘅 WTA ace 數據源（結唔到數嘅注冇得驗證）；總局數兩邊 tour 照出。",
        "⚠ ROI 未驗證：ace 結算 overlap 得約 16 場。已剔走超出校準範圍嘅長賠（>1.25× 預測均值 = 外推假 edge）。",
        "每條記入 prop_tracker、賽後自動結算；睇下面『模型 vs 市場記分卡』知邊個啱（比 ROI 快）。",
        f"🔧 {_ev_note}（模型未夠數據前把機率向 50% 收，避免高估 EV；夠數據會自動放鬆或收緊）。",
        "",
    ]
    val_picks: list[str] = []
    value_legs: list[dict] = []
    for bd in boards:
        hdr = f"### {bd.match_label}｜預測 aces ≈ {bd.predicted_match_mean}"
        if bd.predicted_games:
            hdr += f"｜預測總局數 ≈ {bd.predicted_games}"
        seg = [hdr]
        for tw in bd.match_ou:
            seg.append(_two_way_line("全場aces", tw, val_picks, value_legs))
        for tw in bd.player_ou:
            seg.append(_two_way_line(f"{tw.scope} aces", tw, val_picks, value_legs))
        for tw in bd.games_ou:
            seg.append(_two_way_line("總局數", tw, val_picks, value_legs))
        if bd.anchor:
            a = bd.anchor
            seg.append(f"- N+ 高命中 anchor：{int(a.line)}+ @ {_fmt(a.decimal_odds)}（命中 {_pct(a.blended_prob)}）— 唔代表 +EV")
        if len(seg) > 1:
            lines.extend(seg + [""])
    if val_picks:
        lines.extend(["### ✅ 今日模型認為有 value 嘅 prop（未證實，細注試 + 格價）", "", *val_picks, ""])
    else:
        lines.extend(["今日冇 prop 過到 value 關（soft book 主線都定得緊）。唔好硬追；等記分卡儲夠數據。", ""])
    # Prop parlays (NBA banker structure): different-match legs are independent, so
    # +EV compounds. Surfaced so combinations can be tested during validation.
    lines.extend(_prop_combo_lines(value_legs))
    # ---- Review block: scorecard + segmented ROI (live validation) ----
    try:
        sc = model_vs_market_scorecard(conn)
        roi = prop_roi_report(conn)
        lines.extend(_prop_review_lines(sc, roi))
    except Exception:
        pass
    return lines


def _two_way_line(scope_label: str, tw, val_picks: list[str], value_legs: list[dict] | None = None) -> str:
    """Render one Over/Under prop; record value picks (for the ✅ list and combos)."""
    base = (f"- {scope_label} O/U {tw.line}：Over @ {_fmt(tw.over_odds)} / Under @ {_fmt(tw.under_odds)}"
            f"｜模型 P(over) {_pct(tw.model_prob_over)}｜市場fair {_pct(tw.fair_prob_over)}")
    if tw.value_side:
        tag = f"  ✅ {('大' if tw.value_side=='over' else '細')}({tw.value_side}) @ {_fmt(tw.value_odds)}｜edge {_pct(tw.edge, signed=True)}｜EV {_pct(tw.ev, signed=True)}"
        desc = f"{scope_label} {tw.value_side.upper()} {tw.line} @ {_fmt(tw.value_odds)}"
        val_picks.append(f"- {desc}（模型 {_pct(tw.blended_prob)} / edge {_pct(tw.edge, signed=True)}）")
        if value_legs is not None:
            value_legs.append({"match_id": tw.match_id, "desc": desc,
                               "odds": tw.value_odds, "prob": tw.blended_prob})
        return base + tag
    return base


def _prop_combo_lines(value_legs: list[dict]) -> list[str]:
    """NBA-style prop parlays: combine +EV value legs from DIFFERENT matches
    (independent -> joint prob = product, no correlation haircut). Flat 1u. These
    are the combinations to test during validation."""
    lines = ["## 🎯 Prop 串（NBA banker 式・唔同場獨立相乘）", ""]
    if len(value_legs) < 2:
        lines.extend(["今日 value prop 唔夠 2 條（唔同場）夾唔到串；有得夾會喺度顯示。", ""])
        return lines
    lines.extend([
        "原理：唔同場嘅 prop 互相獨立 → 命中率相乘、賠率相乘、+EV 疊加（同 NBA banker 一樣）。",
        "⚠ 每條 leg 都係未證實嘅 value；平注細試、逐條格價。同場嘅腳唔夾（會相關）。",
        "",
    ])
    combos: list[tuple] = []
    n = len(value_legs)
    for size in (2, 3):
        for idx in combinations(range(n), size):
            legs = [value_legs[i] for i in idx]
            if len({lg["match_id"] for lg in legs}) != size:
                continue  # different matches only
            odds = prob = 1.0
            for lg in legs:
                odds *= lg["odds"]; prob *= lg["prob"]
            ev = prob * odds - 1.0
            combos.append((ev, prob, odds, legs))
    if not combos:
        lines.extend(["今日 value prop 全部同場，夾唔到獨立串。", ""])
        return lines
    combos.sort(key=lambda c: -c[0])
    for i, (ev, prob, odds, legs) in enumerate(combos[:5], 1):
        lines.append(f"### 串 {i}｜{len(legs)} 腳｜Odds {_fmt(round(odds,2))}｜命中 {_pct(prob)}｜EV {_pct(ev, signed=True)}｜1u")
        for lg in legs:
            lines.append(f"- {lg['desc']}")
        lines.append("")
    return lines


def _prop_review_lines(sc: dict, roi: dict) -> list[str]:
    lines = ["## 📊 Prop 結果檢討（上線驗證）", ""]
    n = sc.get("settled", 0)
    if not n:
        lines.extend(["模型 vs 市場記分卡：暫無已結算 prop（跑多幾日 run-daily 就會有）。", ""])
    else:
        m, k = sc["model"], sc["market"]
        lines.extend([
            f"模型 vs 市場記分卡（{n} 條已結算，Brier / LogLoss 越低越準）：",
            f"- 模型：Brier {m['brier']}｜LogLoss {m['log_loss']}",
            f"- 市場：Brier {k['brier']}｜LogLoss {k['log_loss']}",
            f"- 判定：{sc['verdict']}",
            "",
        ])
        if sc.get("calibration"):
            lines.append("校準（模型預測 P vs 實際命中）：")
            for c in sc["calibration"]:
                lines.append(f"  預測 {_pct(c['pred'])} → 實際 {_pct(c['realised'])}（n={c['n']}）")
            lines.append("")
    o = roi.get("overall", {})
    if o.get("settled"):
        lines.append(f"已結算注 ROI：{o['settled']} 注、命中 {_pct(o.get('hit_rate'))}、ROI {_pct(o.get('roi'), signed=True)}（純參考，樣本細）")
        for side, s in (roi.get("by_side") or {}).items():
            if s.get("settled"):
                lines.append(f"  {side}: {s['settled']} 注 命中 {_pct(s.get('hit_rate'))} ROI {_pct(s.get('roi'), signed=True)}")
        lines.append("")
    else:
        lines.extend(["已結算注 ROI：暫無（value 注仲未有結果）。", ""])
    return lines


def _qualifying_singles_lines(legs: list) -> list[str]:
    if not legs:
        return []
    lines = ["## 合格單腳（可獨立考慮）", ""]
    for leg in sorted(legs, key=lambda x: -x.edge):
        factors = _combo_leg_factor_line(leg)
        suffix = f"｜支持：{factors}" if factors else ""
        risk = f"｜{leg.risk_label}" if leg.risk_label else ""
        lines.append(
            f"- {leg.selection_name} @ {_fmt(leg.decimal_odds)}（{leg.match_label}）{risk}｜"
            f"模型 {_pct(leg.model_probability)}｜Edge {_pct(leg.edge, signed=True)}{suffix}"
        )
    lines.append("")
    return lines


def _render_combo_card(combo: dict, idx: int, trial: bool = False) -> list[str]:
    legs = combo["legs"]
    stake = round(combo["stake_units"], 2)
    tag = "試注 " if trial else ""
    lines = [
        f"### {tag}組合 {idx}｜{len(legs)} 腳｜Odds {_fmt(combo['combo_odds'])}｜建議 {stake:g}u",
        f"命中（扣相關後）：{_pct(combo['adjusted_hit'])}｜純連乘：{_pct(combo['naive_hit'])}｜"
        f"相關性折扣：{_pct(combo['correlation_penalty'])}｜MC：{_pct(combo['mc_mean_hit'])}（下限 {_pct(combo['mc_p10_hit'])}）",
        f"組合 EV：{_pct(combo['combo_ev'], signed=True)}｜平均 Edge：{_pct(combo['average_edge'], signed=True)}｜"
        f"Kelly 注碼比：{_pct(combo['kelly_fraction'])}",
    ]
    for leg_idx, leg in enumerate(legs, start=1):
        lines.append(f"- Leg {leg_idx}: {_combo_leg_label(leg)}")
        factor_line = _combo_leg_factor_line(leg)
        if factor_line:
            lines.append(f"    支持因素：{factor_line}")
    if combo["is_same_match"]:
        lines.append("- 注意：同場多腳 exposure 高，已扣相關性，注碼保守。")
    lines.append("")
    return lines


def _combo_leg_label(leg: Leg) -> str:
    line = f" line {_fmt(leg.line)}" if leg.line is not None else ""
    market = f"{leg.market_name}{line}: " if leg.market_name else ""
    risk = f"｜{leg.risk_label}" if leg.risk_label else ""
    return (
        f"{market}{leg.selection_name} @ {_fmt(leg.decimal_odds)} "
        f"（{leg.match_label}｜模型 {_pct(leg.model_probability)}｜Edge {_pct(leg.edge, signed=True)}{risk}）"
    )


def _combo_leg_factor_line(leg: Leg) -> str:
    breakdown = combo_engine.leg_factor_breakdown(leg)
    supportive = [f"{label} {_pct(prob)}" for label, prob in breakdown if prob > 0.52][:4]
    return "、".join(supportive)


def banker_combinations_for_date(match_date: str) -> list[dict]:
    rows = banker_market_predictions_for_date(match_date)
    result, _legs = _build_combo_tiers(match_date, rows)
    out: list[dict] = []
    for tier in combo_engine._TIER_ORDER:
        for combo in result["tiers"].get(tier) or []:
            out.append(_combo_to_legacy_dict(combo, tier))
    # Track the chalk chains too — the headline 穩膽 recommendation must accrue
    # a settled record, not stay report-only.
    out.extend(_chalk_combo_dicts(rows))
    return out


def _combo_to_legacy_dict(combo: dict, tier: str) -> dict:
    """Shape a new-engine combo into the dict the ledger/combo-tracker expects
    (legs as dicts; tier / combo_odds / average_edge / stake_units at top)."""
    legs = []
    for leg in combo["legs"]:
        legs.append(
            {
                "id": leg.leg_id,
                "match_id": leg.match_id,
                "match_label": leg.match_label,
                "market_key": leg.market_key,
                "market_name": leg.market_name,
                "selection_name": leg.selection_name,
                "selection_side": leg.selection_side,
                "line": leg.line,
                "tier": tier,
                "odds": leg.decimal_odds,
                "edge": leg.edge,
                "confidence": leg.confidence,
            }
        )
    return {
        "legs": legs,
        "tier": tier,
        "combo_odds": combo["combo_odds"],
        "adjusted_hit_probability": combo["adjusted_hit"],
        "average_edge": combo["average_edge"],
        "adjusted_edge": combo["average_edge"],
        "min_confidence": min((leg.confidence for leg in combo["legs"]), default=0),
        "adjusted_confidence": min((leg.confidence for leg in combo["legs"]), default=0),
        "stake_units": combo["stake_units"],
    }


def _combo_factor_map(rows: list[dict]) -> dict[int, dict[str, float]]:
    """{match_id: {component_name: player_a_probability}} from the match-winner
    singles prediction, so combo legs can surface Elo/serve/form/pressure/H2H."""
    match_ids = {int(row["match_id"]) for row in rows if row.get("match_id") is not None}
    if not match_ids:
        return {}
    placeholders = ",".join("?" for _ in match_ids)
    out: dict[int, dict[str, float]] = {}
    with get_connection() as conn:
        prediction_rows = conn.execute(
            f"""
            SELECT match_id, pricing_json
            FROM predictions
            WHERE match_id IN ({placeholders})
              AND id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
            """,
            tuple(sorted(match_ids)),
        ).fetchall()
    for row in prediction_rows:
        try:
            payload = json.loads(row["pricing_json"])
            components = payload.get("pricing", {}).get("model", {}).get("components", [])
        except (TypeError, ValueError, KeyError):
            continue
        factors: dict[str, float] = {}
        for component in components:
            if not component.get("active", True):
                continue
            name = component.get("name")
            if name is None:
                continue
            factors[name] = float(component.get("probability") or 0.5)
        out[int(row["match_id"])] = factors
    return out


def _combo_leg_trial(row: dict) -> bool:
    """
    A modelled-but-not-yet-validated leg, usable for clearly-flagged TRIAL combos
    (the opened markets: total games / handicap / set markets). Edge is CAPPED:
    implausibly large 'edges' (>15%) on these models are almost always model
    error (the external backtest showed bigger perceived edge => more wrong), so
    they are rejected rather than chased.
    """
    if _combo_leg_trustworthy(row):
        return False  # already a core leg
    if row.get("model_status") != "DERIVED_MODEL":
        return False
    if not _settlement_supported_market_key(str(row.get("market_key") or "")):
        return False
    try:
        edge = float(row.get("edge") or 0)
        prob = float(row.get("model_probability") or 0)
        conf = int(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return False
    return 0.04 <= edge <= 0.15 and 0.52 <= prob <= 0.85 and conf >= 60


def _combo_leg_trustworthy(row: dict) -> bool:
    """
    Only TRUSTWORTHY legs may enter combos:
      * any market that has passed the settlement-validation gate (banker_eligible), OR
      * a match-winner pick that is a genuine model BET (cleared the full bet
        filter: data quality, +EV-at-price, etc.).
    This deliberately EXCLUDES raw PROP/DERIVED outputs (e.g. aces) whose models
    are not yet validated and otherwise emit miscalibrated, fake-edge legs.
    """
    if row.get("banker_eligible") in {1, True}:
        return True
    return (
        row.get("market_key") == "match_winner"
        and row.get("model_status") == "MODELLED"
        and row.get("decision") == "BET"
    )


def _combo_leg_pool(rows: list[dict], factor_map: dict[int, dict[str, float]], include_trial: bool = False, risk_map: dict[int, tuple[str, str]] | None = None) -> list[Leg]:
    """Normalise priced market predictions into combo Legs. Core (validated)
    legs are always included; when include_trial=True, modelled-but-unvalidated
    market legs (total games / handicap / sets) are added with validated=False so
    they can form clearly-flagged TRIAL combos."""
    legs: list[Leg] = []
    for row in rows:
        trustworthy = _combo_leg_trustworthy(row)
        trial = include_trial and not trustworthy and _combo_leg_trial(row)
        if not trustworthy and not trial:
            continue
        try:
            odds = float(row.get("odds"))
            probability = float(row.get("model_probability"))
        except (TypeError, ValueError):
            continue
        if odds < 1.01 or not (0.0 < probability < 1.0):
            continue
        edge = float(row.get("edge") or 0.0)
        no_vig = row.get("no_vig_market_probability")
        nv = float(no_vig) if no_vig is not None else None
        # Validation-driven sanity gate: an implausibly large "edge" is almost
        # always model error, not value (the external backtest showed bigger
        # perceived edge => worse ROI). Reject extreme edges, and reject legs
        # where the model backs a clear MARKET UNDERDOG as if it were a favourite
        # (a direction conflict, e.g. model 71% on a 4.25 shot the market prices
        # at ~22%). These never enter combos.
        if edge > 0.30:
            continue
        if nv is not None and probability >= 0.55 and nv <= 0.42:
            continue
        match_id = int(row["match_id"])
        tour, level = (risk_map or {}).get(match_id, (None, None))
        risk_label, discount = _segment_risk(tour, level)
        probability, edge = _apply_segment_risk(probability, edge, nv, discount)
        side = row.get("selection_side")
        raw_factors = factor_map.get(match_id, {})
        factors = {
            name: (prob if side != "player_b" else 1.0 - prob)
            for name, prob in raw_factors.items()
        } if row.get("market_key") == "match_winner" else {}
        no_vig = row.get("no_vig_market_probability")
        legs.append(
            Leg(
                leg_id=f"{match_id}|{row.get('market_key')}|{row.get('selection_name')}|{row.get('line')}",
                match_id=match_id,
                match_label=_match_label(row),
                selection_name=_display_label(row.get("selection_name")),
                market_key=str(row.get("market_key") or ""),
                market_name=_display_label(row.get("market_name")),
                selection_side=side,
                line=row.get("line"),
                decimal_odds=odds,
                model_probability=probability,
                no_vig_probability=float(no_vig) if no_vig is not None else None,
                edge=edge,
                confidence=int(row.get("confidence") or 0),
                factors=factors,
                risk_label=risk_label,
                validated=trustworthy,
            )
        )
    legs.sort(key=combo_engine.leg_quality_score, reverse=True)
    return legs[:40]


def _leg_tier_counts(legs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for leg in legs:
        tier = str(leg.get("tier") or "UNKNOWN")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _combo_tier_counts(combos: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for combo in combos:
        tier = _combo_base_tier(combo)
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _combo_base_tier(combo: dict) -> str:
    return str(combo.get("tier") or "UNKNOWN").split("｜", 1)[0]


def _provisional_banker_combinations(rows: list[dict], official_legs: list[dict]) -> list[dict]:
    legs_by_id: dict[str, dict] = {}
    for leg in official_legs:
        effective_probability = _provisional_leg_effective_probability(leg | {"official_ready": True})
        enriched = leg | {
            "provisional_source": "OFFICIAL_BANKER",
            "model_probability": leg.get("model_probability"),
            "effective_probability": effective_probability,
            "official_ready": True,
            "review_note": "已通過 official banker gate，可直接納入 provisional 組合。",
        }
        legs_by_id[str(enriched["id"])] = enriched
    for row in rows:
        leg = _provisional_leg_from_row(row)
        if leg is not None:
            legs_by_id[str(leg["id"])] = leg

    grouped: dict[str, list[dict]] = {}
    for leg in legs_by_id.values():
        grouped.setdefault(leg["match_label"], []).append(leg)

    combos = []
    seen = set()
    for _, match_legs in grouped.items():
        match_legs = sorted(match_legs, key=_provisional_leg_sort_key)
        for size in (1, 2, 3):
            for leg_group in combinations(match_legs, size):
                combo = _provisional_combo_from_legs(leg_group, cross_match=False)
                if combo is None:
                    continue
                key = tuple(sorted(str(leg["id"]) for leg in combo["legs"]))
                if key in seen:
                    continue
                seen.add(key)
                combos.append(combo)

    if len(combos) < 5:
        safe_cross_legs = [
            leg
            for leg in sorted(legs_by_id.values(), key=_provisional_leg_sort_key)[:24]
            if leg.get("market_key") in {"match_winner", "to_win_1st_set"} or _is_to_win_at_least_one_set_market(str(leg.get("market_key") or ""), str(leg.get("market_name") or ""))
        ]
        for leg_group in combinations(safe_cross_legs, 2):
            if len({leg["match_id"] for leg in leg_group}) != 2:
                continue
            combo = _provisional_combo_from_legs(leg_group, cross_match=True)
            if combo is None:
                continue
            key = tuple(sorted(str(leg["id"]) for leg in combo["legs"]))
            if key in seen:
                continue
            seen.add(key)
            combos.append(combo)

    combos.sort(key=_provisional_combo_sort_key)
    return combos[:40]


def _provisional_leg_from_row(row: dict) -> dict | None:
    if row.get("model_status") not in {"MODELLED", "DERIVED_MODEL", "PROP_MODEL"}:
        return None
    try:
        odds = float(row.get("odds"))
        edge = float(row.get("edge"))
        confidence = int(row.get("confidence") or 0)
        probability = float(row.get("model_probability"))
    except (TypeError, ValueError):
        return None
    if probability < 0.70 or confidence < 75 or edge < 0.02:
        return None
    if row.get("model_status") == "PROP_MODEL" and (probability < 0.72 or edge < 0.08):
        return None
    market_key = str(row.get("market_key") or "")
    official_ready = row.get("banker_eligible") in {1, True}
    review_note = _provisional_review_note(row)
    return {
        "id": f"provisional|{row.get('match_id')}|{market_key}|{row.get('selection_name')}|{row.get('line')}",
        "match_id": int(row["match_id"]),
        "match_label": _match_label(row),
        "selection_name": _display_label(row.get("selection_name")),
        "market_name": _display_label(row.get("market_name")),
        "market_key": market_key,
        "selection_side": row.get("selection_side"),
        "tier": "PROVISIONAL_HIGH_HIT",
        "line": row.get("line"),
        "odds": odds,
        "edge": edge,
        "confidence": confidence,
        "model_probability": probability,
        "effective_probability": probability,
        "provisional_source": str(row.get("model_status") or "MODELLED"),
        "official_ready": official_ready,
        "risk_note": _banker_reason_label(str(row.get("reason") or "")),
        "review_note": review_note,
    }


def _provisional_review_note(row: dict) -> str:
    if row.get("banker_eligible") in {1, True}:
        return "已通過 official banker gate；之後照常追蹤 CLV / ROI / hit rate。"
    market_key = str(row.get("market_key") or "")
    if row.get("model_status") == "PROP_MODEL":
        return "Props model review：需要 box score 可結算樣本，確認 hit rate、ROI、CLV 先可升 official。"
    if _settlement_supported_market_key(market_key):
        history = _market_validation_history(market_key)
        return (
            "可做 official 候選：已有模型 + settlement path；"
            f"目前 settled {history['settled']} / tracked {history['tracked']}，"
            f"ROI {_pct(history['roi'], signed=True)}，CLV {_pct(history['avg_clv'], signed=True)}。"
        )
    return "未有完整 settlement support；只可 provisional review，不可升 official。"


def _provisional_leg_sort_key(leg: dict) -> tuple:
    return (
        -float(leg.get("effective_probability") or leg.get("model_probability") or 0),
        -int(leg.get("confidence") or 0),
        -float(leg.get("edge") or 0),
        float(leg.get("odds") or 99),
    )


def _provisional_combo_from_legs(leg_group: tuple[dict, ...], cross_match: bool) -> dict | None:
    if not cross_match and not _combo_compatible(leg_group):
        return None
    if cross_match and len({leg["match_id"] for leg in leg_group}) != len(leg_group):
        return None
    combo_odds = 1.0
    for leg in leg_group:
        combo_odds *= float(leg["odds"])
    if combo_odds < 2.0:
        return None
    probabilities = [_provisional_leg_effective_probability(leg) for leg in leg_group]
    min_probability = min(probabilities)
    if any(probability < 0.70 and not leg.get("official_ready") for probability, leg in zip(probabilities, leg_group)):
        return None
    min_confidence = min(int(leg.get("confidence") or 0) for leg in leg_group)
    average_edge = sum(float(leg.get("edge") or 0) for leg in leg_group) / len(leg_group)
    naive_hit = 1.0
    for probability in probabilities:
        naive_hit *= probability
    adjusted_hit = _provisional_adjusted_hit_probability(leg_group, naive_hit, cross_match)
    adjustment = _cross_match_correlation_adjustment(leg_group, min_confidence, average_edge) if cross_match else _combo_correlation_adjustment(leg_group, min_confidence, average_edge)
    grade = _provisional_grade(min_probability, adjusted_hit, adjustment["adjusted_confidence"], average_edge)
    if grade == "REVIEW":
        return None
    return {
        "legs": list(leg_group),
        "tier": f"Provisional {grade}",
        "combo_odds": combo_odds,
        "min_confidence": min_confidence,
        "adjusted_confidence": adjustment["adjusted_confidence"],
        "average_edge": average_edge,
        "adjusted_edge": adjustment["adjusted_edge"],
        "min_probability": min_probability,
        "naive_hit_probability": naive_hit,
        "adjusted_hit_probability": adjusted_hit,
        "grade": grade,
        "stake_units": _provisional_stake_units(grade),
        "correlation_note": adjustment["note"] if not cross_match else f"{adjustment['note']}；跨場 provisional",
        "risk_note": _provisional_combo_reason(leg_group, grade, cross_match),
        "official_review": _provisional_combo_review(leg_group),
    }


def _provisional_leg_effective_probability(leg: dict) -> float:
    """
    The per-leg hit probability used to build combo hit rates. This MUST be the
    model's estimated win probability — NOT a confidence-score proxy. (The old
    code returned max(model, confidence/100*0.9, 0.70), so every official leg was
    reported at a clamped ~85.5% hit regardless of its true model probability,
    and combo hit rates were multiplications of fictional numbers.)
    """
    model_probability = leg.get("effective_probability") or leg.get("model_probability")
    try:
        return float(model_probability)
    except (TypeError, ValueError):
        return 0.0


def _provisional_adjusted_hit_probability(legs: tuple[dict, ...], naive_hit: float, cross_match: bool) -> float:
    if len(legs) <= 1:
        return naive_hit
    if cross_match:
        return max(0.0, naive_hit * 0.96)
    same_direction = len({leg.get("selection_side") for leg in legs if leg.get("selection_side") in {"player_a", "player_b"}}) == 1
    penalty = 0.90 if same_direction else 0.94
    if len(legs) >= 3:
        penalty -= 0.06
    return max(0.0, naive_hit * penalty)


def _provisional_grade(min_probability: float, adjusted_hit: float, adjusted_confidence: int, average_edge: float) -> str:
    if min_probability >= 0.74 and adjusted_confidence >= 82 and average_edge >= 0.05:
        return "A"
    if min_probability >= 0.70 and adjusted_confidence >= 75 and average_edge >= 0.03:
        return "B"
    if min_probability >= 0.70 and adjusted_confidence >= 68 and average_edge >= 0.02 and adjusted_hit >= 0.48:
        return "C"
    return "REVIEW"


def _provisional_stake_units(grade: str) -> float:
    if grade == "A":
        return 0.25
    if grade == "B":
        return 0.1
    if grade == "C":
        return 0.05
    return 0.0


def _provisional_combo_reason(legs: tuple[dict, ...], grade: str, cross_match: bool) -> str:
    source_labels = sorted({str(leg.get("provisional_source") or "") for leg in legs})
    mode = "跨場" if cross_match else "同場"
    return f"{mode} NBA-style provisional {grade}：high-hit leg pool + odds >= 2.00；來源 {', '.join(source_labels)}"


def _provisional_combo_review(legs: tuple[dict, ...]) -> str:
    if all(leg.get("official_ready") for leg in legs):
        return "已全部通過 official banker gate；review 重點係長期 ROI / CLV 有無保持正數。"
    notes = []
    for leg in legs:
        if leg.get("official_ready"):
            continue
        notes.append(f"{leg.get('market_name')}: {leg.get('review_note')}")
    return " / ".join(notes) if notes else "需要累積 settled sample 後再評估 official qualification。"


def _provisional_combo_sort_key(combo: dict) -> tuple:
    grade_order = {"A": 0, "B": 1, "C": 2}
    return (
        grade_order.get(str(combo.get("grade")), 9),
        len(combo["legs"]),
        -int(combo.get("adjusted_confidence") or 0),
        -float(combo.get("min_probability") or 0),
        -float(combo.get("adjusted_edge") or 0),
        float(combo.get("combo_odds") or 99),
    )


def _provisional_nba_style_combo_sections(combos: list[dict]) -> list[str]:
    selected = _select_non_overlapping_report_combos(combos)
    lines: list[str] = []
    section_labels = (
        ("BANKER", "Banker Combo", "較穩主線，目標 odds 約 2.00-3.20。"),
        ("VALUE", "Value Combo", "價值組合，賠率較高但仍需命中率同 edge 支持。"),
        ("SUPER_HIGH_ODDS", "Super High Odds Combo", "高賠進取小注，只適合細注或觀察。"),
    )
    for section_key, title, note in section_labels:
        section_combos = selected.get(section_key, [])
        lines.extend([f"## {title}", "", note, ""])
        if not section_combos:
            lines.extend(["今日無合資格 non-overlap combo。", ""])
            continue
        for idx, combo in enumerate(section_combos, start=1):
            lines.extend(_provisional_report_combo_card(combo, idx, section_key))
    skipped = selected.get("skipped_count_by_section") or {}
    skipped_total = sum(int(value or 0) for value in skipped.values())
    if skipped_total:
        banker_skipped = int(skipped.get("BANKER") or 0)
        value_skipped = int(skipped.get("VALUE") or 0)
        super_skipped = int(skipped.get("SUPER_HIGH_ODDS") or 0)
        lines.append(
            f"已隱藏同 section 內重複 exposure 候選：Banker {banker_skipped}｜Value {value_skipped}｜Super High {super_skipped}。"
        )
        lines.append("")
    return lines


def _provisional_report_combo_card(combo: dict, idx: int, section_key: str) -> list[str]:
    stake = _section_stake_label(section_key, combo)
    lines = [
        f"### 組合 {idx}｜{stake}｜Odds {_fmt(combo.get('combo_odds'))}",
        f"組合命中：{_pct(combo.get('adjusted_hit_probability'))}｜最低 leg 命中：{_pct(combo.get('min_probability'))}｜平均 Edge：{_pct(combo.get('average_edge'), signed=True)}",
    ]
    for leg_idx, leg in enumerate(combo["legs"], start=1):
        lines.append(f"- Leg {leg_idx}: {_leg_bet_label(leg)}")
    if len(combo["legs"]) == 1:
        lines.append("- 註：此項係 single pick，因 odds 已達 2.00，所以保留作 banker 候選。")
    if _combo_has_repeated_match(combo):
        lines.append("- 注意：同場 / 同球員 exposure 較高，注碼要保守。")
    lines.append("")
    return lines


def _select_non_overlapping_report_combos(combos: list[dict]) -> dict:
    pools = {
        "BANKER": _section_candidates(combos, "BANKER"),
        "VALUE": _section_candidates(combos, "VALUE"),
        "SUPER_HIGH_ODDS": _section_candidates(combos, "SUPER_HIGH_ODDS"),
    }
    selected: dict[str, list[dict]] = {"BANKER": [], "VALUE": [], "SUPER_HIGH_ODDS": []}

    # Avoid repeated legs inside each section. Value / Super High are allowed
    # to reuse Banker legs because they represent separate small-stake angles.
    _fill_non_overlapping_section(selected, "BANKER", pools["BANKER"], set(), limit=3)
    _fill_non_overlapping_section(selected, "VALUE", pools["VALUE"], set(), limit=2)
    _fill_non_overlapping_section(selected, "SUPER_HIGH_ODDS", pools["SUPER_HIGH_ODDS"], set(), limit=1)

    visible_ids = {id(combo) for section in selected.values() for combo in section}
    skipped_count_by_section: dict[str, int] = {}
    for section_key in ("BANKER", "VALUE", "SUPER_HIGH_ODDS"):
        used_in_section: set[str] = set()
        for combo in selected[section_key]:
            used_in_section.update(_combo_leg_ids(combo))
        skipped_count = 0
        seen_candidates: set[int] = set()
        for combo in pools[section_key]:
            combo_id = id(combo)
            if combo_id in seen_candidates or combo_id in visible_ids:
                continue
            seen_candidates.add(combo_id)
            if _combo_leg_ids(combo) & used_in_section:
                skipped_count += 1
        skipped_count_by_section[section_key] = skipped_count
    selected["skipped_count_by_section"] = skipped_count_by_section
    return selected


def _fill_non_overlapping_section(
    selected: dict[str, list[dict]],
    section_key: str,
    candidates: list[dict],
    used_leg_ids: set[str],
    limit: int,
) -> None:
    for combo in candidates:
        if len(selected[section_key]) >= limit:
            break
        leg_ids = _combo_leg_ids(combo)
        if leg_ids & used_leg_ids:
            continue
        selected[section_key].append(combo)
        used_leg_ids.update(leg_ids)


def _section_candidates(combos: list[dict], section_key: str) -> list[dict]:
    candidates = [combo for combo in combos if _combo_section_eligible(combo, section_key)]
    candidates.sort(key=lambda combo: _section_combo_sort_key(combo, section_key))
    return candidates[:16]


def _combo_section_eligible(combo: dict, section_key: str) -> bool:
    odds = float(combo.get("combo_odds") or 0)
    adjusted_hit = float(combo.get("adjusted_hit_probability") or 0)
    average_edge = float(combo.get("average_edge") or 0)
    min_probability = float(combo.get("min_probability") or 0)
    if section_key == "SUPER_HIGH_ODDS":
        return odds >= 4.0 and adjusted_hit >= 0.50
    if section_key == "BANKER":
        return 2.0 <= odds <= 3.2 and adjusted_hit >= 0.50 and min_probability >= 0.71
    if section_key == "VALUE":
        return 2.0 <= odds < 4.0 and adjusted_hit >= 0.48 and average_edge >= 0.05
    return False


def _section_combo_sort_key(combo: dict, section_key: str) -> tuple:
    odds = float(combo.get("combo_odds") or 0)
    adjusted_hit = float(combo.get("adjusted_hit_probability") or 0)
    average_edge = float(combo.get("average_edge") or 0)
    leg_count_penalty = 0 if len(combo.get("legs", [])) >= 2 else 1
    if section_key == "SUPER_HIGH_ODDS":
        return (leg_count_penalty, -adjusted_hit, -average_edge, -odds)
    if section_key == "BANKER":
        return (leg_count_penalty, -adjusted_hit, abs(odds - 2.4), -average_edge)
    return (leg_count_penalty, -average_edge, -adjusted_hit, -odds)


def _first_non_overlapping_combo(candidates: list[dict], used_leg_ids: set[str]) -> dict | None:
    for combo in candidates:
        if not (_combo_leg_ids(combo) & used_leg_ids):
            return combo
    return None


def _combo_leg_ids(combo: dict) -> set[str]:
    return {str(leg.get("id") or f"{leg.get('match_id')}|{leg.get('market_key')}|{leg.get('selection_name')}|{leg.get('line')}") for leg in combo.get("legs", [])}


def _section_stake_label(section_key: str, combo: dict) -> str:
    """Half-Kelly on the correlation-adjusted combo hit probability vs the combo
    odds — same unit system as singles (>=1u floor, capped). Replaces the three
    hardcoded fractional-unit scales the report used to mix."""
    units = _combo_stake_units_kelly(combo)
    if units <= 0:
        return "觀察（Kelly 計 0u）"
    return f"建議 {units:g}u"


def _combo_stake_units_kelly(combo: dict) -> float:
    hit = combo.get("adjusted_hit_probability") or combo.get("naive_hit_probability")
    odds = combo.get("combo_odds")
    return kelly_stake_units(hit, odds)


def _provisional_mobile_combo_cards(combos: list[dict]) -> list[str]:
    lines: list[str] = []
    for idx, combo in enumerate(combos, start=1):
        grade = str(combo.get("grade") or "")
        stake = _fmt(combo.get("stake_units"))
        action = "可落" if grade in {"A", "B"} else "觀察"
        lines.extend(
            [
                f"### #{idx}｜{grade} 級｜{action}｜{stake}u",
                f"Odds：{_fmt(combo.get('combo_odds'))}｜組合命中：{_pct(combo.get('adjusted_hit_probability'))}｜命中底線：{_pct(combo.get('min_probability'))}",
            ]
        )
        for leg_idx, leg in enumerate(combo["legs"], start=1):
            lines.append(f"- Leg {leg_idx}: {_leg_bet_label(leg)}")
        if _combo_has_repeated_match(combo):
            lines.append("- 注意：同場 / 同球員 exposure 較高，注碼要保守。")
        lines.append("")
    return lines


def _combo_has_repeated_match(combo: dict) -> bool:
    match_ids = [leg.get("match_id") for leg in combo.get("legs", [])]
    return len(match_ids) != len(set(match_ids))


def _provisional_betting_plan_lines(combos: list[dict]) -> list[str]:
    recommended = [combo for combo in combos if combo.get("grade") in {"A", "B"}]
    watch_only = [combo for combo in combos if combo.get("grade") == "C"]
    main_picks = recommended[:3]
    backup_picks = recommended[3:6]
    lines: list[str] = []
    if main_picks:
        lines.append("如果只落一注：")
        lines.extend(_provisional_combo_action_block(main_picks[0], 1))
        if len(main_picks) > 1:
            lines.append("")
            lines.append("想加 combo / 分散細注：")
            for idx, combo in enumerate(main_picks[1:], start=2):
                lines.extend(_provisional_combo_action_block(combo, idx))
        if _combo_has_shared_leg(main_picks):
            lines.append("")
            lines.append("注意：上面幾注有重複球員 / leg exposure，唔好當成完全獨立三注；總注碼要保守。")
    else:
        lines.append("主線落注：今日無 A / B 級 pick，建議唔落正式注。")
    if backup_picks:
        lines.append("")
        lines.append("後備細注：")
        for idx, combo in enumerate(backup_picks, start=1):
            lines.extend(_provisional_combo_action_block(combo, idx))
    if watch_only:
        lines.append("")
        lines.append(f"觀察名單：另外 {len(watch_only)} 個 C 級，只建議記錄或最多 0.05u。")
    lines.extend(
        [
            "",
            "點讀：",
            "- 命中底線 = 最弱一條 leg 嘅估算命中率；越高越穩。",
            "- 組合命中 = 扣咗相關性後嘅估算組合命中率；多 leg 會自然低啲。",
            "- Edge = 模型覺得賠率俾多咗幾多價值；正數越大越好。",
        ]
    )
    return lines


def _provisional_combo_action_block(combo: dict, idx: int) -> list[str]:
    lines = [
        f"{idx}. 建議 {_fmt(combo.get('stake_units'))}u｜{combo.get('grade')} 級｜odds {_fmt(combo.get('combo_odds'))}｜組合命中 {_pct(combo.get('adjusted_hit_probability'))}｜命中底線 {_pct(combo.get('min_probability'))}",
    ]
    for leg_idx, leg in enumerate(combo["legs"], start=1):
        lines.append(f"   - Leg {leg_idx}: {_leg_bet_label(leg)}")
    return lines


def _leg_bet_label(leg: dict) -> str:
    return f"{leg.get('market_name')}: {leg.get('selection_name')} @ {_fmt(leg.get('odds'))} ({leg.get('match_label')})"


def _combo_has_shared_leg(combos: list[dict]) -> bool:
    seen: set[str] = set()
    for combo in combos:
        for leg in combo["legs"]:
            key = str(leg.get("id") or f"{leg.get('match_id')}|{leg.get('market_key')}|{leg.get('selection_name')}")
            if key in seen:
                return True
            seen.add(key)
    return False


def _provisional_summary_table(combos: list[dict]) -> list[str]:
    lines = [
        "| # | 級別 | Pick | Odds | 命中底線 | 組合命中 | 信心 | 平均 Edge | 建議注碼 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, combo in enumerate(combos, start=1):
        lines.append(
            "| "
            f"{idx} | "
            f"{combo['grade']} | "
            f"{_combo_legs_label(combo['legs'])} | "
            f"{_fmt(combo['combo_odds'])} | "
            f"{_pct(combo['min_probability'])} | "
            f"{_pct(combo['adjusted_hit_probability'])} | "
            f"{combo['min_confidence']}->{combo['adjusted_confidence']} | "
            f"{_pct(combo['average_edge'], signed=True)} | "
            f"{_fmt(combo['stake_units'])}u |"
        )
    return lines


def _provisional_detail_cards(combos: list[dict]) -> list[str]:
    lines = []
    for idx, combo in enumerate(combos, start=1):
        lines.extend(
            [
                f"### #{idx}｜臨時 {combo['grade']}｜Odds {_fmt(combo['combo_odds'])}｜建議 {_fmt(combo['stake_units'])}u",
                "",
                f"- 組合命中：{_pct(combo['adjusted_hit_probability'])}（未扣相關性 {_pct(combo['naive_hit_probability'])}）",
                f"- 命中底線：{_pct(combo['min_probability'])}",
                f"- 信心：{combo['min_confidence']} -> {combo['adjusted_confidence']}",
                f"- 平均 Edge：{_pct(combo['average_edge'], signed=True)}",
                f"- 入選原因：{combo['risk_note']}",
                f"- 相關性：{combo['correlation_note']}",
                f"- 正式升級覆核：{combo['official_review']}",
                "",
                "| Leg | Market | Selection | Odds | 模型命中 | Edge | 信心 | 覆核 |",
                "|---|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for leg_idx, leg in enumerate(combo["legs"], start=1):
            lines.append(
                "| "
                f"{leg_idx} | "
                f"{leg.get('market_name')} | "
                f"{leg.get('selection_name')} | "
                f"{_fmt(leg.get('odds'))} | "
                f"{_pct(leg.get('model_probability'))} | "
                f"{_pct(leg.get('edge'), signed=True)} | "
                f"{leg.get('confidence')} | "
                f"{leg.get('review_note') or leg.get('risk_note')} |"
            )
        lines.append("")
    return lines


def _unpaired_leg_lines(legs: list[dict]) -> list[str]:
    if not legs:
        return ["無。"]
    lines = []
    for idx, leg in enumerate(sorted(legs, key=lambda item: (item["match_label"], -item["confidence"], -item["edge"])), start=1):
        lines.extend(
            [
                f"**#{idx}｜{_tier_label(str(leg.get('tier') or ''))}｜{leg.get('market_name')}: {leg['selection_name']} @ {_fmt(leg['odds'])}**",
                f"Match：{leg['match_label']}",
                f"Edge：{_pct(leg['edge'], signed=True)}｜信心：{leg['confidence']}",
                "未入組合原因：同場暫時無其他 compatible banker leg，或組合總 odds 未達 2.00。",
                "",
            ]
        )
    return lines


def _tier_section_lines(combos: list[dict], empty_message: str) -> list[str]:
    if not combos:
        return [empty_message]
    lines = []
    grouped: dict[str, list[dict]] = {}
    for combo in combos:
        grouped.setdefault(combo["legs"][0]["match_label"], []).append(combo)
    for match_label, match_combos in grouped.items():
        lines.extend([f"### {match_label}", ""])
        for size in (1, 2, 3):
            sized = [combo for combo in match_combos if len(combo["legs"]) == size]
            if not sized:
                continue
            lines.extend([f"#### {size}-Leg", ""])
            lines.extend(_combo_card_lines(sized))
            lines.append("")
    return lines


def _quick_pick_lines(combos: list[dict]) -> list[str]:
    if not combos:
        return ["暫時未有快速可睇 banker。"]
    ranked = _rank_combos_for_display(combos)
    lines = []
    for idx, combo in enumerate(ranked[:5], start=1):
        lines.extend(_combo_card(combo, idx, include_reason=False))
    return lines


def _rank_combos_for_display(combos: list[dict]) -> list[dict]:
    tier_order = {
        "穩膽": 0,
        "穩膽｜跨場Fallback": 1,
        "穩價值膽": 2,
        "穩價值膽｜跨場Fallback": 3,
        "穩膽+價值": 4,
        "穩膽+價值｜跨場Fallback": 5,
        "價值膽": 6,
        "價值膽｜跨場Fallback": 7,
        "高賠觀察": 8,
        "每日No.1｜進取小注": 9,
    }
    return sorted(
        combos,
        key=lambda combo: (
            tier_order.get(str(combo.get("tier")), 9),
            len(combo["legs"]),
            -combo["min_confidence"],
            -combo["average_edge"],
            combo["combo_odds"],
        ),
    )


def _daily_no1_combo(existing_combos: list[dict], high_odds_rows: list[dict]) -> dict | None:
    if existing_combos:
        return _rank_combos_for_display(existing_combos)[0]

    legs = []
    for row in high_odds_rows:
        leg = _no1_high_odds_leg(row)
        if leg is not None:
            legs.append(leg)
    legs.sort(key=lambda leg: (leg["edge"], leg["confidence"], leg["odds"]), reverse=True)
    if len(legs) < 2:
        return None

    selected = legs[:2]
    combo_odds = 1.0
    for leg in selected:
        combo_odds *= leg["odds"]
    min_confidence = min(leg["confidence"] for leg in selected)
    average_edge = sum(leg["edge"] for leg in selected) / len(selected)
    return {
        "legs": selected,
        "tier": "每日No.1｜進取小注",
        "combo_odds": combo_odds,
        "min_confidence": min_confidence,
        "average_edge": average_edge,
        "adjusted_confidence": max(0, min_confidence - 5),
        "adjusted_edge": max(0.0, average_edge - 0.015),
        "correlation_note": "跨場 2-leg 進取組合，已扣 5 信心分及 1.5% edge；只作每日主線，不當穩膽",
        "stake_units": 0.1,
        "risk_note": "正式 banker = 0；用最高兩條 match-winner +EV 候選組成每日 No.1；非穩膽，只可小注或觀察",
    }


def _no1_high_odds_leg(row: dict) -> dict | None:
    if row.get("market_key") != "match_winner":
        return None
    try:
        odds = float(row.get("odds"))
        edge = float(row.get("edge"))
        confidence = int(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    if odds < 2.5 or edge < 0.08 or confidence < 70:
        return None
    return {
        "id": f"daily-no1|{row.get('match_id')}|{row.get('market_key')}|{row.get('selection_name')}",
        "match_id": int(row["match_id"]),
        "match_label": _match_label(row),
        "selection_name": _display_label(row.get("selection_name")),
        "market_name": _display_label(row.get("market_name")),
        "market_key": row.get("market_key"),
        "selection_side": row.get("selection_side"),
        "tier": "HIGH_ODDS_VALUE",
        "line": row.get("line"),
        "odds": odds,
        "edge": edge,
        "confidence": confidence,
        "risk_note": "高賠 +EV，波動高",
    }


def _combo_table_lines(combos: list[dict]) -> list[str]:
    lines = [
        "| # | Tier | Legs | 參考組合 Odds | 最低信心 | 平均 Edge | 主要原因 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for idx, combo in enumerate(combos, start=1):
        lines.append(
            "| "
            f"{idx} | "
            f"{combo['tier']} | "
            f"{_combo_legs_label(combo['legs'])} | "
            f"{_fmt(combo['combo_odds'])} | "
            f"{combo['min_confidence']} | "
            f"{_pct(combo['average_edge'], signed=True)} | "
            f"{combo['risk_note']} |"
        )
    return lines


def _combo_card_lines(combos: list[dict]) -> list[str]:
    lines = []
    for idx, combo in enumerate(combos, start=1):
        lines.extend(_combo_card(combo, idx, include_reason=True))
    return lines


def _combo_card(combo: dict, idx: int, include_reason: bool) -> list[str]:
    lines = [
        f"**#{idx}｜{combo['tier']}｜Odds {_fmt(combo['combo_odds'])}｜信心 {combo['min_confidence']}→{combo.get('adjusted_confidence', combo['min_confidence'])}｜Edge {_pct(combo.get('adjusted_edge', combo['average_edge']), signed=True)}｜Stake {_fmt(combo.get('stake_units'))}u**",
    ]
    if include_reason:
        lines.append(f"原因：{combo['risk_note']}")
        lines.append(f"相關性調整：{combo.get('correlation_note') or 'N/A'}")
    match_labels = sorted({leg["match_label"] for leg in combo["legs"]})
    lines.append(f"Match：{' / '.join(match_labels)}")
    for leg_idx, leg in enumerate(combo["legs"], start=1):
        lines.append(f"Leg {leg_idx}：{_leg_card_label(leg)}")
    lines.append("")
    return lines


def _leg_card_label(leg: dict) -> str:
    market = leg.get("market_name")
    line = f" line {_fmt(leg.get('line'))}" if leg.get("line") is not None else ""
    market_label = f"{market}{line}: " if market else ""
    tier = _tier_label(str(leg.get("tier") or ""))
    return f"{market_label}{leg['selection_name']} @ {_fmt(leg['odds'])} ({leg['match_label']})｜{tier}"


def _high_odds_table_lines(rows: list[dict]) -> list[str]:
    lines = [
        "| # | Selection | Match | Odds | Model Prob | Edge | Reason |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    rows = sorted(rows, key=lambda row: (float(row.get("edge") or 0), float(row.get("odds") or 0)), reverse=True)
    for idx, row in enumerate(rows[:80], start=1):
        lines.append(
            "| "
            f"{idx} | "
            f"{row.get('market_name')}: {row.get('selection_name')} | "
            f"{_match_label(row)} | "
            f"{_fmt(row.get('odds'))} | "
            f"{_pct(row.get('model_probability'))} | "
            f"{_pct(row.get('edge'), signed=True)} | "
            f"{_banker_reason_label(str(row.get('reason') or 'high_odds_value_not_banker'))} |"
        )
    return lines


def _high_odds_card_lines(rows: list[dict]) -> list[str]:
    lines = []
    rows = sorted(rows, key=lambda row: (float(row.get("edge") or 0), float(row.get("odds") or 0)), reverse=True)
    for idx, row in enumerate(rows[:30], start=1):
        lines.extend(
            [
                f"**#{idx}｜{row.get('market_name')}: {row.get('selection_name')} @ {_fmt(row.get('odds'))}**",
                f"Match：{_match_label(row)}",
                f"Model：{_pct(row.get('model_probability'))}｜Edge：{_pct(row.get('edge'), signed=True)}",
                f"原因：{_banker_reason_label(str(row.get('reason') or 'high_odds_value_not_banker'))}",
                "",
            ]
        )
    return lines


def _near_banker_card_lines(rows: list[dict]) -> list[str]:
    lines = []
    rows = sorted(
        rows,
        key=lambda row: (
            float(row.get("model_probability") or 0),
            int(row.get("confidence") or 0),
            float(row.get("edge") or 0),
        ),
        reverse=True,
    )
    for idx, row in enumerate(rows[:30], start=1):
        lines.extend(
            [
                f"**#{idx}｜準穩膽觀察｜{row.get('market_name')}: {row.get('selection_name')} @ {_fmt(row.get('odds'))}**",
                f"Match：{_match_label(row)}",
                f"Model：{_pct(row.get('model_probability'))}｜Edge：{_pct(row.get('edge'), signed=True)}｜信心：{row.get('confidence')}",
                f"最低可接受：{_fmt(row.get('minimum_acceptable_odds'))}｜建議：0.25u 或只觀察",
                f"原因：{_banker_reason_label(str(row.get('reason') or 'near_banker_watch'))}",
                "",
            ]
        )
    if len(rows) > 30:
        lines.append(f"另外 {len(rows) - 30} 個準穩膽觀察項，詳見 Tennis_Market_Odds.txt。")
    return lines


def _unsupported_card_lines(rows: list[dict]) -> list[str]:
    lines = []
    for idx, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"#{idx}｜{row.get('market_name')}: {row.get('selection_name')} @ {_fmt(row.get('odds'))}",
                f"Status：{row.get('model_status') or 'ODDS_ONLY'}｜原因：{_hk_reason(str(row.get('reason') or 'unsupported_player_props_model_not_built'))}",
                "",
            ]
        )
    return lines


def _unsupported_market_rows(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("model_status") in {"ODDS_ONLY", "UNSUPPORTED_FOR_BANKER"}
        and row.get("banker_eligible") in {0, False, None}
    ]


def _prop_model_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row.get("model_status") == "PROP_MODEL"]


def _market_upgrade_review_rows(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("model_status") == "DERIVED_MODEL"
        and (row.get("market_decision") or row.get("decision")) == "MODEL_REVIEW"
        and _settlement_supported_market_key(str(row.get("market_key") or ""))
    ]


def _trial_banker_combinations(banker_legs: list[dict], market_review_rows: list[dict]) -> list[dict]:
    trial_legs = [_trial_leg_from_row(row) for row in market_review_rows]
    trial_legs = [leg for leg in trial_legs if leg is not None]
    candidate_legs = banker_legs + trial_legs
    combos = []
    seen = set()
    grouped: dict[str, list[dict]] = {}
    for leg in candidate_legs:
        grouped.setdefault(leg["match_label"], []).append(leg)
    for match_label, match_legs in grouped.items():
        for size in (2, 3):
            for leg_group in combinations(match_legs, size):
                if not any(leg.get("tier") == "MARKET_TRIAL" for leg in leg_group):
                    continue
                if not _combo_compatible(leg_group):
                    continue
                key = tuple(sorted(str(leg["id"]) for leg in leg_group))
                if key in seen:
                    continue
                seen.add(key)
                combo_odds = 1.0
                for leg in leg_group:
                    combo_odds *= leg["odds"]
                if combo_odds < 2.0:
                    continue
                min_confidence = min(leg["confidence"] for leg in leg_group)
                average_edge = sum(leg["edge"] for leg in leg_group) / len(leg_group)
                adjustment = _combo_correlation_adjustment(leg_group, min_confidence, average_edge)
                combos.append(
                    {
                        "legs": list(leg_group),
                        "tier": "試用Banker",
                        "combo_odds": combo_odds,
                        "min_confidence": min_confidence,
                        "average_edge": average_edge,
                        "adjusted_confidence": max(0, adjustment["adjusted_confidence"] - 4),
                        "adjusted_edge": max(0.0, adjustment["adjusted_edge"] - 0.015),
                        "correlation_note": f"{adjustment['note']}；未完成 settlement 驗證，額外扣 4 信心分及 1.5% edge",
                        "stake_units": 0.1,
                        "risk_note": "試用：有模型 + 可 settlement，但未夠 20 個 settled sample；只建議極小注觀察",
                    }
                )
    combos.sort(key=lambda combo: (len(combo["legs"]), -combo["adjusted_confidence"], -combo["adjusted_edge"], -combo["combo_odds"]))
    return combos[:20]


def _trial_leg_from_row(row: dict) -> dict | None:
    try:
        odds = float(row.get("odds"))
        edge = float(row.get("edge"))
        confidence = int(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    if edge < 0.05 or confidence < 80:
        return None
    minimum = row.get("minimum_acceptable_odds")
    if minimum is not None and odds < float(minimum):
        return None
    return {
        "id": f"trial|{row.get('match_id')}|{row.get('market_key')}|{row.get('selection_name')}|{row.get('line')}",
        "match_id": int(row["match_id"]),
        "match_label": _match_label(row),
        "selection_name": _display_label(row.get("selection_name")),
        "market_name": _display_label(row.get("market_name")),
        "market_key": row.get("market_key"),
        "selection_side": row.get("selection_side"),
        "tier": "MARKET_TRIAL",
        "line": row.get("line"),
        "odds": odds,
        "edge": edge,
        "confidence": confidence,
        "risk_note": _hk_reason(str(row.get("reason") or "settlement_supported_sample_building")),
    }


def _market_upgrade_card_lines(rows: list[dict]) -> list[str]:
    lines = []
    rows = sorted(rows, key=lambda row: (float(row.get("edge") or 0), float(row.get("model_probability") or 0)), reverse=True)
    for idx, row in enumerate(rows[:25], start=1):
        history = _market_validation_history(str(row.get("market_key") or ""))
        lines.extend(
            [
                f"**#{idx}｜{row.get('market_name')}: {row.get('selection_name')} @ {_fmt(row.get('odds'))}**",
                f"Match：{_match_label(row)}",
                f"Model：{_pct(row.get('model_probability'))}｜Edge：{_pct(row.get('edge'), signed=True)}｜信心：{row.get('confidence')}",
                f"升級狀態：{_hk_reason(str(row.get('reason') or 'settlement_supported_sample_building'))}",
                f"驗證樣本：settled {history['settled']} / tracked {history['tracked']}｜Avg CLV：{_pct(history['avg_clv'], signed=True)}｜ROI：{_pct(history['roi'], signed=True)}",
                "",
            ]
        )
    if len(rows) > 25:
        lines.append(f"另外 {len(rows) - 25} 個升級觀察市場，詳見 Tennis_Market_Odds.txt。")
    return lines


def _market_upgrade_table_lines(rows: list[dict]) -> list[str]:
    rows = sorted(rows, key=lambda row: (float(row.get("edge") or 0), float(row.get("model_probability") or 0)), reverse=True)
    lines = [
        "| # | Market | Selection | Match | Odds | Model Prob | Edge | Conf | Official Review |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(rows[:25], start=1):
        history = _market_validation_history(str(row.get("market_key") or ""))
        lines.append(
            "| "
            f"{idx} | "
            f"{row.get('market_name')} | "
            f"{row.get('selection_name')} | "
            f"{_match_label(row)} | "
            f"{_fmt(row.get('odds'))} | "
            f"{_pct(row.get('model_probability'))} | "
            f"{_pct(row.get('edge'), signed=True)} | "
            f"{row.get('confidence')} | "
            f"settled {history['settled']}/20, ROI {_pct(history['roi'], signed=True)}, CLV {_pct(history['avg_clv'], signed=True)} |"
        )
    if len(rows) > 25:
        lines.append(f"| ... | ... | ... | ... | ... | ... | ... | ... | 另外 {len(rows) - 25} 個，詳見 Tennis_Market_Odds.txt |")
    return lines


def _prop_model_card_lines(rows: list[dict]) -> list[str]:
    lines = []
    rows = sorted(rows, key=lambda row: (float(row.get("edge") or 0), float(row.get("model_probability") or 0)), reverse=True)
    for idx, row in enumerate(rows[:20], start=1):
        lines.extend(
            [
                f"**#{idx}｜{row.get('market_name')}: {row.get('selection_name')} @ {_fmt(row.get('odds'))}**",
                f"Match：{_match_label(row)}",
                f"Model：{_pct(row.get('model_probability'))}｜Edge：{_pct(row.get('edge'), signed=True)}｜信心：{row.get('confidence')}",
                f"原因：{_hk_reason(str(row.get('reason') or 'ace_prop_model_review'))}",
                "",
            ]
        )
    if len(rows) > 20:
        lines.append(f"另外 {len(rows) - 20} 個 modelled props，詳見 Tennis_Market_Odds.txt。")
    return lines


def _legacy_cross_game_report(match_date: str, rows: list[dict]) -> str:
    legs = _banker_eligible_legs(rows)
    combos_by_size = {size: _banker_combinations(legs, size) for size in (2, 3, 4)}
    total_combos = sum(len(combos) for combos in combos_by_size.values())
    lines = [
        "Tennis Wong Choi 全日 Banker Report",
        f"日期：{match_date}",
        "",
        f"合格 banker legs：{len(legs)}",
        f"Banker combinations：{total_combos}",
        "",
        "## Banker Combinations（2-4 Legs，參考 odds >= 2.00）",
        "",
    ]
    for size in (2, 3, 4):
        combos = combos_by_size[size]
        lines.extend([f"### {size}-Leg Banker", ""])
        if not combos:
            lines.extend([f"未有合格 {size}-leg banker。", ""])
            continue
        lines.extend(_combo_table_lines(combos))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_market_odds_report(match_date: str) -> str:
    rows = market_odds_for_date(match_date)
    lines = [
        "Tennis Wong Choi Market Odds Inventory",
        f"Date: {match_date}",
        "",
        "Pricing status: MODELLED markets can enter banker logic. ODDS_ONLY / UNSUPPORTED_FOR_BANKER markets are listed for review only.",
        "注意：呢度嘅狀態 tag 屬 market-path 觀察用，odds re-scrape 後可能同實際落注脫鈎。",
        "正式落注以 Daily Report / Banker Report（predictions 表 decision=BET）為準 —— 即使某腳喺呢度顯示 UNSUPPORTED_FOR_BANKER，只要佢喺 Daily Report 入面係 BET，就係已推介。",
        "",
    ]
    current_match = None
    for row in rows:
        match_label = f"{row['tournament_name']} | {row['player_a_name']} v {row['player_b_name']}"
        if match_label != current_match:
            current_match = match_label
            lines.extend(["", f"## {match_label}", ""])
        status = _market_pricing_status(row)
        line = _fmt(row["line"])
        lines.append(
            f"- {row['market_name']} [{row['market_key']}] | "
            f"{row['selection_name']} | line {line} | odds {_fmt(row['odds'])} | {status}"
        )
    if not rows:
        lines.append("No market odds snapshots found.")
    return "\n".join(lines).strip() + "\n"


def market_odds_for_date(match_date: str) -> list[dict]:
    _ensure_market_predictions_table()
    with get_connection() as conn:
        rows = conn.execute(
            """
            WITH BestLevels AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY tournament_id, tour
                           ORDER BY (source_provider = 'curated_tournament_metadata') DESC, (level != 'UNKNOWN' AND level != '未確認') DESC, (surface IS NOT NULL) DESC, id DESC
                       ) AS rn
                FROM tournament_levels
            )
            SELECT
                mo.*,
                t.name AS tournament_name,
                tl.level AS tournament_level,
                tl.surface AS tournament_surface,
                p1.name AS player_a_name,
                p2.name AS player_b_name,
                lp.prediction_id,
                lp.decision AS prediction_decision,
                mp.model_status,
                mp.decision AS market_decision,
                mp.banker_eligible,
                mp.model_probability,
                mp.no_vig_market_probability,
                mp.edge,
                mp.reason
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            JOIN tournaments t ON t.id = m.tournament_id
            LEFT JOIN BestLevels tl ON tl.tournament_id = m.tournament_id AND tl.tour = m.tour AND tl.rn = 1
            JOIN players p1 ON p1.id = m.player_a_id
            JOIN players p2 ON p2.id = m.player_b_id
            LEFT JOIN market_predictions mp ON mp.market_odds_snapshot_id = mo.id
            LEFT JOIN (
                SELECT p1.match_id, p1.id AS prediction_id, p1.decision
                FROM predictions p1
                JOIN (
                    SELECT match_id, MAX(id) AS max_prediction_id
                    FROM predictions
                    GROUP BY match_id
                ) latest ON latest.max_prediction_id = p1.id
            ) lp ON lp.match_id = m.id
            WHERE m.match_date = ?
              AND mo.id IN (
                SELECT MAX(mo2.id)
                FROM market_odds_snapshots mo2
                JOIN matches m2 ON m2.id = mo2.match_id
                WHERE m2.match_date = ?
                GROUP BY mo2.match_id, mo2.market_key, mo2.market_name, mo2.selection_name, COALESCE(mo2.line, -999999)
              )
            ORDER BY t.name, p1.name, p2.name, mo.market_key, mo.market_name, mo.line, mo.selection_name
            """,
            (match_date, match_date),
        ).fetchall()
    return [dict(row) for row in rows]


def _pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value * 100:.1f}%"


def _fmt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4g}"


def _market_pricing_status(row: dict) -> str:
    if row.get("model_status"):
        status = str(row["model_status"])
        decision = str(row.get("market_decision") or "")
        if row.get("banker_eligible"):
            return f"{status}_BANKER_ELIGIBLE"
        if decision == status:
            return status
        if decision and decision != "None":
            return f"{status}_{decision}"
        return status
    if row["market_key"] != "match_winner":
        return "ODDS_ONLY_MODEL_NOT_BUILT"
    if _outside_mvp_scope(row):
        return "ODDS_ONLY_OUTSIDE_MVP_SCOPE"
    if row.get("prediction_id") is None:
        return "ODDS_ONLY_OUTSIDE_MODEL_SCOPE"
    return f"PRICED_{row.get('prediction_decision') or 'REVIEW'}"


def _outside_mvp_scope(row: dict) -> bool:
    tournament = str(row.get("tournament_name") or "").lower()
    player_a = str(row.get("player_a_name") or "")
    player_b = str(row.get("player_b_name") or "")
    level = str(row.get("tournament_level") or "").upper()
    if any(token in tournament for token in ("challenger", "itf", "futures", "utr")):
        return True
    if "/" in player_a or "/" in player_b:
        return True
    return level == "UNKNOWN"


def _banker_eligible_legs(rows: list[dict]) -> list[dict]:
    legs = []
    for row in rows:
        leg = _banker_eligible_leg(row)
        if leg is not None:
            legs.append(leg)
    return legs


def _banker_eligible_leg(row: dict) -> dict | None:
    if "banker_eligible" in row and "model_status" in row:
        return _banker_leg_from_market_prediction(row)
    if row.get("decision") != "BET":
        return None
    if row.get("market_key", "match_winner") != "match_winner":
        return None

    try:
        odds = float(row.get("current_market_odds"))
        edge = float(row.get("edge"))
        confidence = int(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    if edge < 0.035 or confidence < 65:
        return None

    payload = _pricing_payload(row)
    filter_result = payload.get("filter", {})
    pricing = payload.get("pricing", {})
    if filter_result.get("hard_no_bet_reasons") or pricing.get("errors"):
        return None
    minimum_acceptable = row.get("minimum_acceptable_odds")
    if minimum_acceptable is not None and odds < float(minimum_acceptable):
        return None
    if not _banker_mapping_verified(row, pricing):
        return None

    return {
        "id": _banker_leg_id(row),
        "match_id": int(row["match_id"]),
        "match_label": _match_label(row),
        "selection_name": _display_label(row.get("selection_name")),
        "market_name": "Match Betting",
        "market_key": "match_winner",
        "selection_side": pricing.get("selection_side") or row.get("mapped_selection_side"),
        "tier": _prediction_leg_tier(row),
        "line": None,
        "odds": odds,
        "edge": edge,
        "confidence": confidence,
        "model_probability": float(row.get("model_probability") or 0),
        "risk_note": _banker_risk_note(filter_result),
    }


def _banker_leg_from_market_prediction(row: dict) -> dict | None:
    if row.get("banker_eligible") not in {1, True}:
        return None
    if row.get("model_status") not in {"MODELLED", "DERIVED_MODEL"}:
        return None
    try:
        odds = float(row.get("odds"))
        edge = float(row.get("edge"))
        confidence = int(row.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    if edge < 0.035 or confidence < 65:
        return None
    tier = _market_prediction_tier(row)
    return {
        "id": f"{row.get('match_id')}|{row.get('market_key')}|{row.get('selection_name')}|{row.get('line')}",
        "match_id": int(row["match_id"]),
        "match_label": _match_label(row),
        "selection_name": _display_label(row.get("selection_name")),
        "market_name": _display_label(row.get("market_name")),
        "market_key": row.get("market_key"),
        "selection_side": row.get("selection_side"),
        "tier": tier,
        "line": row.get("line"),
        "odds": odds,
        "edge": edge,
        "confidence": confidence,
        "model_probability": float(row.get("model_probability") or 0),
        "risk_note": _banker_reason_label(str(row.get("reason") or tier)),
    }


def _pricing_payload(row: dict) -> dict:
    raw = row.get("pricing_json") or "{}"
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"pricing": {}, "filter": {"hard_no_bet_reasons": ["invalid_pricing_json"]}}
    return payload if isinstance(payload, dict) else {"pricing": {}, "filter": {}}


def _banker_mapping_verified(row: dict, pricing: dict) -> bool:
    selection = str(row.get("selection_name") or "")
    player_a = str(row.get("player_a_name") or "")
    player_b = str(row.get("player_b_name") or "")
    pricing_side = pricing.get("selection_side")
    if pricing_side == "player_a" and not _same_name(selection, player_a):
        return False
    if pricing_side == "player_b" and not _same_name(selection, player_b):
        return False
    if pricing_side not in {"player_a", "player_b"} and not (_same_name(selection, player_a) or _same_name(selection, player_b)):
        return False

    mapped_side = row.get("mapped_selection_side")
    if mapped_side in {"player_a", "player_b"} and pricing_side in {"player_a", "player_b"} and mapped_side != pricing_side:
        return False
    mapped_odds = row.get("mapped_selection_odds")
    if mapped_odds is not None:
        try:
            return abs(float(mapped_odds) - float(row.get("current_market_odds"))) < 0.0001
        except (TypeError, ValueError):
            return False
    return True


def _banker_leg_id(row: dict) -> str:
    selection = " ".join(str(row.get("selection_name") or "").lower().split())
    return f"{row.get('match_id')}|match_winner|{selection}"


def _banker_risk_note(filter_result: dict) -> str:
    warnings = filter_result.get("warnings") or []
    notes = []
    if any("low_sample" in warning for warning in warnings):
        notes.append("低樣本")
    if any("stale" in warning for warning in warnings):
        notes.append("資料接近 freshness 上限")
    return "、".join(notes) if notes else "無主要紅旗"


def _market_prediction_tier(row: dict) -> str:
    if row.get("tier"):
        return str(row["tier"])
    raw = row.get("pricing_json")
    if raw:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        tier = payload.get("tier")
        if tier:
            return str(tier)
    if row.get("model_status") == "DERIVED_MODEL":
        return "VALUE_BANKER"
    return "CORE_BANKER" if float(row.get("model_probability") or 0) >= 0.68 else "VALUE_BANKER"


def _prediction_leg_tier(row: dict) -> str:
    probability = float(row.get("model_probability") or 0)
    edge = float(row.get("edge") or 0)
    confidence = int(row.get("confidence") or 0)
    odds = float(row.get("current_market_odds") or 0)
    if probability >= 0.68 and edge >= 0.05 and confidence >= 80 and odds <= 2.20:
        return "CORE_BANKER"
    return "VALUE_BANKER"


def _banker_reason_label(reason: str) -> str:
    if reason.startswith("core_banker"):
        return "穩膽：高勝率 + 正 Edge + 通過安全閘"
    if reason.startswith("stable_value_banker"):
        return "穩價值膽：價值膽已被 hit rate + ROI + CLV 驗證，升級為較穩定 value"
    if reason.startswith("value_banker"):
        return "價值膽：勝率合格 + Edge 足夠"
    if reason.startswith("near_banker_watch"):
        return "準穩膽：接近 CORE，但仍差少少安全 margin；只列觀察"
    if reason.startswith("high_odds_value_not_banker"):
        return "高賠 value：有 Edge，但命中率/波動不列穩膽"
    return _hk_reason(reason)


def _banker_combinations(legs: list[dict], size: int) -> list[dict]:
    combos = []
    seen = set()
    for leg_group in combinations(legs, size):
        if len({leg["match_id"] for leg in leg_group}) != size:
            continue
        key = tuple(sorted(leg["id"] for leg in leg_group))
        if key in seen:
            continue
        seen.add(key)

        combo_odds = 1.0
        for leg in leg_group:
            combo_odds *= leg["odds"]
        if combo_odds < 2.0:
            continue

        min_confidence = min(leg["confidence"] for leg in leg_group)
        average_edge = sum(leg["edge"] for leg in leg_group) / size
        risk_notes = sorted({leg["risk_note"] for leg in leg_group if leg["risk_note"] != "無主要紅旗"})
        combos.append(
            {
                "legs": list(leg_group),
                "combo_odds": combo_odds,
                "min_confidence": min_confidence,
                "average_edge": average_edge,
                "risk_note": "、".join(risk_notes) if risk_notes else "無主要紅旗",
            }
        )
    combos.sort(key=lambda combo: (combo["min_confidence"], combo["average_edge"], combo["combo_odds"]), reverse=True)
    return combos


def _same_game_banker_combinations(legs: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for leg in legs:
        grouped.setdefault(leg["match_label"], []).append(leg)
    combos_by_match = {}
    for match_label, match_legs in grouped.items():
        combos = []
        seen = set()
        for size in (1, 2, 3):
            for leg_group in combinations(match_legs, size):
                if not _combo_compatible(leg_group):
                    continue
                key = tuple(sorted(leg["id"] for leg in leg_group))
                if key in seen:
                    continue
                seen.add(key)
                combo_odds = 1.0
                for leg in leg_group:
                    combo_odds *= leg["odds"]
                if combo_odds < 2.0:
                    continue
                min_confidence = min(leg["confidence"] for leg in leg_group)
                average_edge = sum(leg["edge"] for leg in leg_group) / size
                adjustment = _combo_correlation_adjustment(leg_group, min_confidence, average_edge)
                risk_notes = sorted({leg["risk_note"] for leg in leg_group if leg["risk_note"] != "無主要紅旗"})
                combos.append(
                    {
                        "legs": list(leg_group),
                        "tier": _combo_tier(leg_group),
                        "combo_odds": combo_odds,
                        "min_confidence": min_confidence,
                        "average_edge": average_edge,
                        "adjusted_confidence": adjustment["adjusted_confidence"],
                        "adjusted_edge": adjustment["adjusted_edge"],
                        "correlation_note": adjustment["note"],
                        "stake_units": _combo_stake_units(_combo_tier(leg_group)),
                        "risk_note": "、".join(risk_notes) if risk_notes else "無主要紅旗",
                    }
                )
        combos.sort(key=lambda combo: (len(combo["legs"]), -combo["min_confidence"], -combo["average_edge"], -combo["combo_odds"]))
        if combos:
            combos_by_match[match_label] = combos
    return combos_by_match


def _cross_match_fallback_combinations(legs: list[dict]) -> list[dict]:
    combos = []
    seen = set()
    safe_legs = [leg for leg in legs if leg.get("market_key") == "match_winner"]
    for leg_group in combinations(safe_legs, 2):
        if len({leg["match_id"] for leg in leg_group}) != 2:
            continue
        key = tuple(sorted(leg["id"] for leg in leg_group))
        if key in seen:
            continue
        seen.add(key)
        combo_odds = 1.0
        for leg in leg_group:
            combo_odds *= leg["odds"]
        if combo_odds < 2.0:
            continue
        min_confidence = min(leg["confidence"] for leg in leg_group)
        average_edge = sum(leg["edge"] for leg in leg_group) / len(leg_group)
        adjustment = _cross_match_correlation_adjustment(leg_group, min_confidence, average_edge)
        risk_notes = sorted({leg["risk_note"] for leg in leg_group if leg["risk_note"] != "無主要紅旗"})
        risk_note = "跨場 fallback：全日無同場 banker combo，改用不同賽事 2-leg；" + ("、".join(risk_notes) if risk_notes else "每腿通過安全閘")
        tier = _combo_tier(leg_group)
        combos.append(
            {
                "legs": list(leg_group),
                "tier": f"{tier}｜跨場Fallback",
                "combo_odds": combo_odds,
                "min_confidence": min_confidence,
                "average_edge": average_edge,
                "adjusted_confidence": adjustment["adjusted_confidence"],
                "adjusted_edge": adjustment["adjusted_edge"],
                "correlation_note": adjustment["note"],
                "stake_units": min(_combo_stake_units(tier), 0.5),
                "risk_note": risk_note,
            }
        )
    combos.sort(key=lambda combo: (len(combo["legs"]), -combo["min_confidence"], -combo["average_edge"], -combo["combo_odds"]))
    return combos


def _combo_compatible(legs: tuple[dict, ...]) -> bool:
    directional = {leg.get("selection_side") for leg in legs if leg.get("selection_side") in {"player_a", "player_b"}}
    if len(directional) > 1:
        return False
    markets = [str(leg.get("market_name") or "") for leg in legs]
    if len(markets) != len(set(markets)):
        return False
    market_keys = [str(leg.get("market_key") or leg.get("market_name") or "") for leg in legs]
    if len(market_keys) != len(set(market_keys)):
        return False
    return True


def _cross_match_correlation_adjustment(legs: tuple[dict, ...], min_confidence: int, average_edge: float) -> dict:
    adjusted_confidence = max(0, min_confidence - 2)
    adjusted_edge = max(0.0, average_edge - 0.005)
    return {
        "adjusted_confidence": adjusted_confidence,
        "adjusted_edge": adjusted_edge,
        "note": "跨場 fallback 2-leg，已扣 2 信心分及 0.5% edge 作保守處理",
    }


def _combo_correlation_adjustment(legs: tuple[dict, ...], min_confidence: int, average_edge: float) -> dict:
    size = len(legs)
    same_direction = len({leg.get("selection_side") for leg in legs if leg.get("selection_side") in {"player_a", "player_b"}}) == 1 and size > 1
    directional_count = sum(1 for leg in legs if leg.get("selection_side") in {"player_a", "player_b"})
    haircut = max(0, size - 1) * 4
    edge_haircut = max(0, size - 1) * 0.01
    if same_direction and directional_count >= 2:
        haircut += 3
        edge_haircut += 0.005
    adjusted_confidence = max(0, min_confidence - haircut)
    adjusted_edge = max(0.0, average_edge - edge_haircut)
    if size == 1:
        note = "單腿，無同場相關性扣分"
    elif same_direction and directional_count >= 2:
        note = f"同場同方向 {size}-leg，已扣 {haircut} 信心分"
    else:
        note = f"同場相關 {size}-leg，已扣 {haircut} 信心分"
    return {"adjusted_confidence": adjusted_confidence, "adjusted_edge": adjusted_edge, "note": note}


def _combo_stake_units(tier: str) -> float:
    if tier == "穩膽":
        return 1.0
    if tier == "穩價值膽":
        return 0.5
    if tier == "穩膽+價值":
        return 0.5
    if tier == "價值膽":
        return 0.25
    if tier == "高賠觀察":
        return 0.1
    return 0.0


def _combo_tier(legs: tuple[dict, ...]) -> str:
    tiers = {leg.get("tier") for leg in legs}
    if tiers == {"CORE_BANKER"}:
        return "穩膽"
    if "HIGH_ODDS_VALUE" in tiers:
        return "高賠觀察"
    if tiers == {"STABLE_VALUE_BANKER"} or "STABLE_VALUE_BANKER" in tiers:
        return "穩價值膽"
    if "CORE_BANKER" in tiers:
        return "穩膽+價值"
    return "價值膽"


def _combo_legs_label(legs: list[dict]) -> str:
    labels = []
    for leg in legs:
        market = leg.get("market_name")
        line = f" line {_fmt(leg.get('line'))}" if leg.get("line") is not None else ""
        market_label = f"{market}{line}: " if market else ""
        labels.append(f"{market_label}{leg['selection_name']} @ {_fmt(leg['odds'])} ({leg['match_label']})")
    return " / ".join(labels)


def _tier_label(tier: str) -> str:
    labels = {
        "CORE_BANKER": "穩膽 leg",
        "STABLE_VALUE_BANKER": "穩價值膽 leg",
        "VALUE_BANKER": "價值膽 leg",
        "HIGH_ODDS_VALUE": "高賠觀察",
    }
    return labels.get(tier, tier or "未分層")


def _bet_summary_lines(bets: list[dict]) -> list[str]:
    if not bets:
        return ["暫時未有通過所有 hard rule 嘅 BET。"]
    lines = [
        "| 選擇 | 賽事 | 現時賠率 | 最低可接受 | 模型勝率 | Edge | 注碼 | 風險 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in bets:
        lines.append(
            "| "
            f"{row['selection_name']} | "
            f"{_match_label(row)} | "
            f"{_fmt(row['current_market_odds'])} | "
            f"{_fmt(row['minimum_acceptable_odds'])} | "
            f"{_pct(row['model_probability'])} | "
            f"{_pct(row['edge'], signed=True)} | "
            f"{_stake_label(row['stake_units'], row['decision'])} | "
            f"{row['risk']} |"
        )
    lines.append("")
    lines.append("只可喺現時賠率仍然高過「最低可接受」時先考慮；跌穿即 NO_BET。")
    return lines


def _no_bet_summary_lines(no_bets: list[dict]) -> list[str]:
    """Collapse NO_BET matches into a count + compact reason breakdown + a
    short table — instead of printing a full ~30-line card for every match
    (which alone bloated the report past 90KB)."""
    reason_counts: dict[str, int] = {}
    for row in no_bets:
        try:
            filter_result = json.loads(row["pricing_json"]).get("filter", {})
        except (TypeError, ValueError, KeyError):
            filter_result = {}
        reasons = filter_result.get("hard_no_bet_reasons") or ["other"]
        reason_counts[reasons[0]] = reason_counts.get(reasons[0], 0) + 1

    lines = [f"## 不下注（{len(no_bets)} 場，僅摘要）", ""]
    for reason, count in sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {_hk_reason(reason)}：{count} 場")
    lines.append("")
    lines.append("（詳細逐場 odds / 模型數字見 Tennis_Market_Odds.txt；此處不再逐場展開卡片。）")
    lines.append("")
    return lines


def _bsd_status(raw_response: str | None) -> str:
    if not raw_response:
        return "未見近期錯誤"
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return "fixture source error"
    message = str(payload.get("message") or payload)
    if "Sports Addon" in message or "402" in message:
        return "不可即時刷新：BSD Tennis API 需要 Sports Addon"
    return message[:160]


def _hk_reason(reason: str) -> str:
    labels = {
        "current_odds_below_minimum_acceptable_odds": "現時賠率低過最低可接受賠率",
        "data_quality_score_below_65": "資料質素低過 65 分",
        "data_provenance_validation_failed": "資料 provenance 驗證失敗",
        "doubles_outside_mvp_scope": "雙打，不在 MVP 範圍",
        "challenger_outside_mvp_scope": "Challenger，不在 MVP 範圍",
        "itf_outside_mvp_scope": "ITF/Futures，不在 MVP 範圍",
        "longshot_requires_higher_data_quality": "高賠率 longshot 需要更高資料質素",
        "edge_artifact_no_bet": "模型 edge ≥20%，回測證實呢類分歧長期輸錢（artifact），唔落",
        "longshot_negative_roi_no_bet": "賠率 ≥5.0 longshot，回測 ROI −37%，唔落",
        "missing_core_elo_inputs": "缺少核心 Elo 輸入",
        "confidence_below_bet_floor": "風險調整後信心低過下注門檻",
        "negative_ev_at_market_price": "現價計 Kelly 為 0（扣水後 -EV），唔落",
        "missing_market_odds": "缺少市場賠率",
        "other": "其他／未分類",
        "odds_selection_mapping_failed": "賠率 selection 未能可靠對返球員，停止定價",
        "utr_outside_mvp_scope": "UTR，不在 MVP 範圍",
        "competition_metadata_not_confirmed": "賽事級別/場地未有確認 mapping",
        "missing_competition": "缺少賽事 competition metadata",
        "not_linked_to_feature_snapshot": "未能配對到 feature snapshot",
        "unsupported_player_props_model_not_built": "暫未有可驗證模型，僅列 odds-only",
        "missing_match_winner_prediction": "缺少 match-winner prediction",
        "missing_model_or_market_probability": "缺少模型或去水市場概率",
        "below_banker_threshold": "未達 banker 安全門檻",
        "original_prediction_failed_safety_gate": "原始投注安全閘未通過",
        "ace_prop_model_review": "Aces props 已有歷史均值模型；有賽後 box score 時會自動 settlement，未夠 CLV/ROI sample 前暫列 model review",
        "settlement_supported_sample_building": "有模型及可 settlement，正在累積 20 個 settled sample，暫不入 banker",
        "market_validation_not_positive_yet": "已有 settlement sample，但 CLV/ROI 未證明正向，暫不入 banker",
        "settlement_not_supported_for_market": "暫未支援此市場自動 settlement，不入 banker",
        "model_not_ready_for_banker": "模型未達 banker 升級條件",
        "tier_downgraded_negative_roi": "同類 tier 成熟樣本 ROI 轉負，暫時降級為 review-only",
        "tier_downgraded_negative_clv": "同類 tier 成熟樣本 CLV 轉負，暫時降級為 review-only",
        "tier_downgraded_calibration_overconfident": "Calibration 顯示同概率 bucket 過度自信，暫時降級為 review-only",
    }
    return labels.get(reason, reason)


def _source_label(source: str) -> str:
    labels = {
        "tournaments": "賽事 metadata",
        "rankings_atp": "ATP ranking",
        "rankings_wta": "WTA ranking",
        "history": "歷史賽果 / Elo",
        "upcoming_matches": "明日賽程",
        "odds": "Sportsbet odds",
        "event_markets": "Sportsbet 單場 markets",
    }
    return labels.get(source, source)


def _source_error_label(error: str) -> str:
    lowered = error.lower()
    if "only_match_winner" in lowered or "enrichment_incomplete" in lowered:
        return "多市場 enrichment 未完成（只抓到 match-winner）→ 組合會偏少，請確認 live 跑咗 enrich-event-markets"
    if "nodename nor servname provided" in lowered or "could not resolve host" in lowered:
        return "本地 DNS 無法解析外部網站，live refresh 未能連線"
    if "http 402" in lowered or "sports addon" in lowered:
        return "API plan 權限不足，需要 Sports Addon / 對應 provider 權限"
    if "403" in lowered or "forbidden" in lowered:
        return "來源拒絕存取或被封鎖"
    if "timeout" in lowered or "timed out" in lowered:
        return "連線逾時"
    return "資料源連線失敗"


def _stake_label(stake_units: float | None, decision: str | None = None) -> str:
    units = float(stake_units or 0)
    if decision != "BET" or units <= 0:
        return "不下注"
    # 1 unit == $1 against the virtual bankroll. Show the actual half-Kelly size,
    # not a hardcoded "1 unit" (the old label ignored stake_units entirely).
    return f"{units:g}u (${units:.2f})"


def _display_label(value: str | None, fallback: str = "未確認（資料不足）") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text or text.upper() == "UNKNOWN" or text.lower() == "none":
        return fallback
    return text


def _report_red_flags(filter_result: dict) -> list[str]:
    hard_reasons = filter_result.get("hard_no_bet_reasons") or []
    if hard_reasons:
        return [_hk_reason(reason) for reason in hard_reasons[:5]]

    warnings = filter_result.get("warnings") or []
    labels = []
    if any("low_sample" in warning for warning in warnings):
        labels.append("部分 split 樣本偏低，已降低注碼/信心")
    if any("missing_historical_rank" in warning for warning in warnings):
        labels.append("部分歷史對手排名缺失，沒有用現時排名代替")
    if any("missing_player_history" in warning for warning in warnings):
        labels.append("部分球員歷史資料不足，模型只使用有 provenance 嘅特徵")
    if any("rank_seed_elo" in warning for warning in warnings):
        labels.append("Elo 由即時排名 fallback 估算，已降低信心/注碼")
    if any("unknown tournament level" in warning or "unknown_tournament_level" in warning for warning in warnings):
        labels.append("賽事級別未確認，不能作投注建議")
    if any("stale" in warning for warning in warnings):
        labels.append("部分資料接近 freshness 上限")
    risk_adjustments = filter_result.get("risk_adjustments") or []
    if "rank_seed_destaked" in risk_adjustments:
        labels.append("Elo 由即時排名 fallback，可靠度低：已封頂至最低注")
    return labels[:5]


def _match_label(row: dict) -> str:
    player_a = _display_label(row.get("player_a_name"), "Player A")
    player_b = _display_label(row.get("player_b_name"), "Player B")
    return f"{player_a} vs {player_b}"


def _opponent_name(row: dict) -> str | None:
    selection = str(row.get("selection_name") or "").strip()
    player_a = str(row.get("player_a_name") or "").strip()
    player_b = str(row.get("player_b_name") or "").strip()
    if _same_name(selection, player_a):
        return player_b
    if _same_name(selection, player_b):
        return player_a
    return None


def _same_name(left: str, right: str) -> bool:
    return " ".join(left.lower().split()) == " ".join(right.lower().split())


def _model_explanation_lines(row: dict, pricing: dict, components: list[dict]) -> list[str]:
    active_components = [component for component in components if component.get("active", True)]
    if not active_components:
        active_components = components
    selected_probability = float(row["model_probability"] or 0)
    is_player_a = _same_name(str(row.get("selection_name") or ""), str(row.get("player_a_name") or ""))
    selection_side = "player_a" if is_player_a else "player_b"
    selection = _display_label(row.get("selection_name"))
    market_probability = float(row.get("no_vig_market_probability") or 0)
    edge = float(row.get("edge") or 0)
    margin = selected_probability - market_probability
    supportive = _component_summary(active_components, selection_side, True)
    cautious = _component_summary(active_components, selection_side, False)
    lines = [
        f"- 揀 {selection} 主要因為市場只當佢約有 {_pct(market_probability)} 勝算，但模型評到 {_pct(selected_probability)}，中間多出 {_pct(margin, signed=True)}；即係現時賠率比模型認為嘅公平價偏高。",
    ]
    if supportive:
        lines.append(f"- 支持因素：{supportive}。")
    if cautious:
        lines.append(f"- 保留位：{cautious}。")
    lines.append(f"- 下注門檻：現價 {_fmt(row.get('current_market_odds'))} 要高過最低可接受賠率 {_fmt(row.get('minimum_acceptable_odds'))}；跌穿就唔應追。")
    if edge < 0.1:
        lines.append("- 但優勢唔算厚，若賠率稍跌穿門檻就應該放棄。")
    lines.append("- 模型勝率以 Elo 為骨幹，喺 logit 空間加入其他有效因素微調；中性（0.5）或資料不足嘅項目唔會拉低信號。")
    return lines


def _selection_component_probability(component: dict, selection_side: str) -> float:
    probability = float(component.get("probability") or 0.5)
    if selection_side == "player_b":
        return 1 - probability
    return probability


def _component_summary(components: list[dict], selection_side: str, supportive: bool) -> str:
    ranked: list[tuple[float, dict, float]] = []
    for component in components:
        probability = _selection_component_probability(component, selection_side)
        score = (probability - 0.5) * float(component.get("weight") or 0)
        ranked.append((score, component, probability))
    ranked.sort(key=lambda item: item[0], reverse=supportive)
    picked = []
    for score, component, probability in ranked:
        if supportive and score <= 0:
            continue
        if not supportive and score >= 0:
            continue
        picked.append(f"{_component_label(component['name'])} {_pct(probability)}")
        if len(picked) == 3:
            break
    return "、".join(picked)


def _component_label(name: str) -> str:
    labels = {
        "surface_elo_edge": "場地 Elo",
        "overall_elo_edge": "整體 Elo",
        "serve_return_edge": "發球/接發球數據",
        "recent_form_edge": "近期對 Top 100 表現",
        "opponent_rank_bucket_edge": "對相近排名對手表現",
        "tournament_level_edge": "同級賽事表現",
        "round_performance_edge": "相同圈數表現",
        "big_match_edge": "大賽抗壓表現",
        "fatigue_edge": "體能因素",
        "pressure_edge": "壓力位表現",
        "head_to_head_edge": "H2H 對戰",
    }
    return labels.get(name, name)
