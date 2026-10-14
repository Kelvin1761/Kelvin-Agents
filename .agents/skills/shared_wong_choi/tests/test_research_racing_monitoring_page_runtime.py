import fcntl
import hashlib
import json
from dataclasses import replace

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_evaluation import _write_report
from shared_wong_choi.research_index import ResearchIndexError, _hash
from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory
from shared_wong_choi.research_racing_settlement_inventory import freeze_racing_settlement_inventory
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_runner import ResearchDisposition
from test_research_racing_monitoring_samples import _au_source, _hkjc_source
from test_research_racing_settlement_page_runtime import payload
from test_research_supervision import source_runtime


def setup(tmp_path, domain):
    source = _au_source if domain is Domain.AU else _hkjc_source
    root, as_of, result = source(tmp_path)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    inventory_path = runtime.warm_root / "prediction-inventory.json"
    settlement_path = runtime.warm_root / "settlement-inventory.json"
    _write_report(inventory_path, freeze_prediction_inventory(root=root, domain=domain, as_of=as_of))
    _write_report(settlement_path, freeze_racing_settlement_inventory(root=root, domain=domain, as_of=as_of))
    options = dict(domain=domain, evidence_root=root, as_of=as_of,
                   inventory_path=inventory_path, settlement_inventory_path=settlement_path,
                   inventory_sha256=hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
                   settlement_inventory_sha256=hashlib.sha256(settlement_path.read_bytes()).hexdigest(),
                   page_index=0, estimated_bytes=1024, timeout_seconds=10)
    return runtime, registry, options, result


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_page_runtime_rebuilds_once_on_each_side_of_publication(tmp_path, monkeypatch, domain):
    import shared_wong_choi.research_racing_monitoring_pages as pages
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, _ = setup(tmp_path, domain)
    workspace = runtime.warm_root / "paired-publication-replay"
    workspace.mkdir()
    rebuild = pages._inspect_racing_monitoring_page_once
    writer = worker._write_report
    seen, published = [], []

    def traced(**kwargs):
        seen.append(bool(published))
        return rebuild(**kwargs)

    def publish(path, value, **kwargs):
        writer(path, value, **kwargs)
        if path.name.startswith("racing-monitoring-page-"):
            published.append(path)

    monkeypatch.setattr(pages, "_inspect_racing_monitoring_page_once", traced)
    monkeypatch.setattr(worker, "_inspect_racing_monitoring_page_once", traced, raising=False)
    monkeypatch.setattr(worker, "_write_report", publish)
    result = worker.run_racing_monitoring_page_request(
        {"payload": payload(options)}, runtime=runtime, workspace=workspace, checkpoint=lambda: None)
    assert result["disposition"] == "succeeded"
    assert seen == [False, True]
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_monitoring_page_keeps_qualified_join_without_corpus_authority(tmp_path, domain):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringPageInspectionRunner
    runtime, registry, options, _ = setup(tmp_path, domain)
    result = RacingMonitoringPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    assert report["monitoring_report"]["qualified_races"] == 1
    assert report["verified_monitoring_samples"] is None
    assert report["source_coverage_complete"] is False
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["production", "offline", "heavy_lock", "witness", "deadline"])
def test_monitoring_page_preserves_resource_and_input_guards(tmp_path, fault):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringPageInspectionRunner
    runtime, registry, options, _ = setup(tmp_path, Domain.AU)
    handle = None
    expected = ResearchDisposition.DEFERRED
    if fault == "production":
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        options["inventory_path"] = runtime.warm_root / "must-not-open"
    elif fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "offline")
    elif fault == "heavy_lock":
        lock = runtime.state_root / "locks/research-heavy-worker.lock"
        lock.parent.mkdir(parents=True)
        handle = lock.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif fault == "witness":
        options["settlement_inventory_sha256"] = "0" * 64
        expected = ResearchDisposition.FAILED
    else:
        options["timeout_seconds"] = 0.001
        expected = ResearchDisposition.TIMED_OUT
    try:
        result = RacingMonitoringPageInspectionRunner(runtime, registry).run(**options)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["promotion", "feature_hash", "unit_event", "missing_label"])
