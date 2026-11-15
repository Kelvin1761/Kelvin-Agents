"""Bounded native JSON reads; identity only, no PIT/research authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

USE_PRODUCTION = object()
MAX_SOURCE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class JsonSource:
    """Per-call byte identity only, never historical availability/authority.

    sha256=None declares this exact path absent. Omission of the API argument,
    rather than absence, selects the unchanged production cache policy.
    """
    path: Path
    sha256: str | None


def _source_path(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute canonical JSON source path required")
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.parent.is_dir():
        raise ValueError("symlinked or unavailable JSON source parent")
    return path


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON source key")
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("nonfinite JSON source value")


def _finite_tree(value, depth=0):
    if depth > 64:
        raise ValueError("JSON source nesting limit")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite JSON source value")
    if isinstance(value, dict):
        for item in value.values():
            _finite_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _finite_tree(item, depth + 1)


def capture_source_file(path, *, maximum_bytes=None):
    """Observed bytes/metadata only; no review, PIT or publication authority."""
    path = _source_path(path)
    if maximum_bytes is not None and (type(maximum_bytes) is not int or maximum_bytes <= 0):
        raise ValueError("native source byte bound exhausted")
    limit = MAX_SOURCE_BYTES if maximum_bytes is None else min(MAX_SOURCE_BYTES, maximum_bytes)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("bounded regular JSON source required")
        raw = handle.read(before.st_size)
        after = os.fstat(handle.fileno())
    current = _source_path(path).lstat()
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
    if (identity(before) != identity(after) or identity(after) != identity(current)
            or len(raw) != before.st_size):
        raise ValueError("JSON source changed or hash differs")
    return raw, {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
                 "mtime_ns": after.st_mtime_ns, "mode": stat.S_IMODE(after.st_mode)}, identity(after)


def read_bound_json(source: JsonSource) -> dict | None:
    """Read verified local bytes without accessing or changing production cache.

    Stable descriptor checks are not an atomic filesystem lease or a PIT proof.
    This native seam is not connected to the frozen research input protocol.
    """
    if not isinstance(source, JsonSource):
        raise ValueError("typed JSON source binding required")
    path = _source_path(source.path)
    if source.sha256 is None:
        try:
            path.lstat()
        except FileNotFoundError:
            return None
        raise ValueError("declared absent JSON source exists")
    if not isinstance(source.sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", source.sha256):
        raise ValueError("full JSON source hash required")
    raw, metadata, _identity = capture_source_file(path)
    if metadata["sha256"] != source.sha256:
        raise ValueError("JSON source changed or hash differs")
    return decode_json_bytes(raw)


def decode_json_bytes(raw):
    try:
        table = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        _finite_tree(table)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid JSON source JSON") from exc
    if not isinstance(table, dict):
        raise ValueError("JSON source object required")
    return table

