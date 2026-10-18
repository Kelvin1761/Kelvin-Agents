import fcntl
import hashlib
import json
from dataclasses import replace

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_evaluation import _write_report
from shared_wong_choi.research_prediction_page_runtime import (
    PredictionPageInspectionRunner, PredictionCorpusInspectionRunner, verify_prediction_page_receipt,
    verify_prediction_corpus_receipt,
    reconcile_prediction_corpus,
    PredictionCorpusReconciliationRunner,
)
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import ResearchDisposition
from test_research_prediction_artifacts import NOW, fixture
from test_research_supervision import source_runtime


def setup(tmp_path):
    root, _, _, _ = fixture(tmp_path)
    runtime = source_runtime(tmp_path)
    value = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)
    path = runtime.warm_root / "inventory.json"
    _write_report(path, value)
    options = dict(domain=Domain.AU, evidence_root=root, as_of=NOW,
                   inventory_path=path, inventory_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   page_index=0, estimated_bytes=1024, timeout_seconds=10)
    registry = ExperimentRegistry(tmp_path / "registry")
    return runtime, registry, options


def test_real_supervisor_writes_page_without_registering_experiment(tmp_path):
    runtime, registry, options = setup(tmp_path)
    result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.report_path.is_relative_to(runtime.warm_root)
    report = json.loads(result.report_path.read_text())
    assert report["records"][0]["snapshot_bundle_verified"] is True
    assert report["source_coverage_complete"] is False
    assert report["model_promotion_allowed"] is False
    assert not registry.root.exists()


def test_supervised_reconciliation_keeps_prior_attempt_unchanged(tmp_path):
    runtime, registry, result, payload = completed_corpus(tmp_path)
    prior = result.report_path.parent
    before = {p.name: p.read_bytes() for p in prior.iterdir()}
    reconciled = PredictionCorpusReconciliationRunner(runtime, registry).run(
        domain=Domain.AU, evidence_root=payload["evidence_root"], as_of=NOW,
        prior_workspace=prior, inventory_sha256=hashlib.sha256(before["prediction-inventory.json"]).hexdigest(),
        coverage_sha256=hashlib.sha256(before["prediction-coverage.json"]).hexdigest(),
        estimated_bytes=1024, timeout_seconds=10, max_records=2,
    )
    assert reconciled.disposition is ResearchDisposition.SUCCEEDED, reconciled.status
    assert reconciled.status == "prediction_corpus_reconciled_inventory_only"
    assert reconciled.content_hash == result.content_hash
    assert reconciled.report_path.parent != prior
    assert before == {p.name: p.read_bytes() for p in prior.iterdir()}
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["digest", "missing_coverage", "production", "deadline"])
def test_supervised_reconciliation_failure_does_not_acknowledge_prior_output(tmp_path, fault):
    runtime, registry, result, payload = completed_corpus(tmp_path)
    prior = result.report_path.parent
    call = dict(domain=Domain.AU, evidence_root=payload["evidence_root"], as_of=NOW,
                prior_workspace=prior,
                inventory_sha256=hashlib.sha256((prior / "prediction-inventory.json").read_bytes()).hexdigest(),
                coverage_sha256=hashlib.sha256(result.report_path.read_bytes()).hexdigest(),
                estimated_bytes=1024, timeout_seconds=10, max_records=2)
    handle = None
    expected = ResearchDisposition.FAILED
    if fault == "digest":
        call["inventory_sha256"] = "0" * 64
    elif fault == "missing_coverage":
        result.report_path.unlink()
    elif fault == "production":
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        call["prior_workspace"] = runtime.warm_root / "must-not-read"
        expected = ResearchDisposition.DEFERRED
    else:
        call["timeout_seconds"] = 0.001
        expected = ResearchDisposition.TIMED_OUT
    before = {p.name: p.read_bytes() for p in prior.iterdir()}
    try:
        reconciled = PredictionCorpusReconciliationRunner(runtime, registry).run(**call)
    finally:
        if handle:
            handle.close()
    assert reconciled.disposition is expected
    assert reconciled.report_path is None
    assert before == {p.name: p.read_bytes() for p in prior.iterdir()}
    assert not registry.root.exists()


