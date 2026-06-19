from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tennis_wc.config import get_settings


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _walk_datapoints(payload: Any, path: str = "") -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    if isinstance(payload, dict):
        if "value" in payload and "provenance" in payload:
            found.append((path, payload))
        for key, value in payload.items():
            found.extend(_walk_datapoints(value, f"{path}.{key}" if path else key))
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            found.extend(_walk_datapoints(value, f"{path}[{idx}]"))
    return found


def assert_no_llm_generated_stats(feature_snapshot: dict) -> None:
    """
    Raise error if any feature has source_provider == 'llm'
    or if provenance is missing for numeric features.
    """
    for path, point in _walk_datapoints(feature_snapshot):
        value = point.get("value")
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            prov = point.get("provenance")
            if not prov:
                raise ValueError(f"Numeric feature missing provenance at {path}")
            if prov.get("source_provider") == "llm":
                raise ValueError(f"LLM-generated stat detected at {path}")


def validate_data_freshness(feature_snapshot: dict) -> dict:
    """
    Returns:
    {
      "is_valid": bool,
      "score": int,
      "errors": list[str],
      "warnings": list[str]
    }
    """
    settings = get_settings()
    errors: list[str] = []
    warnings: list[str] = []
    score = 100
    warning_penalty = 0

    try:
        assert_no_llm_generated_stats(feature_snapshot)
    except ValueError as exc:
        errors.append(str(exc))
        score -= 50

    context = feature_snapshot.get("match_context", {})
    if not context.get("match_date"):
        errors.append("missing match date")
    surface = context.get("surface", {})
    if isinstance(surface, dict):
        surface = surface.get("value")
    if not surface:
        errors.append("missing tournament surface")
    level = context.get("level", {})
    if isinstance(level, dict):
        level = level.get("value")
    if not level:
        errors.append("missing tournament level")
    if level == "UNKNOWN":
        warnings.append("unknown tournament level")
        warning_penalty += 10
    round_name = context.get("round", {})
    if isinstance(round_name, dict):
        round_name = round_name.get("value")
    if not round_name or round_name == "UNKNOWN":
        warnings.append("unknown match round")
        warning_penalty += 8

    market = feature_snapshot.get("market", {})
    required_odds = ["player_a_odds", "player_b_odds"]
    for key in required_odds:
        if key not in market:
            errors.append("missing market odds")
            continue
        point = market[key]
        if not point.get("provenance"):
            errors.append("missing odds provenance")

    now = datetime.now(timezone.utc)
    for path, point in _walk_datapoints(feature_snapshot):
        prov = point.get("provenance") or {}
        provider = prov.get("source_provider")
        if provider == "llm":
            errors.append(f"LLM source provider at {path}")
        source_time = _parse_time(prov.get("source_timestamp"))
        if source_time is None:
            errors.append(f"missing source timestamp at {path}")
            continue
        age_hours = (now - source_time).total_seconds() / 3600
        if ".market." in f".{path}." and age_hours * 60 > settings.data_max_staleness_minutes_odds:
            errors.append(f"stale odds at {path}")
        if "ranking" in path and age_hours > settings.data_max_staleness_hours_rankings:
            warnings.append(f"stale ranking data at {path}")
            warning_penalty += 5
        for warning in prov.get("warnings", []):
            warnings.append(f"{path}: {warning}")
            if "missing_historical_rank" in warning:
                warning_penalty += 10
            elif "low_sample" in warning:
                warning_penalty += 5
            else:
                warning_penalty += 2

    if not feature_snapshot.get("entity_mapping_complete", True):
        errors.append("missing player identity mapping")

    warnings = sorted(set(warnings))
    score = max(0, min(100, score - 20 * len(errors) - min(35, warning_penalty)))
    return {"is_valid": not errors, "score": score, "errors": errors, "warnings": warnings}
