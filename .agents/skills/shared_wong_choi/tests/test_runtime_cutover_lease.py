"""Real flock/process tests, isolated from native jobs and production state."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.runtime_cutover_lease import (
    FD_ENV, CutoverLeaseError, cutover_lease, inherited_lease, lease_path,
)

HELPER = Path(__file__).resolve().parents[1] / 'runtime_cutover_lease.py'


@pytest.fixture(autouse=True)
def control(tmp_path, monkeypatch):
    monkeypatch.setenv('WONGCHOI_CONTROL_STATE_ROOT', str(tmp_path / 'control'))
    monkeypatch.delenv(FD_ENV, raising=False)


def run(mode, command, **kwargs):
    return subprocess.run([sys.executable, str(HELPER), '--mode', mode, '--', *command],
                          text=True, capture_output=True, timeout=10, **kwargs)


def test_shared_jobs_can_overlap_but_exclude_installer():
    with cutover_lease('shared'):
        assert run('shared', [sys.executable, '-c', 'pass']).returncode == 0
        assert run('exclusive', [sys.executable, '-c', 'raise SystemExit(88)']).returncode == 75


def test_installer_excludes_new_jobs_and_other_installers():
    with cutover_lease('exclusive'):
        for mode in ('shared', 'exclusive'):
            assert run(mode, [sys.executable, '-c', 'raise SystemExit(88)']).returncode == 75


def test_owned_exclusive_descriptor_survives_real_child_verification():
    result = run('exclusive', [sys.executable, str(HELPER), '--mode', 'exclusive', '--verify'])
    assert result.returncode == 0, result.stderr


def test_inherited_shared_descriptor_cannot_upgrade(monkeypatch):
    with cutover_lease('shared') as fd:
        monkeypatch.setenv(FD_ENV, str(fd))
        with pytest.raises(CutoverLeaseError):
            inherited_lease('exclusive', lease_path())
        # The rejected upgrade did not drop or strengthen our shared lease.
        env = dict(os.environ)
        env.pop(FD_ENV)
        assert run('shared', [sys.executable, '-c', 'pass'], env=env).returncode == 0
        assert run('exclusive', [sys.executable, '-c', 'pass'], env=env).returncode == 75


def test_unlocked_descriptor_cannot_forge_exclusive_ownership(monkeypatch):
    with cutover_lease('exclusive'):
        pass
    fd = os.open(lease_path(), os.O_RDWR)
    try:
        monkeypatch.setenv(FD_ENV, str(fd))
        with pytest.raises(CutoverLeaseError):
            inherited_lease('exclusive', lease_path())
    finally:
        os.close(fd)


def test_replaced_path_blocks_inherited_lease(monkeypatch):
    with cutover_lease('exclusive') as fd:
        path = lease_path()
        path.rename(path.with_suffix('.old'))
        path.write_bytes(b'')
        path.chmod(0o600)
        monkeypatch.setenv(FD_ENV, str(fd))
        with pytest.raises(CutoverLeaseError):
            inherited_lease('exclusive', path)


def test_stable_file_retained_after_release():
    with cutover_lease('exclusive'):
        identity = lease_path().stat().st_ino
    with cutover_lease('exclusive'):
        assert lease_path().stat().st_ino == identity


PYTHON_ENTRIES = (
    '.agents/skills/au_racing/au_daily_auto/au_daily_schedule.py',
    '.agents/skills/au_racing/au_daily_auto/au_healthcheck.py',
    '.agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py',
    '.agents/skills/nba/nba_daily_auto/nba_daily_schedule.py',
    'tennis-wong-choi/scripts/tennis_daily_schedule.py',
    'tennis-wong-choi/scripts/tennis_card_recovery.py',
    'tennis-wong-choi/scripts/tennis_preclose_refresh.py',
    '.agents/skills/central_wong_choi/scripts/central_daily_maintenance.py',
    '.agents/skills/central_wong_choi/scripts/central_research_review.py',
)
SHELL_ENTRIES = (
    ('.agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh', 'zsh'),
    ('.agents/skills/au_racing/au_daily_auto/run_au_auxiliary.sh', 'zsh'),
    ('.agents/skills/hkjc_racing/hkjc_daily_auto/run_hkjc_daily_schedule.sh', 'bash'),
    ('.agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh', 'bash'),
    ('tennis-wong-choi/scripts/run_tennis_daily_schedule.sh', 'zsh'),
    ('.agents/skills/central_wong_choi/scripts/run_central_daily_maintenance.sh', 'zsh'),
    ('.agents/skills/central_wong_choi/scripts/run_central_research_review.sh', 'zsh'),
)
INSTALLER_ENTRIES = (
    ('.agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh', 'bash'),
    ('.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh', 'bash'),
    ('tennis-wong-choi/scripts/install_macos_launchd.sh', 'zsh'),
    ('.agents/skills/central_wong_choi/install_macos_launchd.sh', 'zsh'),
    ('.agents/skills/central_wong_choi/install_research_review.sh', 'zsh'),
)
REPO = Path(__file__).resolve().parents[4]


def mini_entry(tmp_path, relative):
    import shutil

    root = tmp_path / 'mini'
    for name in (relative, '.agents/skills/shared_wong_choi/runtime_cutover_lease.py'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    return root


@pytest.mark.parametrize('relative', PYTHON_ENTRIES)
def test_direct_relative_python_x_entries_defer_before_domain_imports(tmp_path, relative):
    root = mini_entry(tmp_path, relative)
    # Miniature checkout deliberately has no domain modules/data/credentials.
    with cutover_lease('exclusive'):
        result = subprocess.run([sys.executable, '-X', 'dev', relative, '--help'],
                                cwd=root, text=True, capture_output=True, timeout=10)
    assert result.returncode == 75, result.stderr
    assert not list(root.rglob('logs'))


@pytest.mark.parametrize('relative,shell', SHELL_ENTRIES)
def test_scheduler_shells_defer_before_config_or_self_update(tmp_path, relative, shell):
    root = mini_entry(tmp_path, relative)
    with cutover_lease('exclusive'):
        result = subprocess.run(['/bin/' + shell, str(root / relative), 'healthcheck'],
                                text=True, capture_output=True, timeout=10)
    assert result.returncode == 75, result.stderr
    assert not list(root.rglob('logs'))


@pytest.mark.parametrize('relative,shell', INSTALLER_ENTRIES)
def test_standalone_installers_defer_to_active_shared_run(tmp_path, relative, shell):
    root = mini_entry(tmp_path, relative)
    with cutover_lease('shared'):
        result = subprocess.run(['/bin/' + shell, str(root / relative)],
                                text=True, capture_output=True, timeout=10)
    assert result.returncode == 75, result.stderr
    assert not list(root.rglob('logs'))


@pytest.mark.parametrize('parent_mode,expected', [('shared', 0), ('exclusive', 75)])
def test_scheduler_child_with_closed_parent_fd_must_reacquire_shared(parent_mode, expected):
    code = ("import sys; sys.path.insert(0, " + repr(str(HELPER.parents[1])) + "); "
            "from shared_wong_choi.runtime_cutover_lease import scheduler_entry; scheduler_entry()")
    env = {**os.environ, FD_ENV: '999999'}
    with cutover_lease(parent_mode):
        result = subprocess.run([sys.executable, '-c', code], env=env,
                                text=True, capture_output=True, timeout=10)
    assert result.returncode == expected, result.stderr
