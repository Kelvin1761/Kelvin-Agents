from dataclasses import replace

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore
from shared_wong_choi.research_index import ResearchIndexError, _hash
from shared_wong_choi.research_prediction_pages import (
    aggregate_prediction_pages,
    freeze_prediction_inventory,
    inspect_prediction_page,
    persist_prediction_page,
    reconcile_prediction_page,
    plan_prediction_pages,
    verify_prediction_inventory,
    verify_prediction_page_plan,
)
from test_research_prediction_artifacts import NOW, fixture, _release


def inventory(tmp_path, count=1):
    root, _, _, _ = fixture(tmp_path)
    store = EvidenceStore(root)
    # Use canonical native parsing, not hand-written evidence JSON.
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    original = _records(root, Domain.AU, NOW, _Reader(lambda: None))[0][0]
    for index in range(1, count):
        store.append(replace(original, record_id=f"{original.record_id}:copy-{index:05d}"))
    return root, freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)


def test_full_inventory_over_5000_refs_has_exact_deterministic_pages(tmp_path):
    _, value = inventory(tmp_path, 1700)
    pages = plan_prediction_pages(value)
    assert value["artifact_refs"] == 5100
    assert len(pages) == 17
    assert all(p["artifact_refs"] == 300 for p in pages)
    assert [r for p in pages for r in p["record_ids"]] == [r["record_id"] for r in value["records"]]
    assert pages == plan_prediction_pages(value)
    assert value["model_promotion_allowed"] is False


def test_bundle_never_splits_to_fit_page(tmp_path):
    _, value = inventory(tmp_path)
    with pytest.raises(ValueError, match="bundle"):
        plan_prediction_pages(value, max_refs=2)


def test_page_bound_cannot_exceed_existing_reader_limit(tmp_path):
    _, value = inventory(tmp_path)
    with pytest.raises(ValueError):
        plan_prediction_pages(value, max_refs=5001)


def test_changed_inventory_rejected_even_when_rehashed(tmp_path):
    root, value = inventory(tmp_path, 2)
    value["records"].pop()
    value["records_seen"] = 1
    value["artifact_refs"] = 3
    value["content_hash"] = _hash({k: v for k, v in value.items() if k != "content_hash"})
    with pytest.raises(ValueError):
        verify_prediction_inventory(value, root=root, domain=Domain.AU, as_of=NOW)


def test_source_append_invalidates_frozen_inventory(tmp_path):
    root, value = inventory(tmp_path)
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    original = _records(root, Domain.AU, NOW, _Reader(lambda: None))[0][0]
    EvidenceStore(root).append(replace(original, record_id=f"{original.record_id}:new"))
    with pytest.raises(ValueError):
        verify_prediction_inventory(value, root=root, domain=Domain.AU, as_of=NOW)


def test_no_artifact_content_is_read_by_inventory(tmp_path):
    root, _, snapshot, _ = fixture(tmp_path)
    for path in snapshot.iterdir():
        path.unlink()
    value = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)
    assert value["artifact_refs"] == 3
    assert value["artifact_contents_verified"] is False


def test_empty_inventory_has_no_pages_and_no_coverage_grant(tmp_path):
    root = tmp_path / "empty"
    _release(EvidenceStore(root))
    value = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)
    assert plan_prediction_pages(value) == ()
    assert value["source_coverage_complete"] is False


@pytest.mark.parametrize("fault", ["omitted", "duplicate", "reordered", "next", "index", "total", "bounds"])
def test_rehashed_page_tampering_is_not_a_valid_plan(tmp_path, fault):
    _, value = inventory(tmp_path, 4)
    page = plan_prediction_pages(value, max_records=2)[0]
    if fault == "omitted":
        page["record_ids"].pop()
        page["artifact_refs"] = 3
    elif fault == "duplicate":
        page["record_ids"][1] = page["record_ids"][0]
    elif fault == "reordered":
        page["record_ids"].reverse()
    elif fault == "next":
        page["next_page_index"] = None
    elif fault == "index":
        page["page_index"] = True
    elif fault == "total":
        page["total_pages"] = 1
    else:
        page["max_refs"] = 5001
    page["content_hash"] = _hash({k: v for k, v in page.items() if k != "content_hash"})
    with pytest.raises(ValueError):
        verify_prediction_page_plan(page, value, max_records=2)


def test_valid_page_plan_is_bound_to_current_inventory_identity(tmp_path):
    _, value = inventory(tmp_path, 4)
    pages = plan_prediction_pages(value, max_records=2)
    for page in pages:
        verify_prediction_page_plan(page, value, max_records=2)
    altered = dict(value, as_of="2026-09-01T00:00:00+00:00")
    altered["content_hash"] = _hash({k: v for k, v in altered.items() if k != "content_hash"})
    with pytest.raises(ValueError):
        verify_prediction_page_plan(pages[0], altered, max_records=2)