def test_monitoring_parent_rejects_rehashed_join_or_missing_companion(tmp_path, fault):
    from shared_wong_choi.research_racing_monitoring_page_runtime import (
        RacingMonitoringPageInspectionRunner, verify_racing_monitoring_page_receipt)
    runtime, registry, options, _ = setup(tmp_path, Domain.AU)
    result = RacingMonitoringPageInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    if fault == "promotion":
        report["model_promotion_allowed"] = True
    elif fault == "feature_hash":
        report["feature_page_hash"] = "0" * 64
    elif fault == "unit_event":
        nested = report["monitoring_report"]
        nested["units"][0]["event_id"] = "forged"
        nested["content_hash"] = _hash({k: v for k, v in nested.items() if k != "content_hash"})
    else:
        next(result.report_path.parent.glob("racing-settlement-page-*.json")).unlink()
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(report))
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        verify_racing_monitoring_page_receipt(payload=payload(options), runtime=runtime,
                                              report_path=result.report_path, receipt={"content_hash": report["content_hash"]})


@pytest.mark.parametrize("published", [False, True])
def test_monitoring_publication_failure_preserves_companions_without_success(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, _ = setup(tmp_path, Domain.AU)
    workspace = runtime.warm_root / "publication-fault"
    workspace.mkdir()
    writer = worker._write_report

    def failed(path, value, **kwargs):
        if published:
            writer(path, value, **kwargs)
        raise OSError("monitoring publication unacknowledged")

    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_monitoring_page_request({"payload": payload(options)}, runtime=runtime,
                                                  workspace=workspace, checkpoint=lambda: None)
    for prefix in ("prediction", "racing-feature", "racing-settlement"):
        assert len(list(workspace.glob(f"{prefix}-page-*.json"))) == 1
    assert len(list(workspace.glob("racing-monitoring-page-*.json"))) == int(published)
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_monitoring_source_changed_during_publication_is_not_acknowledged(tmp_path, monkeypatch, domain):
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, source = setup(tmp_path, domain)
    workspace = runtime.warm_root / "source-publication-fault"
    workspace.mkdir()
    writer = worker._write_report

    def changed(path, value, **kwargs):
        writer(path, value, **kwargs)
        source.write_text("changed during monitoring publication\n", encoding="utf-8")

    monkeypatch.setattr(worker, "_write_report", changed)
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        worker.run_racing_monitoring_page_request({"payload": payload(options)}, runtime=runtime,
                                                  workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("racing-monitoring-page-*.json"))) == 1
    assert not registry.root.exists()


def corpus_setup(tmp_path, domain):
    from test_research_racing_monitoring_pages import corpus
    source = _au_source if domain is Domain.AU else _hkjc_source
    options, _, result = corpus(tmp_path, domain, source)
    runtime, registry = source_runtime(tmp_path), ExperimentRegistry(tmp_path / "registry")
    arguments = dict(domain=domain, evidence_root=options["root"], as_of=options["as_of"],
                     max_records=1, estimated_bytes=1024, timeout_seconds=30)
    return runtime, registry, arguments, result


def corpus_payload(options):
    return {"domain": options["domain"].value, "evidence_root": str(options["evidence_root"]),
            "as_of": options["as_of"].isoformat(), "relocation_roots": [],
            "max_refs": 5000, "max_records": options["max_records"]}


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_monitoring_corpus_covers_three_native_pages(tmp_path, domain):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusInspectionRunner
    runtime, registry, options, _ = corpus_setup(tmp_path, domain)
    result = RacingMonitoringCorpusInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    assert report["qualified_races"] == 3
    assert report["verified_monitoring_samples"] == 3
    assert len(report["page_hashes"]) == 3
    assert report["page_coverage_complete"] is True
    assert report["model_promotion_allowed"] is False
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["missing_page", "forged_count", "promotion"])
def test_monitoring_corpus_parent_rejects_missing_or_false_complete_proof(tmp_path, fault):
    from shared_wong_choi.research_racing_monitoring_page_runtime import (
        RacingMonitoringCorpusInspectionRunner, verify_racing_monitoring_corpus_receipt)
    runtime, registry, options, _ = corpus_setup(tmp_path, Domain.AU)
    result = RacingMonitoringCorpusInspectionRunner(runtime, registry).run(**options)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    report = json.loads(result.report_path.read_text())
    if fault == "missing_page":
        next(result.report_path.parent.glob("racing-monitoring-page-*.json")).unlink()
    elif fault == "forged_count":
        report["verified_monitoring_samples"] += 1
    else:
        report["model_promotion_allowed"] = True
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    result.report_path.write_text(json.dumps(report))
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        verify_racing_monitoring_corpus_receipt(payload=corpus_payload(options), runtime=runtime,
                                                report_path=result.report_path, receipt={"content_hash": report["content_hash"]})


