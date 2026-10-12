"""Shared AU blind-monitor state discipline; no fitting or live activation."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import errno
import os
from pathlib import Path
from datetime import date
import hashlib
import json
import re

SHA256 = re.compile(r'^[a-f0-9]{64}$')


def content_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def validate_config_record(existing, current):
    """Retain legacy config hashes; validate payload instead of trusting hash text."""
    if not isinstance(existing, dict):
        raise ValueError('shadow state must be an object')
    if not existing:
        return
    count = existing.get('races_collected')
    visible = existing.get('outcomes_visible')
    if (not isinstance(count, int) or isinstance(count, bool) or count < 0
            or not isinstance(visible, bool)):
        raise ValueError('shadow collection metadata invalid or missing')
    started = (count > 0 or visible or bool(existing.get('locked_race_keys'))
               or bool(existing.get('sample_sha256')))
    if not started:
        return  # same pre-collection reset policy as the existing monitor
    cfg = existing.get('config')
    if not isinstance(cfg, dict) or not isinstance(cfg.get('config_sha256'), str):
        raise ValueError('shadow config missing after collection started')
    digest = cfg['config_sha256']
    if not SHA256.fullmatch(digest):
        raise ValueError('shadow config changed after collection started: invalid hash')
    if content_hash({k: v for k, v in cfg.items() if k != 'config_sha256'}) != digest:
        raise ValueError('shadow config payload/hash mismatch after collection started')
    if digest != current.get('config_sha256'):
        raise ValueError('shadow config changed after collection started')


def reuse_revealed_state(existing, target):
    """An already revealed record is reused, never silently evaluated again.

    Legacy recency records have no keys/payload seal: preserve their original
    record without retroactively manufacturing that evidence.
    """
    if not existing or not existing.get('outcomes_visible'):
        return None
    if existing['races_collected'] < target:
        raise ValueError('revealed shadow below registered sample threshold')
    if not SHA256.fullmatch(str(existing.get('sample_sha256', ''))):
        raise ValueError('revealed shadow lacks sample hash')
    try:
        date.fromisoformat(existing['date_to'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('revealed shadow terminal date missing or invalid') from exc
    keys = existing.get('locked_race_keys')
    if keys is not None:
        _validate_keys(keys)
        if len(keys) != existing['races_collected'] or keys_hash(keys) != existing['sample_sha256']:
            raise ValueError('revealed shadow key/count/hash mismatch')
    return copy.deepcopy(existing)


def _validate_keys(keys):
    if (not isinstance(keys, list) or not keys
            or any(not isinstance(k, str) or not k for k in keys)
            or len(set(keys)) != len(keys)):
        raise ValueError('shadow sample keys missing or duplicate')


def keys_hash(keys):
    return hashlib.sha256('\n'.join(keys).encode()).hexdigest()


def freeze_complete_day_sample(rows, existing, target, *, key_fn, day_selector):
    """Return full locked input rows and metadata before any outcome evaluation."""
    if not isinstance(target, int) or isinstance(target, bool) or target < 1:
        raise ValueError('shadow target must be a positive integer')
    by_key = {}
    for row in rows:
        key = key_fn(row)
        if key in by_key:
            raise ValueError('shadow input race identity duplicate')
        by_key[key] = row
    keys = existing.get('locked_race_keys')
    if keys is None and (existing.get('sample_sha256') or existing.get('sample_payload_sha256')
                         or existing.get('state') == 'terminal_frozen'):
        raise ValueError('shadow frozen sample keys missing')
    if keys is not None:
        _validate_keys(keys)
        if existing.get('sample_sha256') != keys_hash(keys):
            raise ValueError('shadow locked key hash mismatch')
        if any(k not in by_key for k in keys):
            raise ValueError('shadow locked sample source missing')
        sample = [by_key[k] for k in keys]
        if len(sample) < target or len(sample) != existing.get('races_collected'):
            raise ValueError('shadow locked sample size mismatch')
    else:
        if len(rows) < target:
            return None
        sample = day_selector(rows, target)
        keys = [key_fn(row) for row in sample]
        _validate_keys(keys)
    payload_hash = content_hash(sample)
    if existing.get('locked_race_keys') is not None:
        if existing.get('sample_payload_sha256') != payload_hash:
            raise ValueError('shadow locked sample payload changed or not sealed')
    return {
        'rows': copy.deepcopy(sample), 'locked_race_keys': keys,
        'sample_sha256': keys_hash(keys), 'sample_payload_sha256': payload_hash,
        'races_collected': len(sample),
        'locked_through_date': max(row['date'] for row in sample),
    }


def sealed_status(config, sample):
    """Persist this blind checkpoint before evaluating the frozen sample."""
    return {
        'schema_version': 2, 'config': copy.deepcopy(config),
        'state': 'terminal_frozen', 'outcomes_visible': False,
        **{k: copy.deepcopy(v) for k, v in sample.items() if k != 'rows'},
        'date_to': sample['locked_through_date'],
        'race_days': len({r['date'] for r in sample['rows']}),
    }


@contextmanager
def exclusive_status_lock(output):
    """Nonblocking OS lock; a stale filename cannot hold the monitor forever."""
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name('.' + path.name + '.lock')
    with lock_path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'\0'); handle.flush()
            handle.seek(0)
            lock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            unlock = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            lock = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            unlock = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            lock()
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise RuntimeError('shadow status is owned by another monitor') from exc
            raise
        try:
            yield
        finally:
            handle.seek(0)
            unlock()
