from datetime import datetime, timezone

import pytest

from shared_wong_choi import research_storage_evidence as evidence
from shared_wong_choi.contracts import Domain


NOW = datetime(2026, 9, 2, 2, 0, tzinfo=timezone.utc)


def _status(*, warm=False):
    return {
        "schema_version": "wong-choi-storage-status/v1",
        "status": "attention",
        "attention": ["dashboard_d1_backup_warm_pending", "hot_storage_warning"],
        "tiers": {
            "hot": {"status": "available", "pressure": "warning"},
            "warm": {"configured": True, "status": "available"},
            "cold": {"configured": False, "status": "unconfigured"},
        },
        "backups": {
            "dashboard_d1": {
                "schema_version": "wong-choi-dashboard-d1-backup-status/v1",
                "status": "attention",
                "snapshot_at": "2026-09-01T17:30:00+00:00",
                "stale_after_hours": 24,
                "restore_verified": True,
                "warm_verified": warm,
                "cold_verified": False,
                "artifact_id": "wc-artifact:d1",
            },
            "catalog_artifacts": {
                "status": "ok",
                "known_artifacts": 5,
                "verified_artifacts": 5,
                "unverified_artifacts": 0,
                "providers": ["google_drive"],
                "domains": {"central": {"known": 5, "verified": 5}},
            },
        },
        "inventory": [],
        "inventory_repo": "/repo",
        "policy": {},
    }


def test_storage_projection_separates_service_tiers_and_backup(monkeypatch, tmp_path):
    repo, state = tmp_path / "repo", tmp_path / "state"
    repo.mkdir(); state.mkdir()
    monkeypatch.setattr(evidence, "collect_storage_status", lambda *args, **kwargs: _status())

    report = evidence.collect_research_storage_evidence(
        repo_root=repo, state_root=state, domain=Domain.AU, as_of=NOW,
    )

    assert report["storage_health"] == "attention"
    assert report["tiers"] == {
        "hot": {"status": "available", "pressure": "warning"},
        "warm": {"configured": True, "status": "available"},
        "cold": {"configured": False, "status": "unconfigured"},
    }
    assert report["dashboard_d1"]["service_available"] is None
    assert report["dashboard_d1"]["restore_verified"] is True
    assert report["dashboard_d1"]["warm_verified"] is False
    assert report["artifact_cold"]["verified_artifacts"] == 5
    assert report["artifact_cold"]["providers"] == ["google_drive"]
    assert report["attention"] == [
        "dashboard_d1_backup_warm_pending", "hot_storage_warning",
    ]
    assert report["historical_availability_verified"] is False
    assert report["model_promotion_allowed"] is False
    evidence.verify_research_storage_evidence(
        report, repo_root=repo, state_root=state, domain=Domain.AU,
        as_of=NOW, reverify_source=True,
    )


def test_parent_rebuild_rejects_storage_source_change(monkeypatch, tmp_path):
    repo, state = tmp_path / "repo", tmp_path / "state"
    repo.mkdir(); state.mkdir()
    current = [_status()]
    monkeypatch.setattr(evidence, "collect_storage_status", lambda *args, **kwargs: current[0])
    report = evidence.collect_research_storage_evidence(
        repo_root=repo, state_root=state, domain=Domain.TENNIS, as_of=NOW,
    )
    current[0] = _status(warm=True)

    with pytest.raises(ValueError, match="source changed"):
        evidence.verify_research_storage_evidence(
            report, repo_root=repo, state_root=state, domain=Domain.TENNIS,
            as_of=NOW, reverify_source=True,
        )


def test_future_d1_snapshot_is_not_accepted(monkeypatch, tmp_path):
    repo, state = tmp_path / "repo", tmp_path / "state"
    repo.mkdir(); state.mkdir()
    value = _status()
    value["backups"]["dashboard_d1"]["snapshot_at"] = "2026-09-03T00:00:00+00:00"
    monkeypatch.setattr(evidence, "collect_storage_status", lambda *args, **kwargs: value)

    with pytest.raises(ValueError, match="future"):
        evidence.collect_research_storage_evidence(
            repo_root=repo, state_root=state, domain=Domain.NBA, as_of=NOW,
        )
