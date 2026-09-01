from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.artifact_archive import archive_copy, artifact_digest
from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_dataset import (
    DatasetSnapshotError,
    DatasetSource,
    SplitPolicy,
    StorageTier,
    build_dataset_snapshot,
)
from shared_wong_choi.research_registry import ExperimentSpec


CUTOFF = "2026-08-29T23:59:00+00:00"
SOURCE_AVAILABLE = "2026-08-28T12:00:00+00:00"


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def experiment_spec() -> ExperimentSpec:
    return ExperimentSpec(
        record_id="wc:au:experiment-spec:dataset-v1",
        domain=Domain.AU,
        created_at="2026-08-30T00:00:00+00:00",
        hypothesis="stable dataset fixture",
        evaluation_ruler_id="au-v2",
        evaluation_ruler_digest="1" * 64,
        baseline_commit="a" * 40,
        candidate_commit="b" * 40,
        preregistered_metrics=("gold", "ndcg_at_5"),
        seed=7,
        commands=("python3 evaluate.py --platform au",),
        protocol_artifact_digest="2" * 64,
    )


def rows() -> list[dict]:
    return [
        {
            "row_id": "race-001",
            "event_at": "2026-08-01T03:00:00+00:00",
            "available_at": "2026-08-02T03:00:00+00:00",
            "payload": {"winner": 4, "venue": "A"},
        },
        {
            "row_id": "race-002",
            "event_at": "2026-08-15T03:00:00+00:00",
            "available_at": "2026-08-16T03:00:00+00:00",
            "payload": {"winner": 2, "venue": "B"},
        },
        {
            "row_id": "race-003",
            "event_at": "2026-08-25T03:00:00+00:00",
            "available_at": "2026-08-26T03:00:00+00:00",
            "payload": {"winner": 7, "venue": "C"},
        },
    ]


def policy() -> SplitPolicy:
    return SplitPolicy(
        train_end="2026-08-10T23:59:00+00:00",
        dev_end="2026-08-20T23:59:00+00:00",
        terminal_end=CUTOFF,
    )


def write_artifact(root: Path, values: list[dict]) -> tuple[Path, Path]:
    artifact = root / "artifact"
    artifact.mkdir(parents=True)
    rows_path = artifact / "rows.jsonl"
    rows_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
            for item in values
        ),
        encoding="utf-8",
    )
    return artifact, rows_path


def hot_source(root: Path, values: list[dict] | None = None) -> DatasetSource:
    artifact, rows_path = write_artifact(
        root, rows() if values is None else values
    )
    return DatasetSource(
        source_id="au-hot-results",
        tier=StorageTier.HOT,
        artifact_path=artifact,
        rows_path=rows_path,
        available_at=SOURCE_AVAILABLE,
        expected_digest=artifact_digest(artifact),
    )


def warm_source(tmp_path: Path) -> tuple[DatasetSource, Path]:
    hot_root = tmp_path / "hot"
    artifact, _rows_path = write_artifact(hot_root, rows())
    warm_root = tmp_path / "warm"
    warm_root.mkdir()
    archived = archive_copy(
        artifact,
        warm_root=warm_root,
        catalog_root=tmp_path / "catalog",
        domain="au",
        artifact_class="research-normalized-dataset",
        allowed_roots=[hot_root],
        created_at="2026-08-28T13:00:00+00:00",
    )
    destination = Path(archived["destination"])
    return (
        DatasetSource(
            source_id="au-warm-results",
            tier=StorageTier.WARM,
            artifact_path=destination,
            rows_path=destination / "rows.jsonl",
            available_at=SOURCE_AVAILABLE,
            expected_digest=archived["destination_digest"],
            catalog_record=Path(archived["manifest"]),
        ),
        destination,
    )


def test_same_inputs_create_one_immutable_snapshot_and_same_manifest(
    tmp_path: Path,
) -> None:
    source = hot_source(tmp_path / "source")
    snapshot_root = tmp_path / "snapshots"

    first = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=snapshot_root,
    )
    first_bytes = (first.path / "manifest.json").read_bytes()
    second = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=snapshot_root,
    )

    assert first.status == "created"
    assert second.status == "duplicate"
    assert first.path == second.path
    assert first.manifest.sample_hash == second.manifest.sample_hash
    assert (second.path / "manifest.json").read_bytes() == first_bytes
    assert {item.name: item.row_count for item in first.manifest.splits} == {
        "train": 1,
        "dev": 1,
        "terminal": 1,
    }


def test_material_row_change_creates_a_new_sample_hash(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source = hot_source(source_root)
    first = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )
    changed = rows()
    changed[1]["payload"]["winner"] = 9
    (source.rows_path).write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in changed),
        encoding="utf-8",
    )
    changed_source = replace(source, expected_digest=artifact_digest(source.artifact_path))

    second = build_dataset_snapshot(
        experiment_spec(),
        sources=(changed_source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )

    assert second.manifest.sample_hash != first.manifest.sample_hash
    assert second.path != first.path


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("event_at", "2026-08-30T00:00:00+00:00", "event after terminal cutoff"),
        (
            "available_at",
            "2026-08-30T00:00:00+00:00",
            "availability after point-in-time cutoff",
        ),
        (
            "available_at",
            "2026-08-24T00:00:00+00:00",
            "availability precedes event",
        ),
    ],
)
def test_future_dated_rows_fail_closed(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    values = rows()
    values[-1][field] = value
    source = hot_source(tmp_path / "source", values)

    with pytest.raises(DatasetSnapshotError, match=message):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_verified_warm_is_accepted_but_missing_warm_blocks(tmp_path: Path) -> None:
    source, destination = warm_source(tmp_path)
    result = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )
    assert result.status == "created"
    destination.rename(tmp_path / "warm-offline")

    with pytest.raises(DatasetSnapshotError, match="WARM artifact unavailable"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "other-snapshots",
        )


