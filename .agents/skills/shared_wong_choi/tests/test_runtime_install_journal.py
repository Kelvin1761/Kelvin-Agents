"""Exercise real renderer proofs and file publication, without any native jobs."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import runtime_install_journal as journal
from shared_wong_choi import runtime_snapshot_state as state
from shared_wong_choi.runtime_cutover_lease import FD_ENV, cutover_lease

REPO = Path(__file__).resolve().parents[4]
LABEL = 'com.antigravity.hkjc-wong-choi.prerace'


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    agents = home / 'Library/LaunchAgents'
    agents.mkdir(parents=True)
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir(mode=0o700)
    runtime = home / 'runtime'
    runtime.mkdir()
    (runtime / 'tennis_wc.db').write_bytes(b'fixture, never opened')
    (runtime / '.env').write_text('fixture, never sourced')
    python = runtime / 'python'
    python.write_text('#!/bin/sh\nexit 99\n')
    python.chmod(0o755)
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('WONGCHOI_CONTROL_STATE_ROOT', str(tmp_path / 'control'))
    monkeypatch.setenv('WC_TENNIS_RUNTIME_ROOT', str(runtime))
    monkeypatch.setenv('TENNIS_PYTHON_BIN', str(python))
    monkeypatch.delenv(FD_ENV, raising=False)
    candidate = snapshot / 'candidates'
    render = subprocess.run(['/bin/zsh', str(REPO / '.agents/skills/central_wong_choi/install_production_runtime.sh'),
                             '--render-only', str(candidate)],
                            capture_output=True, text=True, timeout=20)
    assert render.returncode == 0, render.stderr
    assert len(list(candidate.iterdir())) == 20
    target = agents / (LABEL + '.plist')
    target.write_bytes(b'previous fixture plist, never installed')
    shutil.copy2(target, snapshot / target.name)
    def probe(_launchctl, *args):
        if args[0] == 'print-disabled':
            return SimpleNamespace(returncode=0, stdout='disabled services = {}', stderr='')
        return SimpleNamespace(returncode=113, stdout='', stderr='Could not find service')
    monkeypatch.setattr(state, '_probe', probe)
    monkeypatch.setattr(journal, '_probe', probe)
    pointer = home / '.wongchoi_tennis_db'
    pointer.write_bytes(b'original fixture database path\n')
    pointer.chmod(0o640)
    shutil.copy2(pointer, snapshot / '.tennis-db-pointer-original')
    (snapshot / '.tennis-db-pointer-path').write_text(str(pointer) + '\n')
    (snapshot / '.tennis-db-pointer-candidate').write_text(str(runtime / 'tennis_wc.db') + '\n')
    domain = 'gui/' + str(os.getuid())
    state.save_observation(snapshot, agents, launchctl='fake', domain=domain, labels=tuple(sorted(state.LABELS)))
    with cutover_lease('exclusive') as fd:
        monkeypatch.setenv(FD_ENV, str(fd))
        plan = journal.prepare(snapshot, agents, domain=domain, launchctl='fake', commit='1' * 40)
        yield snapshot, agents, domain, plan


def test_plan_precedes_writes_and_cannot_be_rewritten(prepared):
    snapshot, agents, domain, plan = prepared
    assert (agents / (LABEL + '.plist')).read_bytes() == b'previous fixture plist, never installed'
    proof = snapshot / journal.DIRECTORY / 'plan.json'
    assert proof.stat().st_mode & 0o777 == 0o600
    assert len(plan['candidates']) == 20
    with pytest.raises(FileExistsError):
        journal.prepare(snapshot, agents, domain=domain, launchctl='fake', commit='1' * 40)


def test_publisher_requires_begin_before_any_target_write(prepared):
    snapshot, agents, domain, _ = prepared
    before = (agents / (LABEL + '.plist')).read_bytes()
    with pytest.raises(FileNotFoundError):
        journal.publish_job(snapshot, agents, domain=domain, label=LABEL)
    assert (agents / (LABEL + '.plist')).read_bytes() == before


def test_owned_publication_matches_real_renderer_and_allows_recovery(prepared):
    snapshot, agents, domain, _ = prepared
    journal.begin_job(snapshot, agents, domain=domain, launchctl='fake', label=LABEL)
    journal.publish_job(snapshot, agents, domain=domain, label=LABEL)
    assert (agents / (LABEL + '.plist')).read_bytes() == (snapshot / 'candidates' / (LABEL + '.plist')).read_bytes()
    assert journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake') == [LABEL]


@pytest.mark.parametrize('mutation', ['replace', 'remove', 'create'])
def test_unknown_post_snapshot_change_never_becomes_owned(prepared, mutation):
    snapshot, agents, domain, _ = prepared
    label = 'com.antigravity.nba-wong-choi.health' if mutation == 'create' else LABEL
    path = agents / (label + '.plist')
    if mutation == 'remove':
        path.unlink()
        expected = None
    else:
        expected = b'independent actor bytes'
        path.write_bytes(expected)
    with pytest.raises((OSError, journal.OwnershipError)):
        journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake')
    with pytest.raises(journal.OwnershipError):
        journal.begin_job(snapshot, agents, domain=domain, launchctl='fake', label=label)
    assert (path.read_bytes() if path.exists() else None) == expected
    assert not (snapshot / journal.DIRECTORY / (label + '.begin.json')).exists()


def test_foreign_change_after_owned_write_blocks_recovery(prepared):
    snapshot, agents, domain, _ = prepared
    journal.begin_job(snapshot, agents, domain=domain, launchctl='fake', label=LABEL)
    journal.publish_job(snapshot, agents, domain=domain, label=LABEL)
    target = agents / (LABEL + '.plist')
    target.write_bytes(b'foreign replacement after publication')
    with pytest.raises(journal.OwnershipError):
        journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake')
    assert target.read_bytes() == b'foreign replacement after publication'
    assert (snapshot / journal.DIRECTORY / (LABEL + '.begin.json')).exists()


def test_changed_candidate_cannot_be_published_or_adopted(prepared):
    snapshot, agents, domain, _ = prepared
    journal.begin_job(snapshot, agents, domain=domain, launchctl='fake', label=LABEL)
    (snapshot / 'candidates' / (LABEL + '.plist')).write_bytes(b'arbitrary current bytes')
    with pytest.raises((ValueError, journal.OwnershipError)):
        journal.publish_job(snapshot, agents, domain=domain, label=LABEL)
    assert (agents / (LABEL + '.plist')).read_bytes() == b'previous fixture plist, never installed'


def test_damaged_begin_is_not_ignored_even_when_runtime_is_unchanged(prepared):
    snapshot, agents, domain, _ = prepared
    journal.begin_job(snapshot, agents, domain=domain, launchctl='fake', label=LABEL)
    path = snapshot / journal.DIRECTORY / (LABEL + '.begin.json')
    value = json.loads(path.read_text())
    value['label'] = 'wrong'
    path.write_text(json.dumps(value))
    with pytest.raises(journal.OwnershipError):
        journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake')
    with pytest.raises(journal.OwnershipError):
        journal.verify_unchanged(snapshot, agents, domain=domain, launchctl='fake')


def test_no_inherited_exclusive_authority_no_journal_mutation(prepared, monkeypatch):
    snapshot, agents, domain, _ = prepared
    monkeypatch.delenv(FD_ENV)
    with pytest.raises(RuntimeError):
        journal.begin_job(snapshot, agents, domain=domain, launchctl='fake', label=LABEL)
    assert not (snapshot / journal.DIRECTORY / (LABEL + '.begin.json')).exists()


def test_pointer_requires_prewrite_intent_then_publishes_bound_bytes(prepared):
    snapshot, agents, domain, plan = prepared
    target = Path(plan['pointer']['target'])
    original = target.read_bytes()
    with pytest.raises(FileNotFoundError):
        journal.publish_pointer(snapshot, agents, domain=domain)
    assert target.read_bytes() == original
    journal.begin_pointer(snapshot, agents, domain=domain)
    journal.publish_pointer(snapshot, agents, domain=domain)
    assert target.read_bytes() == (snapshot / '.tennis-db-pointer-candidate').read_bytes()
    assert target.stat().st_mode & 0o777 == 0o644
    assert journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake') == []


@pytest.mark.parametrize('phase', ['before-begin', 'after-publish'])
def test_foreign_pointer_is_never_adopted_or_restored(prepared, phase):
    snapshot, agents, domain, plan = prepared
    target = Path(plan['pointer']['target'])
    if phase == 'after-publish':
        journal.begin_pointer(snapshot, agents, domain=domain)
        journal.publish_pointer(snapshot, agents, domain=domain)
    target.write_bytes(b'independent pointer configuration')
    if phase == 'before-begin':
        with pytest.raises(journal.OwnershipError):
            journal.begin_pointer(snapshot, agents, domain=domain)
    with pytest.raises((OSError, journal.OwnershipError)):
        journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake')
    assert target.read_bytes() == b'independent pointer configuration'


def test_other_snapshot_cannot_reuse_an_existing_write_plan(prepared):
    snapshot, agents, domain, _ = prepared
    other = snapshot.parent / 'different-attempt'
    shutil.copytree(snapshot, other)
    with pytest.raises(journal.OwnershipError):
        journal.begin_job(other, agents, domain=domain, launchctl='fake', label=LABEL)


def test_symlink_begin_proof_is_not_read(prepared):
    snapshot, agents, domain, _ = prepared
    root = snapshot / journal.DIRECTORY
    (root / (LABEL + '.begin.json')).symlink_to(root / 'plan.json')
    with pytest.raises(OSError):
        journal.verify_recovery(snapshot, agents, domain=domain, launchctl='fake')


def test_checkout_advance_after_plan_blocks_actual_publisher_cli(prepared):
    snapshot, agents, domain, _ = prepared
    repo = snapshot.parent / 'source-repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()
    git('init')
    git('config', 'user.name', 'Ownership Fixture')
    git('config', 'user.email', 'fixture@example.test')
    git('config', 'commit.gpgSign', 'false')
    git('config', 'core.hooksPath', '/dev/null')
    (repo / 'source').write_text('approved fixture source')
    git('add', 'source')
    git('commit', '-m', 'fixture base')
    original_commit = git('rev-parse', 'HEAD')
    bound = snapshot.parent / 'bound-snapshot'
    shutil.copytree(snapshot, bound, ignore=shutil.ignore_patterns(journal.DIRECTORY))
    journal.prepare(bound, agents, domain=domain, launchctl='fake', commit=original_commit)
    journal.begin_job(bound, agents, domain=domain, launchctl='fake', label=LABEL)
    (repo / 'source').write_text('independent fixture source advance')
    git('add', 'source')
    git('commit', '-m', 'fixture advance')
    target = agents / (LABEL + '.plist')
    before = target.read_bytes()
    result = subprocess.run([sys.executable, str(REPO / '.agents/skills/shared_wong_choi/runtime_install_journal.py'),
        '--mode', 'publish-job', '--snapshot', str(bound), '--agents', str(agents),
        '--domain', domain, '--launchctl', 'fake', '--label', LABEL,
        '--repo', str(repo), '--expected-commit', original_commit],
        pass_fds=(int(os.environ[FD_ENV]),), capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert target.read_bytes() == before
    assert not list(agents.glob('.wc-owned-publication-*'))
