"""Kernel argv decoding/classification and read-only discovery failures."""
import ctypes
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.runtime_active_runs import (
    ActiveRun, BSDInfo, DarwinProcesses, DiscoveryError, decode_procargs,
    protected_command, verify_idle,
)


def test_native_layout_matches_compiled_local_sdk():
    assert ctypes.sizeof(BSDInfo) == 136
    assert BSDInfo.start_sec.offset == 120
    assert BSDInfo.uid.offset == 20


def test_decoder_preserves_spaces_and_stops_before_environment():
    raw = struct.pack('=i', 4) + b'/python\0\0\0python3\0-X\0dev\0dir with spaces/central_research_review.py\0SECRET=never-return\xff\0'
    executable, argv = decode_procargs(raw)
    assert argv == ('python3', '-X', 'dev', 'dir with spaces/central_research_review.py')
    assert protected_command(executable, argv)
    assert 'SECRET' not in repr((executable, argv))


@pytest.mark.parametrize('raw', [b'', struct.pack('=i', 0) + b'x\0',
    struct.pack('=i', 2) + b'/python\0python\0incomplete'])
def test_damaged_kernel_args_block(raw):
    with pytest.raises(DiscoveryError):
        decode_procargs(raw)


@pytest.mark.parametrize('exe,argv', [
    ('/path with space/Python', ('renamed', '-X', 'dev', 'dir with space/nba_daily_schedule.py')),
    ('/python3', ('python3', '-Wignore', '-m', 'package.central_research_review')),
    ('/zsh', ('zsh', '-f', './path with spaces/run_central_research_review.sh')),
    ('/python3', ('python3', '--', 'tennis_preclose_refresh.py')),
])
def test_exact_executed_operands_are_busy(exe, argv):
    assert protected_command(exe, argv)


@pytest.mark.parametrize('exe,argv', [
    ('/python3', ('python3', 'scoped_release.py', '--path', 'nba_daily_schedule.py')),
    ('/python3', ('python3', '-m', 'pytest', 'test_nba_daily_schedule.py')),
    ('/zsh', ('zsh', '保存.sh', '--path', 'run_nba_daily_schedule.sh')),
    ('/native-app', ('python3', 'central_research_review.py')),
])
def test_scope_arguments_do_not_become_jobs(exe, argv):
    assert not protected_command(exe, argv)


@pytest.mark.parametrize('exe,argv', [
    ('/python3', ('python3', '-c', 'arbitrary dynamic code')),
    ('/python3', ('python3', '-')),
    ('/python3', ('python3', '-X')),
    ('/python3', ('python3', '--unknown', 'file.py')),
    ('/zsh', ('zsh', '-lc', 'dynamic shell command')),
])
def test_ambiguous_interpreters_cannot_authorize_installation(exe, argv):
    with pytest.raises(DiscoveryError):
        protected_command(exe, argv)


class Observer:
    def pids(self):
        return {11}

    def identity(self, pid):
        return (pid, os.getuid(), 100, 123, 2)

    def argv(self, pid):
        return '/python3', ('python3', 'scoped_release.py', '--path', 'nba_daily_schedule.py')


def test_two_inventories_are_required():
    class Changed(Observer):
        calls = 0
        def pids(self):
            self.calls += 1
            return {11} if self.calls == 1 else {11, 12}
        def argv(self, pid):
            return super().argv(pid) if pid == 11 else ('/python3', ('python3', 'nba_daily_schedule.py'))
    with pytest.raises(ActiveRun):
        verify_idle(Changed())


def test_pid_reuse_or_unreadable_args_blocks():
    class Reused(Observer):
        calls = 0
        def identity(self, pid):
            self.calls += 1
            return (pid, os.getuid(), 100, self.calls, 2)
    with pytest.raises(DiscoveryError):
        verify_idle(Reused())
    class Unreadable(Observer):
        def argv(self, pid):
            raise PermissionError('sensitive data must not escape')
    with pytest.raises(DiscoveryError):
        verify_idle(Unreadable())
    assert verify_idle(Observer()) == 1


def test_actual_kernel_argv_of_owned_spaced_process(tmp_path):
    import time
    folder = tmp_path / 'folder with spaces'
    folder.mkdir()
    script = folder / 'central_research_review.py'
    script.write_text('import time\ntime.sleep(60)\n')
    process = subprocess.Popen([sys.executable, '-X', 'dev', str(script)])
    try:
        time.sleep(0.1)
        observer = DarwinProcesses()
        before = observer.identity(process.pid)
        executable, argv = observer.argv(process.pid)
        assert observer.identity(process.pid) == before
        assert str(script) in argv
        assert protected_command(executable, argv)
    finally:
        process.terminate()
        process.wait(timeout=10)
