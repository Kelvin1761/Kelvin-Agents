"""Exact historical versions, keyed by original path and recorded digest.

Registration never edits evidence records or today's mutable report. Recovery
does not confer label, feature-availability or model-promotion authority.
"""
import fcntl
import hashlib
import os
import re
import stat
from pathlib import Path

from .immutable_settlement_artifacts import (
    _publish, _read, _sync, artifact_belongs_to_event, settlement_event_folder,
)
from .research_index import _encoded, _safe


def _identity(original, sha256, event_id, domain):
    original = _safe(Path(original))
    if (not artifact_belongs_to_event(original, domain, event_id)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
            or original.name == "manifest.json"):
        raise ValueError("invalid recovered settlement identity")
    identity = {"schema_version": "wong-choi-recovered-settlement/v1",
                "domain": domain, "original_path": str(original),
                "sha256": sha256, "event_id": event_id}
    return original, identity, hashlib.sha256(_encoded(identity)).hexdigest()


def register_recovered_artifact(*, root, original, sha256, event_id, source, domain="au"):
    """Create-only registration; the supplied bytes must match recorded SHA256."""
    original, identity, key = _identity(original, sha256, event_id, domain)
    data = _read(source)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("recovered settlement bytes do not match recorded hash")
    root = _safe(Path(root))
    if not root.is_dir():
        raise ValueError("evidence root unavailable")
    folder = _safe(root / "recovered-settlement-artifacts")
    folder.mkdir(exist_ok=True)
    _sync(root)
    manifest = _encoded({**identity, "bytes": len(data)}) + b"\n"
    fd = os.open(_safe(folder / ".capture.lock"),
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "rb") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("recovery lock must be regular")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _publish(folder, folder / key, manifest, settlement_event_folder(domain, event_id),
                 {original.name: data}, lambda: None)
    return folder / key / settlement_event_folder(domain, event_id) / original.name


def resolve_recovered_artifact(*, root, original, sha256, event_id, reader, blobs, domain="au"):
    """Resolve this exact recorded identity only; missing/corrupt versions fail."""
    original, identity, key = _identity(original, sha256, event_id, domain)
    folder = _safe(Path(root) / "recovered-settlement-artifacts" / key)
    manifest, _ = reader.read(folder / "manifest.json")
    path = _safe(folder / settlement_event_folder(domain, event_id) / original.name)
    _raw, digest, size = blobs.read(path)
    if digest != sha256 or manifest != {**identity, "bytes": size}:
        raise ValueError("recovered settlement artifact provenance mismatch")
    return path
