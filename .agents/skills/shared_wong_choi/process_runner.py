"""Run scheduler children with bounded cleanup and safe log decoding."""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


def run_bounded(
    command: list[str], *, cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run one command and kill its whole process group if the bound expires."""
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
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            # subprocess.run() only kills the direct child. Browser and worker
            # descendants can otherwise keep locks and inherited pipes alive.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:  # pragma: no cover - production is macOS
                process.kill()
            process.wait(timeout=10)
            raise
        return subprocess.CompletedProcess(
            command, process.returncode, stdout, stderr
        )
