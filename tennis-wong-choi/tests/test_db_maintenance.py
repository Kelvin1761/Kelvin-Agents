"""The retention rule has to be safe for the reader, not just small on disk."""

from __future__ import annotations

import sqlite3

from tennis_wc.database.maintenance import prune_raw_response_bodies


SCHEMA = """
CREATE TABLE raw_api_responses (
    id INTEGER PRIMARY KEY,
    provider_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_url_hash TEXT NOT NULL,
    request_params_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    entity_type TEXT,
    entity_external_id TEXT,
    created_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _insert(conn, identifier, provider, endpoint, entity_type, days_ago, body):
    conn.execute(
        """
        INSERT INTO raw_api_responses
            (id, provider_name, endpoint, request_url_hash, request_params_json,
             response_json, status_code, fetched_at, entity_type,
             entity_external_id, created_at)
        VALUES (?, ?, ?, '', '{}', ?, 200, date('now', ?), ?, NULL, date('now'))
        """,
        (identifier, provider, endpoint, body, f"-{days_ago} day", entity_type),
    )


def test_the_newest_body_of_a_series_survives_any_retention_window():
    """Every reader takes MAX(id) / ORDER BY id DESC LIMIT 1. Losing that row is
    the only way this can break the pipeline, so it must be impossible."""
    conn = _connect()
    _insert(conn, 1, "composite", "/hist", "match_history", 400, "oldest")
    _insert(conn, 2, "composite", "/hist", "match_history", 200, "middle")
    _insert(conn, 3, "composite", "/hist", "match_history", 100, "newest")

    result = prune_raw_response_bodies(conn, keep_days=0)

    assert result["rows"] == 2
    bodies = dict(conn.execute("SELECT id, response_json FROM raw_api_responses"))
    assert bodies == {1: "", 2: "", 3: "newest"}


def test_rows_are_kept_so_provenance_still_resolves():
    """feature_builder resolves a snapshot's origin by `WHERE id = ?`. Deleting
    the row would degrade every historical feature snapshot to
    `missing_raw_response`; blanking the body costs the reader nothing."""
    conn = _connect()
    _insert(conn, 1, "composite", "/hist", "match_history", 400, "oldest")
    _insert(conn, 2, "composite", "/hist", "match_history", 100, "newest")

    prune_raw_response_bodies(conn, keep_days=0)

    row = conn.execute(
        "SELECT provider_name, endpoint, fetched_at FROM raw_api_responses WHERE id = 1"
    ).fetchone()
    assert row is not None
    assert row["provider_name"] == "composite"
    assert row["endpoint"] == "/hist"


def test_recent_bodies_are_kept_even_when_superseded():
    conn = _connect()
    _insert(conn, 1, "composite", "/hist", "match_history", 30, "old")
    _insert(conn, 2, "composite", "/hist", "match_history", 2, "yesterday-ish")
    _insert(conn, 3, "composite", "/hist", "match_history", 0, "newest")

    prune_raw_response_bodies(conn, keep_days=7)

    bodies = dict(conn.execute("SELECT id, response_json FROM raw_api_responses"))
    assert bodies == {1: "", 2: "yesterday-ish", 3: "newest"}


def test_series_are_independent_per_provider_and_endpoint():
    conn = _connect()
    _insert(conn, 1, "composite", "/hist", "match_history", 400, "composite-old")
    _insert(conn, 2, "composite", "/hist", "match_history", 300, "composite-new")
    _insert(conn, 3, "tennismylife", "/a.csv", "match_history", 400, "tml-a")
    _insert(conn, 4, "tennismylife", "/b.csv", "match_history", 400, "tml-b")

    prune_raw_response_bodies(conn, keep_days=0)

    bodies = dict(conn.execute("SELECT id, response_json FROM raw_api_responses"))
    assert bodies == {1: "", 2: "composite-new", 3: "tml-a", 4: "tml-b"}


def test_other_entity_types_are_never_touched():
    """sportsbet odds bodies are excluded by design: backfill_match_start_times
    scans all of them, for 3% of the space."""
    conn = _connect()
    _insert(conn, 1, "sportsbet", "/odds", "odds", 400, "old-odds")
    _insert(conn, 2, "sportsbet", "/odds", "odds", 100, "new-odds")
    _insert(conn, 3, "composite", "/hist", "match_history", 400, "old-hist")
    _insert(conn, 4, "composite", "/hist", "match_history", 100, "new-hist")

    result = prune_raw_response_bodies(conn, keep_days=0)

    assert result["rows"] == 1
    bodies = dict(conn.execute("SELECT id, response_json FROM raw_api_responses"))
    assert bodies[1] == "old-odds"
    assert bodies[2] == "new-odds"
    assert bodies[3] == ""


def test_dry_run_reports_without_changing_anything():
    conn = _connect()
    _insert(conn, 1, "composite", "/hist", "match_history", 400, "oldest")
    _insert(conn, 2, "composite", "/hist", "match_history", 100, "newest")

    result = prune_raw_response_bodies(conn, keep_days=0, dry_run=True)

    assert result["rows"] == 1
    assert result["bytes_freed"] == len("oldest")
    bodies = dict(conn.execute("SELECT id, response_json FROM raw_api_responses"))
    assert bodies == {1: "oldest", 2: "newest"}


def test_running_twice_is_a_no_op():
    conn = _connect()
    _insert(conn, 1, "composite", "/hist", "match_history", 400, "oldest")
    _insert(conn, 2, "composite", "/hist", "match_history", 100, "newest")

    prune_raw_response_bodies(conn, keep_days=0)
    second = prune_raw_response_bodies(conn, keep_days=0)

    assert second["rows"] == 0
    assert second["bytes_freed"] == 0


# --------------------------------------------------------------------------- #
# feature_snapshots -- the second unbounded table, added 2026-08-26
# --------------------------------------------------------------------------- #
FEATURE_SCHEMA = """
CREATE TABLE feature_snapshots (
    id INTEGER PRIMARY KEY,
    match_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    feature_set_version TEXT NOT NULL,
    features_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    data_quality_score INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _feature_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FEATURE_SCHEMA)
    return conn


