"""Bounded growth for the tables that have none.

`tennis_wc.db` reached 2.6GB by 2026-08-16 -- 1.3GB of it `raw_api_responses`
-- and the size became an operational failure, not merely untidy: the recovery
job's `disk_headroom` gate demands two database-widths, so a 2.6GB database
needs 5.2GB free, and on 2026-08-15 the volume had 3.7GB. Recovery deferred
itself and the dashboard stayed a day stale with nothing to show for it.

The bulk of that weight is one shape of waste. `entity_type='match_history'`
rows are FULL-REPLACEMENT snapshots: every day the pipeline re-downloads the
same complete historical dump (composite `/mock/historical-matches` alone was
113 copies of a ~5.7MB payload) and appends another row. Every reader of these
takes the newest and only the newest -- `ORDER BY id DESC LIMIT 1` in
ingest_odds and source_status_for_date, `MAX(id) GROUP BY endpoint` in
build_set_distribution. Nothing has ever read a superseded body.

So this blanks superseded BODIES and keeps the ROWS. That distinction is the
point: `feature_builder._provenance_for` resolves a snapshot's origin with
`SELECT provider_name, endpoint, fetched_at ... WHERE id = ?`, and deleting the
row would degrade every historical feature snapshot to `missing_raw_response`.
Blanking the body costs nothing a reader can observe and keeps the audit trail
whole.
"""

from __future__ import annotations

import sqlite3


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
    """Blank superseded full-replacement payloads.

    A body is kept when it is the newest for its (provider_name, endpoint)
    series -- always, at any age -- or when it was fetched within `keep_days`.
    The newest-per-series floor is what makes this safe by construction: no
    reader can lose the row it actually reads, however far retention is turned
    down.
    """
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
    measured = conn.execute(
        f"SELECT COUNT(*) AS rows, IFNULL(SUM(LENGTH(response_json)), 0) AS bytes "
        f"FROM raw_api_responses WHERE {predicate}",
        params,
    ).fetchone()
    result = {
        "rows": int(measured["rows"]),
        "bytes_freed": int(measured["bytes"]),
        "keep_days": int(keep_days),
        "dry_run": bool(dry_run),
    }
    if dry_run or not result["rows"]:
        return result
    conn.execute(
        f"UPDATE raw_api_responses SET response_json = '' WHERE {predicate}", params
    )
    conn.commit()
    return result


def prune_superseded_feature_snapshots(
    conn: sqlite3.Connection,
    keep_days: int = 7,
    dry_run: bool = False,
) -> dict:
    """Blank superseded feature bodies, keeping every row.

    2026-08-26: `feature_snapshots` was 949MB of a 1.9GB database and had no
    retention at all -- this module was written for `raw_api_responses` and the
    second unbounded table was never added. It holds 30,028 rows over 6,390
    distinct (match, player, version) triples: 4.7 copies each, 716MB of which
    is superseded, at ~32KB of JSON per row.

    Same shape as the raw-response prune and safe for the same reason: the
    newest row per (match_id, player_id, feature_set_version) is kept at any
    age, so no reader can lose the row it actually reads. `snapshot_quality`
    and `daily_report` already resolve quality through `MAX(id)` per pair, and
    `data_quality_score` is a column rather than a JSON field, so blanking a
    body costs nothing any reader observes.

    Rows are kept rather than deleted because `player_identity` remaps
    `feature_snapshots.player_id` during a merge and `checks.py` counts them;
    deleting would quietly shrink both.
    """
    predicate = """
        features_json != ''
          AND created_at < date('now', ?)
          AND id NOT IN (
                SELECT MAX(id) FROM feature_snapshots
                GROUP BY match_id, player_id, feature_set_version
          )
    """
    params = (f"-{int(keep_days)} day",)
    measured = conn.execute(
        f"SELECT COUNT(*) AS rows, IFNULL(SUM(LENGTH(features_json)), 0) AS bytes "
        f"FROM feature_snapshots WHERE {predicate}",
        params,
    ).fetchone()
    result = {
        "rows": int(measured["rows"]),
        "bytes_freed": int(measured["bytes"]),
        "keep_days": int(keep_days),
        "dry_run": bool(dry_run),
    }
    if dry_run or not result["rows"]:
        return result
    conn.execute(
        f"UPDATE feature_snapshots SET features_json = '' WHERE {predicate}", params
    )
    conn.commit()
    return result


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
