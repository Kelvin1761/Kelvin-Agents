from __future__ import annotations

from argparse import Namespace
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace


def test_manual_and_review_attach_research_without_changing_native_counters(monkeypatch):
    from tennis_wc import cli
    calls, output = [], []
    monkeypatch.setattr(cli, "settle_bets_for_date", lambda day: {"settled": 2, "pending": 1})
    monkeypatch.setattr(cli, "review_date_entry", lambda day: {"review_report_path": "native.md"})
    monkeypatch.setattr(cli, "_record_research_settlement_for_date",
                        lambda day: calls.append(day) or {"status": "failed", "reason": "fixture"})
    monkeypatch.setattr(cli, "_print_json", output.append)
    args = Namespace(date="2026-09-01")
    cli.settle_bets(args)
    cli.review_date(args)
    assert calls == [args.date, args.date]
    assert output[0] == {"settled": 2, "pending": 1,
                         "prediction_evidence": {"status": "failed", "reason": "fixture"}}
    assert output[1]["review_report_path"] == "native.md"


def test_backlog_retries_frozen_days_when_native_pending_is_empty(monkeypatch):
    from tennis_wc import cli, research_adapter
    calls = []
    monkeypatch.setattr(cli, "settle_pending_backlog", lambda *args, **kwargs: {"dates": {}, "props": {"settled": 3}})
    monkeypatch.setattr(research_adapter, "research_retry_batch", lambda **kwargs: {
        "dates": ["2026-09-01"], "eligible_dates": 12, "deferred_dates": 11,
        "budget": 1, "corpus_qualified": False})
    monkeypatch.setattr(cli, "_record_research_settlement_for_date",
                        lambda day: calls.append(day) or {"status": "duplicate"})
    result = cli._settle_backlog_with_research("2026-09-02")
    assert calls == ["2026-09-01"]
    assert result["props"] == {"settled": 3} and result["dates"] == {}
    assert result["research_retry"]["deferred_dates"] == 11
    assert result["research_retry"]["results"]["2026-09-01"]["status"] == "duplicate"


def test_research_retry_inventory_failure_preserves_native_settlement(monkeypatch):
    from tennis_wc import cli, research_adapter
    monkeypatch.setattr(cli, "settle_pending_backlog", lambda *args, **kwargs: {"dates": {"2026-09-01": {"settled": 1}}})
    def fail(**kwargs):
        raise ValueError("corrupt evidence fixture")
    monkeypatch.setattr(research_adapter, "research_retry_batch", fail)
    result = cli._settle_backlog_with_research("2026-09-02")
    assert result["dates"]["2026-09-01"]["settled"] == 1
    assert result["research_retry"]["status"] == "failed"