def test_production_lock_defers_before_inventory_read(tmp_path):
    runtime, registry, options = setup(tmp_path)
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    options["inventory_path"] = runtime.warm_root / "must-not-open.json"
    try:
        result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.attempt_path is None


def test_inventory_digest_mismatch_fails_without_success_report(tmp_path):
    runtime, registry, options = setup(tmp_path)
    options["inventory_sha256"] = "0" * 64
    result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None


def test_inventory_outside_warm_cannot_be_read_as_approved_input(tmp_path):
    runtime, registry, options = setup(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_bytes(options["inventory_path"].read_bytes())
    options["inventory_path"] = outside
    result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.report_path is None


def test_offline_warm_defers_without_attempt(tmp_path):
    runtime, registry, options = setup(tmp_path)
    runtime = replace(runtime, warm_root=tmp_path / "offline")
    result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.status == "warm_offline"
    assert result.attempt_path is None


def test_shared_heavy_worker_lock_defers_child(tmp_path):
    runtime, registry, options = setup(tmp_path)
    lock = runtime.state_root / "locks/research-heavy-worker.lock"
    lock.parent.mkdir(parents=True)
    handle = lock.open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.status == "heavy_worker_busy"
    assert result.report_path is None


def test_external_deadline_never_returns_success(tmp_path):
    runtime, registry, options = setup(tmp_path)
    options["timeout_seconds"] = 0.001
    result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.TIMED_OUT
    assert result.report_path is None


@pytest.mark.parametrize("fault", ["promotion", "page_identity", "coverage"])
def test_parent_rejects_rehashed_forged_page_receipt(tmp_path, fault):
    runtime, registry, options = setup(tmp_path)
    result = PredictionPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    report = json.loads(result.report_path.read_text())
    if fault == "promotion":
        report["model_promotion_allowed"] = True
    elif fault == "page_identity":
        report["page_index"] = True
    else:
        report["records"] = []
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(report))
    payload = {
        "domain": "au", "evidence_root": str(options["evidence_root"]), "as_of": NOW.isoformat(),
        "inventory_path": str(options["inventory_path"]), "inventory_sha256": options["inventory_sha256"],
        "page_index": 0, "max_refs": 5000, "max_records": 100, "relocation_roots": [],
    }
    with pytest.raises(ValueError):
        verify_prediction_page_receipt(payload=payload, runtime=runtime, report_path=result.report_path,
                                       receipt={"content_hash": report["content_hash"]})


def corpus_options(options):
    return {key: options[key] for key in ("domain", "evidence_root", "as_of", "estimated_bytes", "timeout_seconds")}


def test_supervised_full_corpus_writes_inventory_pages_and_final_coverage(tmp_path):
    runtime, registry, options = setup(tmp_path)
    result = PredictionCorpusInspectionRunner(runtime, registry).run(**corpus_options(options))
    assert result.disposition is ResearchDisposition.SUCCEEDED
    report = json.loads(result.report_path.read_text())
    assert report["records_seen"] == 1 and report["artifact_refs"] == 3
    assert report["page_coverage_complete"] is True
    assert report["artifact_contents_verified"] is True
    assert report["verified_monitoring_samples"] is None
    assert (result.report_path.parent / "prediction-inventory.json").is_file()
    assert len(list(result.report_path.parent.glob("prediction-page-*.json"))) == 1
    assert not registry.root.exists()


