"""Held native completed-result catalog; no frozen-harness or PIT authority."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat

import hkjc_completed_rows as rows
from wongchoi_paths import is_materialized_file
from .native_source_capture import record_source_directory, record_absent_source
from .native_sources import _source_path, capture_source_file, decode_json_bytes

MAX_ENTRIES = 10000
MAX_CATALOG_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class CompletedRowsSource:
    root: Path
    sha256: str | None


def _catalog_path(root, relative):
    path = root / relative
    if ".." in Path(relative).parts or Path(relative).is_absolute():
        raise ValueError('unsafe completed-result relative path')
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('linked completed-result source path')
    return path


def _entries(path, budget):
    path = _catalog_path(path.parent, path.name)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return record_source_directory(path, None)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('completed-result directory required')
    result = []
    for child in path.iterdir():
        budget[0] += 1
        if budget[0] > MAX_ENTRIES:
            raise ValueError('completed-result catalog enumeration bound')
        info = child.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('linked completed-result catalog entry')
        result.append((child.name, stat.S_ISDIR(info.st_mode)))
    return record_source_directory(path, sorted(result))


def _capture(root):
    root = _source_path(root)
    if not root.is_dir():
        raise ValueError('completed-result source directory required')
    budget = [0]
    top = _entries(root, budget)
    seen = {}
    for name, is_dir in top:
        key = rows.season_key_from_results_dir(name) if is_dir else None
        if key:
            if key in seen:
                raise ValueError('ambiguous completed-result season directories')
            seen[key] = name
    seasons = rows.seasons_from_entries(top)
    directories, files, metadata, identities = {}, {}, {}, {}
    total = 0
    def hold(relative, *, daily=False):
        nonlocal total
        path = _catalog_path(root, relative)
        try:
            path.lstat()
        except FileNotFoundError:
            record_absent_source(path)
            files[relative] = metadata[relative] = None
            return
        if not is_materialized_file(path):
            raise ValueError('selected completed-result source is unavailable')
        raw, info, identity = capture_source_file(path, maximum_bytes=MAX_CATALOG_BYTES - total)
        total += len(raw)
        if total > MAX_CATALOG_BYTES:
            raise ValueError('completed-result catalog byte bound; no truncation')
        if daily:
            decode_json_bytes(raw)
        files[relative], metadata[relative], identities[relative] = raw, info, identity
    for season, config in seasons.items():
        relative = str(config['results_dir'])
        directories[relative] = _entries(root / relative, budget)
        hold('comprehensive_stats/' + season + '/' + str(config['csv']))
        context = rows.HeldRows(root, seasons, directories, files)
        base = rows.load_base_rows(season, context)
        for day in rows.selected_days(season, base, context):
            hold(relative + '/' + day + '/full_day_results.json', daily=True)
    # Reobserve both directory namespaces and selected file identities. This is
    # an observation boundary, not an atomic lease or adversarial A/B/A defense.
    check_budget = [0]
    if _entries(root, check_budget) != top:
        raise ValueError('completed-result season inventory changed')
    for relative, expected in directories.items():
        if _entries(root / relative, check_budget) != expected:
            raise ValueError('completed-result day inventory changed')
    for relative, expected in metadata.items():
        path = _catalog_path(root, relative)
        try:
            info = path.lstat()
        except FileNotFoundError:
            if expected is not None:
                raise ValueError('completed-result source disappeared')
            continue
        if expected is None:
            raise ValueError('declared absent completed-result source appeared')
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
        if identity != identities[relative]:
            raise ValueError('completed-result source changed during capture')
    manifest = {'schema_version': 'native-completed-result-catalog/v1', 'seasons': seasons,
                'root_entries': top, 'directories': directories, 'files': metadata}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return rows.HeldRows(root, seasons, directories, files), digest


def observe_catalog_sha256(root):
    """Content/metadata identity, never input eligibility or authorization."""
    return _capture(root)[1]


def read_bound_rows(source):
    if not isinstance(source, CompletedRowsSource):
        raise ValueError('typed completed-result source required')
    root = _source_path(source.root)
    if source.sha256 is None:
        try:
            root.lstat()
        except FileNotFoundError:
            record_absent_source(root)
            return None
        raise ValueError('declared absent completed-result root exists')
    if not isinstance(source.sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', source.sha256):
        raise ValueError('full completed-result catalog hash required')
    context, digest = _capture(root)
    if digest != source.sha256:
        raise ValueError('completed-result catalog hash differs')
    return rows.load_all_completed_rows(context)
