"""One definition of "which side is this selection", pinned by its failures.

Every case here is a real row from the live database on 2026-08-11, found while
checking why the market's own favourite won only 53.8% of graded TOUR matches --
impossible for a bookmaker, and the tell that the stored orientation was wrong
rather than the tennis being strange.
"""
from __future__ import annotations

import pytest

from tennis_wc.ingestion.ingest_odds import (
    _oriented_positional_odds,
    _selection_side,
    selection_side_for,
)


def test_plain_names_resolve_to_their_own_side():
    assert selection_side_for("Learner Tien", "Frances Tiafoe", "Learner Tien") == "player_a"
    assert selection_side_for("Learner Tien", "Frances Tiafoe", "Frances Tiafoe") == "player_b"


def test_hyphen_dropped_by_the_feed_still_resolves():
    # match 5781: the fixture says Auger-Aliassime, the feed says Auger Aliassime.
    # Substring containment returned None and the price became invisible.
    assert selection_side_for(
        "Frances Tiafoe", "Felix Auger-Aliassime", "Felix Auger Aliassime"
    ) == "player_b"


def test_doubles_pair_offered_by_surnames_still_resolves():
    # match 9129: fixture "Nuno Borges/Francisco Cabral", feed "Borges / Cabral".
    assert selection_side_for(
        "Titouan Droguet/Kyrian Jacquet",
        "Nuno Borges/Francisco Cabral",
        "Borges / Cabral",
    ) == "player_b"
    assert selection_side_for(
        "Titouan Droguet/Kyrian Jacquet",
        "Nuno Borges/Francisco Cabral",
        "Droguet / Jacquet",
    ) == "player_a"


def test_status_suffix_on_the_fixture_name_is_ignored():
    # match 10848: the fixture name carried "- Rain Delay".
    assert selection_side_for(
        "Jessica Pegula", "Alexandra Eala - Rain Delay", "Alexandra Eala"
    ) == "player_b"


def test_a_selection_belonging_to_neither_player_is_declined():
    # match 5625 held prices for Bellucci and Collignon, who were not in it.
    assert selection_side_for("Learner Tien", "Felix Auger-Aliassime",
                              "Mattia Bellucci") is None


def test_an_ambiguous_name_is_declined_rather_than_guessed():
    # A guess mirror-flips the price, which is worse than storing nothing.
    assert selection_side_for("Alex Hernandez/Nicolas Mejia",
                              "Nicolas Jarry/Tomas Barrios",
                              "Nicolas") is None


def test_over_under_keeps_its_own_side():
    assert selection_side_for("A Player", "B Player", "Over") == "over"
    assert selection_side_for("A Player", "B Player", "under") == "under"


def test_row_wrapper_and_shared_function_cannot_drift():
    # The bug was two writers answering this question differently. The wrapper
    # must be the same answer, not a second implementation.
    row = {"player_a_name": "Nuno Borges/Francisco Cabral",
           "player_b_name": "Orlando Luz/Rafael Matos"}
    for name in ("Borges / Cabral", "Luz / Matos", "Someone Else", "Over"):
        assert _selection_side(row, name) == selection_side_for(
            row["player_a_name"], row["player_b_name"], name)


class _FakeConn:
    def __init__(self, player_a_name, player_b_name):
        self._row = {"player_a_name": player_a_name, "player_b_name": player_b_name}

    def execute(self, *_args):
        row = self._row

        class _Result:
            def fetchone(self_inner):
                return row

        return _Result()


def test_positional_odds_are_flipped_to_the_fixture_order():
    # The provider lists Matos/Luz first; the fixture lists Borges/Cabral first.
    # 48.6% of composite-fixture rows stored the opponent's price this way.
    row = {"player_a_name": "Luz / Matos", "player_b_name": "Borges / Cabral",
           "player_a_odds": 1.50, "player_b_odds": 2.60,
           "player_a_open_odds": 1.45, "player_b_open_odds": 2.70}
    conn = _FakeConn("Nuno Borges/Francisco Cabral", "Orlando Luz/Rafael Matos")
    assert _oriented_positional_odds(conn, 1, row) == (2.60, 1.50, 2.70, 1.45)


