from dataclasses import replace
from pathlib import Path

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore, RecordKind
from shared_wong_choi.research_index import _Reader, _hash, ResearchIndexError
from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory, plan_prediction_pages
from shared_wong_choi.research_racing_settlement_inventory import freeze_racing_settlement_inventory
from shared_wong_choi.research_racing_settlement_pages import inspect_racing_settlement_page, aggregate_racing_settlement_pages
import test_research_au_settlement_source as au
import test_research_hkjc_settlement_source as hk


def setup(tmp_path, domain, evidenced=True, count=1):
    native = au if domain is Domain.AU else hk
    root = native.settled_fixture(tmp_path, evidence_result=evidenced)[0]
    if domain is Domain.AU:
        from shared_wong_choi.research_au_settlement_source import _evidence
        records = {k: v[0] for k, v in _evidence(root, native.END, _Reader(lambda: None)).items()}
    else:
        from shared_wong_choi.research_hkjc_settlement_source import _evidence
        records = _evidence(root, native.END, _Reader(lambda: None))
    originals = {kind: next(v for v in records.values() if v.kind is kind) for kind in (
        RecordKind.PREDICTION, RecordKind.DECISION, RecordKind.SETTLEMENT)}
    store = EvidenceStore(root)
    for index in range(1, count):
        ids = {kind: old.record_id + f":copy-{index:05d}" for kind, old in originals.items()}
        store.append(replace(originals[RecordKind.PREDICTION], record_id=ids[RecordKind.PREDICTION]))
        store.append(replace(originals[RecordKind.DECISION], record_id=ids[RecordKind.DECISION],
                             links={**originals[RecordKind.DECISION].links, "prediction_id": ids[RecordKind.PREDICTION]}))
        store.append(replace(originals[RecordKind.SETTLEMENT], record_id=ids[RecordKind.SETTLEMENT],
                             links={**originals[RecordKind.SETTLEMENT].links, "decision_id": ids[RecordKind.DECISION]}))
    options = dict(root=root, domain=domain, as_of=native.END, max_records=1,
                   inventory=freeze_prediction_inventory(root=root, domain=domain, as_of=native.END),
                   settlement_inventory=freeze_racing_settlement_inventory(root=root, domain=domain, as_of=native.END))
    return native, options, plan_prediction_pages(options["inventory"], max_records=1)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("evidenced", [True, False])
def test_settlement_page_preserves_native_label_decisions_without_sample_authority(tmp_path, domain, evidenced):
    native, options, pages = setup(tmp_path, domain, evidenced)
    legacy = native.inspect(options["root"])
    result = inspect_racing_settlement_page(page=pages[0], **options)
    assert result["settlement_report"]["candidates"] == legacy["candidates"]
    assert result["settlement_report"]["label_source_verified"] == legacy["label_source_verified"]
    assert result["verified_monitoring_samples"] is None and result["model_promotion_allowed"] is False


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_settlement_pages_cover_all_native_candidates_exactly_once(tmp_path, domain):
    native, options, pages = setup(tmp_path, domain, count=3)
    reports = [inspect_racing_settlement_page(page=page, **options) for page in pages]
    legacy = native.inspect(options["root"])
    candidates = sorted([c for r in reports for c in r["settlement_report"]["candidates"]], key=lambda c: c["settlement_id"])
    assert candidates == legacy["candidates"]
    proof = aggregate_racing_settlement_pages(results=reports, **options)
    assert proof["page_coverage_complete"] is True and proof["settlements_seen"] == 3
    assert proof["label_verified_settlements"] == 3 and len(proof["page_hashes"]) == 3
    assert proof["verified_monitoring_samples"] is None and proof["model_promotion_allowed"] is False


@pytest.mark.parametrize("fault", ["omitted", "reordered", "promotion"])
def test_settlement_coverage_rejects_incomplete_or_rehashed_page_set(tmp_path, fault):
    _, options, pages = setup(tmp_path, Domain.AU, count=3)
    reports = [inspect_racing_settlement_page(page=p, **options) for p in pages]
    if fault == "omitted":
        reports = reports[:-1]
    elif fault == "reordered":
        reports.reverse()
    else:
        reports[0]["model_promotion_allowed"] = True
        reports[0]["content_hash"] = _hash({k: v for k, v in reports[0].items() if k != "content_hash"})
    with pytest.raises((ValueError, ResearchIndexError)):
        aggregate_racing_settlement_pages(results=reports, **options)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_label_page_rejects_result_changed_after_native_projection(tmp_path, domain, monkeypatch):
    _, options, pages = setup(tmp_path, domain)
    if domain is Domain.AU:
        import shared_wong_choi.research_au_settlement_source as worker
        name = "_inspect_au_settlement_records"
    else:
        import shared_wong_choi.research_hkjc_settlement_source as worker
        name = "_inspect_hkjc_settlement_records"
    original = getattr(worker, name)
    def changed(**kwargs):
        report = original(**kwargs)
        Path(report["candidates"][0]["referenced_result_artifact"]).write_text("changed after native label inspection")
        return report
    monkeypatch.setattr(worker, name, changed)
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        inspect_racing_settlement_page(page=pages[0], **options)