@pytest.mark.parametrize("published", [False, True])
def test_monitoring_corpus_final_publication_failure_never_acknowledges(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, _ = corpus_setup(tmp_path, Domain.AU)
    workspace = runtime.warm_root / "corpus-publication-fault"
    workspace.mkdir()
    writer = worker._write_report

    def failed(path, value, **kwargs):
        if path.name == "racing-monitoring-coverage.json":
            if published:
                writer(path, value, **kwargs)
            raise OSError("corpus publication unacknowledged")
        return writer(path, value, **kwargs)

    monkeypatch.setattr(worker, "_write_report", failed)
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_monitoring_corpus_request({"payload": corpus_payload(options)},
                                                   runtime=runtime, workspace=workspace, checkpoint=lambda: None)
    assert len(list(workspace.glob("racing-monitoring-page-*.json"))) == 3
    assert (workspace / "racing-monitoring-coverage.json").exists() is published
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_complete_monitoring_source_changed_at_final_publication_is_rejected(tmp_path, monkeypatch, domain):
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, source = corpus_setup(tmp_path, domain)
    workspace = runtime.warm_root / "complete-source-fault"
    workspace.mkdir()
    writer = worker._write_report

    def changed(path, value, **kwargs):
        writer(path, value, **kwargs)
        if path.name == "racing-monitoring-coverage.json":
            source.write_text("changed after final monitoring publication\n", encoding="utf-8")

    monkeypatch.setattr(worker, "_write_report", changed)
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        worker.run_racing_monitoring_corpus_request({"payload": corpus_payload(options)},
                                                   runtime=runtime, workspace=workspace, checkpoint=lambda: None)
    assert (workspace / "racing-monitoring-coverage.json").is_file()
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["production", "offline", "deadline"])
def test_complete_monitoring_resources_fail_before_success(tmp_path, fault):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusInspectionRunner
    runtime, registry, options, _ = corpus_setup(tmp_path, Domain.AU)
    handle = None
    expected = ResearchDisposition.DEFERRED
    if fault == "production":
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        options["evidence_root"] = tmp_path / "must-not-open"
    elif fault == "offline":
        runtime = replace(runtime, warm_root=tmp_path / "offline")
    else:
        options["timeout_seconds"] = 0.001
        expected = ResearchDisposition.TIMED_OUT
    try:
        result = RacingMonitoringCorpusInspectionRunner(runtime, registry).run(**options)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert not registry.root.exists()


