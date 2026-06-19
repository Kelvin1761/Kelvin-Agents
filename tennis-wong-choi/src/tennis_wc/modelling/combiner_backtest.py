from __future__ import annotations

import math
from collections import defaultdict

from tennis_wc.database.db import get_connection
from tennis_wc.features.feature_builder import assemble_match_feature_snapshot
from tennis_wc.modelling.probability_model import predict_match_probability


def _settled_matches(start_date: str | None, end_date: str | None) -> list[dict]:
    """Matches that have a recorded result, optionally bounded by date."""
    clauses = ["r.winner_player_id IS NOT NULL"]
    params: list[str] = []
    if start_date:
        clauses.append("m.match_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("m.match_date <= ?")
        params.append(end_date)
    where = " AND ".join(clauses)
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT m.id AS match_id, m.match_date, m.player_a_id, m.player_b_id,
                       r.winner_player_id
                FROM matches m
                JOIN match_results r ON r.match_id = m.id
                WHERE {where}
                ORDER BY m.match_date, m.id
                """,
                params,
            ).fetchall()
        ]


def run_combiner_backtest(start_date: str | None = None, end_date: str | None = None) -> dict:
    """
    Replay the deterministic weighted combiner (predict_match_probability) over
    every settled match and score how well its probabilities matched outcomes.

    This is the regression harness for changes to probability_model.py. It is
    read-only (no feature_snapshots are written).
    """
    matches = _settled_matches(start_date, end_date)
    records: list[dict] = []
    skipped = 0
    for match in matches:
        try:
            snapshot, _ = assemble_match_feature_snapshot(int(match["match_id"]))
        except Exception:
            skipped += 1
            continue
        model = predict_match_probability(snapshot)
        prob_a = float(model["player_a_probability"])
        a_won = int(match["winner_player_id"]) == int(match["player_a_id"])
        # probability the model assigned to the actual winner
        winner_probability = prob_a if a_won else (1.0 - prob_a)
        favorite_probability = max(prob_a, 1.0 - prob_a)
        favorite_is_a = prob_a >= 0.5
        favorite_won = favorite_is_a == a_won
        records.append(
            {
                "winner_probability": winner_probability,
                "favorite_probability": favorite_probability,
                "favorite_won": favorite_won,
                "active_weight": float(model.get("active_weight", 0.0)),
            }
        )

    if not records:
        return {"matches": 0, "skipped": skipped, "note": "no settled matches in range"}

    return {
        "start_date": start_date,
        "end_date": end_date,
        "matches": len(records),
        "skipped": skipped,
        "brier_score": _round(_avg((1 - r["winner_probability"]) ** 2 for r in records)),
        "log_loss": _round(_avg(-math.log(_clamp(r["winner_probability"])) for r in records)),
        "favorite_accuracy": _round(_avg(1.0 if r["favorite_won"] else 0.0 for r in records)),
        "favorite_brier_score": _round(
            _avg(((1.0 if r["favorite_won"] else 0.0) - r["favorite_probability"]) ** 2 for r in records)
        ),
        "average_winner_probability": _round(_avg(r["winner_probability"] for r in records)),
        "average_favorite_probability": _round(_avg(r["favorite_probability"] for r in records)),
        "calibration_bins": _calibration_bins(records),
        "note": "Scores predict_match_probability vs actual winners; no market odds / ROI here.",
    }


def _calibration_bins(records: list[dict]) -> list[dict]:
    buckets: dict[str, list[float]] = defaultdict(list)
    outcomes: dict[str, list[float]] = defaultdict(list)
    for row in records:
        probability = row["favorite_probability"]
        lower = int(probability * 10) / 10
        upper = min(lower + 0.1, 1.0)
        key = f"{lower:.1f}-{upper:.1f}"
        buckets[key].append(probability)
        outcomes[key].append(1.0 if row["favorite_won"] else 0.0)
    return [
        {
            "bin": key,
            "matches": len(values),
            "avg_predicted_favorite_probability": _round(_avg(values)),
            "actual_favorite_win_rate": _round(_avg(outcomes[key])),
            "calibration_error": _round(abs((_avg(outcomes[key]) or 0) - (_avg(values) or 0))),
        }
        for key, values in sorted(buckets.items())
    ]


def _avg(values) -> float | None:
    cleaned = [float(v) for v in values if v is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _clamp(value: float, low: float = 0.001, high: float = 0.999) -> float:
    return max(low, min(high, value))


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