def test_preemption_checkpoint_is_not_swallowed(tmp_path):
    root, _ = inventory(tmp_path)
    def stopped():
        raise RuntimeError("production preempted")
    with pytest.raises(RuntimeError, match="preempted"):
        freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW, checkpoint=stopped)


def test_concurrent_append_during_read_fails_recheck(tmp_path, monkeypatch):
    root, _ = inventory(tmp_path)
    from shared_wong_choi.research_index import _Reader
    from shared_wong_choi.research_prediction_artifacts import _records
    original = _records(root, Domain.AU, NOW, _Reader(lambda: None))[0][0]
    recheck = _Reader.recheck
    def changed(reader):
        EvidenceStore(root).append(replace(original, record_id=f"{original.record_id}:concurrent"))
        recheck(reader)
    monkeypatch.setattr(_Reader, "recheck", changed)
    with pytest.raises(ResearchIndexError, match="directory changed"):
        freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)


def completed(root, value, max_records=2):
    plans = plan_prediction_pages(value, max_records=max_records)
    return [inspect_prediction_page(
        inventory=value, page=page, root=root, domain=Domain.AU, as_of=NOW,
        max_records=max_records,
    ) for page in plans]


def test_page_content_matches_legacy_bundle_projection(tmp_path):
    from shared_wong_choi.research_prediction_artifacts import inspect_prediction_artifacts
    root, value = inventory(tmp_path)
    result = completed(root, value)[0]
    legacy = inspect_prediction_artifacts(root=root, domain=Domain.AU, as_of=NOW)
    assert result["records"] == legacy["records"]
    aggregate = aggregate_prediction_pages(
        results=[result], inventory=value, root=root, domain=Domain.AU, as_of=NOW,
        max_records=2,
    )
    assert aggregate["artifact_contents_verified"] is True
    assert aggregate["source_coverage_complete"] is False
    assert aggregate["model_promotion_allowed"] is False


@pytest.mark.parametrize("fault", ["missing", "duplicate", "reordered"])
def test_incomplete_page_coverage_cannot_be_aggregated(tmp_path, fault):
    root, value = inventory(tmp_path, 4)
    results = completed(root, value)
    if fault == "missing":
        results.pop()
    elif fault == "duplicate":
        results[1] = results[0]
    else:
        results.reverse()
    with pytest.raises(ValueError):
        aggregate_prediction_pages(
            results=results, inventory=value, root=root, domain=Domain.AU, as_of=NOW,
            max_records=2,
        )


def test_rehashed_forged_page_proof_is_rebuilt_not_trusted(tmp_path):
    root, value = inventory(tmp_path)
    results = completed(root, value)
    results[0]["records"][0]["resolved_snapshot_root"] = "/private/tmp/forged"
    results[0]["content_hash"] = _hash({k: v for k, v in results[0].items() if k != "content_hash"})
    with pytest.raises(ValueError):
        aggregate_prediction_pages(
            results=results, inventory=value, root=root, domain=Domain.AU, as_of=NOW,
            max_records=2,
        )


def test_missing_blob_remains_blocked_not_hidden_by_full_page_coverage(tmp_path):
    root, _, snapshot, _ = fixture(tmp_path)
    (snapshot / "Race_1_Logic.json").unlink()
    value = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)
    result = aggregate_prediction_pages(
        results=completed(root, value), inventory=value, root=root,
        domain=Domain.AU, as_of=NOW, max_records=2,
    )
    assert result["page_coverage_complete"] is True
    assert result["artifact_contents_verified"] is False
    assert result["verified_monitoring_samples"] is None


def test_full_blob_coverage_above_legacy_limit_is_compact_and_complete(tmp_path):
    root, value = inventory(tmp_path, 1700)
    results = completed(root, value, max_records=100)
    proof = aggregate_prediction_pages(
        results=results, inventory=value, root=root, domain=Domain.AU, as_of=NOW,
    )
    assert (proof["artifact_refs"], proof["records_seen"], proof["verified_bundles"]) == (5100, 1700, 1700)
    assert proof["artifact_contents_verified"] is True
    assert len(proof["page_hashes"]) == 17
    assert "records" not in proof
    assert proof["verified_monitoring_samples"] is None


def test_blob_change_after_page_read_rejects_saved_proof(tmp_path):
    root, _, snapshot, _ = fixture(tmp_path)
    value = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)
    results = completed(root, value)
    (snapshot / "Race_1_Logic.json").write_text("changed after proof")
    with pytest.raises(ValueError, match="proof differs"):
        aggregate_prediction_pages(
            results=results, inventory=value, root=root, domain=Domain.AU,
            as_of=NOW, max_records=2,
        )


