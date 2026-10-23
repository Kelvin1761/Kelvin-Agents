from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi import release_activation as activation  # noqa: E402


@pytest.mark.parametrize("code", [0, 7])
def test_installer_command_preserves_result(tmp_path, code):
    result = activation._run_installer(
        tmp_path, sys.executable, "-c",
        f"import sys; print('out'); print('err', file=sys.stderr); sys.exit({code})",
        timeout=5,
    )
    assert result.returncode == code
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"


def test_installer_timeout_retains_bounded_stage_output(tmp_path):
    result = activation._run_installer(
        tmp_path, sys.executable, "-u", "-c",
        "import sys,time; print('stage:hkjc'); print('x'*10000); "
        "print('last-stage',file=sys.stderr); time.sleep(20)", timeout=0.3,
    )
    assert result.returncode == 124
    message = str(activation._command_failure("installer failed", result))
    assert "timed out" in message
    assert "stage:hkjc" in message and "last-stage" in message
    assert len(message) < 4500


@pytest.mark.parametrize("parent_exits", [False, True])
def test_owned_descendants_stop_before_return(tmp_path, parent_exits):
    child_pid = tmp_path / "child.pid"
    mutation = tmp_path / "late-write"
    child = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(child_pid)!r}).write_text(str(os.getpid())); "
        f"time.sleep(1); Path({str(mutation)!r}).write_text('unsafe')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "from pathlib import Path; "
        f"ready=Path({str(child_pid)!r}); "
        "\nwhile not ready.exists(): time.sleep(0.01)\n"
        + ("" if parent_exits else "time.sleep(20)")
    )
    try:
        if parent_exits:
            result = activation._run_installer(tmp_path, sys.executable, "-c", parent, timeout=5)
            assert result.returncode == 0
        else:
            result = activation._run_installer(tmp_path, sys.executable, "-c", parent, timeout=0.4)
            assert result.returncode == 124
            assert "timed out" in result.stderr
        assert child_pid.exists(), "fixture child must start before timeout"
        time.sleep(1.1)
        assert not mutation.exists(), "installer descendants must not race rollback"
    finally:
        if child_pid.exists():
            try:
                os.kill(int(child_pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
