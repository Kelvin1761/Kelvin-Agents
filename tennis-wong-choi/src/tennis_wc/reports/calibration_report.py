from __future__ import annotations

from tennis_wc.database.db import get_connection


BUCKETS = (
    (0.50, 0.55),
    (0.55, 0.60),
    (0.60, 0.65),
    (0.65, 0.70),
    (0.70, 0.75),
    (0.75, 0.80),
    (0.80, 1.01),
)


def banker_calibration_summary(min_samples: int = 10) -> dict:
    rows = _settled_tracker_rows()
    buckets = []
    for low, high in BUCKETS:
        items = [row for row in rows if row["model_probability"] is not None and low <= float(row["model_probability"]) < high]
        predicted = _avg(float(row["model_probability"]) for row in items)
        actual = _avg(1.0 if row["result_status"] == "WON" else 0.0 for row in items)
        error = abs(actual - predicted) if predicted is not None and actual is not None else None
        buckets.append(
            {
                "bucket": f"{low:.2f}-{min(high, 1.0):.2f}",
                "samples": len(items),
                "avg_predicted_probability": _round(predicted),
                "actual_hit_rate": _round(actual),
                "calibration_error": _round(error),
                "status": _bucket_status(len(items), error, min_samples),
            }
        )
    return {
        "settled_tracked_recommendations": len(rows),
        "min_samples_per_bucket": min_samples,
        "buckets": buckets,
        "overall_brier_score": _round(_avg(_brier(row) for row in rows)),
        "banker_safety_margin": _round(_banker_safety_margin(buckets, min_samples)),
        "warning": _warning(buckets),
    }


def banker_probability_safety_margin(probability: float, min_samples: int = 10) -> float:
    rows = _settled_tracker_rows()
    for low, high in BUCKETS:
        if low <= probability < high:
            items = [row for row in rows if row["model_probability"] is not None and low <= float(row["model_probability"]) < high]
            if len(items) < min_samples:
                return 0.0
            predicted = _avg(float(row["model_probability"]) for row in items)
            actual = _avg(1.0 if row["result_status"] == "WON" else 0.0 for row in items)
            if predicted is None or actual is None:
                return 0.0
            overconfidence = predicted - actual
            return min(0.10, max(0.0, overconfidence)) if overconfidence >= 0.08 else 0.0
    return 0.0


def _settled_tracker_rows() -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT tier, model_probability, result_status
                FROM clv_tracker
                WHERE result_status IN ('WON', 'LOST')
                  AND model_probability IS NOT NULL
                """
            ).fetchall()
        ]


def _bucket_status(samples: int, error: float | None, min_samples: int) -> str:
    if samples < min_samples:
        return "INSUFFICIENT_SAMPLE"
    if error is None:
        return "UNKNOWN"
    if error <= 0.05:
        return "CALIBRATED"
    if error <= 0.10:
        return "WATCH"
    return "OVERCONFIDENT_OR_UNDERCONFIDENT"


def _warning(buckets: list[dict]) -> str:
    mature = [bucket for bucket in buckets if bucket["status"] != "INSUFFICIENT_SAMPLE"]
    flagged = [bucket for bucket in buckets if bucket["status"] == "OVERCONFIDENT_OR_UNDERCONFIDENT"]
    if flagged:
        return "部分成熟 probability bucket 校準偏差較大；未加注前要收緊 banker 門檻。"
    if not mature:
        return "settled tracker 樣本暫時未夠；校準成熟前只應用 CLV + 小注觀察。"
    return "Calibration 樣本已可參考；改 banker 門檻前要先比較各 bucket 命中率。"


def _banker_safety_margin(buckets: list[dict], min_samples: int) -> float:
    margins = []
    for bucket in buckets:
        if int(bucket["samples"] or 0) < min_samples:
            continue
        predicted = bucket.get("avg_predicted_probability")
        actual = bucket.get("actual_hit_rate")
        if predicted is None or actual is None:
            continue
        overconfidence = float(predicted) - float(actual)
        if overconfidence >= 0.08:
            margins.append(min(0.10, overconfidence))
    return max(margins) if margins else 0.0


def _brier(row: dict) -> float:
    actual = 1.0 if row["result_status"] == "WON" else 0.0
    probability = float(row["model_probability"])
    return (actual - probability) ** 2


def _avg(values) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
