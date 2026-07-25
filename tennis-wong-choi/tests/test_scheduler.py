from __future__ import annotations

import subprocess

from scripts import tennis_daily_schedule as scheduler


def test_ensure_live_network_accepts_ready(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "run_cli_json",
        lambda *args: {"diagnosis": "network_ready"},
    )

    scheduler.ensure_live_network()


def test_ensure_live_network_marks_sandbox_dns_as_temporary(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "run_cli_json",
        lambda *args: {"diagnosis": "system_dns_unavailable"},
    )

    try:
        scheduler.ensure_live_network()
    except scheduler.TemporaryDataUnavailable as exc:
        assert "host network access" in str(exc)
    else:
        raise AssertionError("network failure must stop the scheduled workflow")


def test_analysis_retry_reasons_allow_a_genuine_empty_slate():
    assert scheduler.analysis_retry_reasons(
        {
            "matches_analysed": 0,
            "valid_feature_snapshots": 0,
            "source_errors": [],
        }
    ) == []


def test_analysis_retry_reasons_reject_failed_odds_and_enrichment():
    reasons = scheduler.analysis_retry_reasons(
        {
            "matches_analysed": 0,
            "valid_feature_snapshots": 0,
            "source_errors": [
                {"source": "odds", "error": "dns failed"},
                {"source": "event_markets", "error": "only match winner"},
            ],
        }
    )

    assert "zero matches after source failures" in reasons
    assert "odds: dns failed" in reasons
    assert "event_markets: only match winner" in reasons


def test_main_returns_temporary_failure_code_before_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler, "LOG_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "ensure_live_network", lambda: (_ for _ in ()).throw(
        scheduler.TemporaryDataUnavailable("network unavailable")
    ))
    monkeypatch.setattr(
        scheduler,
        "run_cli",
        lambda *args: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, list(args))
        ),
    )

    assert scheduler.main(["--today", "2026-07-25"]) == 75
