"""Point-in-time guard for player_match_history reads (2026-10-15, finding F).

`match_date < as_of_date` is not point-in-time for season files: Sackmann and
TennisMyLife stamp EVERY round of a tournament with the tournament START
date. A replay of a Thursday quarter-final therefore read that player's own
quarter-final (and semi, and final) as "history" -- EXP-20261015-01 found
14.3% of 880 replayed markets had their own match inside the profile. Live
pricing was unaffected only because those rows did not exist yet.

Guard (same rule as scripts/evaluate_prop_shrinkage_anchor.py): a row dated
within SAME_EVENT_WINDOW_DAYS before the match is admissible only if it was
INGESTED (`created_at`) before the match started. Older rows are admitted on
date alone -- a two-week window covers a Grand Slam's start date to its final.

With no start time the cutoff is the match date's 00:00Z (11:00 Sydney), after
the 09:00 card has ingested everything it reads, so live output is unchanged.
"""
from __future__ import annotations

SAME_EVENT_WINDOW_DAYS = 13


def ingestion_cutoff(as_of_date: str, start_time: str | None) -> str:
    return start_time or f"{str(as_of_date)[:10]}T00:00:00Z"


def guard_clause(alias: str = "") -> str:
    """SQL fragment; bind `guard_params(...)` right after the clause's position."""
    a = f"{alias}." if alias else ""
    return (
        f" AND ({a}opponent_id IS NULL OR {a}opponent_id!={a}player_id)"
        f" AND ({a}match_date < date(?, '-{SAME_EVENT_WINDOW_DAYS} days')"
        f" OR julianday({a}created_at) < julianday(?))"
    )


def guard_params(as_of_date: str, start_time: str | None) -> tuple[str, str]:
    return str(as_of_date)[:10], ingestion_cutoff(as_of_date, start_time)
