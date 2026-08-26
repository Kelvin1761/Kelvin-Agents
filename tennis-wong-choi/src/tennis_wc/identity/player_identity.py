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

import sqlite3
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


def terminal_canonical_id(conn, player_id: int | None) -> int | None:
    """Follow `canonical_player_id` to the row that is not itself merged.

    Merges chain across runs: id 20089 was folded into 18856 on one day and
    18856 into 437 on another, so a single hop lands on a row nothing should
    point at any more. Seven such chains existed on 2026-08-27.

    The loop is bounded and returns the last id seen if a cycle is ever written,
    because an identity resolver must not be able to hang the daily card.
    """
    if player_id is None:
        return None
    seen: set[int] = set()
    current = int(player_id)
    for _ in range(16):
        if current in seen:
            return current
        seen.add(current)
        try:
            row = conn.execute(
                "SELECT canonical_player_id FROM players WHERE id = ?", (current,)
            ).fetchone()
        except sqlite3.OperationalError:
            # `canonical_player_id` comes from `ensure_identity_schema`, not
            # `init_db`, so a database that has never been merged does not have
            # it. Ingestion must still work there: an identity resolver that
            # raises on a fresh database takes the whole pipeline with it.
            return current
        if row is None or row[0] is None:
            return current
        current = int(row[0])
    return current


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
        return terminal_canonical_id(conn, int(row[0]))
    row = conn.execute(
        """
        SELECT id, canonical_player_id FROM players
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
        ORDER BY COALESCE(canonical_player_id, id) LIMIT 1
        """,
        (name,),
    ).fetchone()
    if row:
        # Terminal, not one hop: both the alias table and this row can point at
        # an id that has since been merged again.
        return terminal_canonical_id(conn, int(row[1] or row[0]))
    return terminal_canonical_id(conn, _resolve_by_similarity(conn, name, tour))


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