def _snapshot(conn, snapshot_id, match_id, player_id, created_at,
              version="v1", body="x" * 1000) -> None:
    conn.execute(
        "INSERT INTO feature_snapshots (id, match_id, player_id, "
        "feature_set_version, features_json, provenance_json, "
        "data_quality_score, created_at) VALUES (?,?,?,?,?,'{}',90,?)",
        (snapshot_id, match_id, player_id, version, body, created_at),
    )
    conn.commit()


def test_the_newest_snapshot_per_pair_survives_any_retention_window():
    """4.7 copies exist per (match, player); every reader takes MAX(id)."""
    from tennis_wc.database.maintenance import prune_superseded_feature_snapshots

    conn = _feature_conn()
    _snapshot(conn, 1, 10, 100, "2020-01-01")
    _snapshot(conn, 2, 10, 100, "2020-01-02")

    result = prune_superseded_feature_snapshots(conn, keep_days=0)
    assert result["rows"] == 1
    bodies = {
        row["id"]: row["features_json"]
        for row in conn.execute(
            "SELECT id, features_json FROM feature_snapshots").fetchall()
    }
    assert bodies[1] == ""
    assert bodies[2] != "", "the newest body must survive at any age"


def test_snapshot_rows_and_quality_scores_are_kept():
    """`player_identity` remaps player_id on these rows and the quality gates
    read the column, so deleting would quietly shrink both."""
    from tennis_wc.database.maintenance import prune_superseded_feature_snapshots

    conn = _feature_conn()
    _snapshot(conn, 1, 10, 100, "2020-01-01")
    _snapshot(conn, 2, 10, 100, "2020-01-02")

    prune_superseded_feature_snapshots(conn, keep_days=0)
    rows = conn.execute(
        "SELECT COUNT(*) n, MIN(data_quality_score) q FROM feature_snapshots"
    ).fetchone()
    assert rows["n"] == 2 and rows["q"] == 90


def test_a_different_feature_version_is_its_own_series():
    """A version bump is not a supersession -- both are current."""
    from tennis_wc.database.maintenance import prune_superseded_feature_snapshots

    conn = _feature_conn()
    _snapshot(conn, 1, 10, 100, "2020-01-01", version="v1")
    _snapshot(conn, 2, 10, 100, "2020-01-02", version="v2")

    assert prune_superseded_feature_snapshots(conn, keep_days=0)["rows"] == 0


def test_recent_snapshots_are_kept_even_when_superseded():
    from tennis_wc.database.maintenance import prune_superseded_feature_snapshots

    conn = _feature_conn()
    _snapshot(conn, 1, 10, 100, "2999-01-01")
    _snapshot(conn, 2, 10, 100, "2999-01-02")

    assert prune_superseded_feature_snapshots(conn, keep_days=7)["rows"] == 0


def test_feature_prune_dry_run_and_second_run_change_nothing():
    from tennis_wc.database.maintenance import prune_superseded_feature_snapshots

    conn = _feature_conn()
    _snapshot(conn, 1, 10, 100, "2020-01-01")
    _snapshot(conn, 2, 10, 100, "2020-01-02")

    dry = prune_superseded_feature_snapshots(conn, keep_days=0, dry_run=True)
    assert dry["rows"] == 1 and dry["dry_run"] is True
    assert conn.execute(
        "SELECT features_json FROM feature_snapshots WHERE id=1").fetchone()[0] != ""

    prune_superseded_feature_snapshots(conn, keep_days=0)
    assert prune_superseded_feature_snapshots(conn, keep_days=0)["rows"] == 0
