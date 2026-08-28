"""Verified, copy-only artifact archive used by the Wong Choi storage tiers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


class ArtifactArchiveError(RuntimeError):
    """Archive safety or integrity gate failed."""


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_source(source: Path, allowed_roots: Iterable[Path]) -> Path:
    source = source.expanduser()
    if source.is_symlink():
        raise ArtifactArchiveError("symlinked artifacts are not accepted")
    source = source.resolve()
    roots = [root.expanduser().resolve() for root in allowed_roots]
    if not source.exists():
        raise ArtifactArchiveError(f"source does not exist: {source}")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ArtifactArchiveError("symlinked artifacts are not accepted")
    if not any(_is_relative_to(source, root) for root in roots):
        raise ArtifactArchiveError("source is outside configured archive roots")
    return source


def _files(source: Path) -> list[tuple[str, Path]]:
    if source.is_file():
        return [("__file__", source)]
    return [
        (path.relative_to(source).as_posix(), path)
        for path in sorted(source.rglob("*"))
        if path.is_file()
    ]


def artifact_digest(source: Path) -> dict[str, Any]:
    """Hash names, sizes and bytes so directory structure is integrity-protected."""
    digest = hashlib.sha256()
    total = 0
    files = _files(source)
    for relative, path in files:
        size = path.stat().st_size
        total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "bytes": total, "files": len(files)}


def _write_exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ArtifactArchiveError(f"immutable catalog conflict: {path.name}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _copy(source: Path, temporary: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, temporary)
    else:
        shutil.copy2(source, temporary)


def archive_copy(
    source: Path,
    *,
    warm_root: Path,
    catalog_root: Path,
    domain: str,
    artifact_class: str,
    allowed_roots: Iterable[Path],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Copy an artifact to WARM and append a manifest; never mutate the source."""
    source = _validate_source(source, allowed_roots)
    warm_root = warm_root.expanduser().resolve()
    mount = (
        Path("/Volumes") / warm_root.parts[2]
        if len(warm_root.parts) > 2 and warm_root.parts[1] == "Volumes"
        else warm_root
    )
    if not mount.is_dir():
        raise ArtifactArchiveError(f"warm volume is not mounted: {mount}")
    source_digest = artifact_digest(source)
    identity = "|".join((domain, artifact_class, str(source), source_digest["sha256"]))
    artifact_id = "wc-artifact:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    leaf = f"{source.name}--{source_digest['sha256'][:12]}"
    destination = warm_root / quote(domain.lower(), safe="._-") / quote(
        artifact_class.lower(), safe="._-"
    ) / leaf
    record_path = catalog_root.expanduser().resolve() / "records" / f"{quote(artifact_id, safe='._-')}.json"

    if record_path.exists():
        existing = json.loads(record_path.read_text(encoding="utf-8"))
        if (
            existing.get("artifact_id") == artifact_id
            and existing.get("source_digest") == source_digest
            and Path(str(existing.get("destination"))) == destination
            and destination.exists()
            and artifact_digest(destination) == source_digest
        ):
            return {**existing, "status": "duplicate"}
        raise ArtifactArchiveError(f"immutable catalog conflict: {artifact_id}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if artifact_digest(destination) != source_digest:
            raise ArtifactArchiveError(f"destination conflict: {destination}")
    else:
        temporary = destination.with_name(f".{destination.name}.partial-{uuid.uuid4().hex}")
        try:
            _copy(source, temporary)
            copied_digest = artifact_digest(temporary)
            if copied_digest != source_digest:
                raise ArtifactArchiveError("copied artifact hash mismatch")
            os.replace(temporary, destination)
        except Exception:
            if temporary.is_dir():
                shutil.rmtree(temporary, ignore_errors=True)
            elif temporary.exists():
                temporary.unlink(missing_ok=True)
            raise

    destination_digest = artifact_digest(destination)
    if destination_digest != source_digest:
        raise ArtifactArchiveError("published artifact hash mismatch")
    stamp = created_at or datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": "wong-choi-artifact/v1",
        "artifact_id": artifact_id,
        "created_at": stamp,
        "domain": domain.lower(),
        "artifact_class": artifact_class.lower(),
        "source": str(source),
        "destination": str(destination),
        "source_digest": source_digest,
        "destination_digest": destination_digest,
        "source_removed": False,
        "cold_copy_verified": False,
        "restore_verified": False,
    }
    _write_exclusive_json(record_path, manifest)
    return {**manifest, "status": "copied_verified", "manifest": str(record_path)}


