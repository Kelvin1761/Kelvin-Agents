"""Point-in-time Elo: what we knew about a player *before* a given date.

``players.overall_elo`` holds one number per player, overwritten on every
rebuild with the rating computed over the whole record.  Reading it while
building a feature for a past match is look-ahead: the rating already contains
that match.  The Elo builder walks the record chronologically and therefore
already holds the pre-match rating at each step, so recording it costs nothing
beyond the write.
"""
from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS player_elo_history (
    player_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    surface TEXT NOT NULL DEFAULT '',
    rating REAL NOT NULL,
    matches_played INTEGER,
    PRIMARY KEY (player_id, as_of_date, surface)
);
CREATE INDEX IF NOT EXISTS idx_elo_history_lookup
    ON player_elo_history(player_id, surface, as_of_date);
"""


# SHADOW (2026-10-09, EXP-20261009-01). The table above stamps each PRE-match
# rating with the match date, and `rating_as_of` reads the latest row strictly
# before a date -- so every read is the rating from before the player's previous
# match: today's R1 result is invisible to tomorrow's R2 price. It also keeps the
# first row it ever saw for a key (INSERT OR IGNORE), so it is a mixture of
# builds and cannot be reproduced: only 47.9% of the overall-Elo components
# stored with live predictions since 2026-08-28 re-derive from today's corpus.
#
# v2 stores the POST-match rating (the last of the day wins) and is cleared on
# every build, so "latest row strictly before D" is the rating at the start of D.
# It feeds the shadow backbone only; production still reads the table above.
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS player_elo_history_v2 (
    player_id INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    surface TEXT NOT NULL DEFAULT '',
    rating REAL NOT NULL,
    matches_played INTEGER,
    PRIMARY KEY (player_id, as_of_date, surface)
);
CREATE INDEX IF NOT EXISTS idx_elo_history_v2_lookup
    ON player_elo_history_v2(player_id, surface, as_of_date);
"""


def ensure_schema(conn) -> None:
    conn.executescript(SCHEMA)
    conn.executescript(SCHEMA_V2)


def replace_post_match(conn, rows) -> int:
    """Rewrite v2 from scratch with post-match ratings.

    ``rows`` is chronological (player_id, date, surface, rating, matches_played)
    taken AFTER each update, so a later row for the same key -- a second match
    the same day -- correctly replaces the earlier one.
    """
    prepared = [
        (int(player_id), str(as_of_date), str(surface or ""),
         float(rating), matches_played)
        for player_id, as_of_date, surface, rating, matches_played in rows
        if player_id is not None and as_of_date and rating is not None
    ]
    conn.execute("DELETE FROM player_elo_history_v2")
    conn.executemany(
        "INSERT OR REPLACE INTO player_elo_history_v2 "
        "(player_id, as_of_date, surface, rating, matches_played) "
        "VALUES (?, ?, ?, ?, ?)",
        prepared,
    )
    return len(prepared)


def start_of_day_rating(conn, player_id: int, as_of_date: str,
                        surface: str | None = None) -> float | None:
    """Rating at the start of ``as_of_date`` from v2: every result before that
    day counted, none from that day. Surface falls back to overall, as
    `rating_as_of` does."""
    row = conn.execute(
        """
        SELECT rating FROM player_elo_history_v2
        WHERE player_id = ? AND surface = ? AND as_of_date < ?
        ORDER BY as_of_date DESC LIMIT 1
        """,
        (int(player_id), str(surface or ""), str(as_of_date)),
    ).fetchone()
    if row is None and surface:
        return start_of_day_rating(conn, player_id, as_of_date, surface=None)
    return float(row[0]) if row else None


def record(conn, rows) -> int:
    """Upsert pre-match ratings.

    ``rows`` is an iterable of (player_id, as_of_date, surface, rating,
    matches_played); ``surface`` is '' for the overall rating.  Several matches
    can share a date, and the FIRST rating of the day is the one we knew before
    play started, so a same-key collision keeps the existing row.
    """
    prepared = [
        (int(player_id), str(as_of_date), str(surface or ""),
         float(rating), matches_played)
        for player_id, as_of_date, surface, rating, matches_played in rows
        if player_id is not None and as_of_date and rating is not None
    ]
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO player_elo_history "
        "(player_id, as_of_date, surface, rating, matches_played) "
        "VALUES (?, ?, ?, ?, ?)",
        prepared,
    )
    return conn.total_changes - before


def rating_as_of(conn, player_id: int, as_of_date: str,
                 surface: str | None = None) -> float | None:
    """The most recent rating recorded STRICTLY BEFORE ``as_of_date``.

    Strictly before, not on-or-before: a rating stamped with the match date is
    the one that match itself produced.
    """
    row = conn.execute(
        """
        SELECT rating FROM player_elo_history
        WHERE player_id = ? AND surface = ? AND as_of_date < ?
        ORDER BY as_of_date DESC LIMIT 1
        """,
        (int(player_id), str(surface or ""), str(as_of_date)),
    ).fetchone()
    if row is None and surface:
        return rating_as_of(conn, player_id, as_of_date, surface=None)
    return float(row[0]) if row else None


def coverage(conn) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM player_elo_history").fetchone()[0]
    players = conn.execute(
        "SELECT COUNT(DISTINCT player_id) FROM player_elo_history"
    ).fetchone()[0]
    return {"rows": total, "players": players}