def test_positional_odds_are_left_alone_when_already_aligned():
    row = {"player_a_name": "Borges / Cabral", "player_b_name": "Luz / Matos",
           "player_a_odds": 2.60, "player_b_odds": 1.50,
           "player_a_open_odds": None, "player_b_open_odds": None}
    conn = _FakeConn("Nuno Borges/Francisco Cabral", "Orlando Luz/Rafael Matos")
    assert _oriented_positional_odds(conn, 1, row) == (2.60, 1.50, None, None)


def test_unresolvable_order_is_left_alone_rather_than_guessed():
    row = {"player_a_name": "Someone Unrelated", "player_b_name": "Also Unrelated",
           "player_a_odds": 1.90, "player_b_odds": 1.95,
           "player_a_open_odds": None, "player_b_open_odds": None}
    conn = _FakeConn("Nuno Borges/Francisco Cabral", "Orlando Luz/Rafael Matos")
    assert _oriented_positional_odds(conn, 1, row) == (1.90, 1.95, None, None)


def _db_with_one_match(tmp_path):
    import sqlite3

    conn = sqlite3.connect(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, player_a_id INT, player_b_id INT);
        CREATE TABLE market_odds_snapshots (
            id INTEGER PRIMARY KEY, match_id INT, selection_name TEXT,
            selection_side TEXT);
        INSERT INTO players (id, name) VALUES
            (1, 'Toby Samuel'), (2, 'Zachary Svajda'), (3, 'Stefan Kozlov');
        INSERT INTO matches (id, player_a_id, player_b_id) VALUES (10, 1, 2);
        """
    )
    return conn


def test_resync_repairs_sides_left_stale_by_a_player_rewrite(tmp_path):
    # match 8959: the fixture became Samuel v Svajda, but 'Stefan Kozlov' was
    # still stored as player_a from when the row held a different pairing. The
    # matches upsert sets player_a_id = excluded.player_a_id, so this is not a
    # one-off -- it is what that upsert does to every side already stored.
    from tennis_wc.ingestion.ingest_odds import resync_selection_sides

    conn = _db_with_one_match(tmp_path)
    conn.executemany(
        "INSERT INTO market_odds_snapshots (match_id, selection_name, selection_side)"
        " VALUES (?, ?, ?)",
        [(10, "Stefan Kozlov", "player_a"),
         (10, "Zachary Svajda", "player_b"),
         (10, "Toby Samuel", None)],
    )
    changed = resync_selection_sides(conn, 10)
    sides = {row["selection_name"]: row["selection_side"] for row in
             conn.execute("SELECT selection_name, selection_side"
                          " FROM market_odds_snapshots")}
    assert changed == 2
    assert sides == {"Stefan Kozlov": None,      # in neither -- declined
                     "Zachary Svajda": "player_b",
                     "Toby Samuel": "player_a"}  # was silently unusable


def test_resync_leaves_over_under_sides_alone(tmp_path):
    # These carry no player, so re-deriving them from player names would erase
    # a side that was correct.
    from tennis_wc.ingestion.ingest_odds import resync_selection_sides

    conn = _db_with_one_match(tmp_path)
    conn.execute(
        "INSERT INTO market_odds_snapshots (match_id, selection_name, selection_side)"
        " VALUES (10, 'Over 21.5', 'over')")
    assert resync_selection_sides(conn, 10) == 0
    assert conn.execute(
        "SELECT selection_side FROM market_odds_snapshots").fetchone()[0] == "over"


def test_resync_is_idempotent(tmp_path):
    from tennis_wc.ingestion.ingest_odds import resync_selection_sides

    conn = _db_with_one_match(tmp_path)
    conn.execute(
        "INSERT INTO market_odds_snapshots (match_id, selection_name, selection_side)"
        " VALUES (10, 'Toby Samuel', 'player_b')")
    assert resync_selection_sides(conn, 10) == 1
    assert resync_selection_sides(conn, 10) == 0
