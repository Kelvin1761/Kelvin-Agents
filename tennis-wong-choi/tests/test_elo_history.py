"""Point-in-time Elo: a feature must never read a rating that contains its own match."""
from __future__ import annotations


def _setup(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.history import elo_history

    init_db()
    conn = get_connection()
    elo_history.ensure_schema(conn)
    return conn


def test_rating_as_of_is_strictly_before_the_date(tmp_path, monkeypatch):
    """On-or-before would return the rating that match itself produced."""
    from tennis_wc.history import elo_history

    conn = _setup(tmp_path, monkeypatch)
    elo_history.record(conn, [
        (1, "2026-01-01", "", 1500.0, 0),
        (1, "2026-02-01", "", 1560.0, 10),
        (1, "2026-03-01", "", 1610.0, 20),
    ])
    conn.commit()

    assert elo_history.rating_as_of(conn, 1, "2026-02-15") == 1560.0
    # The 2026-03-01 rating was produced BY the 2026-03-01 match.
    assert elo_history.rating_as_of(conn, 1, "2026-03-01") == 1560.0
    assert elo_history.rating_as_of(conn, 1, "2026-03-02") == 1610.0
    # Nothing known before the first record.
    assert elo_history.rating_as_of(conn, 1, "2025-12-31") is None


def test_surface_rating_falls_back_to_overall(tmp_path, monkeypatch):
    from tennis_wc.history import elo_history

    conn = _setup(tmp_path, monkeypatch)
    elo_history.record(conn, [
        (1, "2026-01-01", "", 1500.0, 0),
        (1, "2026-01-01", "clay", 1450.0, 0),
    ])
    conn.commit()

    assert elo_history.rating_as_of(conn, 1, "2026-02-01", surface="clay") == 1450.0
    # No grass record at all -> the overall rating, not None.
    assert elo_history.rating_as_of(conn, 1, "2026-02-01", surface="grass") == 1500.0


def test_first_rating_of_a_day_wins(tmp_path, monkeypatch):
    """Two matches on one date: what we knew before play started is the first."""
    from tennis_wc.history import elo_history

    conn = _setup(tmp_path, monkeypatch)
    elo_history.record(conn, [(1, "2026-01-05", "", 1500.0, 0)])
    elo_history.record(conn, [(1, "2026-01-05", "", 1533.0, 1)])
    conn.commit()

    assert elo_history.rating_as_of(conn, 1, "2026-01-06") == 1500.0


def test_elo_builder_records_the_pre_match_rating(tmp_path, monkeypatch):
    """The chronological walk already holds the pre-match rating at each step."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion.ingest_sackmann import HISTORY_PROVIDERS
    from tennis_wc.modelling.elo_builder import build_sackmann_elo
    from tennis_wc.history import elo_history

    init_db()
    conn = get_connection()
    for pid, name in ((1, "A"), (2, "B")):
        conn.execute(
            "INSERT INTO players (id, name, tour, source_provider, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)", (pid, name, "ATP", "test", "now", "now"))
    provider = HISTORY_PROVIDERS[0]
    for i, (winner, loser, day) in enumerate(((1, 2, "2026-01-01"), (1, 2, "2026-02-01"))):
        for role, (a, b) in (("winner", (winner, loser)), ("loser", (loser, winner))):
            conn.execute(
                """INSERT INTO player_match_history
                   (provider_match_id, player_id, opponent_id, tour, match_date,
                    tournament_external_id, tournament_level, round, format, won,
                    source_provider, raw_response_id, created_at, surface)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"M{i}-{role}", a, b, "ATP", day, "T1", "ATP250", "R1", "BO3",
                 1 if role == "winner" else 0, provider, 0, "now", "hard"))
    conn.commit()

    summary = build_sackmann_elo()
    assert summary["elo_history_rows"] > 0

    conn = get_connection()
    # Before any match both players sit on the initial rating.
    first = elo_history.rating_as_of(conn, 1, "2026-01-02")
    assert first == 1500.0
    # After winning once, the rating recorded before the SECOND match is higher.
    second = elo_history.rating_as_of(conn, 1, "2026-02-02")
    assert second > first
    # The loser moved the other way.
    assert elo_history.rating_as_of(conn, 2, "2026-02-02") < 1500.0


