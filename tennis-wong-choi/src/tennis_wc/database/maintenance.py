"""Lossless compaction of superseded payloads, retaining every source byte.

Original row IDs, timestamps and metadata remain unchanged. Bodies move to a
hash-verified, compressed SQLite store in the same transaction; readers use
payload_archive to resolve both inline and retained representations. Latest
and recent bodies remain inline. This does not restore legacy destructive
prunes, establish historical availability, or qualify model evidence.
"""

from __future__ import annotations

import sqlite3

from tennis_wc.database.payload_archive import compact_payloads


# Full-replacement payloads only. `sportsbet`/`odds` bodies are deliberately
# excluded even though they are also superseded daily: they total ~37MB, and
# scripts/backfill_match_start_times.py scans them ALL for `startTime`, so
# blanking them would silently shrink a corpus for 3% of the benefit.
REPLACEABLE_ENTITY_TYPES = ("match_history",)


def prune_raw_response_bodies(
    conn: sqlite3.Connection,
    entity_types: tuple[str, ...] = REPLACEABLE_ENTITY_TYPES,
    keep_days: int = 7,
    dry_run: bool = False,
) -> dict:
    """Compact superseded history text without deleting its original content."""
    if type(keep_days) is not int or keep_days < 0:
        raise ValueError("keep_days must be a nonnegative integer")
    if not entity_types or any(kind not in REPLACEABLE_ENTITY_TYPES for kind in entity_types):
        raise ValueError("only match_history payload compaction is supported")
    placeholders = ",".join("?" for _ in entity_types)
    predicate = f"""
        entity_type IN ({placeholders})
          AND response_json != ''
          AND fetched_at < date('now', ?)
          AND id NOT IN (
                SELECT MAX(id) FROM raw_api_responses
                WHERE entity_type IN ({placeholders})
                GROUP BY provider_name, endpoint
          )
    """
    params = (*entity_types, f"-{int(keep_days)} day", *entity_types)
    result = compact_payloads(conn, "raw_response", predicate, params, dry_run=dry_run)
    return {**result, "keep_days": keep_days}


def prune_superseded_feature_snapshots(
    conn: sqlite3.Connection,
    keep_days: int = 7,
    dry_run: bool = False,
) -> dict:
    """Keep superseded feature text losslessly; latest/recent remain inline."""
    if type(keep_days) is not int or keep_days < 0:
        raise ValueError("keep_days must be a nonnegative integer")
    predicate = """
        features_json != ''
          AND created_at < date('now', ?)
          AND id NOT IN (
                SELECT MAX(id) FROM feature_snapshots
                GROUP BY match_id, player_id, feature_set_version
          )
    """
    params = (f"-{int(keep_days)} day",)
    result = compact_payloads(conn, "feature_snapshot", predicate, params, dry_run=dry_run)
    return {**result, "keep_days": keep_days}


def vacuum(conn: sqlite3.Connection) -> dict:
    """Return the blanked pages to the filesystem.

    Separate from the prune on purpose. VACUUM rebuilds the file and needs room
    for a second copy, so calling it unconditionally inside a daily run would
    reintroduce exactly the disk-exhaustion failure this module exists to stop.
    The caller decides, having checked headroom.
    """
    before = _database_bytes(conn)
    conn.execute("VACUUM")
    after = _database_bytes(conn)
    return {"bytes_before": before, "bytes_after": after, "bytes_freed": before - after}


def _database_bytes(conn: sqlite3.Connection) -> int:
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    return int(page_count) * int(page_size)
