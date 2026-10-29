"""Cooperative, nonblocking cutover lease. The stable lock file is never removed."""
from __future__ import annotations

import argparse
import errno
import fcntl
import os
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

FD_ENV = 'WC_RUNTIME_CUTOVER_FD'


class CutoverLeaseError(RuntimeError):
    pass


class CutoverBusy(CutoverLeaseError):
    pass


def lease_path() -> Path:
    root = Path(os.environ.get('WONGCHOI_CONTROL_STATE_ROOT') or
                Path.home() / 'WongChoiData/WongChoiControl').absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise CutoverLeaseError('symlinked cutover state root')
    return root / 'runtime-cutover.lock'


def _identity(value):
    return value.st_dev, value.st_ino


def _validate(fd: int, path: Path) -> None:
    metadata = os.fstat(fd)
    named = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or not stat.S_ISREG(named.st_mode)
            or _identity(metadata) != _identity(named)
            or metadata.st_uid != os.getuid() or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600):
        raise CutoverLeaseError('unsafe or replaced cutover lease')


def _try_lock(fd: int, mode: int) -> bool:
    try:
        fcntl.flock(fd, mode | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise


def inherited_lease(mode: str, path: Path) -> int:
    raw = os.environ.get(FD_ENV, '')
    if not raw.isdecimal():
        raise CutoverLeaseError('missing inherited cutover lease')
    fd = int(raw)
    _validate(fd, path)
    probe = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        _validate(probe, path)
        exclusive_held = not _try_lock(probe, fcntl.LOCK_SH)
        if exclusive_held:
            # Reasserting on the same open file description preserves an owned
            # exclusive lock. Another process's exclusive lease must block us.
            if not _try_lock(fd, fcntl.LOCK_EX):
                raise CutoverLeaseError('inherited descriptor does not own exclusive lease')
        elif mode == 'exclusive':
            raise CutoverLeaseError('shared or unlocked descriptor cannot authorize cutover')
        else:
            if not _try_lock(fd, fcntl.LOCK_SH):
                raise CutoverBusy('runtime cutover busy')
        _validate(fd, path)
        return fd
    finally:
        os.close(probe)


@contextmanager
def cutover_lease(mode: str):
    if mode not in {'shared', 'exclusive'}:
        raise CutoverLeaseError('invalid cutover lease mode')
    path = lease_path()
    if FD_ENV in os.environ:
        yield inherited_lease(mode, path)
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        _validate(fd, path)
        lock_mode = fcntl.LOCK_SH if mode == 'shared' else fcntl.LOCK_EX
        if not _try_lock(fd, lock_mode):
            raise CutoverBusy('runtime cutover busy; deferred without mutation')
        _validate(fd, path)
        yield fd
    finally:
        os.close(fd)


def scheduler_entry() -> None:
    """Acquire before CLI imports with side effects; retain until process exit.

    Ordinary job subprocesses can acquire their own shared lease. An inherited
    exclusive descriptor remains exclusive for installer-owned acceptance work.
    """
    import atexit

    # subprocess(close_fds=True) legitimately closes the parent's descriptor.
    # Discard only an EBADF marker, then acquire a NEW kernel shared lock. This
    # never grants inherited exclusive authority or bypasses a live cutover.
    raw = os.environ.get(FD_ENV, '')
    if raw.isdecimal():
        try:
            os.fstat(int(raw))
        except OSError as exc:
            if exc.errno == errno.EBADF:
                os.environ.pop(FD_ENV, None)
            else:
                print('cutover descriptor unverified; scheduler blocked', file=sys.stderr)
                raise SystemExit(1) from exc
    guard = cutover_lease('shared')
    try:
        guard.__enter__()
    except CutoverBusy as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(75) from exc
    except (CutoverLeaseError, OSError, ValueError):
        print('cutover lease unverified; scheduler blocked', file=sys.stderr)
        raise SystemExit(1)
    atexit.register(guard.__exit__, None, None, None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('shared', 'exclusive'), required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.verify:
            if args.command:
                raise CutoverLeaseError('verification cannot execute a command')
            inherited_lease(args.mode, lease_path())
            return 0
        command = args.command
        if command and command[0] == '--':
            command = command[1:]
        if not command:
            raise CutoverLeaseError('missing leased command')
        with cutover_lease(args.mode) as fd:
            env = {**os.environ, FD_ENV: str(fd)}
            result = subprocess.run(command, env=env, pass_fds=(fd,), check=False)
            return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except CutoverBusy as exc:
        print(str(exc), file=sys.stderr)
        return 75
    except (CutoverLeaseError, OSError, ValueError, subprocess.SubprocessError):
        print('cutover lease unverified; operation blocked', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
