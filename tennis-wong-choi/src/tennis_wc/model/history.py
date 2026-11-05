"""As-of reads of player_match_history: only what was knowable before a match.

Two guards apply to every read (see EXP notes in ``features/history_asof`` history):
the row must not be a self-match, and either the match is 13+ days old or the
row was ingested before the priced match's start. Superseded history rows are
excluded.
"""
from __future__ import annotations

import math

SAME_EVENT_WINDOW_DAYS = 13

RATE_FIELDS = ("hold_rate", "break_rate", "first_serve_points_won_pct",
               "second_serve_points_won_pct", "return_points_won_pct")
COUNT_FIELDS = ("ace_count", "double_fault_count", "service_games_played",
                "break_points_saved", "break_points_faced",
                "break_points_converted", "break_points_chances")


def as_of_clause(alias: str = "") -> str:
    """SQL fragment; bind with :func:`as_of_params`."""
    a = f"{alias}." if alias else ""
    return (f" AND ({a}opponent_id IS NULL OR {a}opponent_id!={a}player_id)"
            f" AND ({a}match_date < date(?, '-{SAME_EVENT_WINDOW_DAYS} days')"
            f" OR julianday({a}created_at) < julianday(?))")


def as_of_params(as_of_date: str, start_time: str | None) -> tuple[str, str]:
    return str(as_of_date)[:10], start_time or f"{str(as_of_date)[:10]}T00:00:00Z"


def active_clause(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}history_status='ACTIVE' AND {prefix}player_id <> {prefix}opponent_id"


def measurement(value, *, rate=False):
    """A usable stat value, or None for missing, negative, non-integer counts or rates > 1."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if rate and number > 1:
        return None
    if not rate and not number.is_integer():
        return None
    return number


def clean_history_row(row) -> dict:
    cleaned = dict(row)
    for name in RATE_FIELDS:
        if name in cleaned:
            cleaned[name] = measurement(cleaned[name], rate=True)
    for name in COUNT_FIELDS:
        if name in cleaned:
            cleaned[name] = measurement(cleaned[name])
    for numerator, denominator in (("break_points_saved", "break_points_faced"),
                                   ("break_points_converted", "break_points_chances")):
        if cleaned.get(numerator) is not None and cleaned.get(denominator) is not None:
            if cleaned[numerator] > cleaned[denominator]:
                cleaned[numerator] = cleaned[denominator] = None
    return cleaned
