"""Explicit, one-off approved relocation; never called by the scheduler."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path


def inspect_db(path: Path, connection=None) -> dict:
    conn = connection or sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity verification failed")
        counts = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = name.replace('"', '""')
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
    finally:
        if connection is None:
            conn.close()
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "counts": counts}


def relocate(*, source: Path, destination: Path, warm: Path, recovery: Path,
             mount: Path, expected_sha256: str) -> dict:
    lock = source.parent / ".agents/skills/nba/nba_daily_auto/state/nba_daily_schedule.lock"
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _relocate_locked(source=source, destination=destination, warm=warm,
                                recovery=recovery, mount=mount, expected_sha256=expected_sha256)
    finally:
        os.close(fd)


def assert_no_producer(source: Path) -> None:
    output = subprocess.run(["ps", "-axo", "command="], check=True, capture_output=True,
                            text=True).stdout
    scripts = source.parent / ".agents/skills/nba/nba_reflector/scripts"
    if any(str(scripts / name) in line for line in output.splitlines()
           for name in ("nba_reflector_orchestrator.py", "nba_daily_review_archive.py")):
        raise RuntimeError("Active NBA reflector producer; relocation deferred")


def _relocate_locked(*, source: Path, destination: Path, warm: Path, recovery: Path,
                     mount: Path, expected_sha256: str) -> dict:
    paths = [source, destination, warm, recovery, mount]
    if any(not p.is_absolute() for p in paths):
        raise ValueError("All paths must be absolute")
    if not os.path.ismount(mount) or not warm.is_relative_to(mount):
        raise ValueError("WARM disk must be mounted at the explicit mount point")
    for path in paths:
        if any(p.is_symlink() for p in [path, *path.parents]):
            raise ValueError("Symlink paths are not allowed")
    if not source.is_file() or source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Source missing or exceeds bounded small DB relocation limit")
    for path in [destination, warm, recovery]:
        if path.exists() and (not path.is_file() or path.stat().st_size > 64 * 1024 * 1024
                             or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256):
            raise FileExistsError("Never overwrite a differing destination or recovery copy")
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("SQLite sidecar present; stop for controlled checkpoint review")
    assert_no_producer(source)
    # The scheduler lock prevents launches while SQLite excludes direct writers.
    conn = sqlite3.connect(source.as_uri() + "?mode=rw", uri=True, timeout=0)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        original_stat = source.stat()
        expected = inspect_db(source, conn)
        if expected["sha256"] != expected_sha256:
            raise ValueError("Source changed from the approved inspected bytes")
        raw = source.read_bytes()
        for path in [destination, warm]:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            if inspect_db(path) != expected:
                raise ValueError("Copy verification failed; source retained")
        current_stat = source.stat()
        if ((current_stat.st_dev, current_stat.st_ino, current_stat.st_mtime_ns, current_stat.st_size)
                != (original_stat.st_dev, original_stat.st_ino, original_stat.st_mtime_ns, original_stat.st_size)
                or hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha256):
            raise ValueError("Concurrent source change; source retained")
        recovery.parent.mkdir(parents=True, exist_ok=True)
        assert_no_producer(source)
        # A hard link is exclusive/no-clobber and requires the same local filesystem.
        if not recovery.exists():
            os.link(source, recovery)
        if hashlib.sha256(recovery.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError("Recovery copy verification failed; source retained")
        source.unlink()
        return {"status": "relocated", "source": str(source), "destination": str(destination),
                "warm": str(warm), "recovery": str(recovery), **expected}
    finally:
        conn.rollback()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "destination", "warm", "recovery", "mount"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(relocate(**vars(args)), sort_keys=True))


if __name__ == "__main__":
    main()
