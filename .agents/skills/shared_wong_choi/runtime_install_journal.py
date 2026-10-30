"""Attempt-bound pre-write proofs; these records never grant release approval."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared_wong_choi.runtime_cutover_lease import inherited_lease, lease_path
from shared_wong_choi.runtime_snapshot_state import (
    LABELS, MAX_PLIST_BYTES, _digest, file_state, load_observation, observe,
)

SCHEMA = 'wong-choi-runtime-write-plan/v1'
BEGIN_SCHEMA = 'wong-choi-runtime-write-begin/v1'
DIRECTORY = '.write-ownership'


class OwnershipError(RuntimeError):
    pass


def _exclusive():
    inherited_lease('exclusive', lease_path())


def _safe_root(path: Path, *, private=False):
    if any(item.is_symlink() for item in (path, *path.parents)) or not path.is_dir():
        raise OwnershipError('unsafe ownership root')
    metadata = path.stat()
    if private and (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise OwnershipError('ownership directory is not private')


def _bytes(path: Path, *, private=False) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_size > MAX_PLIST_BYTES
                or (private and (before.st_uid != os.getuid() or before.st_nlink != 1
                                 or stat.S_IMODE(before.st_mode) != 0o600))):
            raise OwnershipError('unsafe proof file')
        data = handle.read(MAX_PLIST_BYTES + 1)
        after = os.fstat(handle.fileno())
        named = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if (len(data) > MAX_PLIST_BYTES or identity(before) != identity(after)
            or identity(after) != identity(named)):
        raise OwnershipError('proof changed while reading')
    return data


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise OwnershipError('duplicate proof key')
        result[key] = value
    return result


def _load(path: Path):
    value = json.loads(_bytes(path, private=True), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise OwnershipError('invalid ownership proof')
    expected = value.get('content_hash')
    body = {k: v for k, v in value.items() if k != 'content_hash'}
    if expected != _digest(body):
        raise OwnershipError('ownership proof hash mismatch')
    return body


def _append(path: Path, body):
    value = {**body, 'content_hash': _digest(body)}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _candidate_states(candidates: Path):
    _safe_root(candidates)
    if {p.name for p in candidates.iterdir()} != {label + '.plist' for label in LABELS}:
        raise OwnershipError('candidate allowlist mismatch')
    states = {}
    for label in sorted(LABELS):
        path = candidates / (label + '.plist')
        state = file_state(path)
        data = _bytes(path)
        payload = plistlib.loads(data)
        if hashlib.sha256(data).hexdigest() != state['sha256']:
            raise OwnershipError('candidate changed during proof capture')
        if payload.get('Label') != label or state['mode'] != 0o644:
            raise OwnershipError('candidate label or mode mismatch')
        states[label] = state
    return states


POINTER = 'tennis-db-pointer'


def _pointer(snapshot: Path):
    path = snapshot / '.tennis-db-pointer-path'
    if not path.exists() and not path.is_symlink():
        return None  # Legacy proof cannot authorize a pointer write.
    raw = _bytes(path)
    target = raw.decode('utf-8').removesuffix('\n')
    if not target.startswith('/') or '\n' in target or len(raw) > 4096:
        raise OwnershipError('unsafe pointer binding')
    original = file_state(snapshot / '.tennis-db-pointer-original')
    candidate = file_state(snapshot / '.tennis-db-pointer-candidate')
    if not candidate['exists']:
        raise OwnershipError('missing pointer candidate')
    return {'target': target, 'before': original, 'candidate': {**candidate, 'mode': 0o644}}


def prepare(snapshot: Path, agents: Path, *, domain: str, launchctl: str, commit: str):
    """Bind original observation and actual rendered candidates BEFORE writes."""
    _exclusive()
    _safe_root(snapshot, private=True)
    _safe_root(agents)
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise OwnershipError('full source SHA required')
    binding = {'domain': domain, 'labels': tuple(sorted(LABELS))}
    before = load_observation(snapshot, agents, **binding)
    candidates = _candidate_states(snapshot / 'candidates')
    if observe(agents, launchctl=launchctl, **binding) != before:
        raise OwnershipError('runtime changed between snapshot and write plan')
    pointer = _pointer(snapshot)
    if pointer and file_state(Path(pointer['target'])) != pointer['before']:
        raise OwnershipError('pointer changed between snapshot and write plan')
    root = snapshot / DIRECTORY
    root.mkdir(mode=0o700)  # Existing records are never rewritten or adopted.
    body = {'schema_version': SCHEMA, 'attempt_id': uuid4().hex, 'commit': commit,
            'snapshot_root': str(snapshot.resolve()), 'agents_root': str(agents.resolve()),
            'domain': domain, 'before_hash': _digest(before), 'candidates': candidates,
            'pointer': pointer}
    _append(root / 'plan.json', body)
    return body


def _context(snapshot: Path, agents: Path, domain: str):
    _exclusive()
    _safe_root(snapshot, private=True)
    _safe_root(agents)
    root = snapshot / DIRECTORY
    _safe_root(root, private=True)
    plan = _load(root / 'plan.json')
    before = load_observation(snapshot, agents, domain=domain, labels=tuple(sorted(LABELS)))
    if (set(plan) != {'schema_version', 'attempt_id', 'commit', 'snapshot_root',
                      'agents_root', 'domain', 'before_hash', 'candidates', 'pointer'}
            or plan['schema_version'] != SCHEMA
            or not re.fullmatch('[0-9a-f]{32}', plan['attempt_id'])
            or not re.fullmatch('[0-9a-f]{40}', plan['commit'])
            or plan['snapshot_root'] != str(snapshot.resolve())
            or plan['agents_root'] != str(agents.resolve()) or plan['domain'] != domain
            or plan['before_hash'] != _digest(before) or plan['pointer'] != _pointer(snapshot)
            or plan['candidates'] != _candidate_states(snapshot / 'candidates')):
        raise OwnershipError('ownership plan binding mismatch')
    allowed = {'plan.json'} | {label + '.begin.json' for label in LABELS | {POINTER}}
    if any(p.name not in allowed for p in root.iterdir()):
        raise OwnershipError('unknown ownership record')
    return root, plan, before


def _begin_record(root, plan, label):
    value = _load(root / (label + '.begin.json'))
    if value != {'schema_version': BEGIN_SCHEMA, 'label': label,
                 'attempt_id': plan['attempt_id'], 'plan_hash': _digest(plan)}:
        raise OwnershipError('write intent binding mismatch')


def begin_job(snapshot: Path, agents: Path, *, domain: str, launchctl: str, label: str):
    """Record intent before any native unload, file publication or flag change."""
    if label not in LABELS:
        raise OwnershipError('unallowlisted job')
    root, plan, before = _context(snapshot, agents, domain)
    current = observe(agents, launchctl=launchctl, domain=domain, labels=tuple(sorted(LABELS)))
    if current['jobs'][label] != before['jobs'][label]:
        raise OwnershipError('unowned state appeared before write intent')
    _append(root / (label + '.begin.json'), {'schema_version': BEGIN_SCHEMA,
            'label': label, 'attempt_id': plan['attempt_id'], 'plan_hash': _digest(plan)})


def publish_job(snapshot: Path, agents: Path, *, domain: str, label: str):
    """Publish only the prebound renderer output, under the exclusive lease."""
    if label not in LABELS:
        raise OwnershipError('unallowlisted job')
    root, plan, before = _context(snapshot, agents, domain)
    _begin_record(root, plan, label)
    target = agents / (label + '.plist')
    data = _bytes(snapshot / 'candidates' / (label + '.plist'))
    if hashlib.sha256(data).hexdigest() != plan['candidates'][label]['sha256']:
        raise OwnershipError('candidate changed before publication')
    _publish_file(target, data, before['jobs'][label]['file'])


def _publish_file(target, data, original):
    if any(part.is_symlink() for part in target.parents):
        raise OwnershipError('symlinked publication parent')
    if file_state(target) != original:
        raise OwnershipError('unowned target before candidate publication')
    identity = target.lstat() if target.exists() else None
    fd, raw = tempfile.mkstemp(prefix='.wc-owned-publication-', dir=target.parent)
    staged = Path(raw)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        os.fchmod(handle.fileno(), 0o644)
        handle.flush()
        os.fsync(handle.fileno())
    # Cooperative peers cannot interleave while the EX lease is held. These
    # checks detect nonparticipating writes; they are not a POSIX atomic CAS.
    _exclusive()
    now = target.lstat() if target.exists() else None
    if file_state(target) != original or identity != now:
        raise OwnershipError('concurrent target change; staged evidence retained')
    os.replace(staged, target)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def begin_pointer(snapshot: Path, agents: Path, *, domain: str):
    root, plan, _ = _context(snapshot, agents, domain)
    pointer = plan['pointer']
    if not pointer or file_state(Path(pointer['target'])) != pointer['before']:
        raise OwnershipError('unowned or missing pointer binding')
    _append(root / (POINTER + '.begin.json'), {'schema_version': BEGIN_SCHEMA,
            'label': POINTER, 'attempt_id': plan['attempt_id'], 'plan_hash': _digest(plan)})


def publish_pointer(snapshot: Path, agents: Path, *, domain: str):
    root, plan, _ = _context(snapshot, agents, domain)
    _begin_record(root, plan, POINTER)
    pointer = plan['pointer']
    if not pointer:
        raise OwnershipError('missing pointer binding')
    data = _bytes(snapshot / '.tennis-db-pointer-candidate')
    if hashlib.sha256(data).hexdigest() != pointer['candidate']['sha256']:
        raise OwnershipError('pointer candidate changed')
    _publish_file(Path(pointer['target']), data, pointer['before'])


def verify_recovery(snapshot: Path, agents: Path, *, domain: str, launchctl: str):
    """Validate ALL changed jobs before a caller mutates any runtime state."""
    root, plan, before = _context(snapshot, agents, domain)
    current = observe(agents, launchctl=launchctl, domain=domain, labels=tuple(sorted(LABELS)))
    pointer_entry = root / (POINTER + '.begin.json')
    if pointer_entry.exists() or pointer_entry.is_symlink():
        _begin_record(root, plan, POINTER)
    if plan['pointer']:
        pointer = plan['pointer']
        current_pointer = file_state(Path(pointer['target']))
        if current_pointer != pointer['before']:
            _begin_record(root, plan, POINTER)
            if current_pointer != pointer['candidate']:
                raise OwnershipError('unowned pointer state; recovery blocked')
    changed = []
    for label in sorted(LABELS):
        entry = root / (label + '.begin.json')
        if entry.exists() or entry.is_symlink():
            _begin_record(root, plan, label)  # Never silently skip damaged records.
        old, new = before['jobs'][label], current['jobs'][label]
        if old == new:
            continue
        _begin_record(root, plan, label)
        if (new['file'] not in (old['file'], plan['candidates'][label])
                or new['disabled'] not in (old['disabled'], False)):
            raise OwnershipError('changed runtime state is not owned by this attempt')
        changed.append(label)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('prepare', 'begin-job', 'publish-job',
                        'begin-pointer', 'publish-pointer', 'verify-recovery'), required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--agents', type=Path, required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--launchctl', required=True)
    parser.add_argument('--commit')
    parser.add_argument('--label')
    args = parser.parse_args(argv)
    binding = {'domain': args.domain}
    try:
        if args.mode == 'prepare':
            prepare(args.snapshot, args.agents, **binding, launchctl=args.launchctl, commit=args.commit or '')
        elif args.mode == 'begin-job':
            begin_job(args.snapshot, args.agents, **binding, launchctl=args.launchctl, label=args.label)
        elif args.mode == 'publish-job':
            publish_job(args.snapshot, args.agents, **binding, label=args.label)
        elif args.mode == 'begin-pointer':
            begin_pointer(args.snapshot, args.agents, **binding)
        elif args.mode == 'publish-pointer':
            publish_pointer(args.snapshot, args.agents, **binding)
        else:
            print('\n'.join(verify_recovery(args.snapshot, args.agents, **binding, launchctl=args.launchctl)))
        return 0
    except (OwnershipError, OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
        print('runtime write ownership unverified; mutation/recovery blocked', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
