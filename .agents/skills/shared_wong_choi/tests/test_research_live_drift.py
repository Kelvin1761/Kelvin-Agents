from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_live_drift import (
    inspect_live_feature_drift,
    live_drift_report_reference,
    verify_live_feature_drift_report,
)


BASELINE = datetime(2026, 9, 1, tzinfo=timezone.utc)
AS_OF = datetime(2026, 9, 4, tzinfo=timezone.utc)


def _record(identity: str, cutoff: str, *, ready: bool = True,
            blockers: list[str] | None = None) -> dict:
    return {
        "record_id": identity,
        "source_cutoff_at": cutoff,
        "bundle_verified": ready,
        "feature_availability_verified": ready,
        "blockers": [] if blockers is None else blockers,
    }


def _source(domain: Domain, as_of: datetime, records: list[dict]) -> dict:
    payload = {
        "schema_version": "fixture-feature-provenance/v1",
        "domain": domain.value,
        "as_of": as_of.isoformat(),
        "records": records,
    }
    payload["content_hash"] = _hash(payload)
    return payload


def _install_sources(monkeypatch, baseline_records: list[dict],
                     current_records: list[dict]):
    def fake(*, root, domain, as_of, relocation_roots, checkpoint):
        checkpoint()
        records = baseline_records if as_of == BASELINE else current_records
        return _source(domain, as_of, records)

    monkeypatch.setattr(
        "shared_wong_choi.research_live_drift._inspect_feature_source", fake,
    )


def test_verified_feature_availability_drift_is_descriptive_and_path_free(
        tmp_path, monkeypatch):
    old = _record("old", "2026-08-31T12:00:00+00:00")
    new_good = _record("new-good", "2026-09-02T12:00:00+00:00")
    new_bad = _record(
        "new-bad", "2026-09-03T12:00:00+00:00", ready=False,
        blockers=["feature_source_missing"],
    )
    _install_sources(monkeypatch, [old], [old, new_good, new_bad])
    root = tmp_path / "evidence"
    root.mkdir()

    report = inspect_live_feature_drift(
        root=root, domain=Domain.AU, baseline_as_of=BASELINE, as_of=AS_OF,
    )
    reference = live_drift_report_reference(tmp_path / "report.json", report)

    assert report["status"] == "verified_descriptive"
    assert report["baseline"]["availability_rate"] == 1.0
    assert report["current"]["availability_rate"] == 0.5
    assert report["availability_delta"] == -0.5
    assert report["direction"] == "degraded"
    assert report["feature_health"] == "attention"
    assert report["live_drift_verified"] is True
    assert report["metric_drift_verified"] is False
    assert report["market_drift_verified"] is False
    assert report["threshold_decision_allowed"] is False
    assert report["model_promotion_allowed"] is False
    assert "root" not in reference and "path" in reference
    assert reference["direction"] == "degraded"


@pytest.mark.parametrize("missing", ["baseline", "current"])
def test_missing_comparison_period_stays_unknown(tmp_path, monkeypatch, missing):
    old = _record("old", "2026-08-31T12:00:00+00:00")
    new = _record("new", "2026-09-02T12:00:00+00:00")
    baseline_records = [] if missing == "baseline" else [old]
    current_records = [old] if missing == "current" else [old, new]
    _install_sources(monkeypatch, baseline_records, current_records)
    root = tmp_path / "evidence"
    root.mkdir()

    report = inspect_live_feature_drift(
        root=root, domain=Domain.TENNIS,
        baseline_as_of=BASELINE, as_of=AS_OF,
    )

    assert report["status"] == "insufficient_data"
    assert report["feature_health"] == "unknown"
    assert report["availability_delta"] is None
    assert report["direction"] == "unknown"
    assert report["live_drift_verified"] is False


def test_late_historical_backfill_blocks_comparison(tmp_path, monkeypatch):
    old = _record("old", "2026-08-31T12:00:00+00:00")
    late = _record("late", "2026-08-30T12:00:00+00:00")
    new = _record("new", "2026-09-02T12:00:00+00:00")
    _install_sources(monkeypatch, [old], [old, late, new])
    root = tmp_path / "evidence"
    root.mkdir()

    report = inspect_live_feature_drift(
        root=root, domain=Domain.HKJC,
        baseline_as_of=BASELINE, as_of=AS_OF,
    )

    assert report["status"] == "source_incomplete"
    assert report["late_historical_records"] == 1
    assert report["live_drift_verified"] is False
    assert report["feature_health"] == "unknown"


def test_historical_source_shrinkage_fails_closed(tmp_path, monkeypatch):
    old = _record("old", "2026-08-31T12:00:00+00:00")
    _install_sources(monkeypatch, [old], [])
    root = tmp_path / "evidence"
    root.mkdir()

    with pytest.raises(ValueError, match="historical feature source shrank"):
        inspect_live_feature_drift(
            root=root, domain=Domain.NBA,
            baseline_as_of=BASELINE, as_of=AS_OF,
        )


def test_rehashed_derived_drift_claim_is_rejected_without_source_rebuild(
        tmp_path, monkeypatch):
    old = _record("old", "2026-08-31T12:00:00+00:00")
    new = _record("new", "2026-09-02T12:00:00+00:00")
    _install_sources(monkeypatch, [old], [old, new])
    root = tmp_path / "evidence"
    root.mkdir()
    report = inspect_live_feature_drift(
        root=root, domain=Domain.AU, baseline_as_of=BASELINE, as_of=AS_OF,
    )
    report["direction"] = "degraded"
    report["content_hash"] = _hash({
        key: value for key, value in report.items() if key != "content_hash"
    })

    with pytest.raises(ValueError, match="derived live drift projection"):
        verify_live_feature_drift_report(
            report, root=root, domain=Domain.AU,
            baseline_as_of=BASELINE, as_of=AS_OF,
            reverify_source=False,
        )


def test_parent_rebuild_rejects_source_change(tmp_path, monkeypatch):
    old = _record("old", "2026-08-31T12:00:00+00:00")
    new = _record("new", "2026-09-02T12:00:00+00:00")
    _install_sources(monkeypatch, [old], [old, new])
    root = tmp_path / "evidence"
    root.mkdir()
    report = inspect_live_feature_drift(
        root=root, domain=Domain.AU, baseline_as_of=BASELINE, as_of=AS_OF,
    )
    changed = _record(
        "new", "2026-09-02T12:00:00+00:00", ready=False,
        blockers=["feature_source_missing"],
    )
    _install_sources(monkeypatch, [old], [old, changed])

    with pytest.raises(ValueError, match="source changed"):
        verify_live_feature_drift_report(
            report, root=root, domain=Domain.AU,
            baseline_as_of=BASELINE, as_of=AS_OF,
            reverify_source=True,
        )


@pytest.mark.parametrize("domain", list(Domain))
def test_real_domain_router_handles_empty_source_as_unknown(tmp_path, domain):
    root = tmp_path / domain.value
    (root / "records").mkdir(parents=True)
    report = inspect_live_feature_drift(
        root=root, domain=domain, baseline_as_of=BASELINE, as_of=AS_OF,
    )
    assert report["status"] == "insufficient_data"
    assert report["live_drift_verified"] is False