def test_full_corpus_missing_blob_preserves_incomplete_artifact_status(tmp_path):
    runtime, registry, options = setup(tmp_path)
    # Resolve the fixture's source path without creating a replacement snapshot.
    value = json.loads(options["inventory_path"].read_text())
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    record = _records(options["evidence_root"], Domain.AU, NOW, _Reader(lambda: None))[0][0]
    from pathlib import Path
    path = next(Path(a.path) for a in record.artifacts if a.path.endswith("Race_1_Logic.json"))
    path.unlink()
    result = PredictionCorpusInspectionRunner(runtime, registry).run(**corpus_options(options))
    assert result.disposition is ResearchDisposition.SUCCEEDED
    report = json.loads(result.report_path.read_text())
    assert report["inventory_hash"] == value["content_hash"]
    assert report["page_coverage_complete"] is True
    assert report["artifact_contents_verified"] is False
    assert report["source_coverage_complete"] is False


def test_full_corpus_production_defer_creates_no_inventory(tmp_path):
    runtime, registry, options = setup(tmp_path)
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = PredictionCorpusInspectionRunner(runtime, registry).run(**corpus_options(options))
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.attempt_path is None


def test_full_corpus_deadline_has_no_completed_coverage(tmp_path):
    runtime, registry, options = setup(tmp_path)
    call = corpus_options(options)
    call["timeout_seconds"] = 0.001
    result = PredictionCorpusInspectionRunner(runtime, registry).run(**call)
    assert result.disposition is ResearchDisposition.TIMED_OUT
    assert result.report_path is None


def completed_corpus(tmp_path, count=4, max_records=2):
    from test_research_prediction_pages import inventory
    root, _ = inventory(tmp_path, count)
    runtime = source_runtime(tmp_path)
    registry = ExperimentRegistry(tmp_path / "registry")
    result = PredictionCorpusInspectionRunner(runtime, registry).run(
        domain=Domain.AU, evidence_root=root, as_of=NOW, estimated_bytes=1024,
        timeout_seconds=120, max_records=max_records,
    )
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    payload = {"domain": "au", "evidence_root": str(root), "as_of": NOW.isoformat(),
               "relocation_roots": [], "max_refs": 5000, "max_records": max_records}
    return runtime, registry, result, payload


