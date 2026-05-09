from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timezone
from statistics import mean, median
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def in_time_window(match_date: str, as_of_date: date, time_window: str) -> bool:
    match_day = parse_date(match_date)
    if match_day >= as_of_date:
        return False
    if time_window == "CAREER":
        return True
    if time_window == "LAST_52_WEEKS":
        return (as_of_date - match_day).days <= 364
    if time_window == "LAST_26_WEEKS":
        return (as_of_date - match_day).days <= 182
    raise ValueError(f"Unsupported time window: {time_window}")


def avg(values: Iterable[float | int | None]) -> float | None:
    cleaned = [float(v) for v in values if v is not None]
    return mean(cleaned) if cleaned else None


def med(values: Iterable[float | int | None]) -> float | None:
    cleaned = [float(v) for v in values if v is not None]
    return median(cleaned) if cleaned else None


def rate(wins: int, matches: int) -> float | None:
    return wins / matches if matches else None


def shrink_rate(raw_rate: float, sample_size: int, prior_rate: float, min_sample: int = 20) -> float:
    weight = min(sample_size / min_sample, 1)
    return raw_rate * weight + prior_rate * (1 - weight)


def provenance(
    source_provider: str,
    source_endpoint: str,
    source_timestamp: str,
    raw_response_id: int | None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source_provider": source_provider,
        "source_endpoint": source_endpoint,
        "source_timestamp": source_timestamp,
        "calculated_at": utc_now(),
        "raw_response_id": raw_response_id,
        "warnings": warnings or [],
    }


def datapoint(value: Any, prov: dict[str, Any] | None, warnings: list[str] | None = None) -> dict[str, Any]:
    payload = {"value": value, "provenance": prov}
    if warnings:
        payload["warnings"] = warnings
    return payload
