"""EXP-20261127-71: scoreboard rows ("Amarilla R.") fold into the full-name row only with proof.

Surname + initial alone is not identity (`_plan_middle_name_merges`: 31 of 101 such
candidates were siblings or namesakes), so every link needs a unique counterpart on
both sides AND a same-day appearance against the same opponent.
"""
from __future__ import annotations

import sqlite3

from conftest import configure_test_db


def _db(tmp_path, monkeypatch) -> sqlite3.Connection:
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.store.migrations import init_db

    init_db()
    conn = sqlite3.connect(db_path)
    from tennis_wc.sources.identity import ensure_identity_schema
    ensure_identity_schema(conn)
    return conn


def _player(conn, pid, name, tour="UNKNOWN"):
    conn.execute("INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
                 "VALUES (?,?,?,'t','now','now')", (pid, name, tour))


def _history(conn, pid, opp, day, n=1):
    for i in range(n):
        conn.execute(
            """INSERT INTO player_match_history
               (provider_match_id, player_id, opponent_id, tour, match_date, tournament_external_id,
                tournament_level, round, format, won, source_provider, raw_response_id, created_at)
               VALUES (?,?,?,'ATP',?,'T1','ITF','R1','BO3',1,'tennisexplorer',0,'now')""",
            (f"H{pid}-{opp}-{day}-{i}", pid, opp, day))


def _fixture(conn, mid, a, b, day):
    conn.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,"
                 "round,source_provider,created_at,updated_at) VALUES (?,?,'ATP',?,1,?,?,'R1','sportsbet','now','now')",
                 (mid, str(mid), day, a, b))


def _ranking(conn, pid, tour, n=6):
    for i in range(n):
        conn.execute("INSERT INTO rankings_history (player_id, ranking_date, tour, rank, source_provider, "
                     "raw_response_id, created_at) VALUES (?,?,?,?,'t',0,'now')",
                     (pid, f"2026-0{1 + i}-01", tour, 300 + i))


def _base(conn):
    """Ramiro Amarilla (two full-name rows) and his scoreboard row, who both met Gomez on 11-20."""
    _player(conn, 1, "Ramiro Amarilla")
    _player(conn, 2, "Ramiro Amarilla")
    _player(conn, 3, "Amarilla R.")
    _player(conn, 10, "Juan Gomez")
    _player(conn, 11, "Gomez J.")
    _history(conn, 3, 11, "2026-11-20", n=3)
    _fixture(conn, 100, 1, 10, "2026-11-21")   # odds feed dates one day later: within +/- 1


def _plans(conn):
    from tennis_wc.sources.identity import plan_abbreviated_merges
    return plan_abbreviated_merges(conn)


def test_links_with_a_same_day_same_opponent_appearance(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    plans = [p for p in _plans(conn) if {3} <= {p.canonical_id, *p.duplicate_ids}]
    assert len(plans) == 1
    plan = plans[0]
    assert {plan.canonical_id, *plan.duplicate_ids} == {1, 2, 3}
    assert plan.canonical_id in (1, 2), "the full-name row stays canonical"
    conn.close()


def test_no_link_without_a_co_appearance(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Ramiro Amarilla")
    _player(conn, 3, "Amarilla R.")
    _player(conn, 10, "Juan Gomez")
    _player(conn, 12, "Pablo Diaz")
    _history(conn, 3, 12, "2026-11-20")
    _fixture(conn, 100, 1, 10, "2026-11-20")   # different opponent
    assert not [p for p in _plans(conn) if 3 in {p.canonical_id, *p.duplicate_ids}]
    conn.close()


def test_no_link_when_the_days_are_too_far_apart(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    conn.execute("UPDATE matches SET match_date = '2026-11-25' WHERE id = 100")
    assert not _plans(conn)
    conn.close()


def test_two_full_name_people_for_one_initial_is_refused(tmp_path, monkeypatch):
    """`R. Amarilla` could be Ramiro or Rodrigo: siblings are exactly the unsafe case."""
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    _player(conn, 4, "Rodrigo Amarilla")
    assert not _plans(conn)
    conn.close()


def test_two_scoreboard_rows_for_one_person_is_refused(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    _player(conn, 5, "Amarilla R.")            # a second scoreboard row: which one is Ramiro?
    _history(conn, 5, 11, "2026-11-20")
    assert not _plans(conn)
    conn.close()


def test_players_who_faced_each_other_are_two_people(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    _history(conn, 3, 1, "2026-10-01")          # the scoreboard row once played the full-name row
    assert not _plans(conn)
    conn.close()


def test_ranked_on_different_tours_is_refused(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    _ranking(conn, 1, "ATP")
    _ranking(conn, 3, "WTA")
    assert not _plans(conn)
    conn.close()


def test_doubles_pairs_are_never_candidates(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Ramiro Amarilla")
    _player(conn, 3, "Amarilla R. / Gomez J.")
    _player(conn, 10, "Juan Gomez")
    _history(conn, 3, 10, "2026-11-20")
    _fixture(conn, 100, 1, 10, "2026-11-20")
    assert not _plans(conn)
    conn.close()


def test_daily_merge_runs_it_only_when_switched_on(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    conn.commit()
    conn.close()
    from tennis_wc import run

    monkeypatch.delenv("TENNIS_ABBREV_LINK", raising=False)
    assert run.merge_identities().get("abbreviated_groups", 0) == 0
    monkeypatch.setenv("TENNIS_ABBREV_LINK", "1")
    summary = run.merge_identities()
    assert summary["abbreviated_groups"] == 1
    assert run.merge_identities().get("abbreviated_groups", 0) == 0, "idempotent: nothing left to link"


def test_unknown_opponents_are_not_a_co_appearance():
    from tennis_wc.sources.identity import _names_compatible

    assert not _names_compatible("", "")
    assert not _names_compatible("", "juan gomez")
    assert _names_compatible("j gomez", "juan gomez")


def test_only_tennisexplorer_scoreboard_rows_are_candidates(tmp_path, monkeypatch):
    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    conn.execute("UPDATE player_match_history SET source_provider = 'jeff_sackmann' WHERE player_id = 3")
    assert not _plans(conn)
    conn.close()


def test_the_scoreboard_spelling_is_not_left_as_a_name_alias(tmp_path, monkeypatch):
    """A future, different "Amarilla R." must not resolve to Ramiro by name alone."""
    from tennis_wc.sources.identity import apply_abbreviated_merges, plan_abbreviated_merges

    conn = _db(tmp_path, monkeypatch)
    _base(conn)
    apply_abbreviated_merges(conn, plan_abbreviated_merges(conn))
    aliases = {row[0] for row in conn.execute("SELECT alias_norm FROM player_aliases")}
    assert "ramiro amarilla" in aliases and "r amarilla" not in aliases
    conn.close()
