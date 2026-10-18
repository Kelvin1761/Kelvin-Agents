import fcntl
import hashlib
import json
from dataclasses import replace

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_evaluation import _write_report
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory
from shared_wong_choi.research_racing_feature_page_runtime import (
    RacingFeaturePageInspectionRunner, verify_racing_feature_page_receipt,
)
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import ResearchDisposition
import test_research_au_feature_provenance as au
import test_research_hkjc_feature_provenance as hk
from test_research_supervision import source_runtime


def setup(tmp_path, domain, mode="valid"):
    native = au if domain is Domain.AU else hk
    value = native.fixture(tmp_path, mode)
    root = value if domain is Domain.AU else value[0]
    runtime = source_runtime(tmp_path)
    inventory = freeze_prediction_inventory(root=root, domain=domain, as_of=native.AS_OF)
    path = runtime.warm_root / "inventory.json"
    _write_report(path, inventory)
    options = dict(domain=domain, evidence_root=root, as_of=native.AS_OF,
                   inventory_path=path, inventory_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   page_index=0, estimated_bytes=1024, timeout_seconds=10)
    registry = ExperimentRegistry(tmp_path / "registry")
    return runtime, registry, options


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_feature_page_keeps_native_proof_without_sample_authority(tmp_path, domain):
    runtime, registry, options = setup(tmp_path, domain)
    result = RacingFeaturePageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    assert report["feature_report"]["feature_availability_verified"] is True
    assert report["source_coverage_complete"] is False and report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False
    assert len(list(result.report_path.parent.glob("prediction-page-*.json"))) == 1
    assert not registry.root.exists()


def test_feature_page_production_defer_does_not_open_inventory(tmp_path):
    runtime, registry, options = setup(tmp_path, Domain.AU)
    handle = runtime.production_lock_paths[0].open("a")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    options["inventory_path"] = runtime.warm_root / "must-not-read"
    try:
        result = RacingFeaturePageInspectionRunner(runtime, registry).run(**options)
    finally:
        handle.close()
    assert result.disposition is ResearchDisposition.DEFERRED
    assert result.attempt_path is None


@pytest.mark.parametrize("fault", ["promotion", "records", "prediction_hash", "availability", "missing_prediction"])
def test_parent_rejects_rehashed_or_missing_feature_page_bindings(tmp_path, fault):
    runtime, registry, options = setup(tmp_path, Domain.AU, "legacy")
    result = RacingFeaturePageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    if fault == "promotion":
        report["model_promotion_allowed"] = True
    elif fault == "records":
        report["feature_report"]["records"] = []
    elif fault == "prediction_hash":
        report["prediction_page_hash"] = "0" * 64
    elif fault == "availability":
        report["feature_report"]["feature_availability_verified"] = True
    else:
        next(result.report_path.parent.glob("prediction-page-*.json")).unlink()
    feature = report["feature_report"]
    feature["content_hash"] = _hash({k: v for k, v in feature.items() if k != "content_hash"})
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(report))
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "inventory_path": str(options["inventory_path"]),
               "inventory_sha256": options["inventory_sha256"], "page_index": 0,
               "max_refs": 5000, "max_records": 100, "relocation_roots": []}
    with pytest.raises((ValueError, OSError)):
        verify_racing_feature_page_receipt(payload=payload, runtime=runtime,
                                          report_path=result.report_path, receipt={"content_hash": report["content_hash"]})


@pytest.mark.parametrize("fault", ["digest", "outside_warm", "offline", "deadline", "heavy_lock"])
def test_feature_page_resource_or_input_failure_never_returns_success(tmp_path, fault):
    runtime, registry, options = setup(tmp_path, Domain.AU)
    expected = ResearchDisposition.FAILED
    handle = None
    if fault == "digest":
        options["inventory_sha256"] = "0" * 64
    elif fault == "outside_warm":
        path = tmp_path / "outside.json"
        path.write_bytes(options["inventory_path"].read_bytes())
        options["inventory_path"] = path
    elif fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "offline")
        expected = ResearchDisposition.DEFERRED
    elif fault == "deadline":
        options["timeout_seconds"] = 0.001
        expected = ResearchDisposition.TIMED_OUT
    else:
        lock = runtime.state_root / "locks/research-heavy-worker.lock"
        lock.parent.mkdir(parents=True)
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        expected = ResearchDisposition.DEFERRED
    try:
        result = RacingFeaturePageInspectionRunner(runtime, registry).run(**options)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected
    assert result.report_path is None
    assert not registry.root.exists()


