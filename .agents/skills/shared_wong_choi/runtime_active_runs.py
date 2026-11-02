"""Read-only native argv guard. Never prints argv, environment or process names."""
from __future__ import annotations

import ctypes
import errno
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

JOBS = frozenset('au_daily_schedule au_healthcheck hkjc_daily_schedule nba_daily_schedule '
                 'tennis_daily_schedule tennis_card_recovery tennis_preclose_refresh '
                 'central_daily_maintenance central_research_review'.split())
LAUNCHERS = frozenset('run_au_daily_schedule run_au_auxiliary run_hkjc_daily_schedule '
                      'run_nba_daily_schedule run_tennis_daily_schedule '
                      'run_central_daily_maintenance run_central_research_review'.split())


class DiscoveryError(RuntimeError):
    pass


class ActiveRun(DiscoveryError):
    pass


class BSDInfo(ctypes.Structure):
    # SDK sys/proc_info.h:136 bytes, start_tvsec offset120, uid offset20.
    _fields_ = [(name, ctypes.c_uint32) for name in (
        'flags status xstatus pid ppid uid gid ruid rgid svuid svgid reserved'.split())] + [
        ('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)] + [
        (name, ctypes.c_uint32) for name in 'nfiles pgid pjobc tdev tpgid nice'.split()] + [
        ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


def decode_procargs(raw: bytes):
    """Consume only argc arguments; never decode or return the environment tail."""
    if len(raw) < 6:
        raise DiscoveryError('truncated process arguments')
    argc = struct.unpack_from('=i', raw)[0]
    if argc < 1 or argc > 65536:
        raise DiscoveryError('invalid process argument count')
    end = raw.find(b'\0', 4)
    if end < 5:
        raise DiscoveryError('missing executable path')
    executable = os.fsdecode(raw[4:end])
    index = end
    while index < len(raw) and raw[index] == 0:
        index += 1
    argv = []
    for _ in range(argc):
        end = raw.find(b'\0', index)
        if end < 0:
            raise DiscoveryError('truncated argument vector')
        argv.append(os.fsdecode(raw[index:end]))
        index = end + 1
    return executable, tuple(argv)


def protected_command(executable: str, argv: tuple[str, ...]) -> bool:
    """Recognize executed operands, never trailing release/test scope arguments."""
    if not argv:
        raise DiscoveryError('empty argument vector')
    name = Path(executable).name.lower()
    if re.fullmatch(r'(python|pypy)[0-9.]*', name):
        index = 1
        while index < len(argv):
            value = argv[index]
            if value == '--':
                index += 1
                break
            if value == '-m':
                if index + 1 >= len(argv):
                    raise DiscoveryError('missing module operand')
                return argv[index + 1].rsplit('.', 1)[-1] in JOBS
            if value == '-c' or value == '-':
                raise DiscoveryError('dynamic Python execution cannot prove idle')
            if value in ('-X', '-W', '--check-hash-based-pycs'):
                if index + 1 >= len(argv):
                    raise DiscoveryError('missing interpreter option value')
                index += 2
                continue
            if value.startswith(('-X', '-W')) or re.fullmatch(r'-[bBdEhiIOPqRsSuvVx]+', value):
                index += 1
                continue
            if value.startswith('-'):
                raise DiscoveryError('unknown interpreter option')
            break
        if index == len(argv):
            raise DiscoveryError('interactive Python cannot prove idle')
        return Path(argv[index]).name in {job + '.py' for job in JOBS}
    if name in {'sh', 'bash', 'zsh', 'ksh', 'dash'}:
        for value in argv[1:]:
            if value == '--':
                continue
            if value.startswith('-'):
                if 'c' in value[1:]:
                    # Do not interpret arbitrary shell code as an argv vector.
                    raise DiscoveryError('dynamic shell execution cannot prove idle')
                continue
            return Path(value).name in {job + '.sh' for job in LAUNCHERS}
    return False


class DarwinProcesses:
    def __init__(self):
        if sys.platform != 'darwin':
            raise DiscoveryError('native argv observation requires Darwin')
        self.lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        self.lib.proc_pidinfo.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int)
        self.lib.proc_pidinfo.restype = ctypes.c_int
        self.lib.sysctl.argtypes = (ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                    ctypes.c_void_p, ctypes.c_size_t)
        self.lib.sysctl.restype = ctypes.c_int

    def pids(self):
        result = subprocess.run(['/bin/ps', '-axo', 'pid=,uid='],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or result.stderr:
            raise DiscoveryError('process inventory unavailable')
        pids = set()
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) != 2 or not all(x.isdecimal() for x in fields):
                raise DiscoveryError('malformed process inventory')
            pid, uid = map(int, fields)
            if uid == os.getuid():
                pids.add(pid)
        if not pids or os.getpid() not in pids:
            raise DiscoveryError('incomplete process inventory')
        return pids

    def identity(self, pid):
        value = BSDInfo()
        ctypes.set_errno(0)
        size = self.lib.proc_pidinfo(pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value))
        if size == 0 and ctypes.get_errno() == errno.ESRCH:
            return None
        if size != ctypes.sizeof(value) or value.pid != pid or value.uid != os.getuid():
            raise DiscoveryError('process identity unavailable')
        # Zombie processes cannot execute a domain job; do not read their args.
        return (value.pid, value.uid, value.start_sec, value.start_usec, value.status)

    def argv(self, pid):
        size = ctypes.c_size_t(4 * 1024 * 1024)
        buffer = ctypes.create_string_buffer(size.value)
        mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN,KERN_PROCARGS2,pid
        ctypes.set_errno(0)
        if self.lib.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0):
            raise DiscoveryError('process arguments unavailable')
        if size.value > len(buffer):
            raise DiscoveryError('oversized process arguments')
        return decode_procargs(buffer.raw[:size.value])


def verify_idle(observer):
    """Two inventories plus start-time identity checks; no signal/stop operations."""
    seen = set()
    failed = False
    for _ in range(2):
        for pid in sorted(observer.pids()):
            try:
                before = observer.identity(pid)
                if before is None or before[-1] == 5:  # SDK SZOMB
                    continue
                executable, argv = observer.argv(pid)
                after = observer.identity(pid)
                if after != before:
                    raise DiscoveryError('process identity changed during observation')
                if protected_command(executable, argv):
                    raise ActiveRun('automation run is active; cutover deferred')
                seen.add(before[:4])
            except ActiveRun:
                raise
            except (DiscoveryError, OSError, ValueError):
                # Keep looking for a positive busy result, but never turn a
                # damaged/unreadable observation into idle acceptance.
                failed = True
    if failed:
        raise DiscoveryError('process inventory could not prove idle')
    return len(seen)



def main():
    try:
        verify_idle(DarwinProcesses())
        return 0
    except ActiveRun as exc:
        print(str(exc), file=sys.stderr)
        return 75
    except (DiscoveryError, OSError, ValueError, subprocess.SubprocessError):
        # Never expose exception values, argv, environment or executable paths.
        print('runtime process discovery failed; cutover blocked', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
