from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from urllib.parse import quote
from pathlib import Path

from tennis_wc.config import get_settings


SQLITE_BUSY_TIMEOUT_MS = 30_000
_HISTORY_SCOPE = ContextVar('tennis_history_read_scope', default=None)
_READ_SOURCE = ContextVar('tennis_readonly_source', default=None)


class _BorrowedReadConnection:
    """Native helpers may close their handles; the outer scope owns this one."""
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def get_history_scope() -> dict | None:
    scope = _HISTORY_SCOPE.get()
    return deepcopy(scope[1]) if scope else None


def get_history_connection():
    scope = _HISTORY_SCOPE.get()
    return _BorrowedReadConnection(scope[0]) if scope else get_connection()


def history_connection_for(conn):
    """Pin pure forecast helpers even when callers pass their source connection."""
    scope = _HISTORY_SCOPE.get()
    if scope is None:
        return conn
    if conn is scope[0] or (isinstance(conn, _BorrowedReadConnection) and conn._conn is scope[0]):
        return _BorrowedReadConnection(scope[0])
    main = next((row[2] for row in conn.execute('PRAGMA database_list') if row[1] == 'main'), None)
    if not main or Path(main).resolve() != _READ_SOURCE.get():
        raise ValueError('forecast helper connection belongs to a different source')
    return _BorrowedReadConnection(scope[0])


@contextmanager
def readonly_source_scope(source_path: Path):
    """Read-only baseline audits without changing history selection."""
    if _HISTORY_SCOPE.get() is not None:
        raise ValueError('cannot change source inside a history scope')
    if source_path.resolve() != get_settings().sqlite_path:
        raise ValueError('audit source does not match configured tennis database')
    token = _READ_SOURCE.set(source_path.resolve())
    try:
        yield
    finally:
        _READ_SOURCE.reset(token)


@contextmanager
def readonly_history_scope(conn, *, source_path: Path, provenance: dict):
    """Explicit shadow-only scope; ordinary production reads remain unchanged."""
    if _HISTORY_SCOPE.get() is not None:
        raise ValueError('nested history scopes are forbidden')
    if source_path.resolve() != get_settings().sqlite_path:
        raise ValueError('generation source does not match configured tennis database')
    if conn.execute('PRAGMA query_only').fetchone()[0] != 1:
        raise ValueError('history scope must be query-only')
    if conn.in_transaction:
        raise ValueError('history scope must not own a caller transaction')
    history_token = _HISTORY_SCOPE.set((conn, deepcopy(provenance)))
    source_token = _READ_SOURCE.set(source_path.resolve())
    try:
        yield
    finally:
        _READ_SOURCE.reset(source_token)
        _HISTORY_SCOPE.reset(history_token)


def get_db_path() -> Path:
    path = get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    # Daily ingestion and review can briefly overlap with manual read/report
    # commands. SQLite's 5-second default turns harmless short overlaps into
    # "database is locked" source failures, so give the active writer time to
    # finish before failing the pipeline.
    source = _READ_SOURCE.get()
    if source is None:
        conn = sqlite3.connect(get_db_path(), timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    else:
        conn = sqlite3.connect('file:' + quote(str(source)) + '?mode=ro', uri=True,
                               timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        conn.execute('PRAGMA query_only=ON')
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def dict_row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
