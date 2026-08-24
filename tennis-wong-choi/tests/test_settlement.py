from __future__ import annotations

import json


def _row(selection, line, a_games, b_games, retired=False):
    score = {
        "player_a_games": a_games,
        "player_b_games": b_games,
        "player_a_sets": 2,
        "player_b_sets": 0,
        "total_sets": 2,
    }
    if retired:
        score["retired"] = True
        score["total_sets"] = 1
    return {
        "market_key": "total_games",
        "market_name": "Total Games",
        "selection_name": selection,
        "market_line": line,
        "score_json": json.dumps(score),
        "winner_player_id": 1,
        "player_a_id": 1,
        "player_b_id": 2,
    }


def test_total_games_over_under_settles_from_scoreline():
    from tennis_wc.betting.ledger import _settle_market_leg

    # 12 + 7 = 19 total games.
    assert _settle_market_leg(_row("Over 22.5", 22.5, 12, 7)) is False
    assert _settle_market_leg(_row("Under 22.5", 22.5, 12, 7)) is True
    assert _settle_market_leg(_row("Over 18.5", 18.5, 12, 7)) is True


def test_total_games_voids_on_retirement():
    from tennis_wc.betting.ledger import _settle_market_leg

    assert _settle_market_leg(_row("Under 18.5", 18.5, 3, 2, retired=True)) is None


def test_total_games_needs_a_line():
    from tennis_wc.betting.ledger import _settle_market_leg

    assert _settle_market_leg(_row("Over", None, 12, 7)) is None


def test_per_set_total_games_settles_from_that_set_not_match_total():
    from tennis_wc.betting.ledger import _settle_market_leg

    # Match total = 6+4 + 6+3 = 19, but Set 1 total = 6+4 = 10.
    score = json.dumps(
        {
            "player_a_games": 12,
            "player_b_games": 7,
            "player_a_sets": 2,
            "player_b_sets": 0,
            "total_sets": 2,
            "sets": [
                {"player_a_games": 6, "player_b_games": 4},
                {"player_a_games": 6, "player_b_games": 3},
            ],
        }
    )
    base = {
        "market_key": "total_games",
        "market_name": "Set 1 Total Games Over/Under 9.5",
        "market_line": 9.5,
        "score_json": score,
        "winner_player_id": 1,
        "player_a_id": 1,
        "player_b_id": 2,
    }
    # Set 1 = 10 games -> Over 9.5 WINS (must NOT use the match total of 19 only).
    assert _settle_market_leg({**base, "selection_name": "Over 9.5"}) is True
    assert _settle_market_leg({**base, "selection_name": "Under 9.5"}) is False
    # Set 2 = 9 games -> Over 9.5 LOSES.
    s2 = {**base, "market_name": "Set 2 Total Games Over/Under 9.5"}
    assert _settle_market_leg({**s2, "selection_name": "Over 9.5"}) is False


# --------------------------------------------------------------------------- #
# A match's result is spread across sources; reading one row loses fields
# (2026-08-25: 30 props over 10 matches were unsettleable because of this)
# --------------------------------------------------------------------------- #
def _seed_multi_source_match(conn, *, match_id=13466):
    """The real 2026-08-22 shape: three sources, only one carries aces.

    ESPN and TennisExplorer both have the full scoreline and no ace count;
    TennisMyLife has the aces. All three tie on "has a scoreline", so the old
    `id DESC` tiebreak handed the row to whichever landed last -- and the ace
    count vanished.
    """
    conn.execute(
        "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
        "VALUES (1,'Open','WTA','T1','test','now','now')"
    )
    for pid, name in ((1, "Player A"), (2, "Player B")):
        conn.execute(
            "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)", (pid, name, "WTA", "test", "now", "now"))
    conn.execute(
        """INSERT INTO matches
           (id,provider_match_id,tour,match_date,tournament_id,player_a_id,
            player_b_id,round,source_provider,created_at,updated_at)
           VALUES (?,'M1','WTA','2026-08-22',1,1,2,'R1','sportsbet','now','now')""",
        (match_id,))
    scoreline = {"player_a_games": 15, "player_b_games": 17,
                 "player_a_sets": 1, "player_b_sets": 2, "total_sets": 3}
    rows = (
        # id ascending, so tennisexplorer (no aces) wins an `id DESC` tiebreak.
        (1, "composite", {**scoreline, "player_a_aces": None, "player_b_aces": None}),
        (2, "tennismylife", {**scoreline, "player_a_aces": 1, "player_b_aces": 4}),
        (3, "tennisexplorer", dict(scoreline)),
    )
    for rid, provider, score in rows:
        conn.execute(
            """INSERT INTO match_results (id,match_id,winner_player_id,source_provider,
               raw_response_id,created_at,score_json) VALUES (?,?,?,?,NULL,'now',?)""",
            (rid, match_id, 2, provider, json.dumps(score)))
    conn.commit()


