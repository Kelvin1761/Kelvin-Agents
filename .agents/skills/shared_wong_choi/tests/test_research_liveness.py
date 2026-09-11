from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_liveness import (
    collect_research_liveness_evidence,
    record_research_liveness_lease,
    verify_research_liveness_evidence,
)
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import ResearchJob
from test_research_runner import configured_queue, spec


NOW = datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)
TOKEN = "process-start:fixture-001"


def _claimed(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry")
    current_spec = spec(Domain.AU)
    queue = configured_queue(
        tmp_path, clock=lambda: NOW - timedelta(minutes=1),
        current_spec=current_spec, registry=registry,
    )
    queued = ResearchJob(
        "wc:au:research-job:liveness-001", Domain.AU, current_spec.record_id,
        tmp_path / "dataset", tmp_path / "baseline", tmp_path / "candidate",
        1024, 600,
    )
    queue.enqueue(queued)
    claim = queue.claim_next("worker-one")
    assert claim is not None
    leases = tmp_path / "leases"
    leases.mkdir()
    return registry, queue, claim, leases


def _record(leases, claim, **changes):
    values = {
        "pid": 4321,
        "process_start_token": TOKEN,
        "observed_at": NOW - timedelta(seconds=30),
        "valid_until": NOW + timedelta(minutes=5),
    }
    values.update(changes)
    return record_research_liveness_lease(
        lease_root=leases, claim=claim, **values,
    )


def _collect(registry, queue, leases, probe=lambda pid: TOKEN):
    return collect_research_liveness_evidence(
        registry_root=registry.root, queue_root=queue.root,
        lease_root=leases, domain=Domain.AU, as_of=NOW,
        process_probe=probe,
    )


def test_exact_live_process_identity_is_required_for_running_status(tmp_path):
    registry, queue, claim, leases = _claimed(tmp_path)
    _record(leases, claim)

    report = _collect(registry, queue, leases)

    assert report["source_snapshot_verified"] is True
    assert report["process_liveness_verified"] is True
    assert report["model_promotion_allowed"] is False
    assert report["counts"] == {
        "claimed_liveness_unverified": 0,
        "claimed_not_alive": 0,
        "queued": 0,
        "running_verified": 1,
        "terminal": 0,
    }
    item = report["queue"][0]
    assert item["status"] == "running_verified"
    assert item["process_alive"] is True
    assert item["pid"] == 4321
    verify_research_liveness_evidence(
        report, registry_root=registry.root, queue_root=queue.root,
        lease_root=leases, domain=Domain.AU, as_of=NOW,
        process_probe=lambda pid: TOKEN, reverify_source=True,
    )


@pytest.mark.parametrize(
    ("lease", "probe", "status", "alive"),
    [
        (False, lambda pid: TOKEN, "claimed_liveness_unverified", None),
        (True, lambda pid: None, "claimed_not_alive", False),
        (True, lambda pid: "process-start:reused-pid", "claimed_not_alive", False),
    ],
)
def test_missing_dead_or_reused_process_never_looks_running(
        tmp_path, lease, probe, status, alive):
    registry, queue, claim, leases = _claimed(tmp_path)
    if lease:
        _record(leases, claim)

    report = _collect(registry, queue, leases, probe=probe)

    assert report["queue"][0]["status"] == status
    assert report["queue"][0]["process_alive"] is alive


def test_expired_lease_is_not_probed_or_reported_alive(tmp_path):
    registry, queue, claim, leases = _claimed(tmp_path)
    _record(
        leases, claim,
        observed_at=NOW - timedelta(seconds=45),
        valid_until=NOW - timedelta(seconds=10),
    )
    probes = []

    report = _collect(
        registry, queue, leases,
        probe=lambda pid: probes.append(pid) or TOKEN,
    )

    assert probes == []
    assert report["queue"][0]["status"] == "claimed_not_alive"
    assert report["queue"][0]["process_alive"] is False
    assert report["queue"][0]["reason"] == "lease_expired"


def test_rehashed_wrong_claim_binding_fails_closed(tmp_path):
    registry, queue, claim, leases = _claimed(tmp_path)
    path = _record(leases, claim)
    payload = json.loads(path.read_text())
    payload["claim_content_hash"] = "f" * 64
    payload.pop("content_hash")
    payload["content_hash"] = _hash(payload)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="binding"):
        _collect(registry, queue, leases)


def test_forged_report_authority_is_rejected(tmp_path):
    registry, queue, claim, leases = _claimed(tmp_path)
    _record(leases, claim)
    report = _collect(registry, queue, leases)
    report["model_promotion_allowed"] = True
    report.pop("content_hash")
    report["content_hash"] = _hash(report)

    with pytest.raises(ValueError, match="authority"):
        verify_research_liveness_evidence(
            report, registry_root=registry.root, queue_root=queue.root,
            lease_root=leases, domain=Domain.AU, as_of=NOW,
            process_probe=lambda pid: TOKEN,
        )
