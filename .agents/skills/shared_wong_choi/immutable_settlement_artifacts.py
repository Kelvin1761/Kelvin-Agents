"""Create-only settlement bytes; no historical repair or evidence authority."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 16


def _safe(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("settlement capture symlink or traversal refused")
    return path


def _read(path, *, remaining=None):
    path = _safe(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        limit = MAX_FILE_BYTES if remaining is None else min(MAX_FILE_BYTES, remaining)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("settlement capture file bound/type refused")
        data = source.read(limit + 1)
        after = os.fstat(source.fileno())
    if (len(data) != before.st_size or len(data) > limit
            or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError("settlement capture source changed during read")
    return data


def _write(path, data):
    with path.open("xb") as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    path.chmod(0o444)


def _sync(directory):
    fd = os.open(_safe(directory), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify(final, manifest_bytes, event_id, payloads):
    final = _safe(final)
    if _read(final / "manifest.json") != manifest_bytes:
        raise ValueError("settlement capture manifest mismatch")
    event = _safe(final / event_id)
    if set(p.name for p in event.iterdir()) != set(payloads):
        raise ValueError("settlement capture file scope mismatch")
    for name, data in payloads.items():
        if _read(event / name) != data:
            raise ValueError("settlement capture bytes mismatch")


def _publish(root, final, manifest_bytes, event_id, payloads, checkpoint):
    checkpoint()
    if final.exists():
        _verify(final, manifest_bytes, event_id, payloads)
        return
    temporary = Path(tempfile.mkdtemp(prefix=".capture-", dir=root))
    try:
        event = temporary / event_id
        event.mkdir()
        for name, data in payloads.items():
            checkpoint()
            _write(event / name, data)
        _write(temporary / "manifest.json", manifest_bytes)
        _sync(event)
        _sync(temporary)
        checkpoint()
        temporary.rename(final)
        _sync(root)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def capture_settlement_artifacts(*, artifacts, event_id, root, checkpoint=lambda: None):
    """Capture a bounded AU bundle under an existing, caller-verified WARM root.

    The event basename and canonical filenames are preserved for strict legacy
    readers. Original mutable sources and all earlier captures stay untouched.
    """
    if (not isinstance(event_id, str) or not event_id or event_id in {".", ".."}
            or Path(event_id).name != event_id or "\\" in event_id):
        raise ValueError("invalid settlement capture event")
    checkpoint()
    warm = _safe(root)
    if not warm.is_dir():
        raise ValueError("settlement capture root unavailable")
    paths = tuple(_safe(path) for path in artifacts)
    if not 0 < len(paths) <= MAX_FILES or len({p.name for p in paths}) != len(paths):
        raise ValueError("settlement capture file scope bound")
    if any(p.parent.name != event_id or p.name == "manifest.json" for p in paths):
        raise ValueError("settlement capture event folder mismatch")
    if sum(p.stat().st_size for p in paths) > MAX_TOTAL_BYTES:
        raise ValueError("settlement capture total byte bound")
    payloads = {}
    remaining = MAX_TOTAL_BYTES
    for path in paths:
        checkpoint()
        data = _read(path, remaining=remaining)
        payloads[path.name] = data
        remaining -= len(data)
    if sum(map(len, payloads.values())) > MAX_TOTAL_BYTES:
        raise ValueError("settlement capture total byte bound")
    manifest = {"schema_version": "wong-choi-settlement-artifacts/v1",
                "domain": "au", "event_id": event_id,
                "files": [{"name": name, "sha256": hashlib.sha256(data).hexdigest(),
                           "bytes": len(data)} for name, data in sorted(payloads.items())]}
    encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    bundle_root = _safe(warm / "settlement-artifacts")
    checkpoint()
    bundle_root.mkdir(exist_ok=True)
    _sync(warm)
    domain_root = _safe(bundle_root / "au")
    domain_root.mkdir(exist_ok=True)
    _sync(bundle_root)
    final = domain_root / hashlib.sha256(encoded).hexdigest()
    lock_fd = os.open(_safe(domain_root / ".capture.lock"),
                      os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(lock_fd, "rb") as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError("settlement capture lock must be regular")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _publish(domain_root, final, encoded, event_id, payloads, checkpoint)
        for source in paths:
            checkpoint()
            if _read(source) != payloads[source.name]:
                raise ValueError("settlement capture source changed before append")
        _verify(final, encoded, event_id, payloads)
        checkpoint()
    return tuple(final / event_id / source.name for source in paths)