def test_aces_are_read_from_whichever_source_carries_them(tmp_path, monkeypatch):
    """The defect, exactly. Total aces is 1 + 4 = 5 and every source agrees on
    the scoreline, but the row that won the tiebreak had no ace field, so
    settlement fell through to history, found nothing, and four value props on
    a fully-known result stayed PENDING."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import actual_total_aces, actual_player_aces

    init_db()
    with get_connection() as conn:
        _seed_multi_source_match(conn)
        assert actual_total_aces(conn, 13466) == 5.0
        assert actual_player_aces(conn, 13466, 1) == 1.0
        assert actual_player_aces(conn, 13466, 2) == 4.0


def test_the_scoreline_still_comes_from_the_preferred_row(tmp_path, monkeypatch):
    """Merging must not undo the reason a single row was chosen: a winner-only
    resolver row must never shadow a real scoreline."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import actual_total_games

    init_db()
    with get_connection() as conn:
        _seed_multi_source_match(conn)
        # A later winner-only row, exactly the case the ordering exists for.
        conn.execute(
            """INSERT INTO match_results (id,match_id,winner_player_id,source_provider,
               raw_response_id,created_at,score_json) VALUES (99,13466,2,'resolver',NULL,'now',?)""",
            (json.dumps({"winner": "Player B"}),))
        conn.commit()
        assert actual_total_games(conn, 13466) == 32.0


def test_a_disagreeing_source_is_not_used_to_fill_gaps(tmp_path, monkeypatch):
    """Filling a gap from a source that contradicts the scoreline would blend
    two different claims about what happened rather than complete one."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import actual_total_aces

    init_db()
    with get_connection() as conn:
        # A contradicting source that ranks BELOW the real rows, so it is a
        # donor rather than the base. Donors are the half merging introduced,
        # and the half agreement has to gate.
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
            "VALUES (2,'Open2','WTA','T2','test','now','now')")
        for pid, name in ((11, "P A"), (12, "P B")):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)", (pid, name, "WTA", "test", "now", "now"))
        conn.execute(
            """INSERT INTO matches
               (id,provider_match_id,tour,match_date,tournament_id,player_a_id,
                player_b_id,round,source_provider,created_at,updated_at)
               VALUES (555,'M555','WTA','2026-08-22',2,11,12,'R1','sportsbet','now','now')""")
        conn.execute(
            """INSERT INTO match_results (id,match_id,winner_player_id,source_provider,
               raw_response_id,created_at,score_json) VALUES (60,555,12,'other',NULL,'now',?)""",
            (json.dumps({"player_a_games": 6, "player_b_games": 2,
                         "player_a_aces": 40, "player_b_aces": 40}),))
        conn.execute(
            """INSERT INTO match_results (id,match_id,winner_player_id,source_provider,
               raw_response_id,created_at,score_json) VALUES (61,555,12,'tennisexplorer',NULL,'now',?)""",
            (json.dumps({"player_a_games": 15, "player_b_games": 17,
                         "player_a_sets": 1, "player_b_sets": 2}),))
        conn.commit()
        # The base (id 61) has the scoreline and no aces. The only ace figures
        # on offer come from a row that disagrees about the games, so there is
        # no ace count for this match -- not 80.
        assert actual_total_aces(conn, 555) is None


def test_the_highest_ranked_row_is_still_the_base(tmp_path, monkeypatch):
    """A limit worth stating rather than discovering later: merging changed who
    may FILL a gap, not who is authoritative. The top-ranked row is still taken
    as given -- if two complete sources disagree, the newest one wins, exactly
    as before. No production match has hit that; all three sources agreed on
    every one of the ten measured."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import actual_total_games

    init_db()
    with get_connection() as conn:
        _seed_multi_source_match(conn, match_id=777)
        conn.execute(
            """INSERT INTO match_results (id,match_id,winner_player_id,source_provider,
               raw_response_id,created_at,score_json) VALUES (98,777,2,'other',NULL,'now',?)""",
            (json.dumps({"player_a_games": 6, "player_b_games": 2}),))
        conn.commit()
        assert actual_total_games(conn, 777) == 8.0