@pytest.mark.parametrize("published", [False, True])
def test_feature_publication_failure_is_uncertain_not_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_feature_page_runtime as worker
    runtime, registry, options = setup(tmp_path, Domain.AU)
    workspace = runtime.warm_root / "fault-attempt"
    workspace.mkdir()
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "inventory_path": str(options["inventory_path"]),
               "inventory_sha256": options["inventory_sha256"], "page_index": 0,
               "max_refs": 5000, "max_records": 100, "relocation_roots": []}
    writer = worker._write_report
    def failed(path, value, **kwargs):
        if path.name.startswith("racing-feature-page-"):
            if published:
                writer(path, value, **kwargs)
            raise OSError("feature publication unacknowledged")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_feature_page_request({"payload": payload}, runtime=runtime,
                                               workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("prediction-page-*.json"))) == 1
    assert len(list(workspace.glob("racing-feature-page-*.json"))) == int(published)
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_feature_page_at_record_bound_preserves_every_record(tmp_path, domain):
    from shared_wong_choi.evidence import EvidenceStore
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    runtime, registry, options = setup(tmp_path, domain)
    root = options["evidence_root"]
    original = _records(root, domain, options["as_of"], _Reader(lambda: None))[0][0]
    for index in range(1, 100):
        EvidenceStore(root).append(replace(original, record_id=f"{original.record_id}:copy-{index:05d}"))
    inventory = freeze_prediction_inventory(root=root, domain=domain, as_of=options["as_of"])
    path = runtime.warm_root / "complete-inventory.json"
    _write_report(path, inventory)
    options.update(inventory_path=path, inventory_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    result = RacingFeaturePageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    feature = json.loads(result.report_path.read_text())["feature_report"]
    assert feature["records_seen"] == feature["verified_feature_entries"] == 100
    assert len({r["record_id"] for r in feature["records"]}) == 100
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_feature_corpus_covers_every_page_without_sample_authority(tmp_path, domain):
    from shared_wong_choi.research_racing_feature_page_runtime import RacingFeatureCorpusInspectionRunner
    from shared_wong_choi.evidence import EvidenceStore
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    runtime, registry, options = setup(tmp_path, domain)
    root = options["evidence_root"]
    original = _records(root, domain, options["as_of"], _Reader(lambda: None))[0][0]
    for index in range(1, 3):
        EvidenceStore(root).append(replace(original, record_id=f"{original.record_id}:copy-{index:05d}"))
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    result = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus, max_records=1)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    proof = json.loads(result.report_path.read_text())
    assert proof["page_coverage_complete"] is True and proof["records_seen"] == 3
    assert len(proof["page_hashes"]) == 3
    assert proof["verified_feature_entries"] == 3
    assert proof["verified_monitoring_samples"] is None and proof["model_promotion_allowed"] is False
    assert len(list(result.report_path.parent.glob("racing-feature-page-*.json"))) == 3
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["missing", "count", "promotion", "omitted"])
def test_feature_corpus_parent_rejects_incomplete_or_rehashed_authority(tmp_path, fault):
    from shared_wong_choi.research_racing_feature_page_runtime import (
        RacingFeatureCorpusInspectionRunner, verify_racing_feature_corpus_receipt,
    )
    runtime, registry, options = setup(tmp_path, Domain.AU)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    result = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    proof = json.loads(result.report_path.read_text())
    if fault == "missing":
        next(result.report_path.parent.glob("racing-feature-page-*.json")).unlink()
    elif fault == "count":
        proof["verified_feature_entries"] += 1
    elif fault == "promotion":
        proof["model_promotion_allowed"] = True
    else:
        proof["page_hashes"] = []
    proof["content_hash"] = _hash({k: v for k, v in proof.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(proof))
    payload = {"domain": "au", "evidence_root": str(corpus["evidence_root"]),
               "as_of": corpus["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    with pytest.raises((ValueError, OSError)):
        verify_racing_feature_corpus_receipt(payload=payload, runtime=runtime,
                                             report_path=result.report_path, receipt={"content_hash": proof["content_hash"]})


@pytest.mark.parametrize("published", [False, True])
def test_feature_corpus_coverage_publication_failure_never_acknowledges_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_feature_page_runtime as worker
    runtime, registry, options = setup(tmp_path, Domain.AU)
    workspace = runtime.warm_root / "corpus-fault-attempt"
    workspace.mkdir()
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    writer = worker._write_report
    def failed(path, value, **kwargs):
        if path.name == "racing-feature-coverage.json":
            if published:
                writer(path, value, **kwargs)
            raise OSError("coverage publication unacknowledged")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_feature_corpus_request({"payload": payload}, runtime=runtime,
                                                 workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("racing-feature-page-*.json"))) == 1
    assert (workspace / "racing-feature-coverage.json").exists() is published
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_feature_corpus_reconciliation_rebuilds_sources_without_mutating_prior(tmp_path, domain):
    from shared_wong_choi.research_racing_feature_page_runtime import (
        RacingFeatureCorpusInspectionRunner, reconcile_racing_feature_corpus,
    )
    runtime, registry, options = setup(tmp_path, domain)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    result = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    workspace = result.report_path.parent
    before = {p.name: p.read_bytes() for p in workspace.iterdir() if p.is_file()}
    payload = {"domain": domain.value, "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    proof = reconcile_racing_feature_corpus(
        payload=payload, runtime=runtime, workspace=workspace,
        inventory_sha256=hashlib.sha256(before["prediction-inventory.json"]).hexdigest(),
        prediction_coverage_sha256=hashlib.sha256(before["prediction-coverage.json"]).hexdigest(),
        feature_coverage_sha256=hashlib.sha256(before["racing-feature-coverage.json"]).hexdigest(),
    )
    assert proof["content_hash"] == result.content_hash
    assert proof["retry_allowed"] is False and proof["model_promotion_allowed"] is False
    assert {p.name: p.read_bytes() for p in workspace.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("fault", ["witness", "missing", "source_append"])
def test_feature_corpus_reconciliation_rejects_missing_changed_or_unpinned_sources(tmp_path, fault):
    from shared_wong_choi.research_racing_feature_page_runtime import (
        RacingFeatureCorpusInspectionRunner, reconcile_racing_feature_corpus,
    )
    from shared_wong_choi.evidence import EvidenceStore
    from shared_wong_choi.research_index import _Reader, ResearchIndexError
    from shared_wong_choi.research_prediction_artifacts import _records
    runtime, registry, options = setup(tmp_path, Domain.AU)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    result = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    workspace = result.report_path.parent
    witnesses = {key: hashlib.sha256((workspace / name).read_bytes()).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("feature_coverage_sha256", "racing-feature-coverage.json"))}
    if fault == "witness":
        witnesses["feature_coverage_sha256"] = "0" * 64
    elif fault == "missing":
        next(workspace.glob("racing-feature-page-*.json")).unlink()
    else:
        original = _records(options["evidence_root"], Domain.AU, options["as_of"], _Reader(lambda: None))[0][0]
        EvidenceStore(options["evidence_root"]).append(replace(original, record_id=original.record_id + ":new"))
    before = {p.name: p.read_bytes() for p in workspace.iterdir() if p.is_file()}
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        reconcile_racing_feature_corpus(payload=payload, runtime=runtime, workspace=workspace, **witnesses)
    assert {p.name: p.read_bytes() for p in workspace.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("stage", ["prediction", "feature"])
def test_feature_reconciliation_rejects_prediction_proof_change_during_feature_rebuild(tmp_path, monkeypatch, stage):
    import shared_wong_choi.research_racing_feature_page_runtime as worker
    from shared_wong_choi.research_index import ResearchIndexError
    runtime, registry, options = setup(tmp_path, Domain.AU)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    result = worker.RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    workspace = result.report_path.parent
    witnesses = {key: hashlib.sha256((workspace / name).read_bytes()).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("feature_coverage_sha256", "racing-feature-coverage.json"))}
    name = "aggregate_racing_feature_pages" if stage == "feature" else "reconcile_prediction_corpus"
    aggregate = getattr(worker, name)
    def changed(**kwargs):
        proof = aggregate(**kwargs)
        path = next(workspace.glob("prediction-page-*.json"))
        path.write_bytes(path.read_bytes() + b" ")
        return proof
    monkeypatch.setattr(worker, name, changed)
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000, "max_records": 100}
    with pytest.raises((ValueError, ResearchIndexError)):
        worker.reconcile_racing_feature_corpus(payload=payload, runtime=runtime, workspace=workspace, **witnesses)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_feature_reconciliation_creates_new_attempt_preserving_prior(tmp_path, domain):
    from shared_wong_choi.research_racing_feature_page_runtime import (
        RacingFeatureCorpusInspectionRunner, RacingFeatureCorpusReconciliationRunner,
    )
    runtime, registry, options = setup(tmp_path, domain)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    first = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first.status
    prior = first.report_path.parent
    before = {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()}
    witnesses = {key: hashlib.sha256(before[name]).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("feature_coverage_sha256", "racing-feature-coverage.json"))}
    result = RacingFeatureCorpusReconciliationRunner(runtime, registry).run(
        **corpus, prior_workspace=prior, **witnesses)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    assert result.report_path.parent != prior and result.content_hash == first.content_hash
    assert result.report_path.read_bytes() == first.report_path.read_bytes()
    assert {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()} == before
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["production", "offline", "heavy_lock", "witness", "deadline"])
def test_supervised_feature_reconciliation_respects_resource_and_byte_witness_guards(tmp_path, fault):
    from shared_wong_choi.research_racing_feature_page_runtime import (
        RacingFeatureCorpusInspectionRunner, RacingFeatureCorpusReconciliationRunner,
    )
    runtime, registry, options = setup(tmp_path, Domain.AU)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    first = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first.status
    prior = first.report_path.parent
    before = {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()}
    witnesses = {key: hashlib.sha256(before[name]).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("feature_coverage_sha256", "racing-feature-coverage.json"))}
    expected, handle = ResearchDisposition.DEFERRED, None
    if fault == "production":
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = runtime.warm_root / "must-not-open"
    elif fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "offline")
    elif fault == "heavy_lock":
        lock = runtime.state_root / "locks/research-heavy-worker.lock"
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == "witness":
        witnesses["feature_coverage_sha256"] = "0" * 64
        expected = ResearchDisposition.FAILED
    else:
        corpus["timeout_seconds"] = 0.001
        expected = ResearchDisposition.TIMED_OUT
    try:
        result = RacingFeatureCorpusReconciliationRunner(runtime, registry).run(
            **corpus, prior_workspace=prior, **witnesses)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert {p.name: p.read_bytes() for p in first.report_path.parent.iterdir() if p.is_file()} == before
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_feature_corpus_above_legacy_reference_limit_covers_all_records(tmp_path, domain):
    from shared_wong_choi.evidence import EvidenceStore
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    from shared_wong_choi.research_racing_feature_page_runtime import RacingFeatureCorpusInspectionRunner
    runtime, registry, options = setup(tmp_path, domain)
    original = _records(options["evidence_root"], domain, options["as_of"], _Reader(lambda: None))[0][0]
    store = EvidenceStore(options["evidence_root"])
    for index in range(1, 1300):
        store.append(replace(original, record_id=f"{original.record_id}:copy-{index:05d}"))
    inventory = freeze_prediction_inventory(root=options["evidence_root"], domain=domain, as_of=options["as_of"])
    assert inventory["artifact_refs"] > 5000
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    corpus.update(estimated_bytes=64 * 1024 * 1024, timeout_seconds=240)
    result = RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    proof = json.loads(result.report_path.read_text())
    assert proof["records_seen"] == proof["verified_feature_entries"] == 1300
    assert proof["page_coverage_complete"] is True and len(proof["page_hashes"]) == 13
    assert proof["verified_monitoring_samples"] is None and proof["model_promotion_allowed"] is False
    prediction = json.loads((result.report_path.parent / "prediction-coverage.json").read_text())
    assert prediction["artifact_refs"] == inventory["artifact_refs"]
    assert len(list(result.report_path.parent.glob("racing-feature-page-*.json"))) == 13
    assert not registry.root.exists()