def reconciliation_setup(tmp_path, domain):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusInspectionRunner
    runtime, registry, options, source = corpus_setup(tmp_path, domain)
    first = RacingMonitoringCorpusInspectionRunner(runtime, registry).run(**options)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first.status
    prior = first.report_path.parent
    witnesses = {key: hashlib.sha256((prior / name).read_bytes()).hexdigest() for key, name in (
        ("inventory_sha256", "prediction-inventory.json"),
        ("prediction_coverage_sha256", "prediction-coverage.json"),
        ("settlement_inventory_sha256", "settlement-inventory.json"),
        ("monitoring_coverage_sha256", "racing-monitoring-coverage.json"))}
    return runtime, registry, options, source, prior, witnesses


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_supervised_monitoring_reconciliation_preserves_prior_bytes_and_outcome(tmp_path, domain):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusReconciliationRunner
    runtime, registry, options, _, prior, witnesses = reconciliation_setup(tmp_path, domain)
    before = {path.name: path.read_bytes() for path in prior.iterdir() if path.is_file()}
    outcome = (prior.parent / "phase-outcome.json").read_bytes()
    result = RacingMonitoringCorpusReconciliationRunner(runtime, registry).run(
        **options, prior_workspace=prior, **witnesses)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    assert result.report_path.parent != prior
    assert {path.name: path.read_bytes() for path in result.report_path.parent.iterdir() if path.is_file()} == before
    assert {path.name: path.read_bytes() for path in prior.iterdir() if path.is_file()} == before
    assert (prior.parent / "phase-outcome.json").read_bytes() == outcome
    assert not registry.root.exists()


@pytest.mark.parametrize("fault", ["missing", "witness", "source", "production"])
def test_monitoring_reconciliation_does_not_repair_invalid_or_busy_prior(tmp_path, fault):
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusReconciliationRunner
    runtime, registry, options, source, prior, witnesses = reconciliation_setup(tmp_path, Domain.AU)
    expected, handle, requested_prior = ResearchDisposition.FAILED, None, prior
    if fault == "missing":
        next(prior.glob("racing-feature-page-*.json")).unlink()
    elif fault == "witness":
        witnesses["monitoring_coverage_sha256"] = "0" * 64
    elif fault == "source":
        source.write_text("changed after completed monitoring corpus\n", encoding="utf-8")
    else:
        expected = ResearchDisposition.DEFERRED
        handle = runtime.production_lock_paths[0].open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        requested_prior = runtime.warm_root / "must-not-open"
    before = {path.name: path.read_bytes() for path in prior.iterdir() if path.is_file()}
    try:
        result = RacingMonitoringCorpusReconciliationRunner(runtime, registry).run(
            **options, prior_workspace=requested_prior, **witnesses)
    finally:
        if handle:
            handle.close()
    assert result.disposition is expected and result.report_path is None
    assert {path.name: path.read_bytes() for path in prior.iterdir() if path.is_file()} == before
    assert not registry.root.exists()


@pytest.mark.parametrize("stage", ["prediction", "monitoring"])
def test_monitoring_reconciliation_pins_all_prior_bytes_before_source_replay(tmp_path, monkeypatch, stage):
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, _, prior, witnesses = reconciliation_setup(tmp_path, Domain.AU)
    name = "reconcile_prediction_corpus" if stage == "prediction" else "aggregate_racing_monitoring_pages"
    native = getattr(worker, name)

    def changed(**kwargs):
        report = native(**kwargs)
        path = next(prior.glob("racing-feature-page-*.json"))
        path.write_bytes(path.read_bytes() + b" ")
        return report

    monkeypatch.setattr(worker, name, changed)
    with pytest.raises((ValueError, ResearchIndexError)):
        worker.reconcile_racing_monitoring_corpus(payload=corpus_payload(options), runtime=runtime,
                                                  workspace=prior, **witnesses)


