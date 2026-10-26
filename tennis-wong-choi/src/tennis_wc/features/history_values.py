"""Validate measurements without clamping bad source values into good data."""
from __future__ import annotations

import math

RATE_FIELDS = ('hold_rate', 'break_rate', 'first_serve_points_won_pct',
               'second_serve_points_won_pct', 'return_points_won_pct')
COUNT_FIELDS = ('ace_count', 'double_fault_count', 'service_games_played',
                'break_points_saved', 'break_points_faced',
                'break_points_converted', 'break_points_chances')


def measurement(value, *, rate=False):
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
    for field in RATE_FIELDS:
        if field in cleaned:
            cleaned[field] = measurement(cleaned[field], rate=True)
    for field in COUNT_FIELDS:
        if field in cleaned:
            cleaned[field] = measurement(cleaned[field])
    for numerator, denominator in (('break_points_saved','break_points_faced'),
                                   ('break_points_converted','break_points_chances')):
        if cleaned.get(numerator) is not None and cleaned.get(denominator) is not None:
            if cleaned[numerator] > cleaned[denominator]:
                cleaned[numerator] = cleaned[denominator] = None
    return cleaned
