from dataclasses import replace

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore, RecordKind
from shared_wong_choi.research_index import _Reader, _hash
from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory, plan_prediction_pages
from shared_wong_choi.research_racing_settlement_inventory import freeze_racing_settlement_inventory
from shared_wong_choi.research_racing_monitoring_samples import inspect_racing_monitoring_samples
from test_research_racing_monitoring_samples import _au_source, _hkjc_source


@pytest.mark.parametrize("domain,source", [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)])
@pytest.mark.parametrize("change", [{}, {"feature_mode": "legacy"}, {"label": False}])
def test_monitoring_page_preserves_native_join_without_whole_corpus_authority(tmp_path, domain, source, change):
    from shared_wong_choi.research_racing_monitoring_pages import inspect_racing_monitoring_page
    root, as_of, _ = source(tmp_path, **change)
    inventory = freeze_prediction_inventory(root=root, domain=domain, as_of=as_of)
    settlements = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=as_of)
    page = plan_prediction_pages(inventory)[0]
    result = inspect_racing_monitoring_page(
        inventory=inventory, settlement_inventory=settlements, page=page,
        root=root, domain=domain, as_of=as_of)
    legacy = inspect_racing_monitoring_samples(root=root, domain=domain, as_of=as_of)
    for key in ("candidates", "units", "qualified_races", "blocked_settlements"):
        assert result["monitoring_report"][key] == legacy[key]
    assert result["source_coverage_complete"] is False
    assert result["verified_monitoring_samples"] is None
    assert result["model_promotion_allowed"] is False


@pytest.mark.parametrize("domain,source", [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)])
def test_monitoring_join_rejects_result_changed_after_join(tmp_path, domain, source, monkeypatch):
    import shared_wong_choi.research_racing_monitoring_pages as module
    root, as_of, result = source(tmp_path)
    inventory = freeze_prediction_inventory(root=root, domain=domain, as_of=as_of)
    settlements = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=as_of)
    native = module._join_reports

    def changed(**kwargs):
        joined = native(**kwargs)
        result.write_text("changed after native join\n", encoding="utf-8")
        return joined

    monkeypatch.setattr(module, "_join_reports", changed)
    with pytest.raises((ValueError, RuntimeError)):
        module.inspect_racing_monitoring_page(
            inventory=inventory, settlement_inventory=settlements,
            page=plan_prediction_pages(inventory)[0], root=root, domain=domain, as_of=as_of)


def test_monitoring_page_rejects_cross_prediction_hash(tmp_path, monkeypatch):
    import shared_wong_choi.research_racing_monitoring_pages as module
    root, as_of, _ = _au_source(tmp_path)
    inventory = freeze_prediction_inventory(root=root, domain=Domain.AU, as_of=as_of)
    settlements = freeze_racing_settlement_inventory(root=root, domain=Domain.AU, as_of=as_of)
    native = module.inspect_racing_settlement_page

    def changed(**kwargs):
        labels = native(**kwargs)
        labels["prediction_page_hash"] = "0" * 64
        return labels

    monkeypatch.setattr(module, "inspect_racing_settlement_page", changed)
    with pytest.raises(ValueError, match="do not share"):
        module.inspect_racing_monitoring_page(
            inventory=inventory, settlement_inventory=settlements,
            page=plan_prediction_pages(inventory)[0], root=root, domain=Domain.AU, as_of=as_of)


def corpus(tmp_path, domain, source, change=None):
    root, as_of, result = source(tmp_path, **(change or {}))
    if domain is Domain.AU:
        from shared_wong_choi.research_au_settlement_source import _evidence
        records = {key: value[0] for key, value in _evidence(root, as_of, _Reader(lambda: None)).items()}
    else:
        from shared_wong_choi.research_hkjc_settlement_source import _evidence
        records = _evidence(root, as_of, _Reader(lambda: None))
    originals = {kind: next(value for value in records.values() if value.kind is kind)
                 for kind in (RecordKind.PREDICTION, RecordKind.DECISION, RecordKind.SETTLEMENT)}
    store = EvidenceStore(root)
    # Distinct fixture identities exercise page coverage, not independent real samples.
    for index in range(1, 3):
        ids = {kind: value.record_id + f":copy-{index}" for kind, value in originals.items()}
        store.append(replace(originals[RecordKind.PREDICTION], record_id=ids[RecordKind.PREDICTION]))
        store.append(replace(originals[RecordKind.DECISION], record_id=ids[RecordKind.DECISION],
                             links={**originals[RecordKind.DECISION].links, "prediction_id": ids[RecordKind.PREDICTION]}))
        store.append(replace(originals[RecordKind.SETTLEMENT], record_id=ids[RecordKind.SETTLEMENT],
                             links={**originals[RecordKind.SETTLEMENT].links, "decision_id": ids[RecordKind.DECISION]}))
    options = dict(root=root, domain=domain, as_of=as_of, max_records=1,
                   inventory=freeze_prediction_inventory(root=root, domain=domain, as_of=as_of),
                   settlement_inventory=freeze_racing_settlement_inventory(root=root, domain=domain, as_of=as_of))
    from shared_wong_choi.research_racing_monitoring_pages import inspect_racing_monitoring_page
    pages = plan_prediction_pages(options["inventory"], max_records=1)
    return options, [inspect_racing_monitoring_page(page=page, **options) for page in pages], result


