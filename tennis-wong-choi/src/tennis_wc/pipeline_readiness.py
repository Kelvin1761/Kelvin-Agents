from __future__ import annotations

from typing import Any


MIN_PRICED_RATIO = 0.35
MIN_FIXTURES_FOR_RATIO_CHECK = 10
CRITICAL_SOURCES = {
    "odds",
    "event_markets",
    "event_markets_check",
    "upcoming_matches",
}


def _intish(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def analysis_retry_reasons(payload: dict[str, Any]) -> list[str]:
    """Return failures that make a live betting report unsafe to publish.

    Empty provider responses are treated as temporary data failures unless an
    upstream calendar has explicitly confirmed that the date has no eligible
    slate. This prevents a silent ``[]`` response from becoming a normal
    "no-bet" report.
    """
    matches = _intish(payload.get("matches_analysed"))
    valid = _intish(payload.get("valid_feature_snapshots"))
    source_errors = payload.get("source_errors") or []
    coverage = payload.get("odds_coverage") or {}
    fixtures = _intish(coverage.get("fixtures"))
    priced = _intish(coverage.get("priced_matches"))
    confirmed_empty = bool(payload.get("confirmed_empty_slate"))
    reasons: list[str] = []

    if fixtures == 0 and priced == 0 and not confirmed_empty:
        reasons.append("zero fixtures and odds without a confirmed empty slate")
    elif fixtures > 0 and priced == 0:
        reasons.append(f"zero Sportsbet-priced matches across {fixtures} fixtures")

    if matches == 0 and source_errors:
        reasons.append("zero matches after source failures")
    elif matches == 0 and priced > 0:
        reasons.append(f"{priced} priced matches produced zero model snapshots")
    elif matches > 0 and valid == 0:
        reasons.append("all feature snapshots are invalid")

    if fixtures >= MIN_FIXTURES_FOR_RATIO_CHECK and priced / fixtures < MIN_PRICED_RATIO:
        reasons.append(
            f"only {priced}/{fixtures} fixtures priced "
            f"({priced / fixtures:.0%} < {MIN_PRICED_RATIO:.0%}) -- book likely not open yet"
        )

    for error in source_errors:
        source = str(error.get("source") or "unknown")
        if source in CRITICAL_SOURCES:
            reasons.append(f"{source}: {error.get('error') or 'unknown error'}")

    return list(dict.fromkeys(reasons))


def analysis_is_ready(payload: dict[str, Any]) -> bool:
    return not analysis_retry_reasons(payload)
