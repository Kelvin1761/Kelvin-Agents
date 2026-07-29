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


# --------------------------------------------------------------------------- #
# Thin odds coverage must not pass as a normal quiet day (2026-07-29)
# --------------------------------------------------------------------------- #
def _payload(fixtures, priced, matches=None, valid=None):
    matches = priced if matches is None else matches
    valid = matches if valid is None else valid
    return {
        "matches_analysed": matches,
        "valid_feature_snapshots": valid,
        "odds_coverage": {"fixtures": fixtures, "priced_matches": priced},
        "source_errors": [],
    }


def test_unopened_book_is_flagged_for_retry():
    """The 20:00 job analyses TOMORROW, when Sportsbet has barely opened the book.
    On 2026-07-29 that produced a published card from 2 priced matches out of 102
    fixtures, and every gate passed because they only checked for zero matches."""
    reasons = scheduler.analysis_retry_reasons(_payload(fixtures=102, priced=2))
    assert reasons, "2/102 priced must not be treated as a valid betting card"
    assert "not open yet" in reasons[0]


def test_healthy_same_day_coverage_passes():
    assert scheduler.analysis_retry_reasons(_payload(fixtures=92, priced=60, valid=40)) == []


def test_genuinely_small_card_is_not_flagged():
    """A real quiet day (few fixtures, nearly all priced) must stay a pass --
    the gate is about coverage, not volume."""
    assert scheduler.analysis_retry_reasons(_payload(fixtures=9, priced=8)) == []


def test_ratio_gate_ignores_tiny_fixture_lists():
    """Below the fixture floor the ratio is noise, so it must not fire."""
    assert scheduler.analysis_retry_reasons(_payload(fixtures=4, priced=1)) == []