def restore_artifact(
    manifest_path: Path,
    destination: Path,
    *,
    restored_at: str | None = None,
) -> dict[str, Any]:
    """Restore to a new path and verify; destination must not already exist."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archived = Path(str(manifest.get("destination") or ""))
    expected = manifest.get("destination_digest")
    if not archived.exists() or artifact_digest(archived) != expected:
        raise ArtifactArchiveError("archived artifact is missing or corrupt")
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise ArtifactArchiveError("restore destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _copy(archived, destination)
        restored = artifact_digest(destination)
        if restored != expected:
            raise ArtifactArchiveError("restored artifact hash mismatch")
        stamp = restored_at or datetime.now(timezone.utc).isoformat()
        event_identity = "|".join(
            (str(manifest.get("artifact_id") or ""), str(destination), restored["sha256"])
        )
        event_id = "wc-artifact-restore:" + hashlib.sha256(
            event_identity.encode("utf-8")
        ).hexdigest()[:24]
        catalog_root = manifest_path.expanduser().resolve().parent.parent
        event_path = catalog_root / "events" / f"{quote(event_id, safe='._-')}.json"
        event = {
            "schema_version": "wong-choi-artifact-restore/v1",
            "event_id": event_id,
            "artifact_id": manifest.get("artifact_id"),
            "restored_at": stamp,
            "source_manifest": str(manifest_path.expanduser().resolve()),
            "destination": str(destination),
            "digest": restored,
        }
        _write_exclusive_json(event_path, event)
    except Exception as exc:
        if destination.is_dir():
            shutil.rmtree(destination, ignore_errors=True)
        elif destination.exists():
            destination.unlink(missing_ok=True)
        if isinstance(exc, ArtifactArchiveError):
            raise
        raise ArtifactArchiveError(
            f"restore transaction failed before event commit: {type(exc).__name__}: {exc}"
        ) from exc
    return {
        "status": "pass",
        "artifact_id": manifest.get("artifact_id"),
        "destination": str(destination),
        "digest": restored,
        "event": str(event_path),
    }


def mirror_artifact(
    manifest_path: Path,
    *,
    cold_root: Path,
    mirrored_at: str | None = None,
) -> dict[str, Any]:
    """Create and verify a second copy; never removes WARM or HOT data."""
    manifest_path = manifest_path.expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archived = Path(str(manifest.get("destination") or ""))
    expected = manifest.get("destination_digest")
    if not archived.exists() or artifact_digest(archived) != expected:
        raise ArtifactArchiveError("warm artifact is missing or corrupt")
    cold_root = cold_root.expanduser().resolve()
    if not cold_root.is_dir():
        raise ArtifactArchiveError(f"cold mirror is unavailable: {cold_root}")
    destination = (
        cold_root
        / quote(str(manifest.get("domain") or "unknown"), safe="._-")
        / quote(str(manifest.get("artifact_class") or "unknown"), safe="._-")
        / archived.name
    )
    catalog_root = manifest_path.parent.parent
    event_identity = "|".join(
        (str(manifest.get("artifact_id") or ""), str(destination), expected["sha256"])
    )
    event_id = "wc-artifact-mirror:" + hashlib.sha256(
        event_identity.encode("utf-8")
    ).hexdigest()[:24]
    event_path = catalog_root / "events" / f"{quote(event_id, safe='._-')}.json"
    if event_path.exists():
        existing = json.loads(event_path.read_text(encoding="utf-8"))
        if destination.exists() and artifact_digest(destination) == expected:
            return {**existing, "status": "duplicate"}
        raise ArtifactArchiveError("cold mirror event exists but copy is missing or corrupt")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if artifact_digest(destination) != expected:
            raise ArtifactArchiveError(f"cold destination conflict: {destination}")
    else:
        temporary = destination.with_name(f".{destination.name}.partial-{uuid.uuid4().hex}")
        try:
            _copy(archived, temporary)
            if artifact_digest(temporary) != expected:
                raise ArtifactArchiveError("cold mirror hash mismatch")
            os.replace(temporary, destination)
        except Exception:
            if temporary.is_dir():
                shutil.rmtree(temporary, ignore_errors=True)
            elif temporary.exists():
                temporary.unlink(missing_ok=True)
            raise
    if artifact_digest(destination) != expected:
        raise ArtifactArchiveError("published cold mirror hash mismatch")
    event = {
        "schema_version": "wong-choi-artifact-mirror/v1",
        "event_id": event_id,
        "artifact_id": manifest.get("artifact_id"),
        "mirrored_at": mirrored_at or datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(manifest_path),
        "destination": str(destination),
        "digest": expected,
    }
    _write_exclusive_json(event_path, event)
    return {**event, "status": "copied_verified", "event": str(event_path)}
