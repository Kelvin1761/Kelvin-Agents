"""Resolve a player name to one canonical id, and merge the ids that already split.

Two jobs:

* ``resolve_player_id`` -- the write path.  Every ingest should route through it
  so a new spelling attaches to the existing player instead of creating a rival
  row.
* ``plan_merges`` / ``apply_merges`` -- the repair path for rows that already
  exist, with a dry run by default because it rewrites foreign keys across
  thirteen tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tennis_wc.ingestion.name_matching import normalise_player_name

# Every column holding a players.id, discovered by walking the schema on
# 2026-08-09.  Listed explicitly rather than re-derived at run time: a merge
# that silently skips a table leaves orphaned rows pointing at a merged-away id.
PLAYER_ID_COLUMNS: tuple[tuple[str, str], ...] = (
    ("bet_ledger", "selection_player_id"),
    ("feature_snapshots", "player_id"),
    ("match_results", "winner_player_id"),
    ("matches", "player_a_id"),
    ("matches", "player_b_id"),
    ("player_big_match_stats", "player_id"),
    ("player_bo_format_stats", "player_id"),
    ("player_match_history", "player_id"),
    ("player_match_history", "opponent_id"),
    ("player_opponent_rank_bucket_stats", "player_id"),
    ("player_round_stats", "player_id"),
    ("player_tournament_level_stats", "player_id"),
    ("predictions", "selection_player_id"),
    ("prop_tracker", "subject_player_id"),
    ("rankings_history", "player_id"),
)

# Names that are not players.  The composite provider writes these when a draw
# position has no player yet; 725 fixtures (18.2% of the table) are one of these
# playing itself.
PLACEHOLDER_NAMES = frozenset({"tbd", "unknown player", "bye", "qualifier", "walkover"})


@dataclass
class MergePlan:
    canonical_id: int
    canonical_name: str
    duplicate_ids: list[int] = field(default_factory=list)
    history_rows_moved: int = 0
    reason: str = ""


def is_placeholder(name: str | None) -> bool:
    return normalise_player_name(name) in PLACEHOLDER_NAMES


def ensure_identity_schema(conn) -> None:
    """Alias table plus a back-pointer on the rows that were merged away."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_aliases (
            alias_norm TEXT PRIMARY KEY,
            canonical_player_id INTEGER NOT NULL,
            source TEXT,
            created_at TEXT
        )
        """
    )
    # A merge overwrites foreign keys in place, so without this there is no way
    # to answer "which id did this history row originally belong to".
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_merge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_player_id INTEGER NOT NULL,
            canonical_name TEXT,
            duplicate_id INTEGER NOT NULL,
            duplicate_name TEXT,
            history_rows_moved INTEGER,
            merged_at TEXT
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
    if "canonical_player_id" not in columns:
        conn.execute("ALTER TABLE players ADD COLUMN canonical_player_id INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_players_canonical "
        "ON players(canonical_player_id)"
    )


def resolve_player_id(conn, name: str | None, tour: str | None = None) -> int | None:
    """Canonical id for ``name``, via the alias table, creating nothing.

    Returns None for placeholders and unknown names so callers decide whether to
    create -- silently minting a player is what produced the duplicates.
    """
    if not name or is_placeholder(name):
        return None
    alias = normalise_player_name(name)
    row = conn.execute(
        "SELECT canonical_player_id FROM player_aliases WHERE alias_norm = ?", (alias,)
    ).fetchone()
    if row:
        return int(row[0])
    row = conn.execute(
        """
        SELECT id, canonical_player_id FROM players
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
        ORDER BY COALESCE(canonical_player_id, id) LIMIT 1
        """,
        (name,),
    ).fetchone()
    if row:
        return int(row[1] or row[0])
    return _resolve_by_similarity(conn, name, tour)


def _resolve_by_similarity(conn, name: str, tour: str | None) -> int | None:
    """Last resort for a spelling convention we have not seen before.

    Feeds disagree about form -- "Glushkova D." on the lower-tier scoreboards,
    "Jodar, Rafael" elsewhere -- so an exact-match-only resolver would mint a
    second row for a player we already hold.  Two or more distinct canonical
    ids matching equally well means we cannot tell, and the caller gets None
    rather than a guess.
    """
    from tennis_wc.ingestion.name_matching import player_name_score

    # Narrow by surname before scoring. The corpus builder calls this for every
    # unseen name on every scoreboard day, and scanning all players each time is
    # O(players) per lookup against a table that grows as the corpus does.
    tokens = normalise_player_name(name).split()
    surname = tokens[-1] if tokens else ""
    if len(surname) < 2:
        return None
    candidates = conn.execute(
        "SELECT id, name, tour, canonical_player_id FROM players "
        "WHERE LOWER(name) LIKE ? OR LOWER(name) LIKE ?",
        (f"%{surname}%", f"%{surname[:4]}%"),
    )
    best_id: int | None = None
    best_score = 0.0
    runner_up = 0.0
    for row in candidates:
        if tour and row[2] and str(tour).upper() in {"ATP", "WTA"} \
                and str(row[2]).upper() in {"ATP", "WTA"} \
                and str(tour).upper() != str(row[2]).upper():
            continue
        score = player_name_score(name, row[1])
        canonical = int(row[3] or row[0])
        if score > best_score:
            if best_id is not None and canonical != best_id:
                runner_up = best_score
            best_score, best_id = score, canonical
        elif score > runner_up and canonical != best_id:
            runner_up = score
    if best_id is None or best_score < 0.92 or best_score - runner_up < 0.02:
        return None
    return best_id


def _history_counts(conn) -> dict[int, int]:
    return {
        int(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT player_id, COUNT(*) FROM player_match_history GROUP BY player_id"
        )
    }


def _played_each_other(conn, ids: list[int]) -> bool:
    """True if two of these ids ever faced each other.

    A player cannot be their own opponent, so this is proof the ids are
    different people who happen to share a normalised name -- the one case
    where merging would corrupt rather than repair.
    """
    if len(ids) < 2:
        return False
    placeholders = ",".join("?" for _ in ids)
    row = conn.execute(
        f"""
        SELECT 1 FROM matches
        WHERE player_a_id IN ({placeholders}) AND player_b_id IN ({placeholders})
          AND player_a_id <> player_b_id
        LIMIT 1
        """,
        tuple(ids) * 2,
    ).fetchone()
    if row:
        return True
    row = conn.execute(
        f"""
        SELECT 1 FROM player_match_history
        WHERE player_id IN ({placeholders}) AND opponent_id IN ({placeholders})
          AND player_id <> opponent_id
        LIMIT 1
        """,
        tuple(ids) * 2,
    ).fetchone()
    return bool(row)


MIN_TOUR_EVIDENCE = 5


def derived_tour(conn, player_id: int) -> str | None:
    """The tour this id actually competes on, read from its record.

    ``players.tour`` is not usable for this.  Measured 2026-08-09: 771 matches
    carry a tour that disagrees with player A's, and every one of the 97 groups
    the ATP-vs-WTA guard first refused turned out to be a WTA player whose
    duplicate row was mislabelled ATP -- Potapova's second id says ATP while her
    ranking history is 118 WTA entries and no ATP.  Rankings are the cleanest
    signal, then the majority of the playing record; below
    ``MIN_TOUR_EVIDENCE`` rows we return None rather than a coin flip.
    """
    row = conn.execute(
        """
        SELECT tour, COUNT(*) k FROM rankings_history
        WHERE player_id = ? AND tour IS NOT NULL
        GROUP BY tour ORDER BY k DESC LIMIT 1
        """,
        (player_id,),
    ).fetchone()
    if row and int(row[1]) >= MIN_TOUR_EVIDENCE:
        return str(row[0]).upper()
    rows = conn.execute(
        """
        SELECT tour, COUNT(*) k FROM player_match_history
        WHERE player_id = ? AND tour IS NOT NULL
        GROUP BY tour ORDER BY k DESC
        """,
        (player_id,),
    ).fetchall()
    total = sum(int(r[1]) for r in rows)
    if not rows or total < MIN_TOUR_EVIDENCE:
        return None
    top, count = str(rows[0][0]).upper(), int(rows[0][1])
    # A clear majority only; the history tour column is itself contaminated.
    return top if count / total >= 0.7 else None


def plan_merges(conn) -> list[MergePlan]:
    """Group players by normalised name and choose one canonical id per group.

    Canonical = most history rows, ties broken by lowest id so the choice is
    stable across runs.
    """
    groups: dict[str, list[tuple[int, str, str | None]]] = {}
    for row in conn.execute("SELECT id, name, tour FROM players"):
        if is_placeholder(row[1]):
            continue
        groups.setdefault(normalise_player_name(row[1]), []).append(
            (int(row[0]), row[1], row[2])
        )
    counts = _history_counts(conn)
    plans: list[MergePlan] = []
    for alias, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        ids = [member[0] for member in members]
        if _played_each_other(conn, ids):
            plans.append(
                MergePlan(
                    canonical_id=min(ids),
                    canonical_name=members[0][1],
                    duplicate_ids=[],
                    reason="refused: these ids faced each other, so they are different people",
                )
            )
            continue
        derived = {pid: derived_tour(conn, pid) for pid in ids}
        confident = {tour for tour in derived.values() if tour}
        if {"ATP", "WTA"} <= confident:
            plans.append(
                MergePlan(
                    canonical_id=min(ids),
                    canonical_name=members[0][1],
                    duplicate_ids=[],
                    reason="refused: their playing records are on different tours",
                )
            )
            continue
        canonical = sorted(ids, key=lambda pid: (-counts.get(pid, 0), pid))[0]
        duplicates = [pid for pid in ids if pid != canonical]
        plans.append(
            MergePlan(
                canonical_id=canonical,
                canonical_name=next(m[1] for m in members if m[0] == canonical),
                duplicate_ids=duplicates,
                history_rows_moved=sum(counts.get(pid, 0) for pid in duplicates),
                reason="merge",
            )
        )
    return plans


def apply_merges(conn, plans: list[MergePlan]) -> dict:
    """Repoint every foreign key onto the canonical id and record the alias.

    Set-based on purpose.  Looping group-by-group meant 847 groups x 15 tables
    x an unindexed scan of tables holding 96k-171k rows: 12,705 scans, still
    running after nineteen minutes and holding a 20 MB journal.  Building one
    mapping table and joining against it once per table is 15 statements.
    """
    ensure_identity_schema(conn)
    summary = {"groups": 0, "ids_merged": 0, "rows_repointed": 0,
               "rows_dropped_as_redundant": 0, "refused": 0}

    conn.execute("DROP TABLE IF EXISTS _player_merge_map")
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _player_merge_map ("
        "duplicate_id INTEGER PRIMARY KEY, canonical_id INTEGER NOT NULL)"
    )
    conn.execute("DELETE FROM _player_merge_map")
    mapping: list[tuple[int, int]] = []
    for plan in plans:
        if not plan.duplicate_ids:
            summary["refused"] += 1
            continue
        summary["groups"] += 1
        summary["ids_merged"] += len(plan.duplicate_ids)
        mapping.extend((dup, plan.canonical_id) for dup in plan.duplicate_ids)
    if not mapping:
        return summary
    conn.executemany(
        "INSERT OR REPLACE INTO _player_merge_map (duplicate_id, canonical_id) "
        "VALUES (?, ?)",
        mapping,
    )

    for plan in plans:
        if not plan.duplicate_ids:
            continue
        placeholders = ",".join("?" for _ in plan.duplicate_ids)
        for row in conn.execute(
            f"SELECT id, name, (SELECT COUNT(*) FROM player_match_history h "
            f"WHERE h.player_id = players.id) FROM players WHERE id IN ({placeholders})",
            tuple(plan.duplicate_ids),
        ).fetchall():
            conn.execute(
                "INSERT INTO player_merge_log (canonical_player_id, canonical_name, "
                "duplicate_id, duplicate_name, history_rows_moved, merged_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (plan.canonical_id, plan.canonical_name, row[0], row[1], row[2]),
            )
        # Every spelling that existed becomes an alias, not just the winner's:
        # the duplicate rows are exactly the variants the feeds actually send.
        spellings = {normalise_player_name(plan.canonical_name)}
        for row in conn.execute(
            f"SELECT name FROM players WHERE id IN ({placeholders})",
            tuple(plan.duplicate_ids),
        ):
            spellings.add(normalise_player_name(row[0]))
        for alias in spellings:
            if alias:
                conn.execute(
                    "INSERT OR REPLACE INTO player_aliases "
                    "(alias_norm, canonical_player_id, source, created_at) "
                    "VALUES (?, ?, 'merge', datetime('now'))",
                    (alias, plan.canonical_id),
                )

    for table, column in PLAYER_ID_COLUMNS:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            continue
        # OR IGNORE, then sweep: several of these tables carry a UNIQUE key that
        # already covers the canonical id's row (the derived stats tables are
        # keyed on player+tour+surface+window, history on the provider's match
        # id). A collision means the canonical row already holds that fact, so
        # the duplicate's copy is redundant -- keep the canonical one and drop
        # the leftover rather than abandoning the merge or storing it twice.
        cursor = conn.execute(
            f"""
            UPDATE OR IGNORE {table}
            SET {column} = (SELECT canonical_id FROM _player_merge_map
                            WHERE duplicate_id = {table}.{column})
            WHERE {column} IN (SELECT duplicate_id FROM _player_merge_map)
            """
        )
        summary["rows_repointed"] += cursor.rowcount or 0
        swept = conn.execute(
            f"DELETE FROM {table} "
            f"WHERE {column} IN (SELECT duplicate_id FROM _player_merge_map)"
        )
        summary["rows_dropped_as_redundant"] += swept.rowcount or 0

    conn.execute(
        """
        UPDATE players
        SET canonical_player_id = (SELECT canonical_id FROM _player_merge_map
                                   WHERE duplicate_id = players.id)
        WHERE id IN (SELECT duplicate_id FROM _player_merge_map)
        """
    )
    # A merge can turn "A vs B" into "A vs A" if both sides were duplicates of
    # one player. Those are not fixtures; leave them detectable rather than
    # silently deleting rows that other tables may point at.
    conn.commit()
    summary["self_matches_after"] = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE player_a_id = player_b_id"
    ).fetchone()[0]
    return summary