def test_paged_reader_retains_native_blob_byte_budget(tmp_path, monkeypatch):
    root, value = inventory(tmp_path)
    import shared_wong_choi.research_prediction_artifacts as native
    monkeypatch.setattr(native, "MAX_TOTAL_BYTES", 2)
    with pytest.raises(ValueError, match="read budget"):
        completed(root, value)


def test_aggregate_preemption_cannot_publish_partial_coverage(tmp_path):
    root, value = inventory(tmp_path, 4)
    results = completed(root, value)
    def stop():
        raise RuntimeError("production preempted")
    with pytest.raises(RuntimeError, match="preempted"):
        aggregate_prediction_pages(
            results=results, inventory=value, root=root, domain=Domain.AU,
            as_of=NOW, max_records=2, checkpoint=stop,
        )


def saved_page(root, value, output, **options):
    return persist_prediction_page(
        inventory=value, page=plan_prediction_pages(value, max_records=2)[0],
        root=root, domain=Domain.AU, as_of=NOW, output_root=output,
        max_records=2, **options,
    )


def test_create_only_receipt_repeat_keeps_identical_bytes(tmp_path):
    root, value = inventory(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir()
    first = saved_page(root, value, output)
    before = first["path"].read_bytes()
    second = saved_page(root, value, output)
    assert first["publication"] == "created"
    assert second["publication"] == "duplicate"
    assert second["path"].read_bytes() == before


def test_existing_receipt_conflict_never_overwrites(tmp_path):
    root, value = inventory(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir()
    first = saved_page(root, value, output)
    first["path"].write_text("tampered")
    from shared_wong_choi.research_evaluation import EvaluationError
    with pytest.raises(EvaluationError, match="conflict"):
        saved_page(root, value, output)
    assert first["path"].read_text() == "tampered"


def test_preempted_page_has_no_published_success(tmp_path):
    root, value = inventory(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir()
    def stop():
        raise RuntimeError("production preempted")
    with pytest.raises(RuntimeError):
        saved_page(root, value, output, checkpoint=stop)
    assert list(output.iterdir()) == []


def test_saved_receipt_reconciliation_is_read_only_and_rechecks_source(tmp_path):
    root, _, snapshot, _ = fixture(tmp_path)
    value = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=NOW)
    output = tmp_path / "receipts"
    output.mkdir()
    saved = saved_page(root, value, output)
    before = saved["path"].read_bytes()
    options = dict(inventory=value, page=plan_prediction_pages(value, max_records=2)[0],
                   root=root, domain=Domain.AU, as_of=NOW, output_root=output, max_records=2)
    assert reconcile_prediction_page(**options)["publication"] == "verified_existing"
    assert saved["path"].read_bytes() == before
    (snapshot / "Race_1_Logic.json").write_text("changed")
    with pytest.raises(ValueError):
        reconcile_prediction_page(**options)


def test_symlink_receipt_directory_rejected(tmp_path):
    root, value = inventory(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises((ValueError, RuntimeError)):
        saved_page(root, value, link)
    assert list(real.iterdir()) == []


def test_lost_ack_after_publication_requires_read_only_reconciliation(tmp_path, monkeypatch):
    root, value = inventory(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir()
    import shared_wong_choi.research_prediction_pages as pages
    writer = pages._write_report
    def interrupted(*args, **kwargs):
        writer(*args, **kwargs)
        raise RuntimeError("publication acknowledgement lost")
    monkeypatch.setattr(pages, "_write_report", interrupted)
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        saved_page(root, value, output)
    files = list(output.iterdir())
    assert len(files) == 1
    before = files[0].read_bytes()
    options = dict(inventory=value, page=plan_prediction_pages(value, max_records=2)[0],
                   root=root, domain=Domain.AU, as_of=NOW, output_root=output, max_records=2)
    proof = reconcile_prediction_page(**options)
    assert proof["publication"] == "verified_existing"
    assert proof["model_promotion_allowed"] is False
    assert files[0].read_bytes() == before


def test_missing_saved_receipt_is_not_created_by_reconciliation(tmp_path):
    root, value = inventory(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir()
    with pytest.raises(FileNotFoundError):
        reconcile_prediction_page(
            inventory=value, page=plan_prediction_pages(value, max_records=2)[0],
            root=root, domain=Domain.AU, as_of=NOW, output_root=output, max_records=2,
        )
    assert list(output.iterdir()) == []


def test_receipt_fifo_rejected_without_opening(tmp_path):
    import os
    root, value = inventory(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir()
    page = plan_prediction_pages(value, max_records=2)[0]
    path = output / f"prediction-page-{page['content_hash']}.json"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        saved_page(root, value, output)
