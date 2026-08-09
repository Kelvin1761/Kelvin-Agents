from __future__ import annotations

import sqlite3
from pathlib import Path

from tennis_wc.config import get_settings


SQLITE_BUSY_TIMEOUT_MS = 30_000


def get_db_path() -> Path:
    path = get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    # Daily ingestion and review can briefly overlap with manual read/report
    # commands. SQLite's 5-second default turns harmless short overlaps into
    # "database is locked" source failures, so give the active writer time to
    # finish before failing the pipeline.
    conn = sqlite3.connect(get_db_path(), timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def dict_row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