def ranking_tour(conn, player_id: int) -> str | None:
    """The tour this id is RANKED on, or None.

    Separate from `derived_tour` because the two carry very different weight. A
    player appears in exactly one ranking system, so a ranking-derived tour is
    authoritative. A match-history-derived one is not: `derived_tour`'s own
    docstring records that "the history tour column is itself contaminated", and
    it is only consulted as a fallback.
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
    return None


def plan_merges(conn) -> list[MergePlan]:
    """Group players by normalised name and choose one canonical id per group.

    Canonical = most history rows, ties broken by lowest id so the choice is
    stable across runs.
    """
    # Self-sufficient: the planner now reads `canonical_player_id`, so it must
    # not depend on a caller having created it first.
    ensure_identity_schema(conn)
    groups: dict[str, list[tuple[int, str, str | None]]] = {}
    # Skip ids that have already been folded into a canonical one. Without this
    # the planner re-proposes every group it has ever merged, forever: the
    # merged rows still carry their old name, so they still group with their
    # canonical id. Harmless when this was run by hand and never twice; once
    # `run-daily` calls it every morning it would re-apply 936 groups a day and
    # grow `player_merge_log` and `player_aliases` without bound.
    for row in conn.execute(
        "SELECT id, name, tour FROM players WHERE canonical_player_id IS NULL"
    ):
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
        # Two people can share a name across tours, and that is what this guard
        # is for. But it must fire on RANKING evidence, not on a playing record.
        #
        # 2026-08-27: all 25 remaining ATP-vs-WTA refusals were women -- Swiatek,
        # Sabalenka, Osaka, Jabeur, Azarenka, Keys, Svitolina, Vondrousova,
        # Andreeva, Kostyuk... In every one of them the real row carried a full
        # WTA ranking history (Swiatek: 115 entries) and the duplicate carried
        # NO ranking history at all, only a match-history block ~90% labelled
        # ATP. `derived_tour` prefers rankings and falls back to that block when
        # there are none, so the duplicate "derived" as ATP and blocked the
        # merge. Measured across those 25: ranking evidence on both sides in
        # ZERO of them, and conflicting rankings in zero.
        #
        # This is the same defect the guard was hardened for once already -- the
        # first version read `players.tour` and refused 97 groups, every one a
        # mislabelled WTA player. Moving to `derived_tour` narrowed it; it did
        # not close it, because the fallback re-admits the contaminated column.
        #
        # So: refuse only when at least two ids are RANKED and their rankings
        # disagree. `_played_each_other` above remains the primary disproof and
        # is unaffected.
        # Ranking evidence outranks playing record, and only where it exists:
        #
        #   two ids ranked, rankings disagree -> refuse (genuinely two people)
        #   exactly one id ranked            -> that tour stands; a contaminated
        #                                       history block on the other side
        #                                       must not veto it (the Swiatek case)
        #   no id ranked                     -> fall back to `derived_tour`, which
        #                                       is all the evidence there is
        #
        # The middle branch is the fix. Without it a WTA player whose duplicate
        # row carries an ATP-labelled history block blocks her own merge -- and
        # she does so silently, because a refusal looks like a safety win.
        ranked_tours = {pid: ranking_tour(conn, pid) for pid in ids}
        distinct_ranked = {tour for tour in ranked_tours.values() if tour}
        refusal = None
        if len(distinct_ranked) > 1:
            refusal = "refused: they are ranked on different tours"
        elif not distinct_ranked:
            derived = {pid: derived_tour(conn, pid) for pid in ids}
            confident = {tour for tour in derived.values() if tour}
            if {"ATP", "WTA"} <= confident:
                refusal = "refused: their playing records are on different tours"
        if refusal:
            plans.append(
                MergePlan(
                    canonical_id=min(ids),
                    canonical_name=members[0][1],
                    duplicate_ids=[],
                    reason=refusal,
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
    plans.extend(_plan_middle_name_merges(conn, groups, counts, plans))
    return plans


def _plan_middle_name_merges(conn, groups, counts, existing) -> list[MergePlan]:
    """Same first and last name, one carrying extra given names.

    `Ammar Faleh Alhogbani` / `Ammar Alhogbani`, `Astrid Wanja Brune Olsen` /
    `Astrid Brune Olsen`, `Rebecca Munk Mortensen` / `Rebecca Mortensen`. The
    feeds disagree about whether to print middle names, so each spelling built
    its own player row and its own missing ranking.

    Deliberately NOT surname-plus-first-initial, which was the obvious rule and
    is unsafe: of its 101 candidates, 31 had genuinely different given names,
    mixing real variants (`Pyotr`/`Petr Nesterov`, `Ilia`/`Ilya Snitari`) with
    real siblings and namesakes (`Evan`/`Eunji Lee`, `Mio`/`Mao Mushika`,
    `Rinko`/`Ryuki Matsuda`). No automated rule separates those, so the initial
    is not enough -- the given name has to match in full, and one token set has
    to contain the other.

    A wrong merge is far more expensive than a missing rank: it fuses two
    players' histories and everything built from them. Both disproofs therefore
    still apply.
    """
    claimed = {pid for plan in existing
               for pid in [plan.canonical_id, *plan.duplicate_ids]}
    by_ends: dict[tuple[str, str], list[tuple[int, str, tuple[str, ...]]]] = {}
    for alias, members in groups.items():
        tokens = tuple(alias.split())
        if len(tokens) < 2:
            continue
        # An initialised given name carries almost no identity: `a fuchs` is
        # Alexander or Anna or Andrea. Worse, `normalise_player_name` rewrites a
        # trailing initial to the front, so the doubles pair `Filin N. / Fuchs
        # A.` becomes `a filin n fuchs` -- same first and last token as `a
        # fuchs`, and nested. The first version of this rule proposed merging
        # that PAIR into the singles player, along with `Zverev A.` into
        # `Townsend / Zverev A.`. Require a real given name, and never a pair.
        if len(tokens[0]) < 2:
            continue
        for pid, name, _tour in members:
            if pid in claimed or "/" in (name or ""):
                continue
            by_ends.setdefault((tokens[0], tokens[-1]), []).append((pid, name, tokens))

    plans: list[MergePlan] = []
    for _ends, members in sorted(by_ends.items()):
        if len(members) < 2:
            continue
        # Nested token sets only: {ammar, alhogbani} inside
        # {ammar, faleh, alhogbani}. Two DIFFERENT middle names are two people.
        sets = [set(t) for _pid, _n, t in members]
        if not all(a <= b or b <= a for a in sets for b in sets):
            continue
        ids = [pid for pid, _n, _t in members]
        if _played_each_other(conn, ids):
            continue
        if len({tour for tour in (ranking_tour(conn, pid) for pid in ids) if tour}) > 1:
            continue
        canonical = sorted(ids, key=lambda pid: (-counts.get(pid, 0), pid))[0]
        duplicates = [pid for pid in ids if pid != canonical]
        plans.append(
            MergePlan(
                canonical_id=canonical,
                canonical_name=next(n for pid, n, _t in members if pid == canonical),
                duplicate_ids=duplicates,
                history_rows_moved=sum(counts.get(pid, 0) for pid in duplicates),
                reason="merge: middle-name variant",
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

    # Carry the duplicate's player-level attributes onto the canonical row.
    #
    # 2026-08-27: the merge repointed every foreign key and recorded every
    # alias, and left these three columns behind -- so it moved the history and
    # abandoned the reason for moving it. Measured: 447 groups merged and
    # `current_rank` coverage on priced players went 44.3% -> 44.3%, because the
    # rank sat on the row that had just been superseded ("Aaron Funk" id 19836
    # held rank 1342; canonical id 5928 held NULL). 395 of those groups had a
    # ranked duplicate and an unranked canonical.
    #
    # COALESCE, so a canonical value is never overwritten -- the duplicate only
    # fills a gap. MIN for the rank because the sharper (lower) number is the
    # more recent publication when two disagree; the ranking ingest refreshes it
    # daily afterwards either way.
    for column, pick in (("current_rank", "MIN"), ("overall_elo", "MAX"),
                         ("surface_elo_json", "MAX")):
        conn.execute(
            f"""
            UPDATE players
            SET {column} = COALESCE({column}, (
                    SELECT {pick}(d.{column}) FROM players d
                    JOIN _player_merge_map m ON m.duplicate_id = d.id
                    WHERE m.canonical_id = players.id AND d.{column} IS NOT NULL
                )),
                updated_at = datetime('now')
            WHERE {column} IS NULL
              AND id IN (SELECT canonical_id FROM _player_merge_map)
            """
        )

    # Correct the surviving row's tour from ranking evidence.
    #
    # Canonical is chosen by history volume, which usually but not always picks
    # the correctly-labelled row: of the 25 WTA groups unblocked on 2026-08-27,
    # 24 canonical rows already said WTA and one (Destanee Aiava) said ATP while
    # ranked WTA. Leaving that stands a wrong label on the row everything else
    # now points at -- and `tour` gates real behaviour downstream
    # (`_aces_gradeable` is ATP-only, format detection reads it).
    #
    # Only where a ranking exists, and only when it disagrees: rankings are
    # authoritative for tour, playing records are not.
    for pid, in conn.execute(
        "SELECT DISTINCT canonical_id FROM _player_merge_map"
    ).fetchall():
        tour = ranking_tour(conn, pid)
        if tour:
            conn.execute(
                "UPDATE players SET tour = ?, updated_at = datetime('now') "
                "WHERE id = ? AND tour != ?",
                (tour, pid, tour),
            )

    conn.execute(
        """
        UPDATE players
        SET canonical_player_id = (SELECT canonical_id FROM _player_merge_map
                                   WHERE duplicate_id = players.id)
        WHERE id IN (SELECT duplicate_id FROM _player_merge_map)
        """
    )
    # Collapse chains left by earlier runs, so a stored pointer is always
    # terminal and one hop is always enough for anyone who reads it.
    for _ in range(8):
        changed = conn.execute(
            """
            UPDATE players
            SET canonical_player_id = (
                SELECT c.canonical_player_id FROM players c
                WHERE c.id = players.canonical_player_id
            )
            WHERE canonical_player_id IS NOT NULL
              AND canonical_player_id IN (
                SELECT id FROM players WHERE canonical_player_id IS NOT NULL
              )
            """
        ).rowcount
        if not changed:
            break

    # A merge can turn "A vs B" into "A vs A" if both sides were duplicates of
    # one player. Those are not fixtures; leave them detectable rather than
    # silently deleting rows that other tables may point at.
    conn.commit()
    summary["self_matches_after"] = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE player_a_id = player_b_id"
    ).fetchone()[0]
    return summary
