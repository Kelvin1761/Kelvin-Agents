from __future__ import annotations

import math

from tennis_wc.database.db import get_connection


def train_ml_baseline() -> dict:
    rows = _training_rows()
    if len(rows) < 50:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "samples": len(rows),
            "minimum_samples": 50,
            "note": "ML baseline 要有足夠 settled tracker rows 先可信；繼續累積 CLV / 賽果資料。",
        }
    split = max(1, int(len(rows) * 0.8))
    train = rows[:split]
    test = rows[split:]
    weights = _fit_logistic(train)
    predictions = [_predict(weights, row) for row in test]
    return {
        "status": "TRAINED_BASELINE",
        "samples": len(rows),
        "train_samples": len(train),
        "test_samples": len(test),
        "log_loss": _round(_log_loss(predictions, [row["actual"] for row in test])),
        "brier_score": _round(_brier(predictions, [row["actual"] for row in test])),
        "weights": {key: _round(value) for key, value in weights.items()},
        "note": "Baseline 只用 settled CLV tracker rows；未證明 out-of-sample CLV/ROI 前，唔好取代 deterministic model。",
    }


def _training_rows() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT recommendation_type, tier, model_probability, edge, odds_taken, confidence, result_status
            FROM clv_tracker
            WHERE result_status IN ('WON', 'LOST')
              AND model_probability IS NOT NULL
              AND edge IS NOT NULL
              AND odds_taken IS NOT NULL
              AND confidence IS NOT NULL
            ORDER BY match_date, id
            """
        ).fetchall()
    return [
        {
            "bias": 1.0,
            "model_probability": float(row["model_probability"]),
            "edge": float(row["edge"]),
            "odds_taken": min(float(row["odds_taken"]), 10.0) / 10.0,
            "confidence": float(row["confidence"]) / 100.0,
            "is_core": 1.0 if row["tier"] == "CORE_BANKER" else 0.0,
            "is_value": 1.0 if row["tier"] == "VALUE_BANKER" else 0.0,
            "actual": 1.0 if row["result_status"] == "WON" else 0.0,
        }
        for row in rows
    ]


def _fit_logistic(rows: list[dict], epochs: int = 600, learning_rate: float = 0.08) -> dict[str, float]:
    keys = ["bias", "model_probability", "edge", "odds_taken", "confidence", "is_core", "is_value"]
    weights = {key: 0.0 for key in keys}
    for _ in range(epochs):
        gradients = {key: 0.0 for key in keys}
        for row in rows:
            pred = _predict(weights, row)
            error = pred - row["actual"]
            for key in keys:
                gradients[key] += error * row[key]
        for key in keys:
            weights[key] -= learning_rate * gradients[key] / len(rows)
    return weights


def _predict(weights: dict[str, float], row: dict) -> float:
    z = sum(weights.get(key, 0.0) * float(row.get(key, 0.0)) for key in weights)
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def _log_loss(predictions: list[float], actuals: list[float]) -> float | None:
    if not predictions:
        return None
    total = 0.0
    for pred, actual in zip(predictions, actuals):
        p = max(0.001, min(0.999, pred))
        total += -(actual * math.log(p) + (1 - actual) * math.log(1 - p))
    return total / len(predictions)


def _brier(predictions: list[float], actuals: list[float]) -> float | None:
    if not predictions:
        return None
    return sum((pred - actual) ** 2 for pred, actual in zip(predictions, actuals)) / len(predictions)


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
