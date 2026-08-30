from __future__ import annotations

from argparse import Namespace
from pathlib import Path


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
