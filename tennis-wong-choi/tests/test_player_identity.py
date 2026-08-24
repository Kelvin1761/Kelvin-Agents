"""Canonical player identity: merge what is one person, refuse what is not."""
from __future__ import annotations


def _setup(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    return get_connection()


def _player(conn, pid, name, tour="WTA"):
    conn.execute(
        "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (pid, name, tour, "test", "now", "now"),
    )


def _history(conn, pid, n, opponent_id=999, start=1):
    for i in range(n):
        conn.execute(
            """INSERT INTO player_match_history
               (provider_match_id, player_id, opponent_id, tour, match_date,
                tournament_external_id, tournament_level, round, format, won,
                source_provider, raw_response_id, created_at, surface, ace_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"H{pid}-{start + i}", pid, opponent_id, "WTA",
             f"2025-01-{start + i:02d}", "T1", "ITF", "R1", "BO3", 1,
             "test", 0, "now", "hard", 5.0),
        )


def test_history_split_across_duplicate_ids_is_reunified(tmp_path, monkeypatch):
    """The measured failure: 70/8/0 across three ids for one player.

    The ace model needs ten prior matches, so the fragments can each look "too
    thin to model" while the player actually has plenty.
    """
    from tennis_wc.identity import player_identity

    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, "Viktoria Hruncakova")
    _player(conn, 2, "Viktoria Hruncakova")
    _player(conn, 3, "viktoria hruncakova", tour="UNKNOWN")
    _history(conn, 1, 7, start=1)
    _history(conn, 2, 4, start=10)
    conn.commit()

    plans = player_identity.plan_merges(conn)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.canonical_id == 1          # most history wins
    assert sorted(plan.duplicate_ids) == [2, 3]
    assert plan.history_rows_moved == 4

    summary = player_identity.apply_merges(conn, plans)
    assert summary["groups"] == 1 and summary["ids_merged"] == 2

    total = conn.execute(
        "SELECT COUNT(*) FROM player_match_history WHERE player_id = 1"
    ).fetchone()[0]
    assert total == 11, "the fragments must end up on one id"
    assert conn.execute(
        "SELECT COUNT(*) FROM player_match_history WHERE player_id IN (2, 3)"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT canonical_player_id FROM players WHERE id = 2"
    ).fetchone()[0] == 1


def test_two_players_who_faced_each_other_are_never_merged(tmp_path, monkeypatch):
    """A player cannot be their own opponent, so this proves they differ."""
    from tennis_wc.identity import player_identity

    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, "Alex Smith", tour="ATP")
    _player(conn, 2, "Alex Smith", tour="ATP")
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at, updated_at)
           VALUES (1,'M1','ATP','2026-01-01',1,1,2,'R1','test','now','now')"""
    )
    conn.commit()

    plans = player_identity.plan_merges(conn)
    assert plans and plans[0].duplicate_ids == []
    assert "faced each other" in plans[0].reason
    summary = player_identity.apply_merges(conn, plans)
    assert summary["refused"] == 1 and summary["ids_merged"] == 0


def test_tour_guard_reads_the_playing_record_not_the_players_label(tmp_path, monkeypatch):
    """players.tour is mislabelled often enough to be useless as a guard.

    All 97 groups the label-based guard first refused were WTA players whose
    duplicate row said ATP -- Potapova's second id claims ATP against 118 WTA
    ranking entries. Refuse only when the RECORDS disagree.
    """
    from tennis_wc.identity import player_identity

    conn = _setup(tmp_path, monkeypatch)
    # Same person, second row mislabelled ATP, but both records are WTA.
    _player(conn, 1, "Anastasia Potapova", tour="WTA")
    _player(conn, 2, "Anastasia Potapova", tour="ATP")
    _history(conn, 1, 8, start=1)
    _history(conn, 2, 6, start=10)
    conn.commit()
    plans = player_identity.plan_merges(conn)
    assert plans[0].duplicate_ids == [2], "a bad label must not block a real merge"

    # Genuinely different tours in the record: refuse.
    _player(conn, 3, "Sam Lee", tour="WTA")
    _player(conn, 4, "Sam Lee", tour="WTA")
    _history(conn, 3, 6, start=1)
    for i in range(6):
        conn.execute(
            """INSERT INTO player_match_history
               (provider_match_id, player_id, opponent_id, tour, match_date,
                tournament_external_id, tournament_level, round, format, won,
                source_provider, raw_response_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"X{i}", 4, 998, "ATP", f"2025-03-{i + 1:02d}", "T2", "ATP250",
             "R1", "BO3", 1, "test", 0, "now"),
        )
    conn.commit()
    plans = player_identity.plan_merges(conn)
    lee = [p for p in plans if p.canonical_name == "Sam Lee"][0]
    assert lee.duplicate_ids == []
    assert "different tours" in lee.reason


def test_placeholders_are_not_players(tmp_path, monkeypatch):
    from tennis_wc.identity import player_identity

    assert player_identity.is_placeholder("TBD")
    assert player_identity.is_placeholder("Unknown Player")
    assert player_identity.is_placeholder("Qualifier")
    assert not player_identity.is_placeholder("Nuno Borges")

    conn = _setup(tmp_path, monkeypatch)
    _player(conn, 1, "TBD", tour="ATP")
    _player(conn, 2, "TBD", tour="ATP")
    conn.commit()
    assert player_identity.plan_merges(conn) == []


def test_resolve_reads_the_alias_table_and_invents_nothing(tmp_path, monkeypatch):
    from tennis_wc.identity import player_identity

    conn = _setup(tmp_path, monkeypatch)
    player_identity.ensure_identity_schema(conn)
    _player(conn, 1, "Denislava Glushkova")
    _player(conn, 2, "Denislava Glushkova")
    _history(conn, 1, 3)
    conn.commit()
    player_identity.apply_merges(conn, player_identity.plan_merges(conn))

    # Accent and surname-initial spellings both land on the canonical id.
    assert player_identity.resolve_player_id(conn, "Denislava Glushkova") == 1
    assert player_identity.resolve_player_id(conn, "Glushkova D.") == 1
    # Unknown names return None rather than minting a rival row.
    assert player_identity.resolve_player_id(conn, "Someone Entirely New") is None
    assert player_identity.resolve_player_id(conn, "TBD") is None


# --------------------------------------------------------------------------- #
# The merge machinery had no caller (2026-08-25)
# --------------------------------------------------------------------------- #
def test_run_daily_merges_identities_before_building_features():
    """`plan_merges`/`apply_merges` were written, tested, safeguarded -- and
    called by nothing. 936 groups had accumulated, and 76 players had a fixture
    or a priced prop on a brand-new id with zero history while a sibling id held
    80 to 261 matches: Alexander Ritschard was priced as having no record at all
    against his own 261-match history.

    Order matters as much as presence. Features are what read a player's
    history, so a merge that runs after them fixes nothing until the next day.
    """
    import inspect
    from tennis_wc import cli

    source = inspect.getsource(cli.run_daily)
    assert "identity_merge" in source, "the merge stage has no caller again"
    assert source.index("identity_merge") < source.index("feature_snapshots"), (
        "identities must be folded together BEFORE features read their history"
    )


def test_the_identity_merge_stage_only_applies_confident_plans(tmp_path, monkeypatch):
    """The planner refuses ids that faced each other and ids on different tours.
    The stage must execute that judgement, never override it -- on the live data
    those refusals were protecting Swiatek, Sabalenka, Osaka and Azarenka from
    being merged with a same-named player on the other tour."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.cli import _merge_player_identities

    init_db()
    with get_connection() as conn:
        ensure_identity_schema(conn)
        for pid, name, tour in ((1, "Sam Twin", "ATP"), (2, "Sam Twin", "ATP"),
                                (3, "Other Guy", "ATP")):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)", (pid, name, tour, "test", "now", "now"))
        # The two "Sam Twin" ids faced each other, so they are two people.
        conn.execute(
            "INSERT INTO tournaments (id,name,tour,external_id,source_provider,created_at,updated_at) "
            "VALUES (1,'Open','ATP','T1','test','now','now')")
        conn.execute(
            """INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,
               player_a_id,player_b_id,round,source_provider,created_at,updated_at)
               VALUES (1,'M1','ATP','2026-08-01',1,1,2,'R1','test','now','now')""")
        conn.commit()

    summary = _merge_player_identities()
    assert summary["groups"] == 0, "a refused group must not be merged"
    assert summary["refused"] >= 1

    with get_connection() as conn:
        still_two = conn.execute(
            "SELECT COUNT(*) FROM players WHERE name='Sam Twin' "
            "AND canonical_player_id IS NULL").fetchone()[0]
    assert still_two == 2


def test_the_merge_stage_is_idempotent(tmp_path, monkeypatch):
    """It runs every day, so a second run on a clean database must be a no-op
    rather than churning rows."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.identity.player_identity import ensure_identity_schema
    from tennis_wc.cli import _merge_player_identities

    init_db()
    with get_connection() as conn:
        ensure_identity_schema(conn)
        for pid, name in ((1, "Dup Name"), (2, "Dup Name")):
            conn.execute(
                "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?)", (pid, name, "ATP", "test", "now", "now"))
        conn.commit()

    first = _merge_player_identities()
    assert first["groups"] == 1
    second = _merge_player_identities()
    assert second["groups"] == 0, "a settled database must not be re-merged"
