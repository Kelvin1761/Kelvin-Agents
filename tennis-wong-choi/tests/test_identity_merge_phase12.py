"""Phase 1.2: the merge rules that were blocking real people, and decaying.

Three separate defects, each of which made the merge machinery quietly weaker
than it looked:

  * the ATP-vs-WTA guard refused 25 groups, every one a WTA player whose
    duplicate row carried an ATP-labelled history block
  * a hyphen was identity, so `Chan-Yeong Oh` and `Chan Yeong Oh` were two people
  * merges decayed daily -- ingestion resolved names without following the
    merge pointer, so fixtures kept landing on ids merged away days earlier
"""
from __future__ import annotations

import sqlite3

from conftest import configure_test_db


def _db(tmp_path, monkeypatch) -> sqlite3.Connection:
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    from tennis_wc.identity.player_identity import ensure_identity_schema
    ensure_identity_schema(conn)
    return conn


def _player(conn, pid, name, tour="UNKNOWN", rank=None):
    conn.execute(
        "INSERT INTO players (id, name, tour, current_rank, source_provider, "
        "created_at, updated_at) VALUES (?,?,?,?,'t','now','now')",
        (pid, name, tour, rank),
    )
    conn.commit()


def _ranking(conn, pid, tour, n=6):
    for i in range(n):
        conn.execute(
            "INSERT INTO rankings_history (player_id, ranking_date, tour, rank, "
            "source_provider, raw_response_id, created_at) VALUES (?,?,?,?,'t',0,'now')",
            (pid, f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}", tour, 50 + i),
        )
    conn.commit()


def _history(conn, pid, n, tour, start=1):
    for i in range(n):
        conn.execute(
            """INSERT INTO player_match_history
               (provider_match_id, player_id, opponent_id, tour, match_date,
                tournament_external_id, tournament_level, round, format, won,
                source_provider, raw_response_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,'t',0,'now')""",
            (f"M{pid}-{i}", pid, 900 + start + i, tour, f"2025-01-{i % 28 + 1:02d}",
             "T1", "ATP250", "R1", "BO3", 1),
        )
    conn.commit()


# --------------------------------------------------------------------------- #
# The tour guard
# --------------------------------------------------------------------------- #
def test_a_ranked_player_is_not_blocked_by_an_unranked_rows_history_label(tmp_path, monkeypatch):
    """All 25 remaining ATP-vs-WTA refusals were women. In every one the real
    row held a full WTA ranking history (Swiatek: 115 entries) and the duplicate
    held NO ranking history, only a match block ~90% labelled ATP. `derived_tour`
    falls back to that block, so the duplicate "derived" as ATP and blocked her
    own merge."""
    from tennis_wc.identity.player_identity import plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Iga Swiatek", tour="WTA")
    _player(conn, 2, "Iga Swiatek", tour="ATP")
    _ranking(conn, 1, "WTA", n=20)          # authoritative
    _history(conn, 1, 30, "WTA", start=1)
    _history(conn, 2, 12, "ATP", start=500)  # contaminated, no ranking

    plan = [p for p in plan_merges(conn) if p.canonical_name.startswith("Iga")][0]
    assert plan.duplicate_ids == [2], plan.reason
    conn.close()


def test_two_players_ranked_on_different_tours_are_still_refused(tmp_path, monkeypatch):
    """The guard has to keep working: ranking evidence on both sides that
    disagrees is exactly the case where two people share a name."""
    from tennis_wc.identity.player_identity import plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Sam Lee")
    _player(conn, 2, "Sam Lee")
    _ranking(conn, 1, "WTA", n=10)
    _ranking(conn, 2, "ATP", n=10)

    plan = [p for p in plan_merges(conn) if p.canonical_name == "Sam Lee"][0]
    assert plan.duplicate_ids == []
    assert "ranked on different tours" in plan.reason
    conn.close()


def test_the_merge_corrects_the_surviving_rows_tour_from_the_ranking(tmp_path, monkeypatch):
    """Canonical is chosen by history volume, which picked an ATP-labelled row
    for Destanee Aiava while she is ranked WTA. `tour` gates real behaviour
    downstream -- ace props are ATP-only."""
    from tennis_wc.identity.player_identity import apply_merges, plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Destanee Aiava", tour="ATP")
    _player(conn, 2, "Destanee Aiava", tour="WTA", rank=559)
    _history(conn, 1, 20, "ATP", start=1)   # more history -> canonical
    _ranking(conn, 2, "WTA", n=10)

    apply_merges(conn, plan_merges(conn))
    row = conn.execute("SELECT tour, current_rank FROM players WHERE id=1").fetchone()
    assert row["tour"] == "WTA"
    assert row["current_rank"] == 559
    conn.close()