def test_cli_observer_uses_query_only_connection_and_closes_it(monkeypatch, tmp_path):
    import pytest
    from tennis_wc import cli, research_adapter
    conn = sqlite3.connect(":memory:")
    monkeypatch.setattr(cli, "get_connection", lambda: conn)
    monkeypatch.setenv("WC_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    def observe(connection, **kwargs):
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE forbidden (id INTEGER)")
        return {"status": "migration_pending"}
    monkeypatch.setattr(research_adapter, "record_research_settlement", observe)
    assert cli._record_research_settlement_for_date("2026-09-01")["status"] == "migration_pending"
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_daily_evidence_is_frozen_before_publish(tmp_path, monkeypatch):
    from tennis_wc import cli

    report = tmp_path / "Daily.md"
    report.write_text("priced card\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        cli,
        "analysis_output_dir",
        lambda _: (_ for _ in ()).throw(
            AssertionError("prediction evidence must not read the Drive mirror")
        ),
    )
    monkeypatch.setenv("WC_EVIDENCE_ROOT", str(tmp_path / "evidence"))

    def fake_record(**kwargs):
        calls.append(kwargs)
        assert kwargs["snapshot"].joinpath("manifest.json").is_file()
        return {"status": "created", "decision_id": "wc:tennis:decision:test"}

    monkeypatch.setattr(
        cli, "record_prediction_decision_if_configured", fake_record
    )
    payload = {}
    predictions = [{"id": 1, "final_decision": "BET", "edge": 0.08}]

    result = cli._record_daily_evidence(
        Namespace(date="2026-08-27"), payload, report, predictions
    )

    assert result["status"] == "created"
    assert payload["prediction_evidence"] == result
    assert Path(payload["prediction_snapshot"]).is_dir()
    assert calls[0]["decision_state"] is cli.DecisionState.RECOMMEND
    assert calls[0]["recommendations"] == predictions


def test_daily_evidence_uses_no_bet_without_final_bet(tmp_path, monkeypatch):
    from tennis_wc import cli

    report = tmp_path / "Daily.md"
    report.write_text("watchlist only\n", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "analysis_output_dir",
        lambda _: (_ for _ in ()).throw(
            AssertionError("prediction evidence must not read the Drive mirror")
        ),
    )
    observed = {}

    def fake_record(**kwargs):
        observed.update(kwargs)
        return {"status": "migration_pending"}

    monkeypatch.setattr(
        cli, "record_prediction_decision_if_configured", fake_record
    )

    cli._record_daily_evidence(
        Namespace(date="2026-08-27"),
        {},
        report,
        [{"id": 1, "final_decision": "WATCHLIST"}],
    )

    assert observed["decision_state"] is cli.DecisionState.NO_BET


def _research_database(monkeypatch):
    from tennis_wc import cli
    from test_stage5_research_evidence import _raws

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE predictions (id INTEGER PRIMARY KEY, created_at TEXT)")
    conn.execute("INSERT INTO predictions VALUES (101, '2026-08-31T22:30:00+00:00')")
    conn.execute("CREATE TABLE raw_api_responses (id INTEGER PRIMARY KEY, provider_name TEXT, "
                 "endpoint TEXT, response_json TEXT, fetched_at TEXT, created_at TEXT)")
    for row in _raws().values():
        conn.execute("INSERT INTO raw_api_responses VALUES (?, ?, ?, ?, ?, ?)",
                     tuple(row[key] for key in ("id", "provider_name", "endpoint", "response_json", "fetched_at", "created_at")))
    conn.commit()
    monkeypatch.setattr(cli, "get_connection", lambda: conn)
    return conn


def test_daily_adapter_freezes_exact_memory_and_raw_provenance(tmp_path, monkeypatch):
    from tennis_wc import cli
    from test_stage5_research_evidence import CUTOFF, EVENT, _pricing, _snapshot
    from shared_wong_choi.research_tennis_feature_provenance import _projection

    conn = _research_database(monkeypatch)
    try:
        source, pricing = _snapshot(), _pricing()
        observation = cli._capture_research_observation(101, source, pricing)
        source["player_a"]["surface_elo"]["value"] = 9999
        pricing["edge"] = -0.2
        assert observation["snapshot"]["player_a"]["surface_elo"]["value"] == 1650
        assert observation["pricing"]["edge"] == 0.08
        monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _: CUTOFF))
        monkeypatch.setattr(cli, "record_prediction_decision_if_configured", lambda **_: {"status": "migration_pending"})
        report = tmp_path / "Daily.md"
        report.write_text("native card")
        payload, predictions = {}, [{"id": 101, "edge": 0.08, "final_decision": "BET"}]
        cli._record_daily_evidence(Namespace(date=EVENT), payload, report, predictions, [observation])
        snapshot = Path(payload["prediction_snapshot"])
        manifest = json.loads((snapshot / "manifest.json").read_bytes())
        assert manifest["created_at"] == CUTOFF.isoformat()
        assert payload["research_evidence"]["status"] == "pregame_provenance_captured"
        contents = {item["name"]: (snapshot / item["name"]).read_bytes() for item in manifest["files"]}
        for item in manifest["files"]:
            assert hashlib.sha256(contents[item["name"]]).hexdigest() == item["sha256"]
            assert len(contents[item["name"]]) == item["bytes"]
        rows, blockers = _projection(
            contents[f"Tennis_Feature_Evidence_{EVENT}.json"], event_id=EVENT, cutoff=CUTOFF,
            recommendations={101: predictions[0]},
            raw_artifacts={name: raw for name, raw in contents.items() if name.startswith("Tennis_Raw_Evidence_")},
        )
        assert not blockers and rows
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM raw_api_responses").fetchone()[0] == 2
    finally:
        conn.close()


