"""Complete incident scans retain native bounds and physical source rechecks."""
from dataclasses import replace
import os

import pytest

from shared_wong_choi import research_production_incidents as module
from shared_wong_choi.contracts import Domain
from shared_wong_choi.evidence import ArtifactRef, EvidenceRecord, RecordKind
from shared_wong_choi.research_index import _MetadataPages, _Reader, ResearchIndexError
from test_research_production_incidents import NOW, STAMP, source


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_complete_graph_above_flat_recheck_budget_keeps_physical_page_caps(
    tmp_path, monkeypatch, domain,
):
    artifact = ArtifactRef("/unread/result.json", "1" * 64, STAMP, "settlement")
    store = source(tmp_path, domain=domain, event="2026-08-28", artifacts=(artifact,))
    for index in range(20):
        store.append(EvidenceRecord(
            f"wc:{domain.value}:model-release:large-{index}",
            RecordKind.MODEL_RELEASE, domain, STAMP,
            {"release_stage": "shadow", "code_commit": "a" * 40,
             "evaluation_contract_version": "v1", "metadata": "x" * 900000},
        ))
    paths = tuple(store.root.rglob("*.json"))
    total = sum(path.stat().st_size for path in paths)
    assert 33554432 / 2 < total < 33554432
    physical_reads = []
    original = _Reader._read_bytes

    def traced(reader, path):
        result = original(reader, path)
        physical_reads.append((path, reader.max_records, reader.max_record_bytes,
                               reader.max_total_bytes, reader.bytes_read))
        return result

    monkeypatch.setattr(_Reader, "_read_bytes", traced)
    report = module.collect_production_incidents(
        root=store.root, domain=domain, as_of=NOW,
    )
    assert report["records_seen"] == len(paths) == 24
    assert report["findings"] == report["events"] == []
    assert report["model_promotion_allowed"] is False
    assert report["source_coverage_complete"] is False
    assert report["verified_monitoring_samples"] is None
    assert len(physical_reads) == len(paths) * 2
    assert sum(row[4] for row in physical_reads) == total * 2 > 33554432
    assert all(count == 1 and file_cap == 1048576 and
               read <= page_cap == 33554432 // 2
               for _, count, file_cap, page_cap, read in physical_reads)
    assert {path for path, *_ in physical_reads} == set(paths)


def test_incident_pagination_keeps_the_global_record_limit(tmp_path, monkeypatch):
    store = source(tmp_path)

    class ThreeRecords(_MetadataPages):
        def __init__(self, checkpoint):
            super().__init__(checkpoint, max_records=3)

    monkeypatch.setattr(module, "_MetadataPages", ThreeRecords)
    with pytest.raises(ResearchIndexError, match="record limit"):
        module.collect_production_incidents(root=store.root, domain=Domain.NBA, as_of=NOW)


@pytest.mark.parametrize("fault", ["equal_size", "append", "symlink", "remove"])
def test_final_recheck_guards_even_future_unselected_metadata(tmp_path, monkeypatch, fault):
    store = source(tmp_path)
    future = EvidenceRecord(
        "wc:nba:model-release:future", RecordKind.MODEL_RELEASE, Domain.NBA,
        "2027-01-01T00:00:00+00:00",
        {"release_stage": "shadow", "code_commit": "b" * 40,
         "evaluation_contract_version": "v1"},
    )
    store.append(future)
    path = store.path_for(future.kind, future.record_id)

    class MutatingPages(_MetadataPages):
        def recheck(self):
            if fault == "equal_size":
                before = path.stat()
                raw = path.read_bytes()
                changed = raw.replace(b"b" * 40, b"c" * 40)
                assert changed != raw and len(changed) == len(raw)
                path.write_bytes(changed)
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            elif fault == "append":
                store.append(replace(future, record_id=future.record_id + "-new"))
            elif fault == "symlink":
                kept = tmp_path / "retained-models"
                path.parent.rename(kept)
                path.parent.symlink_to(kept, target_is_directory=True)
            else:
                path.unlink()
            return super().recheck()

    monkeypatch.setattr(module, "_MetadataPages", MutatingPages)
    with pytest.raises((ResearchIndexError, OSError)):
        module.collect_production_incidents(root=store.root, domain=Domain.NBA, as_of=NOW)