@pytest.mark.parametrize("published", [False, True])
def test_monitoring_reconciliation_copy_failure_preserves_prior_and_partial_attempt(tmp_path, monkeypatch, published):
    import shared_wong_choi.research_racing_monitoring_page_runtime as worker
    runtime, registry, options, _, prior, witnesses = reconciliation_setup(tmp_path, Domain.AU)
    before = {path.name: path.read_bytes() for path in prior.iterdir() if path.is_file()}
    outcome = (prior.parent / "phase-outcome.json").read_bytes()
    workspace = runtime.warm_root / "copy-publication-fault"
    workspace.mkdir()
    writer = worker._write_report

    def failed(path, value, **kwargs):
        if path.name.startswith("racing-feature-page-"):
            if published:
                writer(path, value, **kwargs)
            raise OSError("copy publication unacknowledged")
        return writer(path, value, **kwargs)

    monkeypatch.setattr(worker, "_write_report", failed)
    request = {"payload": {**corpus_payload(options), "prior_workspace": str(prior), **witnesses}}
    with pytest.raises(OSError, match="unacknowledged"):
        worker.run_racing_monitoring_corpus_reconciliation_request(request, runtime=runtime,
                                                                  workspace=workspace, checkpoint=lambda: None)
    assert {path.name: path.read_bytes() for path in prior.iterdir() if path.is_file()} == before
    assert (prior.parent / "phase-outcome.json").read_bytes() == outcome
    assert len(list(workspace.glob("racing-feature-page-*.json"))) == int(published)
    assert (workspace / "prediction-inventory.json").is_file()
    assert not registry.root.exists()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_large_monitoring_corpus_above_legacy_reference_limit_keeps_one_real_fixture_label(tmp_path, domain):
    from datetime import timedelta
    from shared_wong_choi.evidence import EvidenceStore
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusInspectionRunner
    from shared_wong_choi.research_racing_monitoring_samples import inspect_racing_monitoring_samples
    runtime, registry, options, _ = setup(tmp_path, domain)
    original = _records(options["evidence_root"], domain, options["as_of"], _Reader(lambda: None))[0][0]
    store = EvidenceStore(options["evidence_root"])
    # Only prediction metadata is cloned. No cloned settlements count as samples.
    for index in range(1, 1300):
        store.append(replace(original, record_id=f"{original.record_id}:copy-{index:05d}"))
    inventory = freeze_prediction_inventory(root=options["evidence_root"], domain=domain, as_of=options["as_of"])
    assert inventory["records_seen"] == 1300 and inventory["artifact_refs"] > 5000
    with pytest.raises(ValueError, match="reference limit"):
        inspect_racing_monitoring_samples(root=options["evidence_root"], domain=domain, as_of=options["as_of"])
    result = RacingMonitoringCorpusInspectionRunner(runtime, registry).run(
        domain=domain, evidence_root=options["evidence_root"], as_of=options["as_of"],
        estimated_bytes=128 * 1024 * 1024, timeout_seconds=600)
    assert result.disposition is ResearchDisposition.SUCCEEDED, result.status
    proof = json.loads(result.report_path.read_text())
    assert proof["qualified_races"] == proof["verified_monitoring_samples"] == 1
    assert proof["candidate_settlements"] == 1 and proof["blocked_settlements"] == 0
    assert proof["page_coverage_complete"] is True and len(proof["page_hashes"]) == 13
    prediction = json.loads((result.report_path.parent / "prediction-coverage.json").read_text())
    assert prediction["records_seen"] == 1300
    assert prediction["artifact_refs"] == inventory["artifact_refs"]
    assert len(list(result.report_path.parent.glob("racing-monitoring-page-*.json"))) == 13
    assert proof["model_promotion_allowed"] is False and not registry.root.exists()
    # The report is not enough: the actual review child must replay all 13 pages,
    # and the parent must verify their bounded companions without the old cap.
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from test_research_index import fixture as registry_fixture
    registry = registry_fixture(tmp_path)
    before = {path.name: path.read_bytes() for path in result.report_path.parent.iterdir() if path.is_file()}
    review = ResearchReviewRunner(runtime, registry).run(
        domain=domain, window_start=options["as_of"] - timedelta(minutes=1),
        now=options["as_of"], ruler_digest="1" * 64,
        ruler_released_at=options["as_of"] - timedelta(days=30),
        estimated_bytes=128 * 1024 * 1024, timeout_seconds=600,
        racing_sample_report=result.report_path, previous_racing_sample_report=result.report_path,
        racing_sample_evidence_root=options["evidence_root"])
    assert review.disposition is ResearchDisposition.SUCCEEDED, review.status
    summary = json.loads(review.report_path.read_text())
    assert summary["racing_sample_current"]["scope_counts"] == {"all": 1}
    assert summary["racing_sample_previous"] == summary["racing_sample_current"]
    assert summary["sample_growth_observed"] is False
    assert summary["model_promotion_allowed"] is False
    assert {path.name: path.read_bytes() for path in result.report_path.parent.iterdir() if path.is_file()} == before
