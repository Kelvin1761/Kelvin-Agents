from __future__ import annotations

import sqlite3
from pathlib import Path

from tennis_wc.config import get_settings


def get_db_path() -> Path:
    path = get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def dict_row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
