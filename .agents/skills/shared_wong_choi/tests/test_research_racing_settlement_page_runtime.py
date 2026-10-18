import hashlib
import json
import fcntl
from dataclasses import replace
from pathlib import Path

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_evaluation import _write_report
from shared_wong_choi.research_racing_settlement_page_runtime import RacingSettlementPageInspectionRunner
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import ResearchDisposition
from shared_wong_choi.research_index import _hash, ResearchIndexError
from test_research_racing_settlement_pages import setup as native_setup
from test_research_supervision import source_runtime


def setup(tmp_path, domain, count=1):
    _, native, _ = native_setup(tmp_path, domain, count=count)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    paths = {"inventory": runtime.warm_root / "prediction-inventory.json",
             "settlement_inventory": runtime.warm_root / "settlement-inventory.json"}
    for key, path in paths.items():
        _write_report(path, native[key])
    options = dict(domain=domain, evidence_root=native["root"], as_of=native["as_of"],
                   inventory_path=paths["inventory"], settlement_inventory_path=paths["settlement_inventory"],
                   inventory_sha256=hashlib.sha256(paths["inventory"].read_bytes()).hexdigest(),
                   settlement_inventory_sha256=hashlib.sha256(paths["settlement_inventory"].read_bytes()).hexdigest(),
                   page_index=0, estimated_bytes=1024, timeout_seconds=10)
    return runtime, registry, options


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_label_page_binds_prediction_and_complete_settlement_inventory(tmp_path, domain):
    runtime, registry, options = setup(tmp_path, domain)
    result = RacingSettlementPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    assert report["settlement_report"]["label_verified_settlements"] == 1
    assert report["settlement_inventory_hash"] == json.loads(options["settlement_inventory_path"].read_text())["content_hash"]
    assert report["verified_monitoring_samples"] is None and report["model_promotion_allowed"] is False
    assert len(list(result.report_path.parent.glob("prediction-page-*.json"))) == 1
    assert not registry.root.exists()


def payload(options):
    return {"domain": options["domain"].value, "evidence_root": str(options["evidence_root"]),
            "as_of": options["as_of"].isoformat(), "inventory_path": str(options["inventory_path"]),
            "inventory_sha256": options["inventory_sha256"], "page_index": options["page_index"],
            "settlement_inventory_path": str(options["settlement_inventory_path"]),
            "settlement_inventory_sha256": options["settlement_inventory_sha256"],
            "relocation_roots": [], "max_refs": 5000, "max_records": 100}


@pytest.mark.parametrize("fault", ["production", "offline", "heavy_lock", "witness", "outside_warm", "deadline"])
def test_label_page_resource_or_input_failure_never_returns_success(tmp_path, fault):
    runtime, registry, options = setup(tmp_path, Domain.AU)
    expected, handle = ResearchDisposition.DEFERRED, None
    if fault == "production":
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        options["settlement_inventory_path"] = runtime.warm_root / "must-not-open"
    elif fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "offline")
    elif fault == "heavy_lock":
        lock = runtime.state_root / "locks/research-heavy-worker.lock"
        lock.parent.mkdir(parents=True)
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == "witness":
        expected = ResearchDisposition.FAILED
        options["settlement_inventory_sha256"] = "0" * 64
    elif fault == "outside_warm":
        expected = ResearchDisposition.FAILED
        path = tmp_path / "settlement-inventory.json"
        path.write_bytes(options["settlement_inventory_path"].read_bytes())
        options["settlement_inventory_path"] = path
    else:
        expected = ResearchDisposition.TIMED_OUT
        options["timeout_seconds"] = 0.001
    try:
        result = RacingSettlementPageInspectionRunner(runtime, registry).run(**options)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["promotion", "inventory_hash", "candidates", "missing_prediction"])
def test_label_page_parent_rejects_rehashed_or_missing_bindings(tmp_path, fault):
    from shared_wong_choi.research_racing_settlement_page_runtime import verify_racing_settlement_page_receipt
    runtime, registry, options = setup(tmp_path, Domain.AU)
    result = RacingSettlementPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    if fault == "promotion":
        report["model_promotion_allowed"] = True
    elif fault == "inventory_hash":
        report["settlement_inventory_hash"] = "0" * 64
    elif fault == "candidates":
        report["settlement_report"]["candidates"] = []
        nested = report["settlement_report"]
        nested["content_hash"] = _hash({k: v for k, v in nested.items() if k != "content_hash"})
    else:
        next(result.report_path.parent.glob("prediction-page-*.json")).unlink()
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(report))
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        verify_racing_settlement_page_receipt(payload=payload(options), runtime=runtime,
                                              report_path=result.report_path, receipt={"content_hash": report["content_hash"]})


