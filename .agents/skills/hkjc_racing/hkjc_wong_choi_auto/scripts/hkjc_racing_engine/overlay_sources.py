"""Complete native overlay day-file catalog; identity only, no PIT authority."""
from __future__ import annotations
from dataclasses import dataclass
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import stat

from wongchoi_paths import is_materialized_file
from .native_sources import _source_path, capture_source_file, decode_json_bytes
from .overlays import wins_from_payloads

MAX_ENTRIES = 10000
MAX_CATALOG_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class OverlaySource:
    root: Path
    sha256: str | None


def _path(root, relative):
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('linked native overlay source')
    return path


def _entries(path, budget):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('native overlay directory required')
    result = []
    for child in path.iterdir():
        budget[0] += 1
        if budget[0] > MAX_ENTRIES:
            raise ValueError('native overlay enumeration bound')
        info = child.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('linked native overlay inventory')
        result.append((child.name, stat.S_ISDIR(info.st_mode)))
    return sorted(result)


def _capture(root):
    root = _source_path(root)
    # The implicit native glob treats root metacharacters as patterns. Do not
    # silently choose a different file universe in the explicit native route.
    if any(char in str(root) for char in '*?['):
        raise ValueError('ambiguous native overlay glob root')
    budget = [0]
    top = _entries(root, budget)
    directories = {}
    selected = []
    for season, directory in top or []:
        if not directory or not fnmatch.fnmatchcase(season, 'hkjc results *'):
            continue
        directories[season] = _entries(_path(root, season), budget)
        for day, is_directory in directories[season] or []:
            if not is_directory or day.startswith('.'):
                continue
            relative = season + '/' + day
            directories[relative] = _entries(_path(root, relative), budget)
            for name, is_dir in directories[relative] or []:
                if not name.startswith('.') and fnmatch.fnmatchcase(name, '*.json'):
                    if is_dir:
                        raise ValueError('native overlay JSON must be a regular file')
                    selected.append(relative + '/' + name)
    files, identities, payloads = {}, {}, []
    total = 0
    for relative in sorted(selected):
        path = _path(root, relative)
        if not is_materialized_file(path):
            raise ValueError('native overlay source is not materialized')
        raw, info, identity = capture_source_file(path, maximum_bytes=MAX_CATALOG_BYTES - total)
        total += len(raw)
        payloads.append(decode_json_bytes(raw))
        files[relative], identities[relative] = info, identity
    check_budget = [0]
    if _entries(root, check_budget) != top:
        raise ValueError('native overlay season inventory changed')
    for relative, expected in directories.items():
        if _entries(_path(root, relative), check_budget) != expected:
            raise ValueError('native overlay day inventory changed')
    for relative, expected in identities.items():
        info = _path(root, relative).lstat()
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
        if identity != expected:
            raise ValueError('native overlay source changed during capture')
    manifest = {'schema_version': 'native-overlay-catalog/v1', 'root_entries': top,
                'directories': directories, 'files': files}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return payloads, manifest, digest


def observe_catalog_sha256(root):
    """Observed complete file-universe identity; not pre-race availability proof."""
    return _capture(root)[2]


def prepare_bound_history(source):
    if not isinstance(source, OverlaySource):
        raise ValueError('typed native overlay source required')
    root = _source_path(source.root)
    if source.sha256 is None:
        try:
            root.lstat()
        except FileNotFoundError:
            captured = _capture(root)
            if captured[1]['root_entries'] is not None:
                raise ValueError('declared absent native overlay root appeared')
        else:
            raise ValueError('declared absent native overlay root exists')
    else:
        if not isinstance(source.sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', source.sha256):
            raise ValueError('full native overlay catalog hash required')
        captured = _capture(root)
        if captured[2] != source.sha256:
            raise ValueError('native overlay catalog hash differs')
    payloads, manifest, digest = captured
    return wins_from_payloads(payloads), {'root': str(root), 'catalog_sha256': digest, 'catalog': manifest}
