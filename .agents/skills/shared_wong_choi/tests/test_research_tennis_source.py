from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.research_tennis_source import SourceLimitExceeded, TennisSourcePolicy, inspect_tennis_sources


def fixture(tmp_path, fault=None):
    path = tmp_path / "tennis.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE matches(id INTEGER PRIMARY KEY, market_event_id TEXT, match_date TEXT, player_a_id INTEGER, player_b_id INTEGER, start_time_utc TEXT);
    CREATE TABLE players(id INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE raw_api_responses(id INTEGER PRIMARY KEY, provider_name TEXT, endpoint TEXT, response_json TEXT, fetched_at TEXT, created_at TEXT);
    CREATE TABLE market_odds_snapshots(id INTEGER PRIMARY KEY, event_id TEXT, match_id INTEGER, bookmaker TEXT, market_key TEXT, market_name TEXT, selection_name TEXT, selection_side TEXT, line REAL, odds REAL, source_provider TEXT, raw_response_id INTEGER, fetched_at TEXT, created_at TEXT);
    CREATE TABLE feature_snapshots(id INTEGER PRIMARY KEY, match_id INTEGER, player_id INTEGER, feature_set_version TEXT, features_json TEXT, provenance_json TEXT, data_quality_score INTEGER, created_at TEXT);
    """)
    start = "2026-08-25T12:00:00Z"
    seen = "2026-08-25T10:00:00Z"
    built = "2026-08-25T10:01:00Z"
    conn.execute("INSERT INTO matches VALUES(1,'evt-1','2026-08-25',11,12,?)", (start,))
    conn.executemany("INSERT INTO players VALUES(?,?)", [(11, "Alpha Player"), (12, "Beta Player")])
    event = {
        "event_id": "evt-1",
        "bookmaker": "Sportsbet",
        "start_time_utc": start,
        "player_a_name": "Alpha Player",
        "player_b_name": "Beta Player",
        "markets": [
            {
                "market_key": "match_winner",
                "market_name": "Match Betting",
                "selections": [
                    {"selection_name": "Alpha Player", "line": None, "odds": 1.8},
                    {"selection_name": "Beta Player", "line": None, "odds": 2.2},
                ],
            }
        ],
        "in_play": False,
    }
    if fault == "live":
        event["in_play"] = True
    if fault == "start_mismatch":
        event["start_time_utc"] = "2026-08-25T09:00:00Z"
    conn.execute(
        "INSERT INTO raw_api_responses VALUES(1,'sportsbet','/mock/odds',?,?,?)", (json.dumps([event]), seen, seen)
    )
    conn.execute("INSERT INTO raw_api_responses VALUES(2,'composite','/player-stats','{}',?,?)", (seen, seen))
    for index, (name, odds, player) in enumerate([("Alpha Player", 1.8, 11), ("Beta Player", 2.2, 12)], 1):
        conn.execute(
            "INSERT INTO market_odds_snapshots VALUES(?, 'evt-1',1,'Sportsbet','match_winner','Match Betting',?,NULL,NULL,?,'sportsbet',1,?,?)",
            (index, name, odds, seen, seen),
        )
        feature = {
            "id": {"value": player},
            "name": name,
            "overall_elo": {
                "value": 1700 + index * 10,
                "provenance": {
                    "raw_response_id": 2,
                    "source_provider": "composite",
                    "source_endpoint": "/player-stats",
                    "source_timestamp": seen,
                    "calculated_at": built,
                    "warnings": [],
                },
            },
        }
        conn.execute(
            "INSERT INTO feature_snapshots VALUES(?,1,?,'stage3.v1',?,'{}',90,?)",
            (index, player, json.dumps(feature), built),
        )
    if fault == "blank":
        conn.execute("UPDATE feature_snapshots SET features_json='' WHERE id=1")
    if fault == "future_source":
        conn.execute("UPDATE raw_api_responses SET created_at='2026-08-25T13:00:00Z' WHERE id=2")
    if fault == "future_snapshot":
        conn.execute("UPDATE feature_snapshots SET created_at='2026-08-25T13:00:00Z'")
    if fault == "missing_raw":
        conn.execute("DELETE FROM raw_api_responses WHERE id=1")
    if fault == "wrong_price":
        conn.execute("UPDATE market_odds_snapshots SET odds=9 WHERE id=1")
    if fault == "after_start":
        conn.execute("UPDATE market_odds_snapshots SET fetched_at='2026-08-25T13:00:00Z'")
    if fault == "future_feature":
        value = json.loads(conn.execute("SELECT features_json FROM feature_snapshots WHERE id=1").fetchone()[0])
        value["overall_elo"]["provenance"]["source_timestamp"] = "2026-08-25T13:00:00Z"
        conn.execute("UPDATE feature_snapshots SET features_json=? WHERE id=1", (json.dumps(value),))
    if fault == "mutable_fallback":
        value = json.loads(conn.execute("SELECT features_json FROM feature_snapshots WHERE id=1").fetchone()[0])
        value["overall_elo"]["provenance"]["warnings"] = ["elo_not_as_of"]
        conn.execute("UPDATE feature_snapshots SET features_json=? WHERE id=1", (json.dumps(value),))
    if fault == "mock_provider":
        conn.execute("UPDATE raw_api_responses SET provider_name='mock' WHERE id=1")
    if fault == "duplicate_identity":
        conn.execute("INSERT INTO matches VALUES(2,'evt-1','2026-08-25',11,12,?)", (start,))
    # Later odds are deliberately extreme. Earliest MIN(id), never best price.
    conn.execute(
        "INSERT INTO market_odds_snapshots SELECT id+10,event_id,match_id,bookmaker,market_key,market_name,selection_name,selection_side,line,99,source_provider,raw_response_id,'2026-08-25T13:00:00Z','2026-08-25T13:00:00Z' FROM market_odds_snapshots WHERE id<=2"
    )
    conn.commit()
    conn.close()
    policy = TennisSourcePolicy("2026-08-25", "2026-08-25", "2026-08-26T00:00:00Z", ("overall_elo",), 86400, 7200)
    return path, policy


def test_source_export_is_readonly_deterministic_and_not_proposal_authority(tmp_path):
    db, policy = fixture(tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    report = inspect_tennis_sources(db, policy)
    assert len(report.rows) == 1 and not report.exclusions
    row = report.rows[0]
    assert [quote["snapshot_id"] for quote in row["quotes"]] == [1, 2]
    assert [quote["odds"] for quote in row["quotes"]] == [1.8, 2.2]
    assert row["decision_at"] == "2026-08-25T10:01:00+00:00"
    assert report.to_payload()["proposal_ready"] is False
    assert report.to_payload() == inspect_tennis_sources(db, policy).to_payload()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_inventory_pins_exporter_source_identity(tmp_path):
    import shared_wong_choi.research_tennis_source as source

    db, policy = fixture(tmp_path)
    report = inspect_tennis_sources(db, policy).to_payload()
    assert report["exporter_sha256"] == hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "fault",
    [
        "blank",
        "future_source",
        "future_snapshot",
        "missing_raw",
        "wrong_price",
        "after_start",
        "live",
        "start_mismatch",
        "future_feature",
        "mutable_fallback",
        "mock_provider",
        "duplicate_identity",
    ],
)
def test_unverified_sources_are_excluded_with_reasons_not_repaired(tmp_path, fault):
    db, policy = fixture(tmp_path, fault)
    report = inspect_tennis_sources(db, policy)
    assert not report.rows
    assert report.exclusions and all(item["reasons"] for item in report.exclusions)


def test_later_good_snapshot_does_not_hide_first_empty_snapshot(tmp_path):
    db, policy = fixture(tmp_path, "blank")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO feature_snapshots SELECT id+10,match_id,player_id,feature_set_version,features_json,provenance_json,data_quality_score,'2026-08-25T10:02:00Z' FROM feature_snapshots"
        )
        conn.execute(
            "UPDATE feature_snapshots SET features_json=(SELECT features_json FROM feature_snapshots WHERE id=2) WHERE id=11"
        )
    assert not inspect_tennis_sources(db, policy).rows


def test_missing_database_is_not_created(tmp_path):
    _, policy = fixture(tmp_path)
    db = tmp_path / "missing.db"
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        inspect_tennis_sources(db, policy)
    assert not db.exists()


def test_rejected_source_content_is_bound_into_inventory_digest(tmp_path):
    db, policy = fixture(tmp_path, "blank")
    first = inspect_tennis_sources(db, policy).to_payload()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE feature_snapshots SET features_json='   ' WHERE id=1")
    second = inspect_tennis_sources(db, policy).to_payload()
    assert first["exclusions"][0]["reasons"] == second["exclusions"][0]["reasons"]
    assert first["content_hash"] != second["content_hash"], "invalid input also needs immutable identity"


def test_unrelated_labels_or_raw_request_parameters_are_not_read(tmp_path, monkeypatch):
    db, policy = fixture(tmp_path)
    original = sqlite3.connect
    with original(db) as conn:
        conn.execute("ALTER TABLE matches ADD COLUMN winner_player_id INTEGER")
        conn.execute("ALTER TABLE raw_api_responses ADD COLUMN request_params_json TEXT")

    class LabelGuard(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            def guard(action, table, column, database, source):
                if action == sqlite3.SQLITE_READ and column in ("winner_player_id", "request_params_json"):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            self.set_authorizer(guard)
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: original(*a, factory=LabelGuard, **kw))
    assert len(inspect_tennis_sources(db, policy).rows) == 1


@pytest.mark.parametrize("limit", ["max_rows_per_match", "max_json_bytes"])
def test_limits_abort_instead_of_silently_dropping_large_inputs(tmp_path, limit):
    db, policy = fixture(tmp_path)
    with pytest.raises(SourceLimitExceeded):
        inspect_tennis_sources(db, replace(policy, **{limit: 1}))


def test_match_limit_never_returns_a_partial_cohort(tmp_path):
    db, policy = fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO matches SELECT 2,'evt-2',match_date,player_a_id,player_b_id,start_time_utc FROM matches"
        )
    with pytest.raises(SourceLimitExceeded):
        inspect_tennis_sources(db, replace(policy, max_matches=1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("as_of", "2026-08-26T00:00:00"),
        ("date_from", "2026-08-27"),
        ("feature_fields", ()),
        ("feature_fields", ("overall_elo", "overall_elo")),
        ("price_max_age_seconds", float("nan")),
        ("feature_max_age_seconds", True),
        ("max_matches", True),
        ("timeout_seconds", 0),
        ("source_provider", "mock"),
    ],
)
def test_invalid_policy_is_rejected(tmp_path, field, value):
    db, policy = fixture(tmp_path)
    with pytest.raises(ValueError):
        inspect_tennis_sources(db, replace(policy, **{field: value}))


@pytest.mark.parametrize(
    "fault",
    [
        "stale_price",
        "stale_feature",
        "cutoff",
        "duplicate_json",
        "nonfinite",
        "version",
        "pair_duplicate",
        "raw_provider",
        "raw_endpoint",
        "raw_time",
        "identity",
    ],
)
def test_additional_source_boundaries(tmp_path, fault):
    db, policy = fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        if fault == "stale_price":
            policy = replace(policy, price_max_age_seconds=1)
        if fault == "stale_feature":
            policy = replace(policy, feature_max_age_seconds=1)
        if fault == "cutoff":
            policy = replace(policy, as_of="2026-08-25T10:00:30Z")
        if fault == "duplicate_json":
            conn.execute('UPDATE feature_snapshots SET features_json=\'{"id":11,"id":12}\' WHERE id=1')
        if fault == "nonfinite":
            row = conn.execute("SELECT features_json FROM feature_snapshots WHERE id=1").fetchone()[0]
            conn.execute("UPDATE feature_snapshots SET features_json=? WHERE id=1", (row.replace("1710", "1e999"),))
        if fault == "version":
            conn.execute("UPDATE feature_snapshots SET feature_set_version='wrong' WHERE id=1")
        if fault == "pair_duplicate":
            conn.execute(
                "INSERT INTO feature_snapshots SELECT 100,match_id,player_id,feature_set_version,features_json,provenance_json,data_quality_score,created_at FROM feature_snapshots WHERE id=1"
            )
        if fault == "raw_provider":
            conn.execute("UPDATE raw_api_responses SET provider_name='other' WHERE id=2")
        if fault == "raw_endpoint":
            conn.execute("UPDATE raw_api_responses SET endpoint='/other' WHERE id=2")
        if fault == "raw_time":
            conn.execute("UPDATE raw_api_responses SET fetched_at='2026-08-25T09:59:00Z' WHERE id=2")
        if fault == "identity":
            conn.execute("UPDATE players SET name='Another Player' WHERE id=11")
    report = inspect_tennis_sources(db, policy)
    assert not report.rows and report.exclusions


def test_checkpoint_interrupts_and_releases_database_lock(tmp_path):
    db, policy = fixture(tmp_path)
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 8:
            raise RuntimeError("production started")

    with pytest.raises(RuntimeError, match="production started"):
        inspect_tennis_sources(db, policy, checkpoint=checkpoint)
    with sqlite3.connect(db, timeout=0.1) as conn:
        conn.execute("BEGIN EXCLUSIVE")
        conn.rollback()


def test_symlink_source_is_not_followed(tmp_path):
    db, policy = fixture(tmp_path)
    link = tmp_path / "alias.db"
    link.symlink_to(db)
    with pytest.raises(ValueError):
        inspect_tennis_sources(link, policy)


def earlier_raw(db, *, endpoint="/event-odds", legacy=False, unrelated=False, future=False):
    with sqlite3.connect(db) as conn:
        event = json.loads(conn.execute("SELECT response_json FROM raw_api_responses WHERE id=1").fetchone()[0])[0]
        conn.execute("UPDATE raw_api_responses SET id=10 WHERE id=1")
        conn.execute("UPDATE market_odds_snapshots SET raw_response_id=10")
        if unrelated:
            event["event_id"] = "evt-other"
        if legacy:
            event.pop("markets")
            event.update(market="match_winner", player_a_odds=1.8, player_b_odds=2.2)
        conn.execute(
            "INSERT INTO raw_api_responses VALUES(?, 'sportsbet', ?, ?, ?, ?)",
            (
                11 if future else 5,
                endpoint,
                json.dumps(event),
                "2026-08-25T13:00:00Z" if future else "2026-08-25T09:59:00Z",
                "2026-08-25T13:00:00Z" if future else "2026-08-25T09:59:00Z",
            ),
        )


@pytest.mark.parametrize("legacy", [False, True])
def test_pruned_earlier_price_cannot_be_hidden_by_remaining_min_id(tmp_path, legacy):
    db, policy = fixture(tmp_path)
    earlier_raw(db, legacy=legacy)
    report = inspect_tennis_sources(db, policy)
    assert not report.rows, "remaining MIN(id) is not earliest archived capture"
    assert report.to_payload()["market_reconciliation"]["events"][0]["status"] == "earlier_archived_capture"
    assert any("earlier_archived_capture" in str(item["reasons"]) for item in report.exclusions)


@pytest.mark.parametrize("variant", ["unrelated", "future"])
def test_unrelated_or_later_raw_does_not_replace_first_market(tmp_path, variant):
    db, policy = fixture(tmp_path)
    earlier_raw(db, **{variant: True})
    report = inspect_tennis_sources(db, policy)
    assert len(report.rows) == 1
    audit = report.to_payload()["market_reconciliation"]
    assert audit["events"][0]["status"] == "earliest_in_retained_raws"
    assert audit["complete_archive_verified"] is False
    assert [q["raw_response_id"] for q in report.rows[0]["quotes"]] == [10, 10]


@pytest.mark.parametrize("malformed", ["{", "{}", "[null]"])
def test_unparseable_prior_provider_raw_does_not_silently_disappear(tmp_path, malformed):
    db, policy = fixture(tmp_path)
    earlier_raw(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE raw_api_responses SET response_json=? WHERE id=5", (malformed,))
    report = inspect_tennis_sources(db, policy)
    assert not report.rows
    assert report.to_payload()["market_reconciliation"]["unresolved_raws"]


def test_later_id_with_earlier_observation_is_also_detected(tmp_path):
    db, policy = fixture(tmp_path)
    earlier_raw(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE raw_api_responses SET id=20 WHERE id=5")
    assert not inspect_tennis_sources(db, policy).rows


def test_raw_archive_scan_budget_aborts_whole_inventory(tmp_path):
    db, policy = fixture(tmp_path)
    with pytest.raises(SourceLimitExceeded):
        inspect_tennis_sources(db, replace(policy, max_raw_bytes=1))


def test_rating_date_or_exact_numeric_match_does_not_prove_availability(tmp_path):
    db, policy = fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE player_elo_history(player_id INTEGER,as_of_date TEXT,surface TEXT,rating REAL,matches_played INTEGER)"
        )
        conn.executemany("INSERT INTO player_elo_history VALUES(?,'2026-08-24','',?,10)", [(11, 1710), (12, 1999)])
    payload = inspect_tennis_sources(db, policy).to_payload()
    audit = payload["rating_lineage"]
    assert audit["status"] == "unverified"
    assert audit["missing_proof"] == ["ingested_at", "build_version", "input_manifest"]
    assert [row["current_lookup_matches_snapshot"] for row in audit["rows"]] == [True, False]
    assert payload["pit_dataset_ready"] is False


def test_no_rating_table_is_explicitly_unverified_not_created(tmp_path):
    db, policy = fixture(tmp_path)
    payload = inspect_tennis_sources(db, policy).to_payload()
    assert payload["rating_lineage"]["status"] == "history_table_missing"
    with sqlite3.connect(db) as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='player_elo_history'").fetchall()


def test_sqlite_progress_callback_preserves_resource_interruption_reason(tmp_path, monkeypatch):
    db, policy = fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.executemany("INSERT INTO matches VALUES(?,NULL,'1980-01-01',11,12,NULL)", [(i,) for i in range(2, 2002)])
    original = sqlite3.connect
    in_callback = False

    class Instrumented(sqlite3.Connection):
        def set_progress_handler(self, callback, instructions):
            def wrapped():
                nonlocal in_callback
                in_callback = True
                try:
                    return callback()
                finally:
                    in_callback = False

            super().set_progress_handler(wrapped, instructions)

    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: original(*args, factory=Instrumented, **kwargs))

    def checkpoint():
        if in_callback:
            raise RuntimeError("production started inside SQL")

    with pytest.raises(RuntimeError, match="production started inside SQL"):
        inspect_tennis_sources(db, policy, checkpoint=checkpoint)