@pytest.mark.parametrize("published", [False, True])
def test_label_page_publication_failure_preserves_partial_proofs_without_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_settlement_page_runtime as worker
    runtime, registry, options = setup(tmp_path, Domain.AU)
    workspace = runtime.warm_root / "fault-attempt"
    workspace.mkdir()
    writer = worker._write_report
    def failed(path, value, **kwargs):
        if path.name.startswith("racing-settlement-page-"):
            if published:
                writer(path, value, **kwargs)
            raise OSError("label publication unacknowledged")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_settlement_page_request({"payload": payload(options)}, runtime=runtime,
                                                  workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("prediction-page-*.json"))) == 1
    assert len(list(workspace.glob("racing-settlement-page-*.json"))) == int(published)
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_label_source_changed_during_publication_is_not_acknowledged(tmp_path, domain, monkeypatch):
    import shared_wong_choi.research_racing_settlement_page_runtime as worker
    runtime, registry, options = setup(tmp_path, domain)
    workspace = runtime.warm_root / "source-change-attempt"
    workspace.mkdir()
    writer = worker._write_report
    def changed(path, value, **kwargs):
        writer(path, value, **kwargs)
        if path.name.startswith("racing-settlement-page-"):
            source = Path(value["settlement_report"]["candidates"][0]["referenced_result_artifact"])
            source.write_text("changed during proof publication")
    monkeypatch.setattr(worker, "_write_report", changed)
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        worker.run_racing_settlement_page_request({"payload": payload(options)}, runtime=runtime,
                                                  workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("racing-settlement-page-*.json"))) == 1
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_label_corpus_preserves_every_page_and_native_settlement(tmp_path, domain):
    from shared_wong_choi.research_racing_settlement_page_runtime import RacingSettlementCorpusInspectionRunner
    runtime, registry, options = setup(tmp_path, domain, count=3)
    result = RacingSettlementCorpusInspectionRunner(runtime, registry).run(
        domain=domain, evidence_root=options["evidence_root"], as_of=options["as_of"],
        estimated_bytes=1024, timeout_seconds=10, max_records=1)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    proof = json.loads(result.report_path.read_text())
    assert proof["page_coverage_complete"] is True and proof["settlements_seen"] == 3
    assert len(proof["page_hashes"]) == proof["label_verified_settlements"] == 3
    assert proof["verified_monitoring_samples"] is None and proof["model_promotion_allowed"] is False
    assert len(list(result.report_path.parent.glob("racing-settlement-page-*.json"))) == 3
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["missing", "count", "promotion"])
def test_label_corpus_parent_rejects_incomplete_or_rehashed_final_coverage(tmp_path, fault):
    from shared_wong_choi.research_racing_settlement_page_runtime import (
        RacingSettlementCorpusInspectionRunner, verify_racing_settlement_corpus_receipt,
    )
    runtime, registry, options = setup(tmp_path, Domain.AU)
    result = RacingSettlementCorpusInspectionRunner(runtime, registry).run(
        domain=Domain.AU, evidence_root=options["evidence_root"], as_of=options["as_of"],
        estimated_bytes=1024, timeout_seconds=10)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    proof = json.loads(result.report_path.read_text())
    if fault == "missing":
        next(result.report_path.parent.glob("racing-settlement-page-*.json")).unlink()
    elif fault == "count":
        proof["label_verified_settlements"] += 1
    else:
        proof["model_promotion_allowed"] = True
    proof["content_hash"] = _hash({k: v for k, v in proof.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(proof))
    base = {k: v for k, v in payload(options).items() if k in {
        "domain", "evidence_root", "as_of", "relocation_roots", "max_refs", "max_records"}}
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        verify_racing_settlement_corpus_receipt(payload=base, runtime=runtime,
                                                report_path=result.report_path, receipt={"content_hash": proof["content_hash"]})


@pytest.mark.parametrize("published", [False, True])
def test_label_corpus_final_publication_failure_never_acknowledges_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_settlement_page_runtime as worker
    runtime, registry, options = setup(tmp_path, Domain.AU)
    workspace = runtime.warm_root / "corpus-publication-fault"
    workspace.mkdir()
    base = {k: v for k, v in payload(options).items() if k in {
        "domain", "evidence_root", "as_of", "relocation_roots", "max_refs", "max_records"}}
    writer = worker._write_report
    def failed(path, value, **kwargs):
        if path.name == "racing-settlement-coverage.json":
            if published:
                writer(path, value, **kwargs)
            raise OSError("final coverage publication unacknowledged")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_settlement_corpus_request({"payload": base}, runtime=runtime,
                                                    workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("racing-settlement-page-*.json"))) == 1
    assert (workspace / "racing-settlement-coverage.json").exists() is published
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_label_corpus_reconciliation_preserves_prior_and_copies_complete_proofs(tmp_path, domain):
    from shared_wong_choi.research_racing_settlement_page_runtime import (
        RacingSettlementCorpusInspectionRunner, RacingSettlementCorpusReconciliationRunner,
    )
    runtime, registry, options = setup(tmp_path, domain, count=3)
    corpus = dict(domain=domain, evidence_root=options["evidence_root"], as_of=options["as_of"],
                  estimated_bytes=1024, timeout_seconds=10, max_records=1)
    first = RacingSettlementCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first.status
    prior = first.report_path.parent
    before = {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()}
    outcome_path = prior.parent / "phase-outcome.json"
    outcome_before = outcome_path.read_bytes()
    witnesses = {key: hashlib.sha256(before[name]).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("settlement_inventory_sha256", "settlement-inventory.json"),
        ("label_coverage_sha256", "racing-settlement-coverage.json"))}
    result = RacingSettlementCorpusReconciliationRunner(runtime, registry).run(
        **corpus, prior_workspace=prior, **witnesses)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    assert result.report_path.parent != prior and result.content_hash == first.content_hash
    assert result.report_path.read_bytes() == first.report_path.read_bytes()
    assert len(list(result.report_path.parent.glob("racing-settlement-page-*.json"))) == 3
    assert {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()} == before
    assert outcome_path.read_bytes() == outcome_before
    assert not registry.root.exists()


