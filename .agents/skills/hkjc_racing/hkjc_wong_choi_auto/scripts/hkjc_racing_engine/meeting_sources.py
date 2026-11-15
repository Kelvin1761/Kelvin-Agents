"""Held native meeting files, not canonical research inputs or PIT authority."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from wongchoi_paths import is_materialized_file
from .native_sources import _source_path, capture_source_file, decode_json_bytes

MAX_ENTRIES = 10000
MAX_CATALOG_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class MeetingSource:
    root: Path
    sha256: str | None


def _path(root, relative):
    path = root / relative
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('linked native meeting source')
    return path


def _entries(path, budget):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('native meeting directory required')
    result = []
    for child in path.iterdir():
        budget[0] += 1
        if budget[0] > MAX_ENTRIES:
            raise ValueError('native meeting enumeration bound')
        info = child.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('linked native meeting inventory')
        result.append((child.name, stat.S_ISDIR(info.st_mode)))
    return sorted(result)


def _race_number(value):
    if value in (None, ''):
        return None
    text = str(value)
    if not re.fullmatch(r'[0-9]{1,2}', text) or int(text) <= 0:
        raise ValueError('unambiguous native meeting race number required')
    return text


def _capture(logic_path, race_number):
    logic_path = Path(logic_path)
    root = _source_path(logic_path.parent)
    number = _race_number(race_number)
    identity = re.fullmatch(r"Race_([0-9]+)_Logic\.json", logic_path.name, re.I)
    if identity is None or number is None or int(identity.group(1)) != int(number):
        raise ValueError("native meeting filename/Logic race identity differs")
    budget = [0]
    top = _entries(root, budget)
    cache_entries = _entries(_path(root, '.hkjc_cache'), budget)
    names = [name for name, _ in top or []]
    roles = {}
    for role, suffix in [('facts', 'Facts'), ('trackwork', '晨操'), ('formguide', '賽績'), ('racecard', '排位表')]:
        hits = [] if number is None else [name for name in names if fnmatch.fnmatchcase(name, f'*Race {number} {suffix}.md')]
        if len(hits) > 1:
            raise ValueError('multiple native meeting ' + role + ' files')
        roles[role] = hits[0] if hits else None
    injury = [name for name in names if fnmatch.fnmatchcase(name, '*全日出賽馬匹資料*.md')]
    roles['injury'] = injury[0] if injury else None  # Native first sorted page.
    card = roles['racecard']
    roles['priority'] = card if card and fnmatch.fnmatchcase(card, f'* Race {number} 排位表.md') else None
    roles['profile_cache'] = '.hkjc_cache/profile_cache.json' if any(name == 'profile_cache.json' for name, _ in cache_entries or []) else None
    files, metadata, identities = {}, {}, {}
    total = 0
    for relative in sorted(set(value for value in roles.values() if value is not None)):
        path = _path(root, relative)
        if not is_materialized_file(path):
            raise ValueError('native meeting source is not materialized')
        raw, info, identity = capture_source_file(path, maximum_bytes=MAX_CATALOG_BYTES - total)
        total += len(raw)
        files[relative], metadata[relative], identities[relative] = raw, info, identity
    check_budget = [0]
    if _entries(root, check_budget) != top or _entries(_path(root, '.hkjc_cache'), check_budget) != cache_entries:
        raise ValueError('native meeting inventory changed')
    for relative, expected in identities.items():
        info = _path(root, relative).lstat()
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
        if identity != expected:
            raise ValueError('native meeting source changed during capture')
    manifest = {'schema_version': 'native-meeting-catalog/v1', 'logic_name': logic_path.name,
                'race_number': number, 'root_entries': top, 'cache_entries': cache_entries,
                'roles': roles, 'files': metadata}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return files, manifest, digest


class MeetingContext:
    def __init__(self, captured):
        files, manifest, _ = captured
        self._texts = {}
        for role, relative in manifest['roles'].items():
            if role == 'profile_cache':
                continue
            if relative is None:
                self._texts[role] = None
            elif role == 'priority':
                self._texts[role] = files[relative].decode('utf-8', 'replace')
            elif role == 'injury':
                from hkjc_official_injury import decode_text
                self._texts[role] = decode_text(files[relative])
            else:
                self._texts[role] = files[relative].decode('utf-8')
        relative = manifest['roles']['profile_cache']
        cache = {} if relative is None else decode_json_bytes(files[relative])
        profiles = {}
        for key, value in cache.items():
            if value is not None and not isinstance(value, dict):
                raise ValueError('invalid native meeting profile record')
            data = (value or {}).get('data') or {}
            if (not isinstance(data, dict) or not isinstance(data.get('entries') or [], list)
                    or any(not isinstance(entry, dict) for entry in data.get('entries') or [])):
                raise ValueError('invalid native meeting profile data')
            profiles[key] = data
        self._profiles = profiles

    def text(self, role):
        return self._texts[role]

    def profiles(self):
        return deepcopy(self._profiles)


def observe_catalog_sha256(logic_path, race_number):
    captured = _capture(logic_path, race_number)
    MeetingContext(captured)  # Validate all held decoding/shapes before scoring.
    return captured[2]


def prepare_bound_meeting(source, logic_path, race_number, *, profile_source=None):
    if not isinstance(source, MeetingSource):
        raise ValueError('typed native meeting source required')
    root = _source_path(source.root)
    if root != Path(logic_path).parent:
        raise ValueError('native meeting root differs from logic parent')
    if source.sha256 is None:
        try:
            root.lstat()
        except FileNotFoundError:
            captured = _capture(logic_path, race_number)
            if captured[1]['root_entries'] is not None:
                raise ValueError('declared absent native meeting root appeared')
        else:
            raise ValueError('declared absent native meeting root exists')
    else:
        if not isinstance(source.sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', source.sha256):
            raise ValueError('full native meeting catalog hash required')
        captured = _capture(logic_path, race_number)
        if captured[2] != source.sha256:
            raise ValueError('native meeting catalog hash differs')
    if profile_source is not None:
        from .native_sources import JsonSource
        if not isinstance(profile_source, JsonSource):
            raise ValueError('typed profile source binding required')
        profile = _source_path(profile_source.path)
        cache = _path(root, '.hkjc_cache/profile_cache.json')
        same = profile == cache
        if not same:
            try:
                same = os.path.samefile(profile, cache)
            except FileNotFoundError:
                same = False
        if same:
            metadata = captured[1]['files'].get('.hkjc_cache/profile_cache.json')
            expected = None if metadata is None else metadata['sha256']
            if profile_source.sha256 != expected:
                raise ValueError('inconsistent same-file profile source binding')
    context = MeetingContext(captured)
    return context, {'root': str(root), 'catalog_sha256': captured[2], 'catalog': captured[1]}
