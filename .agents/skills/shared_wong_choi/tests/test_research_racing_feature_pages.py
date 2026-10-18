from dataclasses import replace

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore
from shared_wong_choi.research_index import _Reader, _hash
from shared_wong_choi.research_prediction_artifacts import _records
from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory, plan_prediction_pages
from shared_wong_choi.research_racing_feature_pages import inspect_racing_feature_page, aggregate_racing_feature_pages
import test_research_au_feature_provenance as au
import test_research_hkjc_feature_provenance as hk


def setup(tmp_path, domain, mode="valid", count=1):
    native = au if domain is Domain.AU else hk
    value = native.fixture(tmp_path, mode)
    root = value if domain is Domain.AU else value[0]
    original = _records(root, domain, native.AS_OF, _Reader(lambda: None))[0][0]
    for index in range(1, count):
        EvidenceStore(root).append(replace(original, record_id=f"{original.record_id}:copy-{index:05d}"))
    inventory = freeze_prediction_inventory(root=root, domain=domain, as_of=native.AS_OF)
    options = dict(root=root, domain=domain, as_of=native.AS_OF, inventory=inventory, max_records=2)
    return native, options, plan_prediction_pages(inventory, max_records=2)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("mode", ["valid", "legacy", "future", "digest", "output", "projection"])
def test_page_preserves_native_domain_feature_and_pit_decision(tmp_path, domain, mode):
    native, options, pages = setup(tmp_path, domain, mode)
    legacy = native.inspect(options["root"])
    report = inspect_racing_feature_page(page=pages[0], **options)
    assert report["feature_report"]["records"] == legacy["records"]
    assert report["feature_report"]["feature_availability_verified"] == legacy["feature_availability_verified"]
    assert report["source_coverage_complete"] is False
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_feature_pages_cover_native_full_corpus_exactly(tmp_path, domain):
    native, options, pages = setup(tmp_path, domain, count=6)
    reports = [inspect_racing_feature_page(page=p, **options) for p in pages]
    legacy = native.inspect(options["root"])
    assert [r for page in reports for r in page["feature_report"]["records"]] == legacy["records"]
    proof = aggregate_racing_feature_pages(results=reports, **options)
    assert proof["records_seen"] == 6 and proof["verified_feature_entries"] == legacy["verified_feature_entries"]
    assert proof["page_coverage_complete"] is True
    assert proof["feature_availability_verified"] is True
    assert proof["verified_monitoring_samples"] is None
    assert proof["model_promotion_allowed"] is False


@pytest.mark.parametrize("fault", ["omit", "reorder", "promotion", "count", "source_append"])
def test_feature_coverage_rejects_incomplete_or_rehashed_proofs(tmp_path, fault):
    _, options, pages = setup(tmp_path, Domain.AU, count=4)
    reports = [inspect_racing_feature_page(page=p, **options) for p in pages]
    if fault == "omit":
        reports.pop()
    elif fault == "reorder":
        reports.reverse()
    elif fault == "promotion":
        reports[0]["model_promotion_allowed"] = True
    elif fault == "count":
        reports[0]["feature_report"]["verified_feature_entries"] = 0
    else:
        original = _records(options["root"], Domain.AU, au.AS_OF, _Reader(lambda: None))[0][0]
        EvidenceStore(options["root"]).append(replace(original, record_id=f"{original.record_id}:new"))
    for report in reports:
        report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    with pytest.raises(ValueError):
        aggregate_racing_feature_pages(results=reports, **options)


def test_racing_feature_aggregate_rejects_nonracing_even_with_empty_pages(tmp_path):
    from test_research_prediction_artifacts import _release, NOW
    root = tmp_path / "empty"
    _release(EvidenceStore(root))
    inventory = freeze_prediction_inventory(root=root, domain=Domain.NBA, as_of=NOW)
    with pytest.raises(ValueError, match="racing domain"):
        aggregate_racing_feature_pages(results=[], inventory=inventory, root=root, domain=Domain.NBA, as_of=NOW)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_blob_change_between_prediction_and_feature_inspection_is_rejected(tmp_path, domain, monkeypatch):
    from pathlib import Path
    _, options, pages = setup(tmp_path, domain)
    if domain is Domain.AU:
        import shared_wong_choi.research_au_feature_provenance as module
        name = "_inspect_au_feature_records"
    else:
        import shared_wong_choi.research_hkjc_feature_provenance as module
        name = "_inspect_hkjc_feature_records"
    native = getattr(module, name)
    record = _records(options["root"], domain, options["as_of"], _Reader(lambda: None))[0][0]
    source = next(Path(a.path) for a in record.artifacts if a.path.endswith("Facts.md"))
    def changed(**kwargs):
        source.write_text("changed after bundle verification")
        return native(**kwargs)
    monkeypatch.setattr(module, name, changed)
    with pytest.raises(ValueError, match="changed"):
        inspect_racing_feature_page(page=pages[0], **options)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_feature_corpus_above_prediction_reference_cap_is_not_narrowed(tmp_path, domain):
    _, options, _ = setup(tmp_path, domain, count=1300)
    options["max_records"] = 100
    pages = plan_prediction_pages(options["inventory"], max_records=100)
    assert options["inventory"]["artifact_refs"] > 5000
    reports = [inspect_racing_feature_page(page=p, **options) for p in pages]
    proof = aggregate_racing_feature_pages(results=reports, **options)
    assert proof["records_seen"] == proof["verified_feature_entries"] == 1300
    assert len(proof["page_hashes"]) == 13
    assert proof["feature_availability_verified"] is True
    assert "records" not in proof and proof["verified_monitoring_samples"] is None
