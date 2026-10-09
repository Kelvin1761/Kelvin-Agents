from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tennis_wc.research_adapter import freeze_settlement, read_settlement_sources, load_forecast_context, record_research_settlement, research_retry_batch
from tennis_wc.research_evidence import build_settlement_artifacts


AT = datetime(2026, 10, 9, tzinfo=timezone.utc)


def _build(clock):
    return {"Result.json": json.dumps({"captured_at": clock.isoformat(), "winner": 11}).encode()}


def test_retry_preserves_actual_first_capture_clock(tmp_path):
    arguments = dict(root=tmp_path / "captures", identity={"prediction": "fixture", "raw_hash": "a" * 64}, build=_build)
    first = freeze_settlement(**arguments, at=AT)
    again = freeze_settlement(**arguments, at=AT + timedelta(days=1))
    assert again == first
    assert first[1] == AT
    assert json.loads(first[0][0].read_bytes())["captured_at"] == AT.isoformat()


def test_changed_input_appends_without_overwriting(tmp_path):
    first = freeze_settlement(root=tmp_path, identity={"source": 1}, at=AT, build=_build)
    original = first[0][0].read_bytes()
    second = freeze_settlement(root=tmp_path, identity={"source": 2}, at=AT, build=_build)
    assert first[0] != second[0]
    assert first[0][0].read_bytes() == original


def test_rehashed_manifest_cannot_forge_source_bound_bytes(tmp_path):
    paths, _clock, _signature = freeze_settlement(root=tmp_path, identity={"source": 1}, at=AT, build=_build)
    raw = b'{"winner": 99}'
    paths[0].write_bytes(raw)
    manifest_path = paths[0].parent / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="differs from source inputs"):
        freeze_settlement(root=tmp_path, identity={"source": 1}, at=AT, build=_build)
    assert paths[0].read_bytes() == raw


def test_artifact_symlink_is_refused(tmp_path):
    paths, _clock, _signature = freeze_settlement(root=tmp_path, identity={"source": 1}, at=AT, build=_build)
    target = tmp_path / "outside.json"
    target.write_bytes(paths[0].read_bytes())
    paths[0].unlink()
    paths[0].symlink_to(target)
    with pytest.raises(ValueError, match="missing or symlink"):
        freeze_settlement(root=tmp_path, identity={"source": 1}, at=AT, build=_build)


@pytest.mark.parametrize("name", ["../outside", "manifest.json", "", "/absolute"])
def test_unsafe_generated_names_are_refused(tmp_path, name):
    with pytest.raises(ValueError, match="invalid research capture artifact"):
        freeze_settlement(root=tmp_path, identity={}, at=AT, build=lambda _: {name: b"x"})