def test_elo_opponent_updates_are_scoped_to_the_source_provider(tmp_path, monkeypatch):
    """Provider-local ids are not globally unique; one source must never
    overwrite another source's opponent Elo when their match ids collide."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion.ingest_sackmann import HISTORY_PROVIDERS
    from tennis_wc.modelling import elo_builder

    init_db()
    conn = get_connection()
    for pid in range(1, 5):
        conn.execute(
            "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (pid, f"P{pid}", "ATP", "test", "now", "now"),
        )

    provider_a, provider_b = HISTORY_PROVIDERS[:2]

    def add_match(provider, prefix, winner, loser, day):
        for role, player, opponent, won in (
            ("winner", winner, loser, 1), ("loser", loser, winner, 0),
        ):
            conn.execute(
                """INSERT INTO player_match_history
                   (provider_match_id,player_id,opponent_id,tour,match_date,
                    tournament_external_id,tournament_level,round,format,won,
                    source_provider,raw_response_id,created_at,surface)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"{prefix}-{role}", player, opponent, "ATP", day, "T", "ATP250",
                 "R1", "BO3", won, provider, 0, "now", "hard"),
            )

    # Build different pre-match opponent ratings before both providers reuse
    # the same local id on day two.
    add_match(provider_a, "a-first", 1, 2, "2026-01-01")
    add_match(provider_b, "b-first", 4, 3, "2026-01-01")
    add_match(provider_a, "shared", 1, 2, "2026-02-01")
    add_match(provider_b, "shared", 3, 4, "2026-02-01")
    conn.commit()

    monkeypatch.setattr(elo_builder, "get_connection", lambda: conn)
    elo_builder.build_sackmann_elo()

    rows = conn.execute(
        "SELECT source_provider,opponent_elo FROM player_match_history "
        "WHERE provider_match_id='shared-winner' ORDER BY source_provider"
    ).fetchall()
    values = {row["source_provider"]: row["opponent_elo"] for row in rows}
    assert values[provider_a] < 1500.0
    assert values[provider_b] > 1500.0


def test_elo_builder_batches_history_opponent_updates(tmp_path, monkeypatch):
    """Daily rebuild cost must not grow as two SQL UPDATE statements per
    historical match.  A single set-based update keeps the full walk viable."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.ingestion.ingest_sackmann import HISTORY_PROVIDERS
    from tennis_wc.modelling import elo_builder

    init_db()
    conn = get_connection()
    for pid in (1, 2):
        conn.execute(
            "INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)", (pid, f"P{pid}", "ATP", "test", "now", "now"))
    provider = HISTORY_PROVIDERS[0]
    for idx in range(3):
        for role, player, opponent, won in (
            ("winner", 1, 2, 1), ("loser", 2, 1, 0),
        ):
            conn.execute(
                """INSERT INTO player_match_history
                   (provider_match_id,player_id,opponent_id,tour,match_date,
                    tournament_external_id,tournament_level,round,format,won,
                    source_provider,raw_response_id,created_at,surface)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"M{idx}-{role}", player, opponent, "ATP", f"2026-01-0{idx + 1}",
                 "T", "ATP250", "R1", "BO3", won, provider, 0, "now", "hard"),
            )
    conn.commit()

    statements = []
    monkeypatch.setattr(elo_builder, "get_connection", lambda: conn)
    conn.set_trace_callback(statements.append)
    elo_builder.build_sackmann_elo()
    conn.set_trace_callback(None)

    history_updates = [
        sql for sql in statements
        if sql.lstrip().upper().startswith("UPDATE PLAYER_MATCH_HISTORY")
    ]
    assert len(history_updates) <= 1


def test_feature_snapshot_prefers_as_of_elo_over_the_mutable_column(tmp_path, monkeypatch):
    """players.overall_elo is rewritten on every rebuild; the snapshot must not use it."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.features import feature_builder
    from tennis_wc.history import elo_history

    init_db()
    conn = get_connection()
    elo_history.ensure_schema(conn)
    conn.execute(
        "INSERT INTO players (id, name, tour, overall_elo, source_provider, created_at, updated_at) "
        "VALUES (1,'A','ATP', 1900.0, 'test','now','now')")   # today's inflated rating
    elo_history.record(conn, [(1, "2026-01-01", "", 1520.0, 5)])
    conn.commit()

    overall, _surface, as_of = feature_builder._elo_as_of(conn, 1, "2026-06-01", None)
    assert as_of is True
    assert overall == 1520.0, "the as-of rating must win over the mutable column"

    # A player with no recorded history falls back, and says so.
    conn.execute(
        "INSERT INTO players (id, name, tour, overall_elo, source_provider, created_at, updated_at) "
        "VALUES (2,'B','ATP', 1700.0, 'test','now','now')")
    conn.commit()
    overall, _surface, as_of = feature_builder._elo_as_of(conn, 2, "2026-06-01", None)
    assert overall is None and as_of is False
