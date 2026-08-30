"""Immutable, point-in-time dataset snapshots for Stage 5 research."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .artifact_archive import artifact_digest
from .contracts import Domain
from .research_registry import (
    DatasetManifest,
    DatasetSplit,
    ExperimentSpec,
    SourceWatermark,
)


SNAPSHOT_SCHEMA_VERSION = "wong-choi-dataset-snapshot/v1"


class DatasetSnapshotError(RuntimeError):
    """Raised when a research dataset cannot be frozen without ambiguity."""


class StorageTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetSnapshotError(
            f"{field_name} must be timezone-aware ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatasetSnapshotError(f"{field_name} must include a timezone")
    return parsed


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash_value(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class SplitPolicy:
    train_end: str
    dev_end: str
    terminal_end: str

    def validate(self) -> None:
        train = _aware(self.train_end, "split_policy.train_end")
        dev = _aware(self.dev_end, "split_policy.dev_end")
        terminal = _aware(self.terminal_end, "split_policy.terminal_end")
        if not train < dev < terminal:
            raise DatasetSnapshotError(
                "split cutoffs must satisfy train_end < dev_end < terminal_end"
            )

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "train_end": self.train_end,
            "dev_end": self.dev_end,
            "terminal_end": self.terminal_end,
        }

    def split_for(self, event_at: str) -> str:
        event = _aware(event_at, "row.event_at")
        if event <= _aware(self.train_end, "split_policy.train_end"):
            return "train"
        if event <= _aware(self.dev_end, "split_policy.dev_end"):
            return "dev"
        if event <= _aware(self.terminal_end, "split_policy.terminal_end"):
            return "terminal"
        raise DatasetSnapshotError("event after terminal cutoff")


@dataclass(frozen=True)
class DatasetSource:
    source_id: str
    tier: StorageTier
    artifact_path: Path
    rows_path: Path
    available_at: str
    expected_digest: Mapping[str, Any]
    catalog_record: Path | None = None


@dataclass(frozen=True)
class DatasetSnapshotResult:
    status: str
    path: Path
    manifest: DatasetManifest


def _validate_digest(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    expected_fields = {"sha256", "bytes", "files"}
    if set(value) != expected_fields:
        raise DatasetSnapshotError(
            f"{field_name} requires exactly {sorted(expected_fields)}"
        )
    digest = str(value["sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise DatasetSnapshotError(f"{field_name}.sha256 is invalid")
    try:
        byte_count = int(value["bytes"])
        file_count = int(value["files"])
    except (TypeError, ValueError) as exc:
        raise DatasetSnapshotError(
            f"{field_name} bytes/files must be integers"
        ) from exc
    if byte_count < 0 or file_count < 1:
        raise DatasetSnapshotError(f"{field_name} bytes/files are invalid")
    return {"sha256": digest, "bytes": byte_count, "files": file_count}


def _load_catalog_record(source: DatasetSource) -> dict[str, Any]:
    if source.catalog_record is None:
        raise DatasetSnapshotError(
            f"WARM source {source.source_id!r} requires catalog verification"
        )
    path = source.catalog_record.expanduser()
    if path.is_symlink():
        raise DatasetSnapshotError("WARM catalog verification cannot be symlinked")
    path = path.resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DatasetSnapshotError(
            f"WARM catalog verification unavailable: {path}: {exc}"
        ) from exc
    if payload.get("schema_version") != "wong-choi-artifact/v1":
        raise DatasetSnapshotError("WARM catalog verification uses unsupported schema")
    return payload


def _verify_source(
    source: DatasetSource, *, cutoff: datetime, domain: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not source.source_id.strip():
        raise DatasetSnapshotError("dataset source_id is required")
    try:
        tier = StorageTier(source.tier)
    except ValueError as exc:
        raise DatasetSnapshotError(f"unsupported storage tier: {source.tier!r}") from exc
    if tier is StorageTier.COLD:
        raise DatasetSnapshotError("COLD is restore-only and cannot feed a live research run")
    source_available = _aware(source.available_at, "source.available_at")
    if source_available > cutoff:
        raise DatasetSnapshotError("source availability after point-in-time cutoff")

    artifact_path = source.artifact_path.expanduser()
    rows_path = source.rows_path.expanduser()
    if tier is StorageTier.WARM and not artifact_path.exists():
        raise DatasetSnapshotError(f"WARM artifact unavailable: {artifact_path}")
    if not artifact_path.exists():
        raise DatasetSnapshotError(f"HOT artifact unavailable: {artifact_path}")
    if artifact_path.is_symlink() or rows_path.is_symlink():
        raise DatasetSnapshotError("symlinked dataset sources are not accepted")
    if artifact_path.is_dir() and any(
        path.is_symlink() for path in artifact_path.rglob("*")
    ):
        raise DatasetSnapshotError("symlinked dataset sources are not accepted")
    artifact_path = artifact_path.resolve()
    rows_path = rows_path.resolve()
    if not rows_path.is_file():
        raise DatasetSnapshotError(f"dataset rows file unavailable: {rows_path}")
    if artifact_path.is_dir():
        if not _is_relative_to(rows_path, artifact_path):
            raise DatasetSnapshotError("rows_path is outside the source artifact")
    elif rows_path != artifact_path:
        raise DatasetSnapshotError("file artifact must also be the rows_path")

    expected = _validate_digest(source.expected_digest, "source.expected_digest")
    try:
        actual = artifact_digest(artifact_path)
    except OSError as exc:
        raise DatasetSnapshotError(
            f"dataset source is unreadable: {artifact_path}: {exc}"
        ) from exc
    if actual != expected:
        raise DatasetSnapshotError(f"source digest mismatch: {source.source_id}")

    catalog_path = None
    if tier is StorageTier.WARM:
        catalog = _load_catalog_record(source)
        destination_raw = str(catalog.get("destination") or "")
        try:
            destination = Path(destination_raw).expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise DatasetSnapshotError("WARM catalog destination is invalid") from exc
        if destination != artifact_path:
            raise DatasetSnapshotError("WARM catalog destination does not match source")
        if str(catalog.get("domain") or "").lower() != domain:
            raise DatasetSnapshotError("WARM catalog domain does not match experiment")
        source_digest = catalog.get("source_digest")
        destination_digest = catalog.get("destination_digest")
        if source_digest != destination_digest or destination_digest != expected:
            raise DatasetSnapshotError("WARM catalog digest invariant failed")
        catalog_path = str(source.catalog_record.expanduser().resolve())

    rows: list[dict[str, Any]] = []
    try:
        with rows_path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except ValueError as exc:
                    raise DatasetSnapshotError(
                        f"invalid JSON row {source.source_id}:{line_number}"
                    ) from exc
                if not isinstance(value, dict):
                    raise DatasetSnapshotError(
                        f"dataset row must be an object: {source.source_id}:{line_number}"
                    )
                expected_fields = {"row_id", "event_at", "available_at", "payload"}
                if set(value) != expected_fields:
                    raise DatasetSnapshotError(
                        f"dataset row schema mismatch: {source.source_id}:{line_number}"
                    )
                row_id = str(value["row_id"]).strip()
                if not row_id:
                    raise DatasetSnapshotError("dataset row_id is required")
                event = _aware(str(value["event_at"]), "row.event_at")
                available = _aware(str(value["available_at"]), "row.available_at")
                if event > cutoff:
                    raise DatasetSnapshotError("event after terminal cutoff")
                if available < event:
                    raise DatasetSnapshotError("row availability precedes event")
                if available > cutoff:
                    raise DatasetSnapshotError(
                        "availability after point-in-time cutoff"
                    )
                if available > source_available:
                    raise DatasetSnapshotError(
                        "row availability exceeds its source watermark"
                    )
                if not isinstance(value["payload"], dict):
                    raise DatasetSnapshotError("dataset row payload must be an object")
                rows.append(
                    {
                        "row_id": row_id,
                        "event_at": event.isoformat(),
                        "available_at": available.isoformat(),
                        "payload": value["payload"],
                    }
                )
    except OSError as exc:
        raise DatasetSnapshotError(
            f"dataset rows file is unreadable: {rows_path}: {exc}"
        ) from exc
    if not rows:
        raise DatasetSnapshotError(f"dataset source has no rows: {source.source_id}")
    metadata = {
        "source_id": source.source_id,
        "tier": tier.value,
        "artifact_path": str(artifact_path),
        "rows_path": str(rows_path),
        "available_at": source_available.isoformat(),
        "artifact_digest": expected,
        "catalog_record": catalog_path,
    }
    return metadata, rows


def _snapshot_content(
    spec: ExperimentSpec,
    sources: tuple[DatasetSource, ...],
    split_policy: SplitPolicy,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    tuple[SourceWatermark, ...],
    tuple[DatasetSplit, ...],
    str,
    str,
]:
    spec.validate()
    split_policy.validate()
    cutoff = _aware(split_policy.terminal_end, "split_policy.terminal_end")
    if not sources:
        raise DatasetSnapshotError("at least one HOT or WARM source is required")

    metadata: list[dict[str, Any]] = []
    canonical_rows: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    row_ids: set[str] = set()
    for source in sorted(sources, key=lambda item: item.source_id):
        if source.source_id in source_ids:
            raise DatasetSnapshotError(f"duplicate source_id: {source.source_id}")
        source_ids.add(source.source_id)
        source_metadata, rows = _verify_source(
            source, cutoff=cutoff, domain=spec.domain.value
        )
        metadata.append(source_metadata)
        for row in rows:
            row_id = row["row_id"]
            if row_id in row_ids:
                raise DatasetSnapshotError(f"duplicate row_id: {row_id}")
            row_ids.add(row_id)
            split = split_policy.split_for(row["event_at"])
            canonical_rows.append(
                {
                    "row_id": row_id,
                    "source_id": source.source_id,
                    "event_at": row["event_at"],
                    "available_at": row["available_at"],
                    "split": split,
                    "payload": row["payload"],
                }
            )
    canonical_rows.sort(key=lambda item: (item["event_at"], item["row_id"]))
    grouped = {
        name: [item for item in canonical_rows if item["split"] == name]
        for name in ("train", "dev", "terminal")
    }
    empty = [name for name, values in grouped.items() if not values]
    if empty:
        raise DatasetSnapshotError(f"empty frozen split: {', '.join(empty)}")
    splits = tuple(
        DatasetSplit(name, len(grouped[name]), _hash_value(grouped[name]))
        for name in ("train", "dev", "terminal")
    )
    watermarks = tuple(
        SourceWatermark(
            source_id=item["source_id"],
            available_at=item["available_at"],
            content_digest=item["artifact_digest"]["sha256"],
        )
        for item in metadata
    )
    rows_bytes = b"".join(_canonical_bytes(item) + b"\n" for item in canonical_rows)
    rows_digest = _raw_sha256(rows_bytes)
    sample_hash = _hash_value(
        {
            "domain": spec.domain.value,
            "spec_id": spec.record_id,
            "split_policy": split_policy.to_dict(),
            "sources": metadata,
            "rows_digest": rows_digest,
            "splits": [
                {"name": item.name, "row_count": item.row_count, "sample_hash": item.sample_hash}
                for item in splits
            ],
        }
    )
    return metadata, canonical_rows, watermarks, splits, rows_digest, sample_hash


def _snapshot_manifest_payload(
    dataset_manifest: DatasetManifest,
    *,
    split_policy: SplitPolicy,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "append_only": True,
        "dataset_manifest": dataset_manifest.to_payload(),
        "split_policy": split_policy.to_dict(),
        "sources": sources,
        "rows_file": "rows.jsonl",
    }
    payload["content_hash"] = _hash_value(payload)
    return payload


def _loaded_dataset_manifest(value: Any) -> DatasetManifest:
    if not isinstance(value, dict):
        raise DatasetSnapshotError("previous dataset manifest must be an object")
    expected_fields = {
        "schema_version",
        "record_id",
        "kind",
        "domain",
        "created_at",
        "links",
        "point_in_time_cutoff",
        "sample_hash",
        "row_count",
        "source_watermarks",
        "splits",
        "artifact_digest",
        "content_hash",
    }
    if set(value) != expected_fields:
        raise DatasetSnapshotError("previous dataset manifest schema mismatch")
    links = value.get("links")
    if not isinstance(links, dict) or set(links) != {"spec_id"}:
        raise DatasetSnapshotError("previous dataset manifest links mismatch")
    try:
        watermarks = tuple(
            SourceWatermark(**dict(item)) for item in value["source_watermarks"]
        )
        splits = tuple(DatasetSplit(**dict(item)) for item in value["splits"])
        manifest = DatasetManifest(
            record_id=str(value["record_id"]),
            domain=Domain(str(value["domain"])),
            created_at=str(value["created_at"]),
            spec_id=str(links["spec_id"]),
            point_in_time_cutoff=str(value["point_in_time_cutoff"]),
            sample_hash=str(value["sample_hash"]),
            row_count=int(value["row_count"]),
            source_watermarks=watermarks,
            splits=splits,
            artifact_digest=str(value["artifact_digest"]),
        )
        manifest.validate()
    except (KeyError, TypeError, ValueError) as exc:
        raise DatasetSnapshotError(
            f"invalid previous dataset manifest: {exc}"
        ) from exc
    if manifest.to_payload() != value:
        raise DatasetSnapshotError("previous dataset manifest schema mismatch")
    return manifest


def _load_snapshot(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = path / "manifest.json"
    rows_path = path / "rows.jsonl"
    try:
        manifest_bytes = manifest_path.read_bytes()
        payload = json.loads(manifest_bytes.decode("utf-8"))
        rows_bytes = rows_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise DatasetSnapshotError(f"invalid previous dataset snapshot: {path}: {exc}") from exc
    canonical_manifest = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if manifest_bytes != canonical_manifest:
        raise DatasetSnapshotError("previous dataset snapshot manifest hash mismatch")
    expected_fields = {
        "schema_version",
        "append_only",
        "dataset_manifest",
        "split_policy",
        "sources",
        "rows_file",
        "content_hash",
    }
    if set(payload) != expected_fields:
        raise DatasetSnapshotError("previous dataset snapshot schema mismatch")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise DatasetSnapshotError("unsupported previous dataset snapshot schema")
    if payload.get("append_only") is not True or payload.get("rows_file") != "rows.jsonl":
        raise DatasetSnapshotError("previous dataset snapshot schema mismatch")
    content_hash = payload.pop("content_hash", None)
    if content_hash != _hash_value(payload):
        raise DatasetSnapshotError("previous dataset snapshot manifest hash mismatch")
    payload["content_hash"] = content_hash
    dataset_manifest = _loaded_dataset_manifest(payload.get("dataset_manifest"))
    dataset = payload["dataset_manifest"]
    if dataset_manifest.artifact_digest != _raw_sha256(rows_bytes):
        raise DatasetSnapshotError("previous dataset snapshot rows digest mismatch")
    try:
        split_policy = SplitPolicy(**dict(payload["split_policy"]))
        split_policy.validate()
    except (TypeError, ValueError, DatasetSnapshotError) as exc:
        raise DatasetSnapshotError(
            f"previous dataset snapshot split policy mismatch: {exc}"
        ) from exc
    if split_policy.to_dict() != payload["split_policy"]:
        raise DatasetSnapshotError("previous dataset snapshot split policy mismatch")

    source_fields = {
        "source_id",
        "tier",
        "artifact_path",
        "rows_path",
        "available_at",
        "artifact_digest",
        "catalog_record",
    }
    sources = payload["sources"]
    if not isinstance(sources, list) or not sources:
        raise DatasetSnapshotError("previous dataset snapshot sources mismatch")
    source_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict) or set(source) != source_fields:
            raise DatasetSnapshotError("previous dataset snapshot sources mismatch")
        source_id = str(source["source_id"])
        if not source_id or source_id in source_by_id:
            raise DatasetSnapshotError("previous dataset snapshot sources mismatch")
        try:
            tier = StorageTier(source["tier"])
            available_at = _aware(str(source["available_at"]), "source.available_at")
            digest = _validate_digest(
                source["artifact_digest"], "source.artifact_digest"
            )
        except (TypeError, ValueError, DatasetSnapshotError) as exc:
            raise DatasetSnapshotError(
                f"previous dataset snapshot sources mismatch: {exc}"
            ) from exc
        if tier is StorageTier.COLD:
            raise DatasetSnapshotError("previous dataset snapshot contains COLD source")
        if not str(source["artifact_path"]) or not str(source["rows_path"]):
            raise DatasetSnapshotError("previous dataset snapshot sources mismatch")
        if tier is StorageTier.WARM and not str(source["catalog_record"] or ""):
            raise DatasetSnapshotError("previous dataset snapshot sources mismatch")
        if tier is StorageTier.HOT and source["catalog_record"] is not None:
            raise DatasetSnapshotError("previous dataset snapshot sources mismatch")
        source_by_id[source_id] = {
            "available_at": available_at,
            "digest": digest,
        }

    watermarks = {item.source_id: item for item in dataset_manifest.source_watermarks}
    if set(watermarks) != set(source_by_id):
        raise DatasetSnapshotError("previous dataset snapshot source watermark mismatch")
    for source_id, source in source_by_id.items():
        watermark = watermarks[source_id]
        if (
            _aware(watermark.available_at, "source_watermark.available_at")
            != source["available_at"]
            or watermark.content_digest != source["digest"]["sha256"]
        ):
            raise DatasetSnapshotError(
                "previous dataset snapshot source watermark mismatch"
            )

    rows: list[dict[str, Any]] = []
    try:
        decoded_rows = rows_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetSnapshotError("invalid previous snapshot row encoding") from exc
    row_ids: set[str] = set()
    for line_number, raw in enumerate(decoded_rows.splitlines(), start=1):
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except ValueError as exc:
            raise DatasetSnapshotError(
                f"invalid previous snapshot row: {line_number}"
            ) from exc
        row_fields = {
            "row_id",
            "source_id",
            "event_at",
            "available_at",
            "split",
            "payload",
        }
        if not isinstance(item, dict) or set(item) != row_fields:
            raise DatasetSnapshotError("invalid previous snapshot row schema")
        row_id = str(item["row_id"])
        source_id = str(item["source_id"])
        if not row_id or row_id in row_ids or source_id not in source_by_id:
            raise DatasetSnapshotError("invalid previous snapshot row schema")
        row_ids.add(row_id)
        event_at = _aware(str(item["event_at"]), "row.event_at")
        available_at = _aware(str(item["available_at"]), "row.available_at")
        if available_at < event_at:
            raise DatasetSnapshotError("previous snapshot row availability precedes event")
        if item["split"] != split_policy.split_for(event_at.isoformat()):
            raise DatasetSnapshotError("previous snapshot row split mismatch")
        if available_at > source_by_id[source_id]["available_at"]:
            raise DatasetSnapshotError("previous snapshot row exceeds source watermark")
        if not isinstance(item["payload"], dict):
            raise DatasetSnapshotError("invalid previous snapshot row schema")
        rows.append(item)
    canonical_rows_bytes = b"".join(_canonical_bytes(item) + b"\n" for item in rows)
    if rows_bytes != canonical_rows_bytes:
        raise DatasetSnapshotError("previous dataset snapshot rows are not canonical")
    if rows != sorted(rows, key=lambda item: (item["event_at"], item["row_id"])):
        raise DatasetSnapshotError("previous dataset snapshot row order mismatch")
    if dataset_manifest.row_count != len(rows):
        raise DatasetSnapshotError("previous dataset snapshot row_count mismatch")
    grouped = {
        name: [item for item in rows if item["split"] == name]
        for name in ("train", "dev", "terminal")
    }
    expected_splits = {
        item.name: (item.row_count, item.sample_hash)
        for item in dataset_manifest.splits
    }
    actual_splits = {
        name: (len(values), _hash_value(values))
        for name, values in grouped.items()
    }
    if expected_splits != actual_splits:
        raise DatasetSnapshotError("previous dataset snapshot split digest mismatch")
    expected_sample_hash = _hash_value(
        {
            "domain": dataset_manifest.domain.value,
            "spec_id": dataset_manifest.spec_id,
            "split_policy": split_policy.to_dict(),
            "sources": sources,
            "rows_digest": dataset_manifest.artifact_digest,
            "splits": [
                {
                    "name": item.name,
                    "row_count": item.row_count,
                    "sample_hash": item.sample_hash,
                }
                for item in dataset_manifest.splits
            ],
        }
    )
    if dataset_manifest.sample_hash != expected_sample_hash:
        raise DatasetSnapshotError("previous dataset snapshot sample hash mismatch")
    return payload, rows


def _enforce_previous_floor(
    previous_snapshot: Path,
    *,
    spec: ExperimentSpec,
    split_policy: SplitPolicy,
    current_rows: list[dict[str, Any]],
) -> None:
    payload, previous_rows = _load_snapshot(previous_snapshot.expanduser().resolve())
    dataset = payload["dataset_manifest"]
    if dataset.get("domain") != spec.domain.value:
        raise DatasetSnapshotError("previous snapshot domain mismatch")
    if payload.get("split_policy") != split_policy.to_dict():
        raise DatasetSnapshotError("previous snapshot split policy mismatch")
    previous_by_id = {str(item["row_id"]): item for item in previous_rows}
    current_by_id = {str(item["row_id"]): item for item in current_rows}
    missing = sorted(set(previous_by_id).difference(current_by_id))
    if missing:
        raise DatasetSnapshotError(
            f"corpus shrink blocked; missing {len(missing)} prior rows"
        )
    changed = sorted(
        row_id
        for row_id, previous in previous_by_id.items()
        if current_by_id[row_id] != previous
    )
    if changed:
        raise DatasetSnapshotError(
            f"historical row mutation blocked; changed {len(changed)} prior rows"
        )


def load_dataset_snapshot(path: Path) -> DatasetSnapshotResult:
    """Verify and load one immutable snapshot without resolving live sources."""
    resolved = path.expanduser().resolve()
    payload, _rows = _load_snapshot(resolved)
    manifest = _loaded_dataset_manifest(payload["dataset_manifest"])
    if resolved.name != manifest.sample_hash:
        raise DatasetSnapshotError("dataset snapshot path does not match sample hash")
    return DatasetSnapshotResult("verified", resolved, manifest)


def build_dataset_snapshot(
    spec: ExperimentSpec,
    *,
    sources: tuple[DatasetSource, ...],
    split_policy: SplitPolicy,
    snapshot_root: Path,
    previous_snapshot: Path | None = None,
) -> DatasetSnapshotResult:
    """Freeze normalized HOT/WARM rows into one deterministic dataset snapshot."""
    (
        source_metadata,
        canonical_rows,
        watermarks,
        splits,
        rows_digest,
        sample_hash,
    ) = _snapshot_content(spec, sources, split_policy)
    if previous_snapshot is not None:
        _enforce_previous_floor(
            previous_snapshot,
            spec=spec,
            split_policy=split_policy,
            current_rows=canonical_rows,
        )
    dataset_manifest = DatasetManifest(
        record_id=f"wc:{spec.domain.value}:dataset-manifest:{sample_hash[:24]}",
        domain=spec.domain,
        created_at=split_policy.terminal_end,
        spec_id=spec.record_id,
        point_in_time_cutoff=split_policy.terminal_end,
        sample_hash=sample_hash,
        row_count=len(canonical_rows),
        source_watermarks=watermarks,
        splits=splits,
        artifact_digest=rows_digest,
    )
    dataset_manifest.validate()
    manifest_payload = _snapshot_manifest_payload(
        dataset_manifest,
        split_policy=split_policy,
        sources=source_metadata,
    )
    root = snapshot_root.expanduser().resolve() / spec.domain.value
    final = root / sample_hash
    if final.exists():
        existing_manifest, _existing_rows = _load_snapshot(final)
        if existing_manifest != manifest_payload:
            raise DatasetSnapshotError(
                f"immutable dataset snapshot conflict: {sample_hash}"
            )
        return DatasetSnapshotResult("duplicate", final, dataset_manifest)

    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{sample_hash}.partial-{os.getpid()}-{uuid4().hex}"
    temporary.mkdir()
    try:
        rows_bytes = b"".join(
            _canonical_bytes(item) + b"\n" for item in canonical_rows
        )
        (temporary / "rows.jsonl").write_bytes(rows_bytes)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        if _raw_sha256((temporary / "rows.jsonl").read_bytes()) != rows_digest:
            raise DatasetSnapshotError("dataset rows changed during snapshot write")
        try:
            temporary.rename(final)
        except FileExistsError:
            existing_manifest, _existing_rows = _load_snapshot(final)
            if existing_manifest != manifest_payload:
                raise DatasetSnapshotError(
                    f"immutable dataset snapshot conflict: {sample_hash}"
                )
            shutil.rmtree(temporary, ignore_errors=True)
            return DatasetSnapshotResult("duplicate", final, dataset_manifest)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return DatasetSnapshotResult("created", final, dataset_manifest)
