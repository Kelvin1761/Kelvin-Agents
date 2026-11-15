"""Held native CSV priors; identity/read isolation only, never PIT authority.

Engine imports still discover default paths. Explicit consumers independently
capture this catalog and never consult those default path or object caches.
"""
from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import stat

import pandas as pd
from wongchoi_paths import is_materialized_file
from . import live_priors as native
from .native_source_capture import record_source_directory, record_absent_source
from .native_sources import _source_path, capture_source_file

MAX_ENTRIES = 10000
MAX_CATALOG_BYTES = 256 * 1024 * 1024
GENERAL_ROLES = {
    'combo': ('general_pre_race_priors/jockey_trainer_combo_priors.csv', ('Jockey', 'Trainer')),
    'jockey_distance': ('jockey_distance_stats.csv', ('Jockey', 'Distance')),
    'trainer_distance': ('trainer_distance_stats.csv', ('Trainer', 'Distance')),
    'jockey_change': ('general_pre_race_priors/jockey_change_priors.csv', ('JockeyChanged',)),
    'jockey_draw': ('jockey_draw_performance.csv', ()),
}
RECENCY = 'experimental/trainer_recency_90d_stats.csv'
RECENCY_COLUMNS = ('Trainer', 'Wins', 'Starts', 'Places', 'AsOfDate', 'LatestResultDate', 'HalfLifeDays')


@dataclass(frozen=True)
class PriorSource:
    root: Path
    sha256: str | None


def _path(root, relative):
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('linked native prior source')
    return path


def _entries(path, budget):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return record_source_directory(path, None)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('native prior directory required')
    entries = []
    for child in path.iterdir():
        budget[0] += 1
        if budget[0] > MAX_ENTRIES:
            raise ValueError('native prior enumeration bound')
        info = child.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('linked native prior inventory')
        entries.append((child.name, stat.S_ISDIR(info.st_mode)))
    return record_source_directory(path, sorted(entries))


def _frame(raw, columns):
    text = raw.decode('utf-8-sig')
    header = next(csv.reader(io.StringIO(text)), [])
    if not header or len(header) != len(set(header)):
        raise ValueError('invalid native prior CSV header')
    frame = pd.read_csv(io.StringIO(text))
    if any(column not in frame.columns for column in columns):
        raise ValueError('native prior CSV columns missing')
    return frame


def _capture(root):
    root = _source_path(root)
    budget = [0]
    top = _entries(root, budget)
    seasons = [name for name, directory in (top or []) if directory and native._SEASON_STATS_RE.fullmatch(name)]
    seasons = seasons or list(native._FALLBACK_SEASONS)
    directories = {}
    for season in seasons:
        for relative in (season, season + '/general_pre_race_priors'):
            directories[relative] = _entries(_path(root, relative), budget)
    directories['experimental'] = _entries(_path(root, 'experimental'), budget)
    general = {role: [root / season / relative for season in seasons] for role, (relative, _) in GENERAL_ROLES.items()}
    master = {group: [(root / season / f'{group}_master_stats.csv', season) for season in seasons] for group in ('jockey', 'trainer')}
    required = {str(path.relative_to(root)): keys + ('Wins', 'Starts', 'Places')
                for role, paths in general.items() for path in paths for keys in [GENERAL_ROLES[role][1]]}
    for group, paths in master.items():
        required.update({str(path.relative_to(root)): (group.title(), 'Wins', 'Starts', 'Places') for path, _ in paths})
    required[RECENCY] = RECENCY_COLUMNS
    files, metadata, identities = {}, {}, {}
    total = 0
    for relative, columns in sorted(required.items()):
        path = _path(root, relative)
        try:
            path.lstat()
        except FileNotFoundError:
            record_absent_source(path)
            files[relative] = metadata[relative] = None
            continue
        if not is_materialized_file(path):
            raise ValueError('native prior source is not materialized')
        raw, info, identity = capture_source_file(path, maximum_bytes=MAX_CATALOG_BYTES - total)
        total += len(raw)
        _frame(raw, columns)  # Validate even unweighted/manifest-only roles before enrichment.
        files[relative], metadata[relative], identities[relative] = raw, info, identity
    check_budget = [0]
    if _entries(root, check_budget) != top:
        raise ValueError('native prior season inventory changed')
    for relative, expected in directories.items():
        if _entries(_path(root, relative), check_budget) != expected:
            raise ValueError('native prior inventory changed')
    for relative, expected in metadata.items():
        path = _path(root, relative)
        try:
            info = path.lstat()
        except FileNotFoundError:
            if expected is not None:
                raise ValueError('native prior disappeared')
            continue
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
        if expected is None or identity != identities[relative]:
            raise ValueError('native prior changed during capture')
    current_tag = native._current_season_tag()
    manifest = {'schema_version': 'native-prior-catalog/v1', 'current_tag': current_tag,
                'root_entries': top, 'directories': directories, 'files': metadata}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return root, files, manifest, digest, general, master


def observe_catalog_sha256(root):
    """Identity only; not historical availability, review or installation permission."""
    return _capture(root)[3]


class PriorContext:
    def __init__(self, captured):
        root, files, manifest, self.sha256, general, master = captured
        self._evidence = {'root': str(root), 'catalog_sha256': self.sha256, 'catalog': manifest}
        def reader(path, columns):
            key = str(path.relative_to(root))
            raw = files[key]  # Unknown paths fail, never fall back to HOT.
            return None if raw is None else _frame(raw, columns)
        self.ratings = native.JockeyTrainerRatings(reader=reader, master_files=master, current_tag=manifest['current_tag'])
        self.signals = native.TrainerSignalPriors(reader=reader, general_files=general)
        self.recency = native.RecencyTrainerRatings(reader=reader, recency_path=root / RECENCY)
        # Preserve legacy output layout, while the bound catalog digest includes
        # recency. None of this metadata confers point-in-time eligibility.
        self._manifest = [{'source': relative, 'materialized': info is not None,
                           'size': info['size'] if info else 0, 'modified_ns': info['mtime_ns'] if info else 0}
                          for relative, info in sorted(manifest['files'].items()) if relative != RECENCY]

    def evidence(self):
        return deepcopy(self._evidence)

    def manifest(self):
        return [dict(row) for row in self._manifest]


def prepare_bound_priors(source):
    if not isinstance(source, PriorSource):
        raise ValueError('typed native prior source required')
    root = _source_path(source.root)
    if source.sha256 is None:
        try:
            root.lstat()
        except FileNotFoundError:
            captured = _capture(root)
            if captured[2]['root_entries'] is not None:
                raise ValueError('declared absent native prior root appeared')
            return PriorContext(captured)
        raise ValueError('declared absent native prior root exists')
    if not isinstance(source.sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', source.sha256):
        raise ValueError('full native prior catalog hash required')
    captured = _capture(root)
    if captured[3] != source.sha256:
        raise ValueError('native prior catalog hash differs')
    return PriorContext(captured)
