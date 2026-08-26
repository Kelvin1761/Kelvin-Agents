"""Rank coverage was capped seven times over, and the merge threw away the fix.

2026-08-27. `current_rank` is one of only four inputs in the feature set that is
not a re-slice of past results, and it was present on 42.8% of players. The
cause was not that ITF players are unranked -- the ATP feed holds 2,161 of them
down to rank 2,162 and WTA 1,572 down to 1,517 -- but that every layer asked for
500 and the merge then abandoned what arrived.

    baseline                      ITF fixtures both ranked  21.0%
    + request and parser caps                               23.6%
    + merge carries attributes                              49.2%
"""
from __future__ import annotations

import logging
import sqlite3

from tennis_wc.providers import official_ranking_provider as orp


# --------------------------------------------------------------------------- #
# The parsers
# --------------------------------------------------------------------------- #
def _atp_payload(n: int) -> dict:
    return {
        "total": n,
        "rows": [{"rank": i, "name": f"Player {i}", "points": 1000 - i,
                  "playerId": i, "country": {"id": "AUS"}}
                 for i in range(1, n + 1)],
    }


def test_the_atp_parser_no_longer_stops_at_five_hundred():
    """Lifting the REQUEST cap alone changed nothing: the payload arrived with
    all 2,161 rows and the parser still returned 500."""
    rows = orp._parse_atp_uts_rankings(_atp_payload(2161))
    assert len(rows) == 2161
    assert max(r["rank"] for r in rows) == 2161


def test_the_parser_keeps_a_runaway_guard_and_says_when_it_bites(caplog):
    with caplog.at_level(logging.WARNING):
        rows = orp._parse_atp_uts_rankings(_atp_payload(orp.MAX_RANKING_ROWS + 50))
    assert len(rows) == orp.MAX_RANKING_ROWS
    assert "guard" in caplog.text, "silent truncation is the defect, not the cap"


def test_the_guard_sits_far_above_a_real_ladder():
    """ATP holds 2,161 ranked players and WTA 1,572, so a real feed must never
    reach the guard -- otherwise it is just the 500 cap again with a bigger
    number."""
    assert orp.MAX_RANKING_ROWS > 2 * 2161


def test_the_request_asks_for_the_whole_ladder():
    assert orp.OfficialRankingProvider.ATP_ROW_COUNT >= 2161
    # WTA pages at 100; five pages was 500 and the feed ends at page 15.
    assert (orp.OfficialRankingProvider.WTA_MAX_PAGES
            * orp.OfficialRankingProvider.WTA_PAGE_SIZE) >= 1572


# --------------------------------------------------------------------------- #
# The merge
# --------------------------------------------------------------------------- #
def _real_db(tmp_path, monkeypatch) -> sqlite3.Connection:
    """The real schema. The merge walks 15 tables, so a hand-rolled `players`
    table is not enough to exercise it."""
    from conftest import configure_test_db

    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    from tennis_wc.identity.player_identity import ensure_identity_schema
    ensure_identity_schema(conn)
    return conn


def _player(conn, pid, name, rank=None, elo=None, surface=None):
    conn.execute(
        "INSERT INTO players (id, name, tour, current_rank, overall_elo, "
        "surface_elo_json, source_provider, created_at, updated_at) "
        "VALUES (?,?,'ATP',?,?,?,'test','now','now')",
        (pid, name, rank, elo, surface),
    )
    conn.commit()


def _merge(conn, canonical_id, duplicate_ids):
    """Drive the real `apply_merges` with the plan shape it consumes."""
    from tennis_wc.identity.player_identity import apply_merges

    class Plan:
        pass
    plan = Plan()
    plan.canonical_id = canonical_id
    plan.canonical_name = conn.execute(
        "SELECT name FROM players WHERE id=?", (canonical_id,)).fetchone()["name"]
    plan.duplicate_ids = list(duplicate_ids)
    return apply_merges(conn, [plan])


def _rank(conn, pid):
    return conn.execute(
        "SELECT current_rank FROM players WHERE id=?", (pid,)).fetchone()[0]


def test_the_merge_carries_the_rank_onto_the_surviving_row(tmp_path, monkeypatch):
    """447 groups merged and coverage moved 44.3% -> 44.3%, because the rank sat
    on the row that had just been superseded."""
    conn = _real_db(tmp_path, monkeypatch)
    _player(conn, 5928, "Aaron Funk")                 # canonical, no rank
    _player(conn, 19836, "Aaron Funk", rank=1342)     # duplicate, holds it
    _merge(conn, 5928, [19836])
    assert _rank(conn, 5928) == 1342
    conn.close()


