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
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared_wong_choi.runtime_cutover_lease import inherited_lease, lease_path
from shared_wong_choi.runtime_snapshot_state import (
    LABELS, MAX_PLIST_BYTES, _digest, _probe, disabled_jobs, job_loaded, file_state, load_observation, observe,
)

SCHEMA = 'wong-choi-runtime-write-plan/v1'
BEGIN_SCHEMA = 'wong-choi-runtime-write-begin/v1'
DIRECTORY = '.write-ownership'


class OwnershipError(RuntimeError):
    pass


def _exclusive():
    return inherited_lease('exclusive', lease_path())


def _safe_root(path: Path, *, private=False):
    if any(item.is_symlink() for item in (path, *path.parents)) or not path.is_dir():
        raise OwnershipError('unsafe ownership root')
    metadata = path.stat()
    if private and (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise OwnershipError('ownership directory is not private')


def _bytes(path: Path, *, private=False, limit=MAX_PLIST_BYTES) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit
                or (private and (before.st_uid != os.getuid() or before.st_nlink != 1
                                 or stat.S_IMODE(before.st_mode) != 0o600))):
            raise OwnershipError('unsafe proof file')
        data = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
        named = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if (len(data) > limit or identity(before) != identity(after)
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
            'prepared_at': datetime.now(timezone.utc).isoformat(),
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
                      'agents_root', 'domain', 'before_hash', 'candidates', 'pointer', 'prepared_at'}
            or plan['schema_version'] != SCHEMA
            or not re.fullmatch('[0-9a-f]{32}', plan['attempt_id'])
            or not re.fullmatch('[0-9a-f]{40}', plan['commit'])
            or plan['snapshot_root'] != str(snapshot.resolve())
            or plan['agents_root'] != str(agents.resolve()) or plan['domain'] != domain
            or plan['before_hash'] != _digest(before) or plan['pointer'] != _pointer(snapshot)
            or plan['candidates'] != _candidate_states(snapshot / 'candidates')):
        raise OwnershipError('ownership plan binding mismatch')
    _aware_time(plan['prepared_at'])
    allowed = {'plan.json'} | {label + '.begin.json' for label in LABELS | {POINTER}}
    if any(p.name not in allowed for p in root.iterdir()):
        raise OwnershipError('unknown ownership record')
    return root, plan, before


def _begin_record(root, plan, label):
    value = _load(root / (label + '.begin.json'))
    if value != {'schema_version': BEGIN_SCHEMA, 'label': label,
                 'attempt_id': plan['attempt_id'], 'plan_hash': _digest(plan)}:
        raise OwnershipError('write intent binding mismatch')


def _job_current(agents: Path, domain: str, launchctl: str, label: str):
    registry = _probe(launchctl, 'print-disabled', domain)
    if registry.returncode:
        raise OwnershipError('cannot observe native flags')
    value = {'file': file_state(agents / (label + '.plist')),
             'loaded': job_loaded(launchctl, domain, label),
             'disabled': disabled_jobs(registry.stdout).get(label, False)}
    if value['loaded'] and not value['file']['exists']:
        raise OwnershipError('loaded job has no restorable plist')
    return value


def verify_unchanged(snapshot: Path, agents: Path, *, domain: str, launchctl: str):
    _exclusive()
    _safe_root(snapshot, private=True)
    ownership = snapshot / DIRECTORY
    if ownership.exists() or ownership.is_symlink():
        if verify_recovery(snapshot, agents, domain=domain, launchctl=launchctl):
            raise OwnershipError('owned jobs have not returned to original state')
        pointer = _pointer(snapshot)
        if pointer and file_state(Path(pointer['target'])) != pointer['before']:
            raise OwnershipError('owned pointer has not returned to original state')
        return
    before = load_observation(snapshot, agents, domain=domain, labels=tuple(sorted(LABELS)))
    if observe(agents, launchctl=launchctl, domain=domain, labels=tuple(sorted(LABELS))) != before:
        raise OwnershipError('no write proof for changed runtime')
    pointer = _pointer(snapshot)
    if pointer and file_state(Path(pointer['target'])) != pointer['before']:
        raise OwnershipError('no write proof for changed pointer')


def verify_job(snapshot: Path, agents: Path, *, domain: str, launchctl: str, label: str):
    if label not in LABELS:
        raise OwnershipError('unallowlisted job')
    root, plan, before = _context(snapshot, agents, domain)
    _begin_record(root, plan, label)
    old = before['jobs'][label]
    current = _job_current(agents, domain, launchctl, label)
    if (current['file'] not in (old['file'], plan['candidates'][label])
            or current['disabled'] not in (old['disabled'], False)):
        raise OwnershipError('unowned job state; recovery blocked')