@pytest.fixture
def sources():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matches (id INTEGER PRIMARY KEY, match_date TEXT, player_a_id INTEGER, player_b_id INTEGER);
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, match_id INTEGER, created_at TEXT,
            selection_player_id INTEGER, model_probability REAL, no_vig_market_probability REAL);
        CREATE TABLE match_results (id INTEGER PRIMARY KEY, match_id INTEGER, winner_player_id INTEGER,
            source_provider TEXT, raw_response_id INTEGER, created_at TEXT, score_json TEXT);
        CREATE TABLE raw_api_responses (id INTEGER PRIMARY KEY, provider_name TEXT, endpoint TEXT,
            response_json TEXT, fetched_at TEXT, created_at TEXT);
        INSERT INTO players VALUES (11, 'Player A'), (22, 'Player B');
        INSERT INTO matches VALUES (7, '2026-10-09', 11, 22);
        INSERT INTO predictions VALUES (1, 7, '2026-10-08T23:00:00+00:00', 11, 0.6, 0.55);
        INSERT INTO predictions VALUES (2, 7, '2026-10-09T01:00:00+00:00', 22, 0.8, 0.7);
        INSERT INTO raw_api_responses VALUES (90, 'tennismylife', 'results',
            '{"winner_name": "Player A", "loser_name": "Player B"}',
            '2026-10-09T20:00:00+00:00', '2026-10-09T20:01:00+00:00');
        INSERT INTO match_results VALUES (8, 7, 11, 'tennismylife', 90, '2026-10-09T20:02:00+00:00', '{}');
    """)
    forecast = dict(prediction_id=1, match_id=7, prediction_created_at="2026-10-08T23:00:00Z",
                    selection_player_id=11, model_probability=0.6, no_vig_market_probability=0.55,
                    feature_snapshot={"player_a": {"id": {"value": 11}}, "player_b": {"id": {"value": 22}}})
    yield conn, forecast
    conn.close()


def test_read_sources_is_select_only_and_never_uses_latest_forecast(sources):
    conn, forecast = sources
    changes = conn.total_changes
    conn.execute("PRAGMA query_only=ON")
    statements = []
    conn.set_trace_callback(statements.append)
    outcomes, raw = read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast])
    assert len(outcomes) == 1 and outcomes[0]["prediction_id"] == 1
    assert outcomes[0]["selection_player_id"] == 11
    assert outcomes[0]["winner_player_id"] == 11
    assert set(raw) == {90}
    assert raw[90]["response_json"].startswith('{"winner_name"')
    assert conn.total_changes == changes
    assert all(statement.lstrip().startswith("SELECT") for statement in statements)


@pytest.mark.parametrize("column,value", [
    ("model_probability", 0.61), ("no_vig_market_probability", 0.56),
    ("selection_player_id", 22), ("created_at", "2026-10-09T00:00:00Z"),
    ("match_id", 99),
])
def test_mutated_forecast_never_becomes_settlement_evidence(sources, column, value):
    conn, forecast = sources
    conn.execute(f"UPDATE predictions SET {column}=? WHERE id=1", (value,))
    with pytest.raises(ValueError, match="differs|coverage missing"):
        read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast])


@pytest.mark.parametrize("table", ["match_results", "raw_api_responses"])
def test_missing_canonical_result_or_raw_is_blocked(sources, table):
    conn, forecast = sources
    conn.execute(f"DELETE FROM {table}")
    with pytest.raises(ValueError, match="provenance missing"):
        read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast])


def test_native_result_priority_aces_then_provider_then_latest(sources):
    conn, forecast = sources
    def selected():
        return read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast])[0][0]
    conn.execute("INSERT INTO match_results VALUES (9,7,22,'other',90,'2026-10-09T20:02:00Z','{}')")
    assert selected()["winner_player_id"] == 11  # preferred provider, not newest
    conn.execute("UPDATE match_results SET score_json=? WHERE id=9", ('{"player_a_aces":0,"player_b_aces":0}',))
    assert selected()["winner_player_id"] == 22  # complete aces precedes provider
    conn.execute("UPDATE match_results SET score_json=? WHERE id=8", ('{"player_a_aces":1,"player_b_aces":2}',))
    assert selected()["winner_player_id"] == 11
    conn.execute("INSERT INTO match_results VALUES (10,7,22,'tennismylife',90,'2026-10-09T20:02:00Z',?)",
                 ('{"player_a_aces":1,"player_b_aces":2}',))
    assert selected()["winner_player_id"] == 22


def test_duplicate_forecast_and_changed_participants_are_blocked(sources):
    conn, forecast = sources
    with pytest.raises(ValueError, match="duplicate"):
        read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast, forecast])
    conn.execute("UPDATE matches SET player_a_id=22,player_b_id=11")
    with pytest.raises(ValueError, match="differs"):
        read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast])


def test_exact_query_feeds_validated_immutable_capture(sources, tmp_path):
    conn, forecast = sources
    outcomes, raw = read_settlement_sources(conn, event_id="2026-10-09", forecast_rows=[forecast])
    cutoff = datetime(2026, 10, 8, 23, 30, tzinfo=timezone.utc)
    clock = datetime(2026, 10, 10, tzinfo=timezone.utc)
    def build(at):
        return build_settlement_artifacts(event_id="2026-10-09", source_cutoff_at=cutoff,
                                         settled_at=at, outcomes=outcomes, raw_responses=raw)
    arguments = dict(root=tmp_path, identity={"forecast": forecast, "outcomes": outcomes, "raw": raw}, build=build)
    first = freeze_settlement(**arguments, at=clock)
    assert freeze_settlement(**arguments, at=clock + timedelta(days=1)) == first
    from shared_wong_choi.research_tennis_settlement_source import _outcomes
    files = {path.name: path.read_bytes() for path in first[0]}
    name = "Tennis_Settlement_Evidence_2026-10-09.json"
    verified, valid = _outcomes(files[name], event_id="2026-10-09", cutoff=cutoff,
                               settled_at=first[1], recommendation_ids={1},
                               raw_artifacts={key: value for key, value in files.items() if key != name})
    assert valid and verified == 1
    # A DB winner without the corresponding raw winner must not become evidence.
    outcomes[0]["winner_player_id"] = 22
    with pytest.raises(ValueError, match="does not confirm winner"):
        build(clock)


@pytest.fixture
def frozen_parent(tmp_path):
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.evidence import DecisionState, ReleaseStage
    from shared_wong_choi.model_registry import ModelRegistry, ModelReleaseRequest
    from shared_wong_choi.immutable_snapshot import create_immutable_snapshot
    from shared_wong_choi.domain_evidence import record_prediction_decision
    from tennis_wc.research_evidence import build_prediction_artifacts
    from test_stage5_research_evidence import CUTOFF, EVENT, _observation, _raws

    root = tmp_path / "evidence"
    release = ModelRegistry(root).register(ModelReleaseRequest(
        domain=Domain.TENNIS, model_id="fixture", code_commit="a" * 40,
        evaluation_contract_version="tennis-v1", target_stage=ReleaseStage.RESEARCH,
        evaluation_verdict="BASELINE_MIGRATION", created_at="2026-08-31T20:00:00+00:00",
    ))
    artifacts = build_prediction_artifacts(event_id=EVENT, captured_at=CUTOFF,
                                         observations=[_observation()], raw_responses=_raws())
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "Daily.md").write_text("fixture card\n")
    snapshot = create_immutable_snapshot(output, domain="tennis", event_id=EVENT,
                                        patterns=["Daily.md"], recommendations=[{"id": 101, "edge": 0.08}],
                                        additional_files=artifacts, at=CUTOFF)
    result = record_prediction_decision(domain=Domain.TENNIS, event_id=EVENT, snapshot=snapshot,
                                        evidence_root=root, decision_state=DecisionState.SHADOW,
                                        recommendations=[{"id": 101, "edge": 0.08}],
                                        model_release_id=release["record_id"], source_cutoff_at=CUTOFF.isoformat())
    return root, snapshot, result


def test_context_verifies_actual_evidence_chain_and_frozen_features(frozen_parent):
    root, snapshot, result = frozen_parent
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    context = load_forecast_context(evidence_root=root, event_id="2026-09-01", at=AT)
    assert context["decision_id"] == result["decision_id"]
    assert context["forecast_rows"][0]["prediction_id"] == 101
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before
    assert load_forecast_context(evidence_root=root, event_id="2026-09-02", at=AT) is None


def test_context_refuses_hash_changed_or_missing_bundle(frozen_parent):
    root, snapshot, _ = frozen_parent
    path = snapshot / "Tennis_Feature_Evidence_2026-09-01.json"
    path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="bundle unverified"):
        load_forecast_context(evidence_root=root, event_id="2026-09-01", at=AT)


def test_context_refuses_ambiguous_same_time_decisions(frozen_parent):
    from shared_wong_choi.domain_evidence import record_prediction_decision
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.evidence import DecisionState
    root, snapshot, _ = frozen_parent
    record_prediction_decision(domain=Domain.TENNIS, event_id="2026-09-01", snapshot=snapshot,
                               evidence_root=root, decision_state=DecisionState.BLOCKED,
                               recommendations=[{"id": 101, "edge": 0.08}])
    with pytest.raises(ValueError, match="ambiguous"):
        load_forecast_context(evidence_root=root, event_id="2026-09-01", at=AT)


def _align_database_with_frozen_parent(conn):
    conn.execute("UPDATE matches SET id=501,match_date='2026-09-01'")
    conn.execute("UPDATE predictions SET id=101,match_id=501,model_probability=0.62,"
                 "no_vig_market_probability=0.54,created_at='2026-08-31T22:30:00Z' WHERE id=1")
    conn.execute("UPDATE match_results SET match_id=501,created_at='2026-09-01T20:02:00Z'")
    conn.execute("UPDATE raw_api_responses SET fetched_at='2026-09-01T20:00:00Z',created_at='2026-09-01T20:01:00Z'")


def test_guarded_callback_is_result_backed_and_idempotent(frozen_parent, sources, tmp_path):
    from shared_wong_choi.evidence import EvidenceStore
    root, _, parent = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    arguments = dict(evidence_root=root, capture_root=tmp_path / "captures", event_id="2026-09-01")
    changes = conn.total_changes
    conn.execute("PRAGMA query_only=ON")
    first = record_research_settlement(conn, **arguments, at=AT)
    again = record_research_settlement(conn, **arguments, at=AT + timedelta(days=1))
    assert first["status"] == "created" and again["status"] == "duplicate"
    assert first["settlement_id"] == again["settlement_id"]
    assert first["decision_id"] == parent["decision_id"]
    assert first["verified_outcomes"] == 1 and first["live_acceptance"] == "pending"
    store = EvidenceStore(root)
    assert store.audit()["counts"]["settlement"] == 1
    assert store.load(first["settlement_id"])["body"]["settled_at"] == AT.isoformat()
    from shared_wong_choi.research_tennis_settlement_source import inspect_tennis_settlement_candidates
    report = inspect_tennis_settlement_candidates(root=root, as_of=AT + timedelta(days=1))
    assert report["verified_outcomes"] == 1
    assert report["label_verified_settlements"] == 1
    assert conn.total_changes == changes


def test_missing_results_record_unverified_not_success(frozen_parent, sources, tmp_path):
    from shared_wong_choi.evidence import EvidenceStore
    root, _, _ = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    conn.execute("DELETE FROM match_results")
    result = record_research_settlement(conn, evidence_root=root, capture_root=tmp_path / "captures",
                                        event_id="2026-09-01", at=AT)
    record = EvidenceStore(root).load(result["settlement_id"])
    assert record["body"]["settlement_state"] == "unverified"
    assert result["research_status"] == "unverified" and result["verified_outcomes"] == 0
    assert all("Tennis_Settlement_Evidence" not in item["path"] for item in record["artifacts"])


def test_callback_publication_error_is_not_hidden_as_missing_sources(frozen_parent, sources, tmp_path, monkeypatch):
    from shared_wong_choi import domain_evidence
    root, _, _ = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    def refuse(**kwargs):
        assert kwargs["expected_decision_id"]
        raise RuntimeError("settlement decision changed since source capture")
    monkeypatch.setattr(domain_evidence, "record_settlement_for_event", refuse)
    with pytest.raises(RuntimeError, match="decision changed"):
        record_research_settlement(conn, evidence_root=root, capture_root=tmp_path / "captures",
                                   event_id="2026-09-01", at=AT)


def test_retry_inventory_rotates_without_ledger_or_sample_qualification(frozen_parent):
    from shared_wong_choi.evidence import EvidenceStore, EvidenceRecord, ArtifactRef, RecordKind
    from shared_wong_choi.contracts import Domain
    root, _, parent = frozen_parent
    store = EvidenceStore(root)
    raw = store.load(parent["prediction_id"])
    for index, event in enumerate(["2026-09-02", "2026-09-03", "2026-10-15"]):
        store.append(EvidenceRecord(
            record_id=f"wc:tennis:prediction:retry-fixture-{index}", kind=RecordKind.PREDICTION,
            domain=Domain.TENNIS, created_at=raw["created_at"],
            body={**raw["body"], "event_id": event}, links=raw["links"],
            artifacts=tuple(ArtifactRef(**item) for item in raw["artifacts"]),
        ))
    batches = [research_retry_batch(evidence_root=root, before_date=f"2026-10-{day:02}", max_dates=1)
               for day in (9, 10, 11)]
    assert {batch["dates"][0] for batch in batches} == {"2026-09-01", "2026-09-02", "2026-09-03"}
    assert all(batch["eligible_dates"] == 3 and batch["deferred_dates"] == 2
               and batch["corpus_qualified"] is False for batch in batches)
    assert research_retry_batch(evidence_root=root, before_date="2026-10-09", max_dates=0)["dates"] == []


def test_real_parent_change_between_capture_and_publication_is_refused(frozen_parent, sources, tmp_path, monkeypatch):
    from tennis_wc import research_adapter
    from shared_wong_choi.evidence import EvidenceStore, EvidenceRecord, RecordKind
    from shared_wong_choi.contracts import Domain
    root, _, parent = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    original = research_adapter.freeze_settlement
    def racing_capture(**kwargs):
        capture = original(**kwargs)
        EvidenceStore(root).append(EvidenceRecord(
            record_id="wc:tennis:decision:race-fixture", kind=RecordKind.DECISION,
            domain=Domain.TENNIS, created_at=AT.isoformat(),
            body={"decision_state": "blocked", "recommendation_count": 1},
            links={"prediction_id": parent["prediction_id"]},
        ))
        return capture
    monkeypatch.setattr(research_adapter, "freeze_settlement", racing_capture)
    with pytest.raises(RuntimeError, match="decision changed since source capture"):
        record_research_settlement(conn, evidence_root=root, capture_root=tmp_path / "captures",
                                   event_id="2026-09-01", at=AT)
    assert EvidenceStore(root).audit()["counts"].get("settlement", 0) == 0
    # Captured source bytes remain recoverable; no wrong-parent settlement is written.
    assert list((tmp_path / "captures").glob("*/Tennis_Settlement_Evidence*"))


def test_capture_io_failure_does_not_append_settlement(frozen_parent, sources, tmp_path, monkeypatch):
    from pathlib import Path
    from shared_wong_choi.evidence import EvidenceStore
    root, _, _ = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    def fail_rename(self, target):
        raise OSError("fixture disk full")
    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(OSError, match="disk full"):
        record_research_settlement(conn, evidence_root=root, capture_root=tmp_path / "captures",
                                   event_id="2026-09-01", at=AT)
    assert EvidenceStore(root).audit()["counts"].get("settlement", 0) == 0


def test_changed_native_result_cannot_overwrite_previous_verified_capture(frozen_parent, sources, tmp_path):
    from shared_wong_choi.evidence import EvidenceStore
    root, _, _ = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    arguments = dict(evidence_root=root, capture_root=tmp_path / "captures", event_id="2026-09-01")
    first = record_research_settlement(conn, **arguments, at=AT)
    before = {path: path.read_bytes() for path in (tmp_path / "captures").rglob("*.json")}
    conn.execute("UPDATE match_results SET winner_player_id=22")
    second = record_research_settlement(conn, **arguments, at=AT + timedelta(hours=1))
    assert second["research_status"] == "unverified"  # raw bytes still confirm Player A
    assert first["settlement_id"] != second["settlement_id"]
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert EvidenceStore(root).audit()["counts"]["settlement"] == 2


def test_capture_refuses_parent_symlink_without_writing_target(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="root symlink"):
        freeze_settlement(root=link / "captures", identity={}, at=AT, build=_build)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("budget,value", [("CAPTURE_MAX_FILES", 1),
    ("CAPTURE_MAX_FILE_BYTES", 3), ("CAPTURE_MAX_TOTAL_BYTES", 6)])
def test_generated_artifact_budgets_refuse_without_publishing(tmp_path, monkeypatch, budget, value):
    from tennis_wc import research_adapter
    monkeypatch.setattr(research_adapter, budget, value)
    with pytest.raises(ValueError, match="artifact budget"):
        freeze_settlement(root=tmp_path, identity={}, at=AT,
                          build=lambda clock: {"a.json": b"abcd", "b.json": b"efgh"})
    assert list(tmp_path.iterdir()) == []


def test_cached_manifest_and_artifact_reads_are_bounded(tmp_path, monkeypatch):
    from tennis_wc import research_adapter
    arguments = dict(root=tmp_path, identity={}, at=AT, build=_build)
    paths, _, _ = freeze_settlement(**arguments)
    monkeypatch.setattr(research_adapter, "CAPTURE_MAX_MANIFEST_BYTES", 10)
    with pytest.raises(ValueError, match="size limit"):
        freeze_settlement(**arguments)
    monkeypatch.setattr(research_adapter, "CAPTURE_MAX_MANIFEST_BYTES", 1024 * 1024)
    paths[0].write_bytes(b"x" * 20)
    monkeypatch.setattr(research_adapter, "CAPTURE_MAX_FILE_BYTES", 10)
    with pytest.raises(ValueError, match="size limit"):
        freeze_settlement(**arguments)
    assert paths[0].read_bytes() == b"x" * 20


def test_changed_capture_before_real_writer_cannot_be_rehashed_as_valid(frozen_parent, sources, tmp_path, monkeypatch):
    from tennis_wc import research_adapter
    from shared_wong_choi.evidence import EvidenceStore
    root, _, _ = frozen_parent
    conn, _ = sources
    _align_database_with_frozen_parent(conn)
    original = research_adapter.freeze_settlement
    def corrupted_capture(**kwargs):
        captured = original(**kwargs)
        captured[0][0].write_bytes(b"{}")
        return captured
    monkeypatch.setattr(research_adapter, "freeze_settlement", corrupted_capture)
    with pytest.raises(RuntimeError, match="artifact changed since source capture"):
        record_research_settlement(conn, evidence_root=root, capture_root=tmp_path / "captures",
                                   event_id="2026-09-01", at=AT)
    assert EvidenceStore(root).audit()["counts"].get("settlement", 0) == 0