# --------------------------------------------------------------------------- #
# Hyphens and middle names
# --------------------------------------------------------------------------- #
def test_a_hyphen_is_orthography_not_identity():
    from tennis_wc.ingestion.name_matching import normalise_player_name

    assert normalise_player_name("Chan-Yeong Oh") == normalise_player_name("Chan Yeong Oh")
    assert normalise_player_name("Nuria Parrizas-Diaz") == normalise_player_name("Nuria Parrizas Diaz")


def test_a_middle_name_variant_merges(tmp_path, monkeypatch):
    from tennis_wc.identity.player_identity import plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Ammar Faleh Alhogbani", rank=1727)
    _player(conn, 2, "Ammar Alhogbani")

    plan = [p for p in plan_merges(conn) if "middle-name" in p.reason]
    assert len(plan) == 1 and set(plan[0].duplicate_ids) | {plan[0].canonical_id} == {1, 2}
    conn.close()


def test_a_doubles_pair_is_never_merged_into_a_singles_player(tmp_path, monkeypatch):
    """The first version of the middle-name rule proposed exactly this.
    `normalise_player_name` moves a trailing initial to the front, so the pair
    `Filin N. / Fuchs A.` becomes `a filin n fuchs` -- same first and last token
    as `a fuchs`, and nested."""
    from tennis_wc.identity.player_identity import plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Fuchs A.")
    _player(conn, 2, "Filin N. / Fuchs A.")

    assert not [p for p in plan_merges(conn) if p.duplicate_ids], \
        "a doubles pair is not a player"
    conn.close()


def test_an_initialised_given_name_is_too_thin_to_merge_on(tmp_path, monkeypatch):
    """`a fuchs` is Alexander or Anna or Andrea."""
    from tennis_wc.identity.player_identity import plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Fuchs A.")
    _player(conn, 2, "Fuchs A. B.")

    assert not [p for p in plan_merges(conn) if p.duplicate_ids]
    conn.close()


def test_two_different_middle_names_are_two_people(tmp_path, monkeypatch):
    from tennis_wc.identity.player_identity import plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Maria Elena Costa")
    _player(conn, 2, "Maria Sofia Costa")

    assert not [p for p in plan_merges(conn) if p.duplicate_ids], \
        "nested token sets only -- these two are disjoint in the middle"
    conn.close()


# --------------------------------------------------------------------------- #
# Decay
# --------------------------------------------------------------------------- #
def test_a_chain_resolves_to_the_terminal_row(tmp_path, monkeypatch):
    """Merges chain across runs: 20089 -> 18856 -> 437. One hop lands on a row
    nothing should point at any more."""
    from tennis_wc.identity.player_identity import terminal_canonical_id

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 437, "Ammar Faleh Alhogbani")
    _player(conn, 18856, "Ammar Alhogbani")
    _player(conn, 20089, "Ammar Alhogbani")
    conn.execute("UPDATE players SET canonical_player_id=437 WHERE id=18856")
    conn.execute("UPDATE players SET canonical_player_id=18856 WHERE id=20089")
    conn.commit()

    assert terminal_canonical_id(conn, 20089) == 437
    assert terminal_canonical_id(conn, 437) == 437
    conn.close()


def test_a_cycle_cannot_hang_the_resolver(tmp_path, monkeypatch):
    """An identity resolver must not be able to hang the daily card."""
    from tennis_wc.identity.player_identity import terminal_canonical_id

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "A B")
    _player(conn, 2, "A B")
    conn.execute("UPDATE players SET canonical_player_id=2 WHERE id=1")
    conn.execute("UPDATE players SET canonical_player_id=1 WHERE id=2")
    conn.commit()

    assert terminal_canonical_id(conn, 1) in (1, 2)
    conn.close()


def test_applying_a_merge_leaves_no_chain(tmp_path, monkeypatch):
    from tennis_wc.identity.player_identity import apply_merges, plan_merges

    conn = _db(tmp_path, monkeypatch)
    _player(conn, 1, "Ammar Faleh Alhogbani")
    _player(conn, 2, "Ammar Alhogbani")
    _player(conn, 3, "Ammar Alhogbani")
    conn.execute("UPDATE players SET canonical_player_id=2 WHERE id=3")
    conn.commit()

    apply_merges(conn, plan_merges(conn))
    chained = conn.execute(
        """SELECT COUNT(*) FROM players a JOIN players b ON b.id = a.canonical_player_id
           WHERE a.canonical_player_id IS NOT NULL AND b.canonical_player_id IS NOT NULL"""
    ).fetchone()[0]
    assert chained == 0
    conn.close()


def test_a_database_without_the_column_still_resolves(tmp_path, monkeypatch):
    """`canonical_player_id` comes from `ensure_identity_schema`, not `init_db`.
    A resolver that raises on a fresh database takes the pipeline with it."""
    from tennis_wc.identity.player_identity import terminal_canonical_id

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO players VALUES (7, 'Someone')")
    conn.commit()
    assert terminal_canonical_id(conn, 7) == 7
    conn.close()
