from __future__ import annotations

from datetime import date
from typing import Any


MIN_PRICED_RATIO = 0.35
MIN_FIXTURES_FOR_RATIO_CHECK = 10
CRITICAL_SOURCES = {
    "odds",
    "event_markets",
    "event_markets_check",
    "upcoming_matches",
}

# Which day the analysis is FOR, relative to the day it runs. An empty board
# means opposite things in the two cases, and until 2026-08-11 they produced
# the same log line.
#
# Sportsbet does not open tomorrow's book at 18:00. Its own listing responses,
# same call and same target date at different clocks:
#
#   2026-08-07 18:07 Sydney, asking for 08-08  ->  list[0], 2 bytes, HTTP 200
#   2026-08-08 09:08 Sydney, asking for 08-08  ->  list[55]
#   2026-08-08 12:08 Sydney, asking for 08-08  ->  list[45]
#
# So a next-day pass finding nothing is the ordinary state of the world, and a
# same-day pass finding nothing never is. Because both raised the same
# TEMPORARY DATA FAILURE, the pipeline ran dark from 2026-08-09 to 2026-08-11
# -- three days with zero odds captured -- and every evening looked normal.
HORIZON_SAME_DAY = "same_day"
HORIZON_NEXT_DAY = "next_day"
HORIZON_PAST = "past"

# What the caller should do about it.
SEVERITY_OK = "ok"
SEVERITY_EXPECTED_EMPTY = "expected_empty"   # next-day warm pass, book not open
SEVERITY_RETRY = "retry"                     # partial book; come back later
SEVERITY_ERROR = "error"                     # the board should be here and is not


def _intish(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def horizon_for(match_date: Any, today: Any = None) -> str:
    """Is this analysis for today, a future day, or a past one?

    One definition, shared by the scheduler and the CLI's publish gate, because
    the two disagreeing about which day they are looking at is how the
    distinction went missing in the first place.
    """
    def _as_date(value):
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    target = _as_date(match_date)
    reference = _as_date(today) or date.today()
    if target is None:
        return HORIZON_SAME_DAY
    if target > reference:
        return HORIZON_NEXT_DAY
    if target < reference:
        return HORIZON_PAST
    return HORIZON_SAME_DAY


def _coverage_reasons(payload: dict[str, Any]) -> list[str]:
    """Reasons that are about the BOOK being open, not about us being broken."""
    coverage = payload.get("odds_coverage") or {}
    fixtures = _intish(coverage.get("fixtures"))
    priced = _intish(coverage.get("priced_matches"))
    confirmed_empty = bool(payload.get("confirmed_empty_slate"))
    reasons: list[str] = []
    if fixtures == 0 and priced == 0 and not confirmed_empty:
        reasons.append("zero fixtures and odds without a confirmed empty slate")
    elif fixtures > 0 and priced == 0:
        reasons.append(f"zero Sportsbet-priced matches across {fixtures} fixtures")
    if (
        fixtures >= MIN_FIXTURES_FOR_RATIO_CHECK
        and priced / fixtures < MIN_PRICED_RATIO
    ):
        reasons.append(
            f"only {priced}/{fixtures} fixtures priced "
            f"({priced / fixtures:.0%} < {MIN_PRICED_RATIO:.0%}) -- book likely not open yet"
        )
    return reasons


def _pipeline_reasons(payload: dict[str, Any]) -> list[str]:
    """Reasons that are about US, and are never expected on any horizon."""
    matches = _intish(payload.get("matches_analysed"))
    valid = _intish(payload.get("valid_feature_snapshots"))
    source_errors = payload.get("source_errors") or []
    coverage = payload.get("odds_coverage") or {}
    priced = _intish(coverage.get("priced_matches"))
    reasons: list[str] = []
    if matches == 0 and source_errors:
        reasons.append("zero matches after source failures")
    elif matches == 0 and priced > 0:
        reasons.append(f"{priced} priced matches produced zero model snapshots")
    elif matches > 0 and valid == 0:
        reasons.append("all feature snapshots are invalid")
    for error in source_errors:
        source = str(error.get("source") or "unknown")
        if source in CRITICAL_SOURCES:
            reasons.append(f"{source}: {error.get('error') or 'unknown error'}")
    return reasons


def analysis_readiness(
    payload: dict[str, Any], *, horizon: str = HORIZON_SAME_DAY
) -> dict[str, Any]:
    """Reasons the analysis is not publishable, and what to do about them.

    ``horizon`` decides how an empty board is read. On a next-day warm pass it
    is the expected state of the world and the run has succeeded; on a same-day
    pass it means the board we price from is missing, which is an error and has
    to be loud.
    """
    coverage = _coverage_reasons(payload)
    pipeline = _pipeline_reasons(payload)
    reasons = list(dict.fromkeys(coverage + pipeline))

    if pipeline:
        severity = SEVERITY_ERROR
    elif not coverage:
        severity = SEVERITY_OK
    elif horizon == HORIZON_NEXT_DAY:
        # Nothing is wrong; the book has not opened. Say so instead of raising
        # the same alarm a dead pipeline raises.
        severity = SEVERITY_EXPECTED_EMPTY
    else:
        odds = payload.get("odds_coverage") or {}
        fixtures = _intish(odds.get("fixtures"))
        priced = _intish(odds.get("priced_matches"))
        # Nothing at all on the day itself is a failure. A partial book is
        # worth another pass.
        severity = SEVERITY_ERROR if priced == 0 else SEVERITY_RETRY
        if fixtures == 0 and priced == 0:
            severity = SEVERITY_ERROR

    return {
        "horizon": horizon,
        "severity": severity,
        "reasons": [] if severity in (SEVERITY_OK, SEVERITY_EXPECTED_EMPTY) else reasons,
        "observed": reasons,
        "publishable": severity in (SEVERITY_OK,),
    }


def analysis_retry_reasons(
    payload: dict[str, Any], *, horizon: str = HORIZON_SAME_DAY
) -> list[str]:
    """Backwards-compatible view: the reasons a caller should act on."""
    return analysis_readiness(payload, horizon=horizon)["reasons"]


def analysis_is_ready(
    payload: dict[str, Any], *, horizon: str = HORIZON_SAME_DAY
) -> bool:
    return analysis_readiness(payload, horizon=horizon)["publishable"]