def test_supervised_multiple_pages_cover_each_record_once(tmp_path):
    _, registry, result, _ = completed_corpus(tmp_path)
    proof = json.loads(result.report_path.read_text())
    pages = [json.loads(p.read_text()) for p in result.report_path.parent.glob("prediction-page-*.json")]
    ids = [r["record_id"] for page in pages for r in page["records"]]
    assert len(pages) == 2 and len(ids) == len(set(ids)) == proof["records_seen"] == 4
    assert proof["artifact_refs"] == 12 and proof["artifact_contents_verified"] is True
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["missing_page", "missing_inventory", "page_hash", "promotion", "count", "reorder"])
def test_parent_rejects_incomplete_or_rehashed_corpus(tmp_path, fault):
    runtime, _, result, payload = completed_corpus(tmp_path)
    proof = json.loads(result.report_path.read_text())
    if fault == "missing_page":
        next(result.report_path.parent.glob("prediction-page-*.json")).unlink()
    elif fault == "missing_inventory":
        (result.report_path.parent / "prediction-inventory.json").unlink()
    elif fault == "page_hash":
        proof["page_hashes"][0] = "0" * 64
    elif fault == "promotion":
        proof["model_promotion_allowed"] = True
    elif fault == "count":
        proof["records_seen"] -= 1
    else:
        proof["page_hashes"].reverse()
    proof["content_hash"] = _hash({k: v for k, v in proof.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(proof))
    with pytest.raises((ValueError, OSError)):
        verify_prediction_corpus_receipt(payload=payload, runtime=runtime,
                                        report_path=result.report_path, receipt={"content_hash": proof["content_hash"]})


def test_supervised_corpus_above_legacy_reference_cap_is_not_truncated(tmp_path):
    _, registry, result, _ = completed_corpus(tmp_path, count=1700, max_records=100)
    proof = json.loads(result.report_path.read_text())
    assert proof["records_seen"] == 1700 and proof["artifact_refs"] == 5100
    assert len(proof["page_hashes"]) == 17
    assert proof["page_coverage_complete"] is True and proof["artifact_contents_verified"] is True
    assert proof["source_coverage_complete"] is False and proof["verified_monitoring_samples"] is None
    assert not registry.root.exists()


@pytest.mark.parametrize("published", [False, True])
def test_final_coverage_publication_failure_never_returns_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_prediction_page_runtime as worker
    runtime, registry, options = setup(tmp_path)
    workspace = runtime.warm_root / "fault-attempt"
    workspace.mkdir()
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": NOW.isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    writer = worker._write_report
    def fail_final(path, value, **kwargs):
        if path.name == "prediction-coverage.json":
            if published:
                writer(path, value, **kwargs)
            raise OSError("coverage publication unacknowledged")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(worker, "_write_report", fail_final)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_prediction_corpus_request({"payload": payload}, runtime=runtime,
                                             workspace=workspace, checkpoint=lambda: None)
    assert (workspace / "prediction-coverage.json").exists() is published
    assert len(list(workspace.glob("prediction-page-*.json"))) == 1
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", [None, "wrong_inventory_digest", "wrong_coverage_digest", "missing_page", "source_append", "source_blob", "domain", "symlink", "interrupted"])
def test_explicit_corpus_reconciliation_is_read_only_and_source_pinned(tmp_path, fault):
    runtime, registry, result, payload = completed_corpus(tmp_path)
    workspace = result.report_path.parent
    inventory_path = workspace / "prediction-inventory.json"
    inventory_digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    coverage_digest = hashlib.sha256(result.report_path.read_bytes()).hexdigest()
    checkpoint = lambda: None
    if fault == "wrong_inventory_digest":
        inventory_digest = "0" * 64
    elif fault == "wrong_coverage_digest":
        coverage_digest = "0" * 64
    elif fault == "missing_page":
        next(workspace.glob("prediction-page-*.json")).unlink()
    elif fault == "source_append":
        from pathlib import Path
        from shared_wong_choi.evidence import EvidenceStore
        from shared_wong_choi.research_index import _Reader
        from shared_wong_choi.research_prediction_artifacts import _records
        root = Path(payload["evidence_root"])
        original = _records(root, Domain.AU, NOW, _Reader(lambda: None))[0][0]
        EvidenceStore(root).append(replace(original, record_id=f"{original.record_id}:new"))
    elif fault == "source_blob":
        from pathlib import Path
        from shared_wong_choi.research_index import _Reader
        from shared_wong_choi.research_prediction_artifacts import _records
        record = _records(Path(payload["evidence_root"]), Domain.AU, NOW, _Reader(lambda: None))[0][0]
        path = next(Path(a.path) for a in record.artifacts if a.path.endswith("Race_1_Logic.json"))
        path.write_text("changed bytes")
    elif fault == "domain":
        payload["domain"] = "hkjc"
    elif fault == "symlink":
        link = runtime.warm_root / "workspace-link"
        link.symlink_to(workspace, target_is_directory=True)
    elif fault == "interrupted":
        def checkpoint():
            raise RuntimeError("production preempted")
    before = {p.name: p.read_bytes() for p in workspace.iterdir()}
    call = dict(payload=payload, runtime=runtime, workspace=workspace,
                inventory_sha256=inventory_digest, coverage_sha256=coverage_digest, checkpoint=checkpoint)
    if fault == "symlink":
        call["workspace"] = link
    if fault:
        with pytest.raises((ValueError, OSError, RuntimeError)):
            reconcile_prediction_corpus(**call)
    else:
        reconciliation = reconcile_prediction_corpus(**call)
        assert reconciliation["status"] == "verified_existing_corpus"
        assert reconciliation["content_hash"] == result.content_hash
        assert reconciliation["retry_allowed"] is False
        assert reconciliation["model_promotion_allowed"] is False
    assert before == {p.name: p.read_bytes() for p in workspace.iterdir()}
    assert not registry.root.exists()
