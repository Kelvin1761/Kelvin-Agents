"""Exercise real process, pipe and lock failures without production data."""
import fcntl
import os
import signal
import subprocess
import sys
import time
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups and locks")
def test_scheduler_sigterm_finishes_manifest_and_releases_worker_lock(tmp_path):
    package_parent = str(Path(__file__).resolve().parents[2])
    lock = tmp_path / "worker.lock"
    ready = tmp_path / "ready"
    worker = """
import fcntl, os, sys, time
from pathlib import Path
with open(sys.argv[1], 'w') as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    ready = Path(sys.argv[2])
    pending = ready.with_suffix('.tmp')
    pending.write_text(str(os.getpgrp()))
    pending.rename(ready)
    time.sleep(30)
"""
    scheduler = """
import sys
from datetime import date
from pathlib import Path
from shared_wong_choi.command_adapter import ManifestCommandAdapter
from shared_wong_choi.contracts import Domain, Operation, RunIdentity, RunRequest
from shared_wong_choi.control_plane import _next_request
from shared_wong_choi.control import RetryPolicy

root = Path(sys.argv[1])
class Adapter(ManifestCommandAdapter):
    def command(self, request):
        return [sys.executable, '-c', sys.argv[2], sys.argv[3], sys.argv[4]]
    def run_timeout_seconds(self, request):
        return 20

request = RunRequest(RunIdentity(Domain.TENNIS, 'card', date(2026,11,4), '09:00'), Operation.PREDICT)
result = Adapter(root, root).execute(request)
assert result.state.value == 'failed'
assert _next_request(request, root, RetryPolicy(), force=True).identity.attempt == 2
"""
    with subprocess.Popen(
        [sys.executable, "-c", scheduler, str(tmp_path), worker, str(lock), str(ready)],
        env={**os.environ, "PYTHONPATH": package_parent},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "worker never acquired its lock"
            process.terminate()
            # Wait without reading inherited pipes until the worker is cleaned up.
            assert process.wait(timeout=5) == 0
            with lock.open() as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if process.poll() is None:
                process.kill()
            if ready.exists():
                try:
                    os.killpg(int(ready.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
