"""Deterministic create-only prediction snapshots for domains without one."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


SOURCE_METADATA_NAME = "Research_Source_File_Metadata.json"
SOURCE_METADATA_SCHEMA = "wong-choi-snapshot-source-metadata/v1"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 512 * 1024 * 1024


def _source_identity(value) -> tuple:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, value.st_mode)


def _source_record(path: Path, *, max_bytes: int = MAX_SOURCE_BYTES) -> tuple[dict, tuple]:
    """Observe original filesystem metadata; it is NOT availability evidence."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= max_bytes:
            raise ValueError("snapshot metadata requires a bounded regular file")
        digest, count = hashlib.sha256(), 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, max_bytes - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > max_bytes:
                raise ValueError("snapshot source exceeds metadata read bound")
            digest.update(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if _source_identity(before) != _source_identity(after) or count != before.st_size:
        raise RuntimeError("snapshot source changed during metadata capture")
    return {"name": path.name, "bytes": count, "sha256": digest.hexdigest(),
            "mtime_ns": before.st_mtime_ns, "mode": stat.S_IMODE(before.st_mode)}, _source_identity(after)


def _copy_bound_source(source: Path, destination: Path, expected: dict, identity: tuple) -> None:
    """Copy at most the captured size; growth cannot consume unbounded scratch."""
    if os.utime not in os.supports_fd:
        raise RuntimeError("descriptor metadata copy unavailable")
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    target_fd = None
    try:
        before = os.fstat(source_fd)
        if _source_identity(before) != identity:
            raise RuntimeError("snapshot source changed before bounded copy")
        target_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        digest, count = hashlib.sha256(), 0
        while count < expected["bytes"]:
            chunk = os.read(source_fd, min(1024 * 1024, expected["bytes"] - count))
            if not chunk:
                raise RuntimeError("snapshot source truncated during bounded copy")
            digest.update(chunk)
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(target_fd, remaining)
                if written <= 0:
                    raise OSError("snapshot bounded copy made no progress")
                remaining = remaining[written:]
            count += len(chunk)
        if (os.read(source_fd, 1) or _source_identity(os.fstat(source_fd)) != identity
                or digest.hexdigest() != expected["sha256"]):
            raise RuntimeError("snapshot source changed during bounded copy")
        os.fchmod(target_fd, expected["mode"])
        os.utime(target_fd, ns=(before.st_atime_ns, expected["mtime_ns"]))
        os.fsync(target_fd)
        published = os.stat(destination, follow_symlinks=False)
        held = os.fstat(target_fd)
        if (published.st_dev, published.st_ino) != (held.st_dev, held.st_ino):
            raise RuntimeError("snapshot copied path changed ownership")
    finally:
        try:
            if target_fd is not None:
                os.close(target_fd)
        finally:
            os.close(source_fd)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_immutable_snapshot(
    source_dir: Path,
    *,
    domain: str,
    event_id: str,
    patterns: Iterable[str],
    recommendations: Iterable[Mapping[str, Any]] = (),
    additional_files: Mapping[str, bytes] | None = None,
    root_name: str = "_prediction_snapshots",
    at: datetime | None = None,
    capture_file_metadata: bool = False,
    metadata_source_names: Iterable[str] | None = None,
    reuse_latest_only: bool = False,
) -> Path:
    if type(capture_file_metadata) is not bool:
        raise ValueError("boolean metadata capture flag required")
    if type(reuse_latest_only) is not bool:
        raise ValueError("boolean snapshot reuse policy required")
    if metadata_source_names is not None and not capture_file_metadata:
        raise ValueError("metadata source selection requires metadata capture")
    source_dir = source_dir.resolve()
    files = sorted(
        {
            path
            for pattern in patterns
            for path in source_dir.glob(pattern)
            if path.is_file() and path.stat().st_size > 0
        }
    )
    if not files:
        raise RuntimeError(f"no prediction artifacts in {source_dir}")
    selected = [dict(item) for item in recommendations]
    generated: dict[str, bytes] = {}
    for raw_name, raw_payload in (additional_files or {}).items():
        name = str(raw_name)
        path = Path(name)
        if (not name or path.name != name or name == "manifest.json"
                or not isinstance(raw_payload, bytes) or not raw_payload):
            raise ValueError("additional snapshot files require a safe basename and non-empty bytes")
        generated[name] = raw_payload
    source_names = {path.name for path in files}
    if len(source_names) != len(files):
        raise ValueError("snapshot source basenames must be unique")
    originals, identities = {}, {}
    if capture_file_metadata:
        if SOURCE_METADATA_NAME in generated or SOURCE_METADATA_NAME in source_names:
            raise ValueError("reserved snapshot source metadata filename")
        if len(files) > 5000:
            raise ValueError("snapshot metadata source count bound exceeded")
        source_bytes = 0
        for path in files:
            originals[path.name], identities[path.name] = _source_record(
                path, max_bytes=min(MAX_SOURCE_BYTES, MAX_TOTAL_SOURCE_BYTES - source_bytes),
            )
            source_bytes += originals[path.name]["bytes"]
        selected_names = list(originals) if metadata_source_names is None else list(metadata_source_names)
        if (any(not isinstance(name, str) or name not in originals for name in selected_names)
                or len(set(selected_names)) != len(selected_names)):
            raise ValueError("metadata must select unique captured source basenames")
        if sum(item["bytes"] for item in originals.values()) > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError("snapshot metadata total source bound exceeded")
        generated[SOURCE_METADATA_NAME] = (json.dumps({
            "schema_version": SOURCE_METADATA_SCHEMA, "domain": domain, "event_id": event_id,
            "files": [originals[name] for name in sorted(selected_names)], "point_in_time_verified": False,
            "resource_completeness_verified": False, "model_promotion_allowed": False,
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    collision = source_names.intersection(generated)
    if collision:
        raise ValueError(f"additional snapshot file collides with source: {sorted(collision)}")
    file_manifest = [
        {key: item[key] for key in ("name", "bytes", "sha256")}
        for item in originals.values()
    ] if capture_file_metadata else [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    file_manifest.extend(
        {
            "name": name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for name, payload in generated.items()
    )
    file_manifest.sort(key=lambda item: item["name"])
    signature = hashlib.sha256(
        json.dumps(
            {"files": file_manifest, "recommendations": selected},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=not capture_file_metadata,
        ).encode("utf-8")
    ).hexdigest()
    root = source_dir / root_name
    if capture_file_metadata and root.is_symlink():
        raise ValueError("symlinked snapshot root cannot bind source metadata")
    # Old snapshots moved to the archive disk (wongchoi_paths.SNAPSHOT_OFFLOAD_SUFFIX).
    # A new local folder would shadow them: readers prefer the local one.
    if (source_dir / f"{root_name}.offloaded.json").exists():
        raise RuntimeError(
            f"{source_dir.name}: snapshots are offloaded to the archive disk; "
            "restore first with .agents/scripts/offload_prediction_snapshots.py --restore"
        )
    if root.exists():
        manifests = sorted(root.glob("*/manifest.json"), reverse=True)
        for manifest_path in manifests[:1] if reuse_latest_only else manifests:
            if capture_file_metadata and (manifest_path.is_symlink() or manifest_path.parent.is_symlink()):
                raise ValueError("symlinked snapshot cannot bind source metadata")
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if existing.get("signature") == signature:
                if capture_file_metadata:
                    if (existing.get("schema_version") != "wong-choi-prediction-snapshot/v1"
                            or existing.get("domain") != domain or existing.get("event_id") != event_id
                            or existing.get("append_only") is not True):
                        raise RuntimeError("existing metadata snapshot manifest differs")
                    for key, expected in (("files", file_manifest), ("recommendations", selected)):
                        if (json.dumps(existing.get(key), sort_keys=True, allow_nan=False)
                                != json.dumps(expected, sort_keys=True, allow_nan=False)):
                            raise RuntimeError("existing metadata snapshot manifest contents differ")
                    try:
                        created = datetime.fromisoformat(existing["created_at"])
                        if created.tzinfo is None or created.utcoffset() is None:
                            raise ValueError("aware snapshot clock required")
                    except (KeyError, TypeError, ValueError) as exc:
                        raise RuntimeError("existing metadata snapshot clock invalid") from exc
                    expected_name = created.strftime("%Y%m%dT%H%M%S.%f%z") + f"-{signature[:12]}"
                    if manifest_path.parent.name != expected_name:
                        raise RuntimeError("existing metadata snapshot clock/path identity differs")
                    for expected in file_manifest:
                        actual, _ = _source_record(manifest_path.parent / expected["name"])
                        if any(actual[key] != expected[key] for key in ("name", "bytes", "sha256")):
                            raise RuntimeError("existing metadata snapshot bytes differ")
                        if expected["name"] in selected_names and actual != originals[expected["name"]]:
                            raise RuntimeError("existing metadata snapshot source metadata differs")
                return manifest_path.parent

    clock = at or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("snapshot timestamp must be timezone-aware")
    root.mkdir(parents=True, exist_ok=True)
    name = clock.strftime("%Y%m%dT%H%M%S.%f%z") + f"-{signature[:12]}"
    temporary = root / f".{name}.tmp"
    final = root / name
    if final.exists() or temporary.exists():
        raise RuntimeError(f"snapshot destination already exists: {final}")
    temporary.mkdir()
    try:
        for source in files:
            if capture_file_metadata:
                _copy_bound_source(source, temporary / source.name, originals[source.name], identities[source.name])
                current, identity = _source_record(source)
                copied, _ = _source_record(temporary / source.name)
                if (current != originals[source.name] or identity != identities[source.name]
                        or copied != originals[source.name]):
                    raise RuntimeError("snapshot source or copied metadata changed")
            else:
                shutil.copy2(source, temporary / source.name)
        for name, payload in sorted(generated.items()):
            (temporary / name).write_bytes(payload)
        manifest = {
            "schema_version": "wong-choi-prediction-snapshot/v1",
            "domain": domain,
            "event_id": event_id,
            "created_at": clock.isoformat(),
            "signature": signature,
            "append_only": True,
            "recommendations": selected,
            "files": file_manifest,
        }
        if domain == "hkjc":
            manifest.update(platform="hkjc", meeting=event_id, immutable_prediction_snapshot=True)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return final