def test_incomplete_memory_coverage_is_explicitly_blocked(tmp_path, monkeypatch):
    from tennis_wc import cli

    monkeypatch.setattr(cli, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("must not reconstruct memory from DB")))
    monkeypatch.setattr(cli, "record_prediction_decision_if_configured", lambda **_: {"status": "migration_pending"})
    report = tmp_path / "Daily.md"
    report.write_text("native card")
    payload = {}
    cli._record_daily_evidence(Namespace(date="2026-09-01"), payload, report, [{"id": 101}], [])
    assert payload["research_evidence"]["status"] == "blocked"
    assert "coverage incomplete" in payload["research_evidence"]["reason"]
    snapshot = Path(payload["prediction_snapshot"])
    assert not list(snapshot.glob("Tennis_Feature_Evidence_*"))
    assert (snapshot / "Daily.md").read_text() == "native card"


def test_missing_raw_source_does_not_fabricate_provenance(tmp_path, monkeypatch):
    from tennis_wc import cli
    from test_stage5_research_evidence import CUTOFF, EVENT, _observation

    conn = _research_database(monkeypatch)
    try:
        conn.execute("DELETE FROM raw_api_responses WHERE id = 902")
        conn.commit()
        monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _: CUTOFF))
        monkeypatch.setattr(cli, "record_prediction_decision_if_configured", lambda **_: {"status": "migration_pending"})
        report = tmp_path / "Daily.md"
        report.write_text("native card")
        payload = {}
        cli._record_daily_evidence(Namespace(date=EVENT), payload, report, [{"id": 101}], [_observation()])
        assert payload["research_evidence"]["status"] == "blocked"
        assert "missing Tennis raw response: 902" in payload["research_evidence"]["reason"]
        assert not list(Path(payload["prediction_snapshot"]).glob("Tennis_Feature_Evidence_*"))
    finally:
        conn.close()


def test_verified_watchlist_preserves_no_bet_and_feature_evidence(tmp_path, monkeypatch):
    from tennis_wc import cli
    from test_stage5_research_evidence import CUTOFF, EVENT, _observation
    conn = _research_database(monkeypatch)
    try:
        calls = []
        monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _: CUTOFF))
        monkeypatch.setattr(cli, "record_prediction_decision_if_configured",
                            lambda **kwargs: calls.append(kwargs) or {"status": "migration_pending"})
        report = tmp_path / "Daily.md"
        report.write_text("native watchlist, no bet")
        predictions = [{"id": 101, "edge": 0.08, "final_decision": "WATCHLIST"}]
        payload = {}
        cli._record_daily_evidence(Namespace(date=EVENT), payload, report, predictions, [_observation()])
        assert calls[0]["decision_state"] is cli.DecisionState.NO_BET
        assert calls[0]["recommendations"] == predictions
        assert payload["research_evidence"]["status"] == "pregame_provenance_captured"
        assert Path(payload["prediction_snapshot"]).joinpath(f"Tennis_Feature_Evidence_{EVENT}.json").is_file()
        assert predictions[0]["final_decision"] == "WATCHLIST"
    finally:
        conn.close()


def test_empty_native_card_is_not_a_verified_research_sample(tmp_path, monkeypatch):
    from tennis_wc import cli
    calls = []
    monkeypatch.setattr(cli, "record_prediction_decision_if_configured",
                        lambda **kwargs: calls.append(kwargs) or {"status": "migration_pending"})
    monkeypatch.setattr(cli, "get_connection", lambda: (_ for _ in ()).throw(AssertionError("empty card must not query features")))
    report = tmp_path / "Daily.md"
    report.write_text("native no matches")
    payload = {}
    cli._record_daily_evidence(Namespace(date="2026-09-01"), payload, report, [], [])
    assert calls[0]["decision_state"] is cli.DecisionState.NO_BET
    assert payload["research_evidence"]["status"] == "blocked"
    assert not list(Path(payload["prediction_snapshot"]).glob("Tennis_Feature_Evidence*"))
    assert report.read_text() == "native no matches"
