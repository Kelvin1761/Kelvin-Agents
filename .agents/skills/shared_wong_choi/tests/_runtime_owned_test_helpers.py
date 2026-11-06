"""Build real pre-write proofs in fixture roots; never synthesize journal JSON."""
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEASE = ROOT / '.agents/skills/shared_wong_choi/runtime_cutover_lease.py'
JOURNAL = ROOT / '.agents/skills/shared_wong_choi/runtime_install_journal.py'
INSTALLER = ROOT / '.agents/skills/central_wong_choi/install_production_runtime.sh'


def owned_cli(env, snapshot, mode, label=None):
    snapshot = Path(snapshot)
    scope = snapshot.parent.resolve()
    runtime = Path(env['WC_TENNIS_RUNTIME_ROOT'])
    control = Path(env['WONGCHOI_CONTROL_STATE_ROOT'])
    assert runtime.resolve().is_relative_to(scope)
    assert control.resolve().is_relative_to(scope)
    if not (snapshot / '.write-ownership').exists():
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / 'tennis_wc.db').touch(exist_ok=True)  # Fixture only; renderer never opens it.
        (runtime / '.env').write_text('fixture, never sourced')
        python = runtime / 'fixture-python'
        python.write_text('#!/bin/sh\nexit 99\n')
        python.chmod(0o755)
        env = {**env, 'TENNIS_PYTHON_BIN': str(python)}
        rendered = subprocess.run(['/bin/zsh', str(INSTALLER), '--render-only', str(snapshot / 'candidates')],
                                  env=env, capture_output=True, text=True, timeout=20)
        assert rendered.returncode == 0, rendered.stderr
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        result = _run(env, snapshot, 'prepare', commit=commit)
        assert result.returncode == 0, result.stderr
    result = _run(env, snapshot, mode, label=label)
    assert result.returncode == 0, result.stderr


def _run(env, snapshot, mode, *, label=None, commit=None):
    args = [sys.executable, str(LEASE), '--mode', 'exclusive', '--',
            sys.executable, str(JOURNAL), '--mode', mode, '--snapshot', str(snapshot),
            '--agents', env['WC_LAUNCH_AGENTS_DIR'], '--launchctl', env['WC_LAUNCHCTL_BIN'],
            '--domain', 'gui/' + str(os.getuid())]
    if label:
        args += ['--label', label]
    if commit:
        args += ['--commit', commit]
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)


def owned_publication(env, snapshot, label):
    owned_cli(env, snapshot, 'begin-job', label)
    owned_cli(env, snapshot, 'publish-job', label)


def isolated_observer_installer(tmp_path):
    """Keep simulated recovery independent of host process activity."""
    observer = tmp_path / "idle-observer.py"
    observer.write_text("raise SystemExit(0)\n")
    isolated_installer = tmp_path / "install-runtime.sh"
    source = INSTALLER.read_text()
    assert 'runtime_active_guard || exit $?' in source
    assert 'runtime_active_guard || return 1' in source
    source = source.replace('PROJECT_ROOT="${SCRIPT_DIR:h:h:h}"',
                            'PROJECT_ROOT=' + shlex.quote(str(ROOT)), 1)
    source = source.replace('ACTIVE_RUN_GUARD="$PROJECT_ROOT/.agents/skills/shared_wong_choi/runtime_active_runs.py"',
                            'ACTIVE_RUN_GUARD=' + shlex.quote(str(observer)), 1)
    isolated_installer.write_text(source)
    return isolated_installer
