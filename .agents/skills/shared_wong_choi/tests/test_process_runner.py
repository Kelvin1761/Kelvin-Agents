"""Exercise real process, pipe and lock failures without production data."""
import fcntl
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.process_runner import run_bounded  # noqa: E402


def test_invalid_log_bytes_preserve_exit_status(tmp_path):
    result = run_bounded(
        [
            sys.executable,
            "-c",
            "import os; os.write(2, b'bad: \\xef\\n'); raise SystemExit(7)",
        ],
        cwd=tmp_path,
        timeout=5,
    )
    assert result.returncode == 7
    assert "bad: \ufffd" in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups and locks")
def test_timeout_releases_grandchild_lock(tmp_path):
    lock = tmp_path / "worker.lock"
    ready = tmp_path / "ready"
    worker = (
        "import fcntl,time,pathlib; "
        f"f=open({str(lock)!r},'w'); fcntl.flock(f,fcntl.LOCK_EX); "
        f"pathlib.Path({str(ready)!r}).touch(); time.sleep(60)"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{worker!r}]); "
        "time.sleep(60)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", parent], cwd=tmp_path, timeout=1)
    assert ready.exists(), "The worker must acquire the lock before timeout"
    with lock.open() as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
