"""Run scheduler children with bounded cleanup and safe log decoding."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from pathlib import Path


class SchedulerTerminated(RuntimeError):
    """The scheduler received SIGTERM while owning a subprocess."""


def run_bounded(
    command: list[str], *, cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run one command and kill its whole process group if the bound expires."""
    # launchd can terminate the adapter while it waits on a detached child.
    # Defer the first signal during spawn and repeated signals during cleanup.
    owns_sigterm = (
        os.name == "posix"
        and threading.current_thread() is threading.main_thread()
        and signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    )
    interrupted = False
    waiting = False

    def terminate(_signum, _frame):
        nonlocal interrupted, waiting
        interrupted = True
        if waiting:
            waiting = False
            # selectors treats InterruptedError as a retryable system-call error.
            raise SchedulerTerminated("scheduler received SIGTERM")

    if owns_sigterm:
        signal.signal(signal.SIGTERM, terminate)
    try:
        with subprocess.Popen(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            try:
                waiting = True
                if interrupted:
                    raise SchedulerTerminated("scheduler received SIGTERM")
                stdout, stderr = process.communicate(timeout=timeout)
            except BaseException:
                waiting = False
                # Descendants can otherwise keep locks and inherited pipes alive.
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:  # pragma: no cover - production is macOS
                    process.kill()
                process.wait(timeout=10)
                raise
            finally:
                waiting = False
            if interrupted:
                raise SchedulerTerminated("scheduler received SIGTERM")
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        if owns_sigterm:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