def begin_job(snapshot: Path, agents: Path, *, domain: str, launchctl: str, label: str):
    """Record intent before any native unload, file publication or flag change."""
    if label not in LABELS:
        raise OwnershipError('unallowlisted job')
    root, plan, before = _context(snapshot, agents, domain)
    current = _job_current(agents, domain, launchctl, label)
    if current != before['jobs'][label]:
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



def restore_job(snapshot: Path, agents: Path, *, domain: str, launchctl: str, label: str):
    """Restore verified original bytes without exposing a partial target file."""
    verify_job(snapshot, agents, domain=domain, launchctl=launchctl, label=label)
    _, plan, before = _context(snapshot, agents, domain)
    original = before['jobs'][label]['file']
    if not original['exists']:
        raise OwnershipError('original plist is absent')
    target = agents / (label + '.plist')
    current = file_state(target)
    if current == original:
        return
    if current != plan['candidates'][label]:
        raise OwnershipError('unowned target before original publication')
    data = _bytes(snapshot / (label + '.plist'))
    if hashlib.sha256(data).hexdigest() != original['sha256']:
        raise OwnershipError('original changed before publication')
    _publish_file(target, data, current, mode=original['mode'])


def _publish_file(target, data, original, *, mode=0o644):
    if any(part.is_symlink() for part in target.parents):
        raise OwnershipError('symlinked publication parent')
    if file_state(target) != original:
        raise OwnershipError('unowned target before candidate publication')
    identity = target.lstat() if target.exists() else None
    fd, raw = tempfile.mkstemp(prefix='.wc-owned-publication-', dir=target.parent)
    staged = Path(raw)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        os.fchmod(handle.fileno(), mode)
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



