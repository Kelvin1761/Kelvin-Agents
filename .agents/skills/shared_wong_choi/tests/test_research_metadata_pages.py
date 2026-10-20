from dataclasses import replace
import os

import pytest

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import EvidenceStore, RecordKind
from shared_wong_choi.research_index import ResearchIndexError, _Reader
from test_research_racing_settlement_inventory import fixture


def test_metadata_page_performs_one_native_path_guard_per_physical_read(tmp_path, monkeypatch):
    from shared_wong_choi import research_index as module
    path = tmp_path / "record.json"
    path.write_text("{}")
    calls, guard = [], module._safe

    def traced(value):
        calls.append(value)
        return guard(value)

    monkeypatch.setattr(module, "_safe", traced)
    reader = module._MetadataPages(lambda: None)
    reader.read(path)
    reader.recheck()
    assert calls == [path, path]


def test_metadata_pages_keep_native_bounds_and_cumulative_io(tmp_path, monkeypatch):
    from shared_wong_choi.research_index import _MetadataPages
    reads = []
    original = _Reader._read_bytes

    def traced(reader, path):
        result = original(reader, path)
        reads.append((id(reader), reader.bytes_read, reader.max_total_bytes))
        return result

    monkeypatch.setattr(_Reader, "_read_bytes", traced)
    reader = _MetadataPages(lambda: None, max_record_bytes=64, max_total_bytes=128)
    for index in range(8):
        path = tmp_path / f"{index}.json"
        path.write_text('{"value":1}' + " " * 40)
        reader.read(path)
    reader.recheck()
    assert len(reader.files) == 8
    assert len(reads) == 16
    assert reader.bytes_read > reader.max_total_bytes
    assert all(observed <= limit == 64 for _, observed, limit in reads)


def test_failed_initial_json_parse_does_not_become_a_verified_recheck(tmp_path):
    from shared_wong_choi.research_safety import ResearchSafetyError
    path = tmp_path / "invalid.json"
    path.write_text("{invalid")
    reader = _Reader(lambda: None)
    with pytest.raises((ValueError, ResearchSafetyError)):
        reader.read(path)
    with pytest.raises((ValueError, ResearchSafetyError)):
        reader.recheck()


@pytest.mark.parametrize("paged", [False, True])
def test_recheck_detects_equal_size_mutation_with_original_mtime(tmp_path, paged):
    from shared_wong_choi.research_index import _MetadataPages
    path = tmp_path / "record.json"
    path.write_text('{"value":1}')
    reader = (_MetadataPages if paged else _Reader)(lambda: None)
    reader.read(path)
    before = path.stat()
    path.write_text('{"value":2}')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ResearchIndexError, match="bytes changed"):
        reader.recheck()


@pytest.mark.parametrize("paged", [False, True])
def test_recheck_rejects_parent_replaced_by_symlink_to_identical_bytes(tmp_path, paged):
    from shared_wong_choi.research_index import _MetadataPages
    parent = tmp_path / "records"
    parent.mkdir()
    path = parent / "record.json"
    path.write_text('{"value":1}')
    reader = (_MetadataPages if paged else _Reader)(lambda: None)
    reader.read(path)
    moved = tmp_path / "original-records"
    parent.rename(moved)
    parent.symlink_to(moved, target_is_directory=True)
    assert path.read_bytes() == (moved / path.name).read_bytes()
    with pytest.raises(ResearchIndexError, match="non-symlink"):
        reader.recheck()


@pytest.mark.parametrize("fault", ["file_size", "page_bytes", "record_count", "changed_bytes"])
def test_metadata_pages_do_not_bypass_native_guards(tmp_path, fault):
    from shared_wong_choi.research_index import _MetadataPages
    path = tmp_path / "first.json"
    path.write_text('{"value":1}' + " " * 40)
    reader = _MetadataPages(lambda: None, max_records=1,
                            max_record_bytes=32 if fault == "file_size" else 64,
                            max_total_bytes=64 if fault == "page_bytes" else 128)
    if fault in {"file_size", "page_bytes"}:
        with pytest.raises(ResearchIndexError):
            reader.read(path)
    else:
        reader.read(path)
        if fault == "record_count":
            other = tmp_path / "second.json"
            other.write_text("{}")
            with pytest.raises(ResearchIndexError, match="record limit"):
                reader.read(other)
        else:
            path.write_text('{"value":2}' + " " * 40)
            with pytest.raises(ResearchIndexError, match="bytes changed"):
                reader.recheck()


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_full_native_metadata_over_half_budget_is_complete_and_rechecked(tmp_path, domain):
    from shared_wong_choi.research_native_evidence_snapshot import _NativeEvidenceSnapshot
    from shared_wong_choi.research_prediction_pages import freeze_prediction_inventory
    from shared_wong_choi.research_racing_settlement_inventory import freeze_racing_settlement_inventory
    from shared_wong_choi.research_prediction_artifacts import _records
    root, end = fixture(tmp_path, domain)
    store = EvidenceStore(root)
    prediction = _records(root, domain, end, _Reader(lambda: None))[0][0]
    for index in range(40):
        copied = replace(prediction, record_id=f"{prediction.record_id}:large-{index:04d}")
        path = store.append(copied).path
        raw = path.read_bytes()
        path.write_bytes(raw + b" " * (512 * 1024 - len(raw)))
    before = {path: path.stat().st_size for path in root.glob("records/*/*.json")}
    snapshot = _NativeEvidenceSnapshot(root=root, domain=domain, as_of=end)
    records = snapshot.read(root=root, domain=domain, as_of=end)
    assert sum((value[0] if domain is Domain.AU else value).kind is RecordKind.PREDICTION
               for value in records.values()) == 41
    predictions = freeze_prediction_inventory(root=root, domain=domain, as_of=end)
    settlements = freeze_racing_settlement_inventory(root=root, domain=domain, as_of=end)
    assert predictions["records_seen"] == 41
    assert settlements["evidence_records_seen"] == len(records)
    assert settlements["verified_monitoring_samples"] is None
    assert settlements["model_promotion_allowed"] is False
    assert {path: path.stat().st_size for path in before} == before
    target = next(path for path in before if "large-0000" in path.name)
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises((ResearchIndexError, ValueError), match="bytes changed"):
        snapshot.read(root=root, domain=domain, as_of=end)
