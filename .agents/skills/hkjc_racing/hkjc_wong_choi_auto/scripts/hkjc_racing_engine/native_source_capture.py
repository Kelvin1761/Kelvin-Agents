"""Per-invocation observed source coherence, never an atomic/PIT/auth proof."""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import stat

MAX_CAPTURE_BYTES = 256 * 1024 * 1024
MAX_OBSERVATIONS = 20000
MAX_NAMESPACE_ENTRIES = 10000
_ACTIVE = ContextVar('hkjc_native_source_capture', default=None)


def _path(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('unsafe native source coherence path')
    return path


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)


class _Capture:
    def __init__(self, source_names):
        self.source_names = tuple(source_names)
        self.files, self.inodes, self.directories = {}, {}, {}
        self.absent = set()
        self.paths = set()
        self.bytes_read = self.namespace_entries = 0
        self.verified = False

    def claim(self, path):
        if self.verified:
            raise ValueError('native source coherence capture already finalized')
        path = str(_path(path))
        self.paths.add(path)
        if len(self.paths) > MAX_OBSERVATIONS:
            raise ValueError('native source coherence observation bound')
        return path

    def file(self, path, metadata, identity):
        path = self.claim(path)
        value = (dict(metadata), tuple(identity))
        if path in self.absent or path in self.directories:
            raise ValueError('native source coherence presence conflict')
        if path in self.files and self.files[path] != value:
            raise ValueError('native source coherence conflicting path captures')
        key = tuple(identity[:2])
        if key in self.inodes and self.inodes[key] != value:
            raise ValueError('native source coherence conflicting inode captures')
        self.bytes_read += metadata['size']
        if self.bytes_read > MAX_CAPTURE_BYTES:
            raise ValueError('native source coherence byte bound')
        self.files[path], self.inodes[key] = value, value

    def absence(self, path):
        path = self.claim(path)
        if path in self.files or (path in self.directories and self.directories[path] is not None):
            raise ValueError('native source coherence absence conflict')
        self.absent.add(path)

    def directory(self, path, entries):
        path = self.claim(path)
        entries = None if entries is None else tuple((name, bool(directory)) for name, directory in entries)
        if path in self.files or (path in self.absent and entries is not None):
            raise ValueError('native source coherence directory conflict')
        if path in self.directories and self.directories[path] != entries:
            raise ValueError('native source coherence conflicting directory captures')
        if path not in self.directories:
            self.namespace_entries += len(entries or ())
            if self.namespace_entries > MAX_NAMESPACE_ENTRIES:
                raise ValueError('native source coherence namespace bound')
        self.directories[path] = entries

    def finish(self):
        if self.verified:
            raise ValueError('native source coherence capture already finalized')
        for path, (_metadata, expected) in self.files.items():
            if _identity(_path(path).lstat()) != expected:
                raise ValueError('native source changed after preparation')
        for path in self.absent:
            try:
                _path(path).lstat()
            except FileNotFoundError:
                continue
            raise ValueError('native source coherence absent path appeared')
        count = 0
        for path, expected in self.directories.items():
            path = _path(path)
            try:
                info = path.lstat()
            except FileNotFoundError:
                actual = None
            else:
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError('native source coherence directory changed type')
                actual = []
                for child in path.iterdir():
                    count += 1
                    if count > MAX_NAMESPACE_ENTRIES:
                        raise ValueError('native source coherence namespace bound')
                    info = child.lstat()
                    if stat.S_ISLNK(info.st_mode):
                        raise ValueError('linked native source coherence inventory')
                    actual.append((child.name, stat.S_ISDIR(info.st_mode)))
                actual = tuple(sorted(actual))
            if actual != expected:
                raise ValueError('native source coherence inventory changed after preparation')
        self.verified = True
        return deepcopy({'schema_version': 'native-source-observation/v1',
            'source_names': list(self.source_names), 'bytes_read': self.bytes_read,
            'files': {path: {**metadata, 'observed_identity': list(identity)}
                      for path, (metadata, identity) in sorted(self.files.items())},
            'absent_paths': sorted(self.absent), 'directories': dict(sorted(self.directories.items()))})


@contextmanager
def source_capture(source_names):
    if _ACTIVE.get() is not None:
        raise ValueError('nested native source coherence capture')
    if not source_names:
        yield None
        return
    capture = _Capture(source_names)
    token = _ACTIVE.set(capture)
    try:
        yield capture
    finally:
        _ACTIVE.reset(token)


def capture_byte_limit(limit):
    capture = _ACTIVE.get()
    if capture is not None:
        limit = min(limit, MAX_CAPTURE_BYTES - capture.bytes_read)
        if limit <= 0:
            raise ValueError('native source coherence byte bound exhausted')
    return limit


def record_source_file(path, metadata, identity):
    capture = _ACTIVE.get()
    if capture is not None:
        capture.file(path, metadata, identity)


def record_absent_source(path):
    capture = _ACTIVE.get()
    if capture is not None:
        capture.absence(path)


def record_source_directory(path, entries):
    capture = _ACTIVE.get()
    if capture is not None:
        capture.directory(path, entries)
    return entries