def test_warm_catalog_must_belong_to_experiment_domain(tmp_path: Path) -> None:
    source, _destination = warm_source(tmp_path)
    catalog = json.loads(source.catalog_record.read_text(encoding="utf-8"))
    catalog["domain"] = "hkjc"
    source.catalog_record.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(DatasetSnapshotError, match="catalog domain"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_unverified_warm_and_cold_runtime_inputs_are_rejected(tmp_path: Path) -> None:
    source = hot_source(tmp_path / "source")

    with pytest.raises(DatasetSnapshotError, match="catalog verification"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(replace(source, tier=StorageTier.WARM),),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )
    with pytest.raises(DatasetSnapshotError, match="COLD is restore-only"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(replace(source, tier=StorageTier.COLD),),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_digest_mismatch_blocks_instead_of_accepting_changed_source(
    tmp_path: Path,
) -> None:
    source = hot_source(tmp_path / "source")
    source.rows_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(DatasetSnapshotError, match="digest mismatch"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_previous_snapshot_blocks_corpus_shrink(tmp_path: Path) -> None:
    values = rows()
    values.insert(
        1,
        {
            "row_id": "race-001b",
            "event_at": "2026-08-05T03:00:00+00:00",
            "available_at": "2026-08-06T03:00:00+00:00",
            "payload": {"winner": 8, "venue": "A"},
        },
    )
    source = hot_source(tmp_path / "source", values)
    first = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )
    source.rows_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in values[1:]),
        encoding="utf-8",
    )
    smaller = replace(source, expected_digest=artifact_digest(source.artifact_path))

    with pytest.raises(DatasetSnapshotError, match="corpus shrink"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(smaller,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
            previous_snapshot=first.path,
        )


def test_previous_snapshot_blocks_historical_row_mutation(tmp_path: Path) -> None:
    source = hot_source(tmp_path / "source")
    first = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )
    changed = rows()
    changed[1]["payload"]["winner"] = 9
    source.rows_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in changed),
        encoding="utf-8",
    )
    changed_source = replace(
        source, expected_digest=artifact_digest(source.artifact_path)
    )

    with pytest.raises(DatasetSnapshotError, match="historical row mutation"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(changed_source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
            previous_snapshot=first.path,
        )


@pytest.mark.parametrize("target", ["manifest.json", "rows.jsonl"])
def test_tampered_previous_snapshot_is_rejected(
    tmp_path: Path, target: str
) -> None:
    source = hot_source(tmp_path / "source")
    first = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )
    target_path = first.path / target
    target_path.write_bytes(target_path.read_bytes() + b" ")

    with pytest.raises(DatasetSnapshotError, match="hash mismatch|digest mismatch"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "other-snapshots",
            previous_snapshot=first.path,
        )


def test_rehashed_unknown_snapshot_field_is_rejected(tmp_path: Path) -> None:
    source = hot_source(tmp_path / "source")
    first = build_dataset_snapshot(
        experiment_spec(),
        sources=(source,),
        split_policy=policy(),
        snapshot_root=tmp_path / "snapshots",
    )
    manifest_path = first.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("content_hash")
    manifest["unreviewed_override"] = True
    manifest["content_hash"] = canonical_hash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(DatasetSnapshotError, match="snapshot schema mismatch"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "other-snapshots",
            previous_snapshot=first.path,
        )


def test_row_availability_cannot_exceed_source_watermark(tmp_path: Path) -> None:
    values = rows()
    values[-1]["available_at"] = "2026-08-29T00:00:00+00:00"
    source = hot_source(tmp_path / "source", values)

    with pytest.raises(DatasetSnapshotError, match="source watermark"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_nested_symlink_source_is_rejected(tmp_path: Path) -> None:
    source = hot_source(tmp_path / "source")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (source.artifact_path / "linked.txt").symlink_to(outside)
    linked_source = replace(
        source, expected_digest=artifact_digest(source.artifact_path)
    )

    with pytest.raises(DatasetSnapshotError, match="symlinked dataset"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(linked_source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_duplicate_row_id_across_sources_is_rejected(tmp_path: Path) -> None:
    first = hot_source(tmp_path / "first")
    second = replace(
        hot_source(tmp_path / "second"), source_id="au-hot-results-2"
    )

    with pytest.raises(DatasetSnapshotError, match="duplicate row_id"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(first, second),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )


def test_each_frozen_split_must_have_rows(tmp_path: Path) -> None:
    only_train = [rows()[0]]
    source = hot_source(tmp_path / "source", only_train)

    with pytest.raises(DatasetSnapshotError, match="empty frozen split"):
        build_dataset_snapshot(
            experiment_spec(),
            sources=(source,),
            split_policy=policy(),
            snapshot_root=tmp_path / "snapshots",
        )