@pytest.mark.parametrize("domain,source", [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)])
@pytest.mark.parametrize("change", [{}, {"feature_mode": "legacy"}, {"label": False}])
def test_complete_monitoring_corpus_matches_native_sample_clock(tmp_path, domain, source, change):
    from shared_wong_choi.research_racing_monitoring_pages import (
        aggregate_racing_monitoring_pages, paged_monitoring_sample_snapshot)
    options, pages, _ = corpus(tmp_path, domain, source, change)
    report = aggregate_racing_monitoring_pages(results=pages, **options)
    legacy = inspect_racing_monitoring_samples(root=options["root"], domain=domain, as_of=options["as_of"])
    for key in ("candidates", "units", "qualified_races", "blocked_settlements", "source_coverage_complete"):
        assert report[key] == legacy[key]
    assert report["page_coverage_complete"] is True
    assert report["model_promotion_allowed"] is False
    snapshot = paged_monitoring_sample_snapshot(report=report, results=pages, **options)
    assert snapshot.unit_ids == frozenset(unit["unit_id"] for unit in legacy["units"])


@pytest.mark.parametrize("domain,source", [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)])
def test_aggregation_uses_two_complete_native_passes_not_nested_four(tmp_path, domain, source, monkeypatch):
    import shared_wong_choi.research_racing_monitoring_pages as module
    options, pages, _ = corpus(tmp_path, domain, source)
    join = module._join_reports
    seen = []

    def traced(**kwargs):
        seen.append(kwargs["features"]["records"][0]["record_id"])
        return join(**kwargs)

    monkeypatch.setattr(module, "_join_reports", traced)
    report = module.aggregate_racing_monitoring_pages(results=pages, **options)
    expected = [p["record_ids"][0] for p in plan_prediction_pages(options["inventory"], max_records=1)]
    assert seen == expected * 2
    assert report["page_coverage_complete"] is True
    assert report["model_promotion_allowed"] is False


@pytest.mark.parametrize("fault", ["omitted", "reordered", "duplicate", "forged", "changed_source"])
def test_monitoring_corpus_rejects_incomplete_or_false_proofs(tmp_path, fault):
    from shared_wong_choi.research_racing_monitoring_pages import aggregate_racing_monitoring_pages
    options, pages, result = corpus(tmp_path, Domain.AU, _au_source)
    if fault == "omitted":
        pages.pop()
    elif fault == "reordered":
        pages.reverse()
    elif fault == "duplicate":
        pages[1] = pages[0]
    elif fault == "forged":
        pages[0]["monitoring_report"]["units"][0]["event_id"] = "forged"
        pages[0]["content_hash"] = _hash({k: v for k, v in pages[0].items() if k != "content_hash"})
    else:
        result.write_text("changed source\n", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        aggregate_racing_monitoring_pages(results=pages, **options)


def test_paged_snapshot_cannot_skip_source_or_report_reverification(tmp_path):
    from shared_wong_choi.research_racing_monitoring_pages import (
        aggregate_racing_monitoring_pages, paged_monitoring_sample_snapshot)
    options, pages, _ = corpus(tmp_path, Domain.AU, _au_source)
    report = aggregate_racing_monitoring_pages(results=pages, **options)
    report["units"][0]["event_id"] = "forged"
    report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    assert all(unit["event_id"] != "forged" for page in pages
               for unit in page["monitoring_report"]["units"])
    with pytest.raises(ValueError):
        paged_monitoring_sample_snapshot(report=report, results=pages, **options)


@pytest.mark.parametrize("domain,source", [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)])
def test_corpus_rechecks_earlier_page_source_after_last_page(tmp_path, domain, source, monkeypatch):
    import shared_wong_choi.research_racing_monitoring_pages as module
    options, pages, result = corpus(tmp_path, domain, source)
    native = module._inspect_racing_monitoring_page_once
    calls = 0

    def changed(**kwargs):
        nonlocal calls
        report = native(**kwargs)
        calls += 1
        if calls == len(pages):
            result.write_text("changed after first complete pass\n", encoding="utf-8")
        return report

    monkeypatch.setattr(module, "_inspect_racing_monitoring_page_once", changed)
    with pytest.raises((ValueError, RuntimeError)):
        module.aggregate_racing_monitoring_pages(results=pages, **options)


@pytest.mark.parametrize("limit", ["MAX_SETTLEMENTS", "MAX_RACES"])
def test_monitoring_aggregation_does_not_bypass_global_limits(tmp_path, monkeypatch, limit):
    import shared_wong_choi.research_racing_monitoring_pages as module
    options, pages, _ = corpus(tmp_path, Domain.AU, _au_source)
    monkeypatch.setattr(module, limit, 1)
    with pytest.raises(ValueError, match="bound exceeded"):
        module.aggregate_racing_monitoring_pages(results=pages, **options)


@pytest.mark.parametrize("domain,source", [(Domain.AU, _au_source), (Domain.HKJC, _hkjc_source)])
def test_snapshot_rechecks_sources_after_coverage_was_completed(tmp_path, domain, source):
    from shared_wong_choi.research_racing_monitoring_pages import (
        aggregate_racing_monitoring_pages, paged_monitoring_sample_snapshot)
    options, pages, result = corpus(tmp_path, domain, source)
    report = aggregate_racing_monitoring_pages(results=pages, **options)
    result.write_text("changed after completed coverage\n", encoding="utf-8")
    with pytest.raises((ValueError, RuntimeError)):
        paged_monitoring_sample_snapshot(report=report, results=pages, **options)
