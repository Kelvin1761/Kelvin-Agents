"""Consumer boundary tests; mocked replay is not native corpus acceptance."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared_wong_choi.research_index import ResearchIndexError, _hash


def inputs(tmp_path):
    from shared_wong_choi.research_racing_monitoring_pages import COVERAGE_SCHEMA
    workspace = tmp_path / "research-phases/au/racing-monitoring-corpus-test/attempt-1"
    workspace.mkdir(parents=True)
    report = dict(schema_version=COVERAGE_SCHEMA, domain="au", root=str(tmp_path / "source"),
                  as_of="2026-10-10T00:00:00+00:00", relocation_roots=[], max_refs=5000,
                  max_records=100, units=[{"unit_id": "fixture:race:1"}],
                  verified_monitoring_samples=1, source_coverage_complete=True,
                  page_coverage_complete=True, model_promotion_allowed=False)
    report["content_hash"] = _hash(report)
    path = workspace / "racing-monitoring-coverage.json"
    path.write_text(json.dumps(report))
    for name in ("prediction-inventory.json", "prediction-coverage.json", "settlement-inventory.json"):
        (workspace / name).write_text("{}")
    return path, report, SimpleNamespace(warm_root=tmp_path)


def test_paged_consumer_must_replay_source_before_snapshot(tmp_path, monkeypatch):
    from shared_wong_choi.research_monitoring_samples import source_reverified_paged_monitoring_samples
    import shared_wong_choi.research_racing_monitoring_page_runtime as runtime_module
    path, report, runtime = inputs(tmp_path)
    calls = []

    def replay(**kwargs):
        calls.append(kwargs)
        return {"content_hash": report["content_hash"], "verified_monitoring_samples": 1}

    monkeypatch.setattr(runtime_module, "reconcile_racing_monitoring_corpus", replay)
    samples = source_reverified_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)
    assert len(calls) == 1
    assert samples[0].unit_ids == frozenset({"fixture:race:1"})
    assert calls[0]["workspace"] == path.parent


def test_paged_consumer_propagates_source_replay_failure(tmp_path, monkeypatch):
    from shared_wong_choi.research_monitoring_samples import source_reverified_paged_monitoring_samples
    import shared_wong_choi.research_racing_monitoring_page_runtime as runtime_module
    path, _, runtime = inputs(tmp_path)

    def replay(**kwargs):
        raise ValueError("native source changed")

    monkeypatch.setattr(runtime_module, "reconcile_racing_monitoring_corpus", replay)
    with pytest.raises(ValueError, match="native source changed"):
        source_reverified_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)


def test_paged_consumer_rejects_outside_path_before_open(tmp_path, monkeypatch):
    from shared_wong_choi.research_monitoring_samples import source_reverified_paged_monitoring_samples
    from shared_wong_choi.research_index import _Reader
    path, _, runtime = inputs(tmp_path)
    runtime.warm_root = tmp_path / "elsewhere"

    def must_not_read(*args, **kwargs):
        raise AssertionError("out-of-scope file opened")

    monkeypatch.setattr(_Reader, "read", must_not_read)
    with pytest.raises(ValueError, match="owned corpus phase"):
        source_reverified_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)


@pytest.mark.parametrize("fault", ["outside", "partial", "hash", "changed_after_replay"])
def test_paged_consumer_rejects_unsafe_or_changed_report(tmp_path, monkeypatch, fault):
    from shared_wong_choi.research_monitoring_samples import source_reverified_paged_monitoring_samples
    import shared_wong_choi.research_racing_monitoring_page_runtime as runtime_module
    path, report, runtime = inputs(tmp_path)
    if fault == "outside":
        runtime.warm_root = tmp_path / "elsewhere"
    elif fault == "partial":
        path = path.with_name("racing-monitoring-page-fixture.json")
        path.write_text(json.dumps(report))
    elif fault == "hash":
        report["content_hash"] = "0" * 64
        path.write_text(json.dumps(report))

    def replay(**kwargs):
        if fault == "changed_after_replay":
            path.write_text("{}")
        return {"content_hash": report["content_hash"], "verified_monitoring_samples": 1}

    monkeypatch.setattr(runtime_module, "reconcile_racing_monitoring_corpus", replay)
    with pytest.raises((ValueError, RuntimeError)):
        source_reverified_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)


def test_bounded_parent_consumer_verifies_companions_without_native_replay(tmp_path, monkeypatch):
    from shared_wong_choi.research_monitoring_samples import bounded_paged_monitoring_samples
    import shared_wong_choi.research_racing_monitoring_page_runtime as module
    path, report, runtime = inputs(tmp_path)
    calls = []

    def verify(**kwargs):
        calls.append(kwargs)

    def forbidden(**kwargs):
        raise AssertionError("parent must not replay opaque sources")

    monkeypatch.setattr(module, "verify_racing_monitoring_corpus_receipt", verify)
    monkeypatch.setattr(module, "reconcile_racing_monitoring_corpus", forbidden)
    samples = bounded_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)
    assert len(calls) == 1
    assert calls[0]["receipt"] == {"content_hash": report["content_hash"], "verified_monitoring_samples": 1}
    assert samples[0].unit_ids == frozenset({"fixture:race:1"})


def test_bounded_parent_propagates_missing_companion(tmp_path, monkeypatch):
    from shared_wong_choi.research_monitoring_samples import bounded_paged_monitoring_samples
    import shared_wong_choi.research_racing_monitoring_page_runtime as module
    path, _, runtime = inputs(tmp_path)

    def verify(**kwargs):
        raise ValueError("missing native companion")

    monkeypatch.setattr(module, "verify_racing_monitoring_corpus_receipt", verify)
    with pytest.raises(ValueError, match="missing native companion"):
        bounded_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)


def test_bounded_parent_rejects_report_changed_during_verification(tmp_path, monkeypatch):
    from shared_wong_choi.research_monitoring_samples import bounded_paged_monitoring_samples
    import shared_wong_choi.research_racing_monitoring_page_runtime as module
    path, _, runtime = inputs(tmp_path)

    def verify(**kwargs):
        path.write_text("{}")

    monkeypatch.setattr(module, "verify_racing_monitoring_corpus_receipt", verify)
    with pytest.raises((ValueError, RuntimeError)):
        bounded_paged_monitoring_samples(path=path, runtime=runtime, checkpoint=lambda: None)


@pytest.mark.parametrize("side", ["child", "parent"])
def test_review_dispatch_uses_separate_paged_verification_boundaries(tmp_path, monkeypatch, side):
    import shared_wong_choi.research_monitoring_samples as module
    path, report, runtime = inputs(tmp_path)
    calls = []
    expected = module._paged_sample_snapshot(report)

    def selected(**kwargs):
        calls.append(kwargs)
        return expected

    def forbidden(*args, **kwargs):
        raise AssertionError("wrong verification boundary")

    monkeypatch.setattr(module, "source_reverified_paged_monitoring_samples", selected if side == "child" else forbidden)
    monkeypatch.setattr(module, "bounded_paged_monitoring_samples", selected if side == "parent" else forbidden)
    monkeypatch.setattr(module, "monitoring_sample_snapshots", forbidden)
    dispatch = getattr(module, f"review_{side}_monitoring_samples")
    samples, reference = dispatch(path=path, report=report, runtime=runtime, checkpoint=lambda: None)
    assert samples == expected and len(calls) == 1
    assert reference["scope_counts"] == {"all": 1}
    assert reference["content_hash"] == report["content_hash"]


@pytest.mark.parametrize("side", ["child", "parent"])
def test_review_dispatch_preserves_legacy_domain_router(tmp_path, monkeypatch, side):
    import shared_wong_choi.research_monitoring_samples as module
    path, report, runtime = inputs(tmp_path)
    report["schema_version"] = "legacy-fixture"
    expected = module._paged_sample_snapshot(report)
    calls = []

    def legacy(value):
        calls.append(value)
        return expected

    monkeypatch.setattr(module, "monitoring_sample_snapshots", legacy)
    samples, reference = getattr(module, f"review_{side}_monitoring_samples")(
        path=path, report=report, runtime=runtime, checkpoint=lambda: None)
    assert samples == expected and len(calls) == 1
    assert reference["scope_counts"] == {"all": 1}


@pytest.mark.parametrize("side", ["child", "parent"])
def test_review_dispatch_rejects_report_argument_changed_without_rehash(tmp_path, monkeypatch, side):
    import shared_wong_choi.research_monitoring_samples as module
    path, report, runtime = inputs(tmp_path)
    samples = module._paged_sample_snapshot(report)
    report["source_coverage_complete"] = False
    monkeypatch.setattr(module, "source_reverified_paged_monitoring_samples", lambda **kwargs: samples)
    monkeypatch.setattr(module, "bounded_paged_monitoring_samples", lambda **kwargs: samples)
    with pytest.raises(ResearchIndexError, match="hash mismatch"):
        getattr(module, f"review_{side}_monitoring_samples")(
            path=path, report=report, runtime=runtime, checkpoint=lambda: None)


@pytest.mark.parametrize("domain", ["au", "hkjc"])
def test_supervised_review_accepts_native_paged_corpus_with_previous_clock(tmp_path, domain):
    from datetime import timedelta
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.research_runner import ResearchDisposition
    from shared_wong_choi.research_racing_monitoring_page_runtime import RacingMonitoringCorpusInspectionRunner
    from shared_wong_choi.research_review_runtime import ResearchReviewRunner
    from test_research_review_runtime import setup, read_summary
    from test_research_racing_monitoring_samples import _au_source, _hkjc_source
    runtime, registry = setup(tmp_path)
    source = _au_source if domain == "au" else _hkjc_source
    root, end, _ = source(tmp_path / "native")
    corpus = RacingMonitoringCorpusInspectionRunner(runtime, registry).run(
        domain=Domain(domain), evidence_root=root, as_of=end,
        estimated_bytes=1048576, timeout_seconds=30)
    assert corpus.disposition is ResearchDisposition.SUCCEEDED, corpus.status
    result = ResearchReviewRunner(runtime, registry).run(
        domain=Domain(domain), window_start=end - timedelta(minutes=1), now=end,
        ruler_digest="1" * 64, ruler_released_at=end - timedelta(days=30),
        estimated_bytes=1048576, timeout_seconds=30,
        racing_sample_report=corpus.report_path, previous_racing_sample_report=corpus.report_path,
        racing_sample_evidence_root=root)
    summary = read_summary(result)
    assert summary["sample_evidence_status"] == "verified_complete"
    assert summary["racing_sample_current"]["scope_counts"] == {"all": 1}
    assert summary["racing_sample_previous"] == summary["racing_sample_current"]
    assert summary["sample_growth_observed"] is False
    assert summary["model_promotion_allowed"] is False


@pytest.mark.parametrize("domain", ["au", "hkjc"])
@pytest.mark.parametrize("fault", [None, "missing_companion", "false_count", "changed_source"])
def test_cursor_creates_paged_watermark_and_resumes_in_fresh_instance(tmp_path, domain, fault):
    from datetime import timedelta
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.research_runner import ResearchDisposition
    from shared_wong_choi.research_review_cursor import ResearchReviewCursorRunner
    from shared_wong_choi.research_racing_monitoring_pages import COVERAGE_SCHEMA
    from test_research_review_cursor import setup, state, sample_state
    from test_research_racing_monitoring_samples import _au_source, _hkjc_source
    runtime, registry = setup(tmp_path)
    root, end, source_result = (_au_source if domain == "au" else _hkjc_source)(tmp_path / "native")
    (runtime.state_root / "research-review-cursors").mkdir(parents=True)
    runner = ResearchReviewCursorRunner(runtime, registry)
    path = runner.initialize(domain=Domain(domain), initial_window_start=end - timedelta(minutes=1),
                             ruler_digest="1" * 64, ruler_released_at=end - timedelta(days=30))
    runner.initialize_racing_samples(domain=Domain(domain), evidence_root=root)
    options = dict(domain=Domain(domain), now=end, ruler_digest="1" * 64,
                   ruler_released_at=end - timedelta(days=30), estimated_bytes=1048576,
                   timeout_seconds=30)
    first = runner.run(**options)
    assert first.disposition is ResearchDisposition.SUCCEEDED, first
    saved = sample_state(path)
    before_cursor = state(path)
    proof = Path(saved["last_report"]["path"])
    assert json.loads(proof.read_text())["schema_version"] == COVERAGE_SCHEMA
    if fault == "missing_companion":
        next(proof.parent.glob("racing-feature-page-*.json")).unlink()
    elif fault == "false_count":
        altered = json.loads(proof.read_text())
        altered["verified_monitoring_samples"] += 1
        altered["content_hash"] = _hash({key: value for key, value in altered.items() if key != "content_hash"})
        proof.write_text(json.dumps(altered))
    elif fault == "changed_source":
        source_result.write_text("changed after successful cursor review\n")
    fresh = ResearchReviewCursorRunner(runtime, registry)
    second = fresh.run(**{**options, "now": end + timedelta(minutes=1)})
    if fault is not None:
        expected = ResearchDisposition.FAILED if fault == "changed_source" else ResearchDisposition.BLOCKED
        assert second.disposition is expected, second
        assert second.advanced is False
        assert state(path) == before_cursor and sample_state(path) == saved
        return
    assert second.disposition is ResearchDisposition.SUCCEEDED, second
    assert state(path)["generation"] == sample_state(path)["generation"] == 2
    summary = json.loads(second.review.report_path.read_text())
    assert summary["racing_sample_previous"] == saved["last_report"]
    assert summary["sample_growth_observed"] is False
    assert summary["model_promotion_allowed"] is False