def test_a_value_already_on_the_canonical_row_is_never_overwritten(tmp_path, monkeypatch):
    conn = _real_db(tmp_path, monkeypatch)
    _player(conn, 1, "Iga Swiatek", rank=2)
    _player(conn, 2, "Iga Swiatek", rank=880)
    _merge(conn, 1, [2])
    assert _rank(conn, 1) == 2
    conn.close()


def test_elo_and_surface_elo_are_carried_too(tmp_path, monkeypatch):
    """Elo is another of the four independent inputs, at 64.6% coverage, and it
    sits in the same column set -- it would be lost the same way."""
    conn = _real_db(tmp_path, monkeypatch)
    _player(conn, 1, "Alex Bolt")
    _player(conn, 2, "Alex Bolt", elo=1873.5, surface='{"hard": 1880}')
    _merge(conn, 1, [2])
    row = conn.execute(
        "SELECT overall_elo, surface_elo_json FROM players WHERE id=1").fetchone()
    assert row["overall_elo"] == 1873.5
    assert row["surface_elo_json"] == '{"hard": 1880}'
    conn.close()


def test_the_sharper_rank_wins_when_two_duplicates_disagree(tmp_path, monkeypatch):
    conn = _real_db(tmp_path, monkeypatch)
    _player(conn, 1, "Jordan Smith")
    _player(conn, 2, "Jordan Smith", rank=1500)
    _player(conn, 3, "Jordan Smith", rank=940)
    _merge(conn, 1, [2, 3])
    assert _rank(conn, 1) == 940
    conn.close()


def test_merging_nothing_leaves_the_row_alone(tmp_path, monkeypatch):
    conn = _real_db(tmp_path, monkeypatch)
    _player(conn, 1, "Nobody Here", rank=77)
    _merge(conn, 1, [])
    assert _rank(conn, 1) == 77
    conn.close()


# --------------------------------------------------------------------------- #
# The look-ahead path the coverage fix would otherwise have widened
# --------------------------------------------------------------------------- #
def test_a_historical_rebuild_does_not_receive_todays_rank(tmp_path, monkeypatch):
    """`players.current_rank` has no as-of date, so reading it for a match
    already played is look-ahead. 19.0% of the 5,748 player-sides on priced
    fixtures were taking that path -- and lifting the feed's 500-cap made it
    fire MORE often, which is the opposite of what a coverage fix should do."""
    from conftest import configure_test_db

    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.feature_builder import _rank_as_of

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO players (id, name, tour, current_rank, source_provider, "
        "created_at, updated_at) VALUES (1,'Ranked Today','ATP',412,'t','now','now')"
    )
    conn.commit()
    player = conn.execute("SELECT * FROM players WHERE id=1").fetchone()

    # No rankings_history row exists for either date.
    assert _rank_as_of(conn, 1, "2026-05-10", player) is None, \
        "a match from May must not be handed today's rank"
    conn.close()


def test_a_live_card_still_gets_a_rank_when_the_refresh_is_late(tmp_path, monkeypatch):
    """The fallback exists for the morning the ranking ingest has not landed
    yet. Closing it entirely would cost live coverage for no gain."""
    from datetime import date

    from conftest import configure_test_db

    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.feature_builder import _rank_as_of

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO players (id, name, tour, current_rank, source_provider, "
        "created_at, updated_at) VALUES (1,'Playing Today','ATP',412,'t','now','now')"
    )
    conn.commit()
    player = conn.execute("SELECT * FROM players WHERE id=1").fetchone()

    assert _rank_as_of(conn, 1, date.today().isoformat(), player) == 412
    conn.close()


def test_a_genuine_as_of_row_always_wins_over_the_fallback(tmp_path, monkeypatch):
    from datetime import date

    from conftest import configure_test_db

    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.features.feature_builder import _rank_as_of

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO players (id, name, tour, current_rank, source_provider, "
        "created_at, updated_at) VALUES (1,'Both Available','ATP',412,'t','now','now')"
    )
    conn.execute(
        "INSERT INTO rankings_history (player_id, ranking_date, tour, rank, "
        "source_provider, raw_response_id, created_at) "
        "VALUES (1,'2026-05-01','ATP',980,'t',0,'now')"
    )
    conn.commit()
    player = conn.execute("SELECT * FROM players WHERE id=1").fetchone()

    assert _rank_as_of(conn, 1, "2026-05-10", player) == 980
    assert _rank_as_of(conn, 1, date.today().isoformat(), player) == 980
    conn.close()