def _aware_time(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise OwnershipError('acceptance time must be timezone-aware')
    return stamp


def _receipt_payload(path: Path):
    if any(parent.is_symlink() for parent in path.parents):
        raise OwnershipError('symlinked acceptance receipt root')
    if not path.is_absolute() or '..' in path.parts or path != path.resolve():
        raise OwnershipError('noncanonical acceptance receipt path')
    path.relative_to(lease_path().parent.resolve() / 'runs' / 'central')
    raw = _bytes(path, limit=1024 * 1024)
    value = json.loads(raw, object_pairs_hook=_pairs)
    if (not isinstance(value, dict) or value.get('content_hash') != _digest(
            {key: item for key, item in value.items() if key != 'content_hash'})
            or value.get('run_log') != str(path) or value.get('status') != 'succeeded'
            or value.get('schema_version') != 'wong-choi-central-research-review-run/v1'):
        raise OwnershipError('native acceptance receipt is invalid')
    return raw, value


def installation_binding(snapshot: Path, agents: Path, *, domain: str):
    _, plan, _ = _context(snapshot, agents, domain)
    return {'attempt_id': plan['attempt_id'], 'plan_hash': _digest(plan), 'commit': plan['commit']}


def _native_status(receipt: Path):
    repo = Path(__file__).resolve().parents[3]
    checked = subprocess.run(
        ['/bin/zsh', str(repo / '.agents/skills/central_wong_choi/scripts/run_central_research_review.sh'),
         '--status', '--receipt', str(receipt)], text=True, capture_output=True,
        timeout=60, check=False, pass_fds=(_exclusive(),))
    if checked.returncode or len(checked.stdout.encode()) > 2 * 1024 * 1024:
        raise OwnershipError('authoritative native acceptance verification failed')
    value = json.loads(checked.stdout, object_pairs_hook=_pairs)
    if not isinstance(value, dict) or value.get('status') != 'verified':
        raise OwnershipError('authoritative native acceptance is not verified')
    return value


def record_acceptance(snapshot: Path, agents: Path, *, domain: str, receipt: Path):
    """Bind the actual native verifier's successful report to this install plan.

    Hashes are evidence identity, never permission to install or run research.
    Invoke the existing authoritative native status verifier here, never accept
    a caller-supplied JSON claim that verification happened.
    """
    _, plan, _ = _context(snapshot, agents, domain)
    receipt = receipt.absolute()
    raw, payload = _receipt_payload(receipt)
    checked = _native_status(receipt)
    started = _aware_time(payload.get('started_at'))
    now = datetime.now(timezone.utc)
    if (not isinstance(checked, dict) or checked.get('status') != 'verified'
            or checked.get('receipt') != payload
            or checked.get('receipt_sha256') != hashlib.sha256(raw).hexdigest()
            or payload.get('installation_binding') != installation_binding(snapshot, agents, domain=domain)
            or checked.get('receipt_stale')
            or not _aware_time(plan['prepared_at']) <= started <= now
            or now.timestamp() - started.timestamp() > 36 * 3600
            or set(checked.get('domains', {})) != {'au', 'hkjc', 'nba', 'tennis'}
            or any(item.get('status') != 'verified' for item in checked['domains'].values())):
        raise OwnershipError('native acceptance report does not verify this fresh receipt')
    body = {'schema_version': 'wong-choi-runtime-acceptance/v1',
            'attempt_id': plan['attempt_id'], 'plan_hash': _digest(plan),
            'commit': plan['commit'], 'snapshot_root': str(snapshot.resolve()),
            'receipt_path': str(receipt), 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
            'receipt_content_hash': payload['content_hash'],
            'recorded_at': now.isoformat()}
    _append(snapshot / '.native-acceptance.json', body)
    return body


def verify_acceptance(snapshot: Path, agents: Path, *, domain: str):
    _, plan, _ = _context(snapshot, agents, domain)
    proof = _load(snapshot / '.native-acceptance.json')
    fields = {'schema_version', 'attempt_id', 'plan_hash', 'commit', 'snapshot_root',
              'receipt_path', 'receipt_sha256', 'receipt_content_hash', 'recorded_at'}
    if (set(proof) != fields or proof['schema_version'] != 'wong-choi-runtime-acceptance/v1'
            or proof['attempt_id'] != plan['attempt_id'] or proof['plan_hash'] != _digest(plan)
            or proof['commit'] != plan['commit'] or proof['snapshot_root'] != str(snapshot.resolve())):
        raise OwnershipError('native acceptance belongs to another attempt')
    raw, payload = _receipt_payload(Path(proof['receipt_path']))
    checked = _native_status(Path(proof['receipt_path']))
    now = datetime.now(timezone.utc)
    started = _aware_time(payload.get('started_at'))
    if (checked.get('receipt_sha256') != hashlib.sha256(raw).hexdigest()
            or checked.get('receipt') != payload
            or payload.get('installation_binding') != installation_binding(snapshot, agents, domain=domain)
            or hashlib.sha256(raw).hexdigest() != proof['receipt_sha256']
            or payload['content_hash'] != proof['receipt_content_hash']
            or not _aware_time(plan['prepared_at']) <= started <= _aware_time(proof['recorded_at']) <= now
            or now.timestamp() - started.timestamp() > 36 * 3600):
        raise OwnershipError('native acceptance receipt changed or expired')
    return proof

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('prepare', 'begin-job', 'publish-job',
                        'begin-pointer', 'publish-pointer', 'restore-job', 'verify-job', 'verify-unchanged', 'verify-recovery', 'record-acceptance', 'verify-acceptance'), required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--agents', type=Path, required=True)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--launchctl', required=True)
    parser.add_argument('--commit')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--expected-commit')
    parser.add_argument('--label')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    binding = {'domain': args.domain}
    try:
        pointer = _pointer(args.snapshot)
        expected_pointer = os.environ.get('WC_TENNIS_DB_POINTER') or str(Path.home() / '.wongchoi_tennis_db')
        if pointer and pointer['target'] != expected_pointer:
            raise OwnershipError('pointer configuration changed since snapshot')
        if args.expected_commit and not args.repo:
            raise OwnershipError('expected source requires a bound checkout')
        if args.repo:
            actual = subprocess.run(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'],
                                    text=True, capture_output=True, timeout=10, check=False)
            current = actual.stdout.strip()
            if actual.returncode or not re.fullmatch('[0-9a-f]{40}', current):
                raise OwnershipError('current checkout source unverified')
            if args.expected_commit and current != args.expected_commit:
                raise OwnershipError('checkout differs from immutable activation target')
            if args.mode == 'prepare' and current != args.commit:
                raise OwnershipError('planned source differs from current checkout')
            proof = args.snapshot / DIRECTORY / 'plan.json'
            if proof.exists() or proof.is_symlink():
                if _load(proof).get('commit') != current:
                    raise OwnershipError('attempt belongs to a different checkout source')
        if args.mode == 'prepare':
            prepare(args.snapshot, args.agents, **binding, launchctl=args.launchctl, commit=args.commit or '')
        elif args.mode == 'begin-job':
            begin_job(args.snapshot, args.agents, **binding, launchctl=args.launchctl, label=args.label)
        elif args.mode == 'publish-job':
            publish_job(args.snapshot, args.agents, **binding, label=args.label)
        elif args.mode == 'restore-job':
            restore_job(args.snapshot, args.agents, **binding, launchctl=args.launchctl, label=args.label)
        elif args.mode == 'verify-job':
            verify_job(args.snapshot, args.agents, **binding, launchctl=args.launchctl, label=args.label)
        elif args.mode == 'verify-unchanged':
            verify_unchanged(args.snapshot, args.agents, **binding, launchctl=args.launchctl)
        elif args.mode == 'record-acceptance':
            record_acceptance(args.snapshot, args.agents, **binding, receipt=args.receipt)
        elif args.mode == 'verify-acceptance':
            print(json.dumps(verify_acceptance(args.snapshot, args.agents, **binding)))
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
