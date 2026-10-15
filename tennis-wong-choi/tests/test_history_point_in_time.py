"""Point-in-time guard on serve history (EXP-20261015-01 finding F). Temp DB.

Season files stamp every round with the tournament START date, so
`match_date < as_of` let a replay read the player's own later rounds. The
invariance property: appending rows AFTER a match started must not change any
profile priced for that match.
"""
from __future__ import annotations

import pytest

MATCH_DATE = "2026-09-04"           # a Thursday quarter-final
START = "2026-09-04T09:00:00Z"
EVENT_START = "2026-08-31"          # how the season file dates every round


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = get_connection()
    for i in range(12):   # older history, ingested long ago
        _history(conn, f"old{i}", 1, 2, f"2026-07-{10 + i:02d}", aces=6, hold=0.80,
                 created="2026-07-25T00:00:00Z")
        _history(conn, f"old{i}", 2, 1, f"2026-07-{10 + i:02d}", aces=4, hold=0.75,
                 created="2026-07-25T00:00:00Z")
    # Rounds 1-2 of this event, ingested before the QF started: admissible.
    for r, opp in (("r1", 3), ("r2", 6)):
        _history(conn, r, 1, opp, EVENT_START, aces=9, hold=0.85, created="2026-09-03T12:00:00Z")
    conn.commit()
    return conn


def _history(conn, mid, pid, opp, day, *, aces, hold, created):
    conn.execute(
        """INSERT INTO player_match_history (provider_match_id, player_id, opponent_id,
               tour, match_date, surface, tournament_external_id, tournament_level,
               round, format, won, ace_count, service_games_played, hold_rate,
               break_rate, first_serve_points_won_pct, second_serve_points_won_pct,
               return_points_won_pct, source_provider, raw_response_id, created_at)
           VALUES (?, ?, ?, 'ATP', ?, 'Hard', 'E', 'A', 'R', 'BO3', 1, ?, 12, ?, 0.2,
                   0.7, 0.5, 0.38, 'jeff_sackmann', 0, ?)""",
        (f"{mid}-{pid}", pid, opp, day, aces, hold, created),
    )


def _profiles(conn):
    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.ace_model import player_ace_profile
    from tennis_wc.props.games_model import combined_hold

    return (
        player_ace_profile(conn, 1, MATCH_DATE, "hard", start_time=START),
        combined_hold(conn, 1, 2, MATCH_DATE, start_time=START),
        serve_return_profile(conn, 1, MATCH_DATE, surface="hard", start_time=START),
    )


def test_future_append_does_not_change_profiles(conn):
    before = _profiles(conn)
    # The season file re-pull lands the QF itself, the SF and the final -- all
    # dated the event start, all ingested after the QF began.
    for r, opp in (("qf", 4), ("sf", 7), ("f", 8)):
        _history(conn, r, 1, opp, EVENT_START, aces=25, hold=0.99,
                 created="2026-09-08T00:00:00Z")
    conn.commit()
    assert _profiles(conn) == before


def test_rows_ingested_before_start_still_count(conn):
    ace, hold_sum, serve = _profiles(conn)
    assert ace.n == 14, "12 old + the two earlier rounds of this event"
    assert serve.matches == 14


def test_unguarded_read_would_have_leaked(conn):
    """The same append WITHOUT a start time on a pre-guard cutoff: the guard's
    date-only fallback (match day 00:00Z) still excludes it."""
    from tennis_wc.props.ace_model import player_ace_profile

    _history(conn, "qf", 1, 4, EVENT_START, aces=25, hold=0.99,
             created="2026-09-08T00:00:00Z")
    conn.commit()
    assert player_ace_profile(conn, 1, MATCH_DATE, "hard").n == 14


def test_old_rows_need_no_ingestion_proof(conn):
    """Outside the 13-day window the date alone is enough: a backfill created
    today must not erase last season."""
    from tennis_wc.props.ace_model import player_ace_profile

    _history(conn, "backfill", 1, 5, "2026-06-01", aces=7, hold=0.8,
             created="2026-10-14T00:00:00Z")
    conn.commit()
    assert player_ace_profile(conn, 1, MATCH_DATE, "hard", last_n=50,
                              start_time=START).n == 15
