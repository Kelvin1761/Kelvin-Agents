from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore, RecordKind
from shared_wong_choi.research_index import _Reader, ResearchIndexError
from test_research_racing_settlement_inventory import fixture


def native(domain):
    if domain is Domain.AU:
        from shared_wong_choi import research_au_settlement_source as module
    else:
        from shared_wong_choi import research_hkjc_settlement_source as module
    return module


def freeze(root, domain, end):
    from shared_wong_choi.research_native_evidence_snapshot import _NativeEvidenceSnapshot
    return _NativeEvidenceSnapshot(root=root, domain=domain, as_of=end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("fault", [None, "unselected_bytes", "during_recheck"])
def test_page_copy_keeps_parent_closure_and_complete_source_guard(tmp_path, domain, fault, monkeypatch):
    from shared_wong_choi import research_native_evidence_snapshot as module
    root, end = fixture(tmp_path, domain)
    complete = native(domain)._evidence(root, end, _Reader(lambda: None))
    record = lambda value: value[0] if domain is Domain.AU else value
    prediction = next(record(value) for value in complete.values()
                      if record(value).kind is RecordKind.PREDICTION)
    unrelated = replace(prediction, record_id=prediction.record_id + ":unrelated")
    EvidenceStore(root).append(unrelated)
    snapshot = freeze(root, domain, end)
    path = EvidenceStore(root).path_for(unrelated.kind, unrelated.record_id)
    copied = []
    original_copy = module.deepcopy

    def traced(value):
        copied.append(set(value))
        return original_copy(value)

    monkeypatch.setattr(module, "deepcopy", traced)
    options = dict(root=root, domain=domain, as_of=end, checkpoint=lambda: None,
                   selected_prediction_ids={prediction.record_id})
    if fault == "unselected_bytes":
        path.write_bytes(path.read_bytes() + b" ")
        with pytest.raises(ValueError, match="bytes changed"):
            snapshot._begin_read(**options)
    else:
        page, reader = snapshot._begin_read(**options)
        assert set(page) == set(complete)
        assert copied == [set(complete)]
        if fault == "during_recheck":
            path.write_bytes(path.read_bytes() + b" ")
            with pytest.raises(ResearchIndexError, match="bytes changed"):
                reader.recheck()
        else:
            reader.recheck()
            page.clear()
            assert len(snapshot.read(root=root, domain=domain, as_of=end)) == len(complete) + 1


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("selection", ["prediction", "empty", "unknown", "wrong_kind"])
def test_selected_native_report_preserves_full_graph_count(tmp_path, domain, selection):
    from shared_wong_choi.research_prediction_artifacts import inspect_prediction_artifacts
    root, end = fixture(tmp_path, domain)
    complete = native(domain)._evidence(root, end, _Reader(lambda: None))
    record = lambda value: value[0] if domain is Domain.AU else value
    prediction = next(record(value) for value in complete.values()
                      if record(value).kind is RecordKind.PREDICTION)
    EvidenceStore(root).append(replace(prediction, record_id=prediction.record_id + ":unrelated"))
    inspect = getattr(native(domain), "_inspect_au_settlement_records" if domain is Domain.AU
                      else "_inspect_hkjc_settlement_records")
    selected = {"prediction": {prediction.record_id}, "empty": set(),
                "unknown": {"missing-prediction"},
                "wrong_kind": {prediction.links["model_release_id"]}}[selection]
    options = dict(root=root, end=end, roots=(), checkpoint=lambda: None,
                   selected_prediction_ids=selected,
                   prediction_report=inspect_prediction_artifacts(root=root, domain=domain, as_of=end))
    baseline = inspect(**options)
    assert baseline["evidence_records_seen"] == len(complete) + 1
    assert inspect(**options, evidence_snapshot=freeze(root, domain, end)) == baseline


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_native_graph_is_built_once_but_bytes_are_rechecked_on_every_reuse(tmp_path, domain, monkeypatch):
    root, end = fixture(tmp_path, domain)
    module = native(domain)
    builder = module._evidence
    calls = []

    def traced(*args):
        calls.append(1)
        return builder(*args)

    monkeypatch.setattr(module, "_evidence", traced)
    snapshot = freeze(root, domain, end)
    first = snapshot.read(root=root, domain=domain, as_of=end)
    assert first == snapshot.read(root=root, domain=domain, as_of=end)
    assert len(calls) == 1
    assert first == builder(root, end, _Reader(lambda: None))


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("fault", ["bytes", "remove", "append_future", "symlink", "foreign_name"])
def test_snapshot_reuse_rejects_changed_complete_source(tmp_path, domain, fault):
    root, end = fixture(tmp_path, domain)
    snapshot = freeze(root, domain, end)
    path = next((root / "records" / "prediction").glob("*.json"))
    if fault == "bytes":
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "remove":
        path.unlink()
    elif fault == "symlink":
        saved = path.read_bytes()
        target = tmp_path / "replacement.json"
        target.write_bytes(saved)
        path.unlink()
        path.symlink_to(target)
    elif fault == "foreign_name":
        (path.parent / "unknown.json").write_text("{}")
    else:
        values = snapshot.read(root=root, domain=domain, as_of=end)
        old = next((v[0] if domain is Domain.AU else v) for v in values.values()
                   if (v[0] if domain is Domain.AU else v).kind is RecordKind.PREDICTION)
        EvidenceStore(root).append(replace(old, record_id=old.record_id + ":future",
                                           created_at=(end + timedelta(days=1)).isoformat()))
    with pytest.raises((ValueError, OSError, ResearchIndexError)):
        snapshot.read(root=root, domain=domain, as_of=end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("fault", ["root", "domain", "time"])
def test_snapshot_never_reuses_another_scope(tmp_path, domain, fault):
    root, end = fixture(tmp_path, domain)
    snapshot = freeze(root, domain, end)
    scope = dict(root=root, domain=domain, as_of=end)
    scope[fault if fault != "time" else "as_of"] = {
        "root": tmp_path, "domain": Domain.NBA, "time": end + timedelta(seconds=1),
    }[fault]
    with pytest.raises(ValueError, match="scope"):
        snapshot.read(**scope)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_returned_native_records_are_detached_and_preemption_is_not_cached(tmp_path, domain):
    root, end = fixture(tmp_path, domain)
    snapshot = freeze(root, domain, end)
    records = snapshot.read(root=root, domain=domain, as_of=end)
    before = snapshot.read(root=root, domain=domain, as_of=end)
    records.clear()
    assert snapshot.read(root=root, domain=domain, as_of=end) == before

    def preempt():
        raise RuntimeError("production_active")

    with pytest.raises(RuntimeError, match="production_active"):
        snapshot.read(root=root, domain=domain, as_of=end, checkpoint=preempt)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_snapshot_preserves_missing_parent_rejection_at_construction(tmp_path, domain):
    root, end = fixture(tmp_path, domain)
    next((root / "records" / "decision").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="parent"):
        freeze(root, domain, end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_snapshot_recheck_catches_bytes_changed_after_first_digest_read(tmp_path, domain, monkeypatch):
    root, end = fixture(tmp_path, domain)
    snapshot = freeze(root, domain, end)
    target = next((root / "records" / "prediction").glob("*.json"))
    read = _Reader.read
    changed = []

    def change_after_read(reader, path):
        result = read(reader, path)
        if path == target and not changed:
            changed.append(True)
            target.write_bytes(target.read_bytes() + b" ")
        return result

    monkeypatch.setattr(_Reader, "read", change_after_read)
    with pytest.raises(ResearchIndexError, match="bytes changed"):
        snapshot.read(root=root, domain=domain, as_of=end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("fault", [None, "forged", "during_label"])
def test_native_settlement_snapshot_preserves_report_and_end_of_read_guard(tmp_path, domain, fault, monkeypatch):
    from shared_wong_choi.research_prediction_artifacts import inspect_prediction_artifacts
    root, end = fixture(tmp_path, domain)
    module = native(domain)
    inspect = getattr(module, "_inspect_au_settlement_records" if domain is Domain.AU
                      else "_inspect_hkjc_settlement_records")
    options = dict(root=root, end=end, roots=(), checkpoint=lambda: None,
                   prediction_report=inspect_prediction_artifacts(root=root, domain=domain, as_of=end))
    baseline = inspect(**options)
    snapshot = freeze(root, domain, end)
    if fault == "forged":
        with pytest.raises(ValueError, match="snapshot"):
            inspect(**options, evidence_snapshot={"verified": True})
    elif fault == "during_label":
        parse = module._result_counts
        target = next((root / "records" / "decision").glob("*.json"))

        def mutate(*args):
            result = parse(*args)
            target.write_bytes(target.read_bytes() + b" ")
            return result

        monkeypatch.setattr(module, "_result_counts", mutate)
        with pytest.raises(ResearchIndexError, match="bytes changed"):
            inspect(**options, evidence_snapshot=snapshot)
    else:
        def no_rebuild(*args):
            raise AssertionError("native graph unexpectedly rebuilt")

        monkeypatch.setattr(module, "_evidence", no_rebuild)
        assert inspect(**options, evidence_snapshot=snapshot) == baseline


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_monitoring_corpus_propagates_one_phase_snapshot_to_all_native_label_reads(tmp_path, domain, monkeypatch):
    from shared_wong_choi.research_racing_monitoring_page_runtime import run_racing_monitoring_corpus_request
    from test_research_racing_monitoring_page_runtime import setup
    runtime, registry, options, _ = setup(tmp_path, domain)
    workspace = runtime.warm_root / "snapshot-corpus"
    workspace.mkdir()
    module = native(domain)
    name = "_inspect_au_settlement_records" if domain is Domain.AU else "_inspect_hkjc_settlement_records"
    inspect = getattr(module, name)
    seen = []

    def traced(**kwargs):
        seen.append(kwargs.get("evidence_snapshot"))
        return inspect(**kwargs)

    monkeypatch.setattr(module, name, traced)
    result = run_racing_monitoring_corpus_request({"payload": {
        "domain": domain.value, "evidence_root": str(options["evidence_root"]),
        "as_of": options["as_of"].isoformat(), "relocation_roots": [],
        "max_refs": 5000, "max_records": 100,
    }}, runtime=runtime, workspace=workspace, checkpoint=lambda: None)
    assert result["verified_monitoring_samples"] == 1 and not registry.root.exists()
    assert seen and all(value is not None for value in seen)
    assert len({id(value) for value in seen}) == 1


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_monitoring_replay_constructs_fresh_snapshot_each_phase_and_preserves_prior(tmp_path, domain, monkeypatch):
    from shared_wong_choi.research_racing_monitoring_page_runtime import reconcile_racing_monitoring_corpus
    from test_research_racing_monitoring_page_runtime import reconciliation_setup, corpus_payload
    runtime, registry, options, _, prior, witnesses = reconciliation_setup(tmp_path, domain)
    before = {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()}
    module = native(domain)
    name = "_inspect_au_settlement_records" if domain is Domain.AU else "_inspect_hkjc_settlement_records"
    inspect = getattr(module, name)
    seen = []

    def traced(**kwargs):
        seen.append(kwargs.get("evidence_snapshot"))
        return inspect(**kwargs)

    monkeypatch.setattr(module, name, traced)
    phases = []
    for _ in range(2):
        seen.clear()
        reconcile_racing_monitoring_corpus(payload=corpus_payload(options), runtime=runtime,
                                          workspace=prior, **witnesses)
        assert seen and all(value is not None for value in seen)
        assert len({id(value) for value in seen}) == 1
        phases.append(seen[0])
    assert phases[0] is not phases[1]
    assert {p.name: p.read_bytes() for p in prior.iterdir() if p.is_file()} == before
    assert not registry.root.exists()


def inventories(root, domain, end):
    from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory
    from shared_wong_choi.research_racing_settlement_inventory import freeze_racing_settlement_inventory
    return (freeze_prediction_inventory(root=root, domain=domain, as_of=end),
            freeze_racing_settlement_inventory(root=root, domain=domain, as_of=end))


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_combined_inventory_witnesses_are_rebuilt_once_and_full_source_still_rechecked(tmp_path, domain, monkeypatch):
    from shared_wong_choi import research_prediction_pages as predictions
    from shared_wong_choi import research_racing_settlement_inventory as settlements
    root, end = fixture(tmp_path, domain)
    prediction, settlement = inventories(root, domain, end)
    snapshot = freeze(root, domain, end)
    calls = []
    for module, name in ((predictions, "freeze_prediction_inventory"),
                         (settlements, "freeze_racing_settlement_inventory")):
        original = getattr(module, name)

        def traced(_original=original, _name=name, **kwargs):
            calls.append(_name)
            return _original(**kwargs)

        monkeypatch.setattr(module, name, traced)
    for _ in range(2):
        snapshot.verify_inventories(prediction, settlement, root=root, domain=domain, as_of=end)
    assert calls == ["freeze_prediction_inventory", "freeze_racing_settlement_inventory"]
    target = next((root / "records" / "prediction").glob("*.json"))
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bytes changed"):
        snapshot.verify_inventories(prediction, settlement, root=root, domain=domain, as_of=end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
@pytest.mark.parametrize("fault", ["narrow_prediction", "narrow_settlement", "authority", "future_metadata"])
def test_combined_inventory_rejects_rehashed_forgery_and_changed_source(tmp_path, domain, fault):
    from shared_wong_choi.research_index import _hash
    root, end = fixture(tmp_path, domain)
    prediction, settlement = inventories(root, domain, end)
    snapshot = freeze(root, domain, end)
    snapshot.verify_inventories(prediction, settlement, root=root, domain=domain, as_of=end)
    if fault == "future_metadata":
        values = snapshot.read(root=root, domain=domain, as_of=end)
        old = next((v[0] if domain is Domain.AU else v) for v in values.values()
                   if (v[0] if domain is Domain.AU else v).kind is RecordKind.PREDICTION)
        EvidenceStore(root).append(replace(old, record_id=old.record_id + ":future",
                                           created_at=(end + timedelta(days=1)).isoformat()))
    else:
        report = prediction if fault == "narrow_prediction" else settlement
        if fault == "narrow_prediction":
            report["records"] = []
            report["records_seen"] = report["artifact_refs"] = 0
        elif fault == "narrow_settlement":
            report["settlements"] = []
        else:
            report["model_promotion_allowed"] = True
        report["content_hash"] = _hash({k: v for k, v in report.items() if k != "content_hash"})
    with pytest.raises((ValueError, ResearchIndexError)):
        snapshot.verify_inventories(prediction, settlement, root=root, domain=domain, as_of=end)


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_label_page_combines_complete_checks_before_and_after_without_changing_proof(tmp_path, domain, monkeypatch):
    from shared_wong_choi import research_racing_settlement_pages as pages
    from shared_wong_choi.research_prediction_pages import plan_prediction_pages
    root, end = fixture(tmp_path, domain)
    prediction, settlement = inventories(root, domain, end)
    options = dict(inventory=prediction, settlement_inventory=settlement,
                   page=plan_prediction_pages(prediction)[0], root=root, domain=domain, as_of=end)
    baseline = pages.inspect_racing_settlement_page(**options)
    snapshot = freeze(root, domain, end)
    snapshot.verify_inventories(prediction, settlement, root=root, domain=domain, as_of=end)

    def no_duplicate(*args, **kwargs):
        raise AssertionError("duplicate complete inventory reconstruction")

    monkeypatch.setattr(pages, "verify_prediction_inventory", no_duplicate)
    monkeypatch.setattr(pages, "verify_racing_settlement_inventory", no_duplicate)
    assert pages.inspect_racing_settlement_page(**options, evidence_snapshot=snapshot) == baseline


def test_evidence_path_rejects_parent_symlink_even_with_identical_bytes(tmp_path):
    from shared_wong_choi.research_index import _safe
    target = tmp_path / "source"
    target.mkdir()
    (target / "record.json").write_text("{}")
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(ResearchIndexError, match="non-symlink"):
        _safe(linked / "record.json")


def test_evidence_path_preserves_missing_leaf_read_failure(tmp_path):
    from shared_wong_choi.research_index import _safe
    path = tmp_path / "absent.json"
    assert _safe(path) == path
    with pytest.raises(FileNotFoundError):
        _Reader(lambda: None).read(path)


def test_evidence_path_permission_failure_cannot_become_safe(tmp_path, monkeypatch):
    import shared_wong_choi.research_index as module

    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(module.os, "lstat", denied)
    monkeypatch.setattr(Path, "is_symlink", denied)
    with pytest.raises(PermissionError, match="denied"):
        module._safe(tmp_path / "record.json")
