from __future__ import annotations

from tennis_wc.database.db import get_connection


MIN_SETTLEMENT_COVERAGE = 0.80


def market_validation_summary(min_samples: int = 20, min_coverage: float = MIN_SETTLEMENT_COVERAGE) -> dict:
    rows = _market_rows()
    by_market = []
    for row in rows:
        settled = int(row["settled"] or 0)
        tracked = int(row["tracked"] or 0)
        profit = float(row["profit"] or 0)
        roi = profit / settled if settled else None
        coverage_rate = settled / tracked if tracked else None
        by_market.append(
            {
                "market_key": row["market_key"],
                "tier": row["tier"],
                "tracked": tracked,
                "settled": settled,
                "coverage_rate": _round(coverage_rate),
                "hit_rate": _round(float(row["wins"] or 0) / settled) if settled else None,
                "avg_clv": _round(row["avg_clv"]),
                "flat_1u_roi": _round(roi),
                "stable_value_candidate": _stable_value_candidate(
                    row["tier"], settled, tracked, row["wins"], row["avg_clv"], roi, min_coverage
                ),
                "status": _market_status(settled, coverage_rate, row["avg_clv"], roi, min_samples, min_coverage),
            }
        )
    return {
        "min_samples": min_samples,
        "min_coverage": min_coverage,
        "by_market": by_market,
        "note": "Promotion requires enough settled samples, enough settlement coverage, and positive CLV/ROI.",
    }


def aces_prop_sanity_for_date(match_date: str, min_history: int = 10) -> dict:
    rows = _aces_prop_rows(match_date)
    validations = []
    for row in rows:
        validation = _validate_aces_row(row, min_history)
        validations.append(validation)
    validations.sort(key=lambda item: (item["status"], -(item.get("edge") or 0), item["market"]))
    return {
        "date": match_date,
        "props_checked": len(validations),
        "min_history": min_history,
        "validations": validations,
        "note": "Historical sanity check only; banker promotion still needs settled CLV/ROI support.",
    }


def _market_rows() -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT market_key, tier, COUNT(*) AS tracked,
                       SUM(CASE WHEN result_status IN ('WON', 'LOST') THEN 1 ELSE 0 END) AS settled,
                       SUM(CASE WHEN result_status = 'WON' THEN 1 ELSE 0 END) AS wins,
                       AVG(clv) AS avg_clv,
                       SUM(COALESCE(profit_loss_units, 0)) AS profit
                FROM clv_tracker
                WHERE recommendation_type = 'MARKET_LEG'
                  AND COALESCE(edge, 0) > 0
                GROUP BY market_key, tier
                ORDER BY settled DESC, tracked DESC, market_key
                """
            ).fetchall()
        ]


def _aces_prop_rows(match_date: str) -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT mp.*, pa.name AS player_a_name, pb.name AS player_b_name,
                       m.player_a_id, m.player_b_id
                FROM market_predictions mp
                JOIN matches m ON m.id = mp.match_id
                JOIN players pa ON pa.id = m.player_a_id
                JOIN players pb ON pb.id = m.player_b_id
                WHERE m.match_date = ?
                  AND mp.model_status = 'PROP_MODEL'
                  AND (lower(mp.market_key) LIKE '%ace%' OR lower(mp.market_name) LIKE '%ace%')
                """,
                (match_date,),
            ).fetchall()
        ]


def _validate_aces_row(row: dict, min_history: int) -> dict:
    line = float(row["line"]) if row.get("line") is not None else None
    if line is None:
        return _validation_row(row, None, None, 0, "NO_LINE")
    player_id = _ace_player_id(row)
    values = _historical_ace_values(int(row["match_id"]), player_id)
    if len(values) < min_history:
        return _validation_row(row, None, None, len(values), "INSUFFICIENT_HISTORY")
    is_over = "over" in str(row.get("selection_name") or "").lower()
    if is_over:
        hit_rate = sum(1 for value in values if value > line) / len(values)
    else:
        hit_rate = sum(1 for value in values if value < line) / len(values)
    model_probability = float(row["model_probability"]) if row.get("model_probability") is not None else None
    gap = abs(hit_rate - model_probability) if model_probability is not None else None
    status = "SANITY_OK" if gap is not None and gap <= 0.12 else "SANITY_REVIEW"
    return _validation_row(row, hit_rate, gap, len(values), status)


def _validation_row(row: dict, hit_rate: float | None, gap: float | None, samples: int, status: str) -> dict:
    return {
        "match": f"{row.get('player_a_name')} vs {row.get('player_b_name')}",
        "market": f"{row.get('market_name')}: {row.get('selection_name')}",
        "odds": row.get("odds"),
        "model_probability": _round(row.get("model_probability")),
        "historical_hit_rate": _round(hit_rate),
        "probability_gap": _round(gap),
        "samples": samples,
        "edge": _round(row.get("edge")),
        "status": status,
    }


def _ace_player_id(row: dict) -> int | None:
    market = _norm(f"{row.get('market_key') or ''} {row.get('market_name') or ''}")
    player_a = _norm(row.get("player_a_name"))
    player_b = _norm(row.get("player_b_name"))
    if player_a and player_a in market:
        return int(row["player_a_id"])
    if player_b and player_b in market:
        return int(row["player_b_id"])
    return None


def _historical_ace_values(match_id: int, player_id: int | None) -> list[float]:
    with get_connection() as conn:
        if player_id is None:
            match = conn.execute("SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)).fetchone()
            a_rows = conn.execute(
                "SELECT ace_count FROM player_match_history WHERE player_id = ? AND ace_count IS NOT NULL ORDER BY match_date DESC LIMIT 40",
                (match["player_a_id"],),
            ).fetchall()
            b_rows = conn.execute(
                "SELECT ace_count FROM player_match_history WHERE player_id = ? AND ace_count IS NOT NULL ORDER BY match_date DESC LIMIT 40",
                (match["player_b_id"],),
            ).fetchall()
            return [float(a["ace_count"]) + float(b["ace_count"]) for a, b in zip(a_rows, b_rows)]
        rows = conn.execute(
            "SELECT ace_count FROM player_match_history WHERE player_id = ? AND ace_count IS NOT NULL ORDER BY match_date DESC LIMIT 40",
            (player_id,),
        ).fetchall()
        return [float(row["ace_count"]) for row in rows]


def _market_status(
    settled: int,
    coverage_rate: float | None,
    avg_clv: float | None,
    roi: float | None,
    min_samples: int,
    min_coverage: float,
) -> str:
    if settled < min_samples:
        return "SAMPLE_BUILDING"
    if coverage_rate is not None and coverage_rate < min_coverage:
        return "LOW_SETTLEMENT_COVERAGE"
    if (avg_clv or 0) > 0 and (roi or 0) > 0:
        return "PROMOTE_CANDIDATE"
    return "KEEP_REVIEW"


def _stable_value_candidate(
    tier: str,
    settled: int,
    tracked: int,
    wins,
    avg_clv: float | None,
    roi: float | None,
    min_coverage: float,
) -> bool:
    if tier != "VALUE_BANKER" or settled < 30:
        return False
    if tracked and settled / tracked < min_coverage:
        return False
    hit_rate = float(wins or 0) / settled
    return hit_rate >= 0.58 and (avg_clv or 0) > 0 and (roi or 0) > 0


def _norm(value: str | None) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def _round(value) -> float | None:
    return round(float(value), 6) if value is not None else None
