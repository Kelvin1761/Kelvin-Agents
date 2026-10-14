import copy
from dataclasses import replace
from datetime import timedelta

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore, RecordKind
from shared_wong_choi.research_index import _Reader, _hash, ResearchIndexError
from shared_wong_choi.research_racing_settlement_inventory import (
    freeze_racing_settlement_inventory, verify_racing_settlement_inventory,
)
import test_research_au_settlement_source as au
import test_research_hkjc_settlement_source as hk


def fixture(tmp_path, domain):
    native = au if domain is Domain.AU else hk
    root = native.settled_fixture(tmp_path, evidence_result=True)[0]
    return root, native.END


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_settlement_inventory_is_deterministic_complete_metadata_without_authority(tmp_path, domain):
    root, end = fixture(tmp_path, domain)
    report = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=end)
    assert report == freeze_racing_settlement_inventory(root=root, domain=domain, as_of=end)
    assert len(report["settlements"]) == 1
    assert report["settlements"][0]["prediction_id"].startswith(f"wc:{domain.value}:prediction:")
    assert len(report["source_files"]) >= 4
    assert report["verified_monitoring_samples"] is None and report["model_promotion_allowed"] is False
    verify_racing_settlement_inventory(report, root=root, domain=domain, as_of=end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("fault", ["append", "future_append", "narrowed", "authority", "missing_parent"])
def test_settlement_inventory_rebuild_rejects_changed_or_rehashed_incomplete_metadata(tmp_path, domain, fault):
    root, end = fixture(tmp_path, domain)
    report = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=end)
    if fault in {"append", "future_append"}:
        if domain is Domain.AU:
            from shared_wong_choi.research_au_settlement_source import _evidence
            values = [v[0] for v in _evidence(root, end, _Reader(lambda: None)).values()]
        else:
            from shared_wong_choi.research_hkjc_settlement_source import _evidence
            values = list(_evidence(root, end, _Reader(lambda: None)).values())
        old = next(v for v in values if v.kind is RecordKind.SETTLEMENT)
        changes = {"record_id": old.record_id + ":new"}
        if fault == "future_append":
            changes["created_at"] = (end + timedelta(days=1)).isoformat()
        EvidenceStore(root).append(replace(old, **changes))
    elif fault == "narrowed":
        report = copy.deepcopy(report)
        report["settlements"] = []
        report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    elif fault == "authority":
        report = copy.deepcopy(report)
        report["verified_monitoring_samples"] = 1
        report["model_promotion_allowed"] = True
        report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    else:
        next((root / "records" / RecordKind.DECISION.value).glob("*.json")).unlink()
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        verify_racing_settlement_inventory(report, root=root, domain=domain, as_of=end)


def test_settlement_inventory_rejects_non_racing_domain_and_missing_root(tmp_path):
    with pytest.raises(ValueError):
        freeze_racing_settlement_inventory(root=tmp_path, domain=Domain.NBA, as_of=au.END)
    with pytest.raises((ValueError, OSError)):
        freeze_racing_settlement_inventory(root=tmp_path / "missing", domain=Domain.AU, as_of=au.END)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_settlement_inventory_runs_supervised_without_registering_samples(tmp_path, domain):
    import json
    from shared_wong_choi.research_racing_settlement_inventory import RacingSettlementInventoryRunner
    from shared_wong_choi.research_registry import ExperimentRegistry
    from shared_wong_choi.research_runner import ResearchDisposition
    from test_research_supervision import source_runtime
    root, end = fixture(tmp_path, domain)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = RacingSettlementInventoryRunner(runtime, registry).run(
        domain=domain, evidence_root=root, as_of=end, estimated_bytes=1024, timeout_seconds=10)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    assert result.report_path.is_relative_to(runtime.warm_root)
    report = json.loads(result.report_path.read_text())
    verify_racing_settlement_inventory(report, root=root, domain=domain, as_of=end)
    assert report["verified_monitoring_samples"] is None and report["model_promotion_allowed"] is False
    assert not registry.root.exists()


def test_settlement_inventory_defers_before_opening_missing_source_when_production_active(tmp_path):
    import fcntl
    from shared_wong_choi.research_racing_settlement_inventory import RacingSettlementInventoryRunner
    from shared_wong_choi.research_registry import ExperimentRegistry
    from shared_wong_choi.research_runner import ResearchDisposition
    from test_research_supervision import source_runtime
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = RacingSettlementInventoryRunner(runtime, registry).run(
            domain=Domain.AU, evidence_root=tmp_path / "must-not-read", as_of=au.END,
            estimated_bytes=1024, timeout_seconds=10)
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED and result.attempt_path is None
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["promotion", "samples", "collection", "duplicate", "root"])
def test_settlement_inventory_parent_rejects_rehashed_invalid_receipt(tmp_path, fault):
    import json
    from shared_wong_choi.research_racing_settlement_inventory import (
        RacingSettlementInventoryRunner, verify_racing_settlement_inventory_receipt,
    )
    from shared_wong_choi.research_registry import ExperimentRegistry
    from shared_wong_choi.research_runner import ResearchDisposition
    from test_research_supervision import source_runtime
    root, end = fixture(tmp_path, Domain.AU)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    result = RacingSettlementInventoryRunner(runtime, registry).run(
        domain=Domain.AU, evidence_root=root, as_of=end, estimated_bytes=1024, timeout_seconds=10)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    if fault == "promotion":
        report["model_promotion_allowed"] = True
    elif fault == "samples":
        report["verified_monitoring_samples"] = 1
    elif fault == "collection":
        report["collections"] = report["collections"][:-1]
    elif fault == "duplicate":
        report["source_files"].append(report["source_files"][0])
    else:
        report["root"] = str(tmp_path / "wrong")
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(report))
    with pytest.raises((ValueError, ResearchIndexError)):
        verify_racing_settlement_inventory_receipt(
            payload={"domain": "au", "evidence_root": str(root), "as_of": end.isoformat()},
            runtime=runtime, report_path=result.report_path, receipt={"content_hash": report["content_hash"]})


@pytest.mark.parametrize("fault", ["offline", "heavy_lock", "deadline"])
def test_settlement_inventory_supervisor_resource_failure_never_returns_success(tmp_path, fault):
    import fcntl
    from shared_wong_choi.research_racing_settlement_inventory import RacingSettlementInventoryRunner
    from shared_wong_choi.research_registry import ExperimentRegistry
    from shared_wong_choi.research_runner import ResearchDisposition
    from test_research_supervision import source_runtime
    root, end = fixture(tmp_path, Domain.AU)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    timeout, handle, expected = 10, None, ResearchDisposition.DEFERRED
    if fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "offline")
    elif fault == "heavy_lock":
        lock = runtime.state_root / "locks/research-heavy-worker.lock"
        lock.parent.mkdir(parents=True)
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        timeout, expected = 0.001, ResearchDisposition.TIMED_OUT
    try:
        result = RacingSettlementInventoryRunner(runtime, registry).run(
            domain=Domain.AU, evidence_root=root, as_of=end, estimated_bytes=1024, timeout_seconds=timeout)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert not registry.root.exists()