def reconciliation_setup(tmp_path):
    from shared_wong_choi.research_racing_settlement_page_runtime import RacingSettlementCorpusInspectionRunner
    runtime, registry, options = setup(tmp_path, Domain.AU)
    corpus = dict(domain=Domain.AU, evidence_root=options["evidence_root"], as_of=options["as_of"],
                  estimated_bytes=1024, timeout_seconds=10)
    first = RacingSettlementCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first.status
    prior = first.report_path.parent
    witnesses = {key: hashlib.sha256((prior / name).read_bytes()).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("settlement_inventory_sha256", "settlement-inventory.json"),
        ("label_coverage_sha256", "racing-settlement-coverage.json"))}
    return runtime, registry, corpus, prior, witnesses


@pytest.mark.parametrize("fault", ["missing", "witness", "source", "production"])
def test_label_reconciliation_rejects_invalid_or_busy_prior_without_repair(tmp_path, fault):
    from shared_wong_choi.research_racing_settlement_page_runtime import RacingSettlementCorpusReconciliationRunner
    runtime, registry, corpus, prior, witnesses = reconciliation_setup(tmp_path)
    expected, handle, requested_prior = ResearchDisposition.FAILED, None, prior
    if fault == "missing":
        next(prior.glob("racing-settlement-page-*.json")).unlink()
    elif fault == "witness":
        witnesses["settlement_inventory_sha256"] = "0" * 64
    elif fault == "source":
        report = json.loads(next(prior.glob("racing-settlement-page-*.json")).read_text())
        Path(report["settlement_report"]["candidates"][0]["referenced_result_artifact"]).write_text("changed source")
    else:
        expected = ResearchDisposition.DEFERRED
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        requested_prior = runtime.warm_root / "must-not-read"
    before = {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()}
    try:
        result = RacingSettlementCorpusReconciliationRunner(runtime, registry).run(
            **corpus, prior_workspace=requested_prior, **witnesses)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()} == before
    assert not registry.root.exists()


@pytest.mark.parametrize("stage", ["prediction", "label"])
def test_label_reconciliation_pins_prediction_proof_across_all_source_reconstruction(tmp_path, stage, monkeypatch):
    import shared_wong_choi.research_racing_settlement_page_runtime as worker
    runtime, registry, corpus, prior, witnesses = reconciliation_setup(tmp_path)
    name = "reconcile_prediction_corpus" if stage == "prediction" else "aggregate_racing_settlement_pages"
    original = getattr(worker, name)
    def changed(**kwargs):
        report = original(**kwargs)
        path = next(prior.glob("prediction-page-*.json"))
        path.write_bytes(path.read_bytes() + b" ")
        return report
    monkeypatch.setattr(worker, name, changed)
    base = {"domain": "au", "evidence_root": str(corpus["evidence_root"]),
            "as_of": corpus["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    with pytest.raises((ValueError, ResearchIndexError)):
        worker.reconcile_racing_settlement_corpus(payload=base, runtime=runtime, workspace=prior, **witnesses)