@pytest.mark.parametrize("published", [False, True])
def test_feature_reconciliation_copy_fault_keeps_prior_and_never_acknowledges_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_feature_page_runtime as worker
    runtime, registry, options = setup(tmp_path, Domain.AU)
    corpus = {k: v for k, v in options.items() if k not in {"inventory_path", "inventory_sha256", "page_index"}}
    first = worker.RacingFeatureCorpusInspectionRunner(runtime, registry).run(**corpus)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first.status
    prior = first.report_path.parent
    before = {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()}
    witnesses = {key: hashlib.sha256(before[name]).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("feature_coverage_sha256", "racing-feature-coverage.json"))}
    payload = {"domain": "au", "evidence_root": str(options["evidence_root"]),
               "as_of": options["as_of"].isoformat(), "relocation_roots": [], "max_refs": 5000,
               "max_records": 100, "prior_workspace": str(prior), **witnesses}
    workspace = runtime.warm_root / "reconciliation-copy-fault"
    workspace.mkdir()
    writer = worker._write_report
    def failed(path, value, **kwargs):
        if path.name.startswith("racing-feature-page-"):
            if published:
                writer(path, value, **kwargs)
            raise OSError("copy publication unacknowledged")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_feature_corpus_reconciliation_request(
            {"payload": payload}, runtime=runtime, workspace=workspace, checkpoint=lambda: None)
    assert {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()} == before
    assert len(list(workspace.glob("racing-feature-page-*.json"))) == int(published)
    assert not registry.root.exists()
