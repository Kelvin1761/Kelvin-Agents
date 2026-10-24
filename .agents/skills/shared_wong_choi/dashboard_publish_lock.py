"""Serialize live-read/merge/upload transactions across dashboard producers.

The inherited marker is internal: a deploy command invoked by a locked Python
producer must not acquire the same lock again. Never set it in scheduler config.
"""
from __future__ import annotations

import contextlib
import fcntl
import functools
import os
from pathlib import Path
import subprocess
import sys
import time

HELD_ENV = "_WC_DASHBOARD_PUBLICATION_LOCK_HELD"


@contextlib.contextmanager
def publication_lock():
    if os.environ.get(HELD_ENV) == "1":
        yield
        return
    root = Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT",
                               Path.home() / "WongChoiData/WongChoiControl"))
    path = Path(os.environ.get("WC_DASHBOARD_PUBLICATION_LOCK_PATH",
                               root / "dashboard-publication.lock"))
    path.parent.mkdir(parents=True, exist_ok=True)
    timeout = float(os.environ.get("WC_DASHBOARD_PUBLICATION_LOCK_TIMEOUT", "3600"))
    deadline = time.monotonic() + max(0, timeout)
    with path.open("a") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"dashboard publication lock busy: {path}")
                time.sleep(0.25)
        previous = os.environ.get(HELD_ENV)
        os.environ[HELD_ENV] = "1"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(HELD_ENV, None)
            else:
                os.environ[HELD_ENV] = previous
            fcntl.flock(handle, fcntl.LOCK_UN)


def serialized_publication(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        with publication_lock():
            return function(*args, **kwargs)
    return wrapped


def main(argv=None):
    command = list(sys.argv[1:] if argv is None else argv)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        raise SystemExit("usage: dashboard_publish_lock.py -- command [args]")
    with publication_lock():
        result = subprocess.run(command, check=False)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
