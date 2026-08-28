"""Sanity checks over the warehouse, each one a defect we actually shipped.

Severity is what to DO about it, not how bad it feels:

* ``critical`` -- the number the card is built from cannot be trusted; stop.
* ``warning``  -- worth fixing, does not by itself invalidate today's output.

``run_checks`` returns a list of :class:`CheckResult`; ``critical_failures``
gives the subset the daily job should refuse to publish through.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str
    detail: str
    count: int = 0
    examples: list = field(default_factory=list)


def _rows(conn, sql: str, params: tuple = ()) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def _count(conn, sql: str, params: tuple = ()) -> int:
    rows = _rows(conn, sql, params)
    return int(rows[0][0]) if rows else 0


def check_features_are_as_of(conn) -> CheckResult:
    """Look-ahead is about the DATA a prediction used, not when it was written.

    The first version of this check compared ``predictions.created_at`` to the
    match date and reported 368 failures. That is the wrong quantity: a
    legitimate backfill is stamped today for a match in May and trips it, while
    a prediction written before the match off a rating that silently contains
    the match's own result passes it. What matters is whether the rating was
    read as-of, and the feature builder now records ``elo_not_as_of`` on the
    datapoint whenever it had to fall back to the mutable column.
    """
    # Latest snapshot per (match, player) only. Snapshots accumulate 4.7 deep,
    # so counting all of them measured a mixture of current and long-superseded
    # builds -- and superseded BODIES are now blanked by retention, which would
    # have silently walked this share down as a side effect of a disk cleanup.
    latest = """
        SELECT fs.id, fs.features_json FROM feature_snapshots fs
        WHERE fs.id = (SELECT MAX(x.id) FROM feature_snapshots x
                       WHERE x.match_id = fs.match_id
                         AND x.player_id = fs.player_id
                         AND x.feature_set_version = fs.feature_set_version)
    """
    count = _count(
        conn,
        f"SELECT COUNT(*) FROM ({latest}) WHERE features_json LIKE '%elo_not_as_of%'",
    )
    total = _count(conn, f"SELECT COUNT(*) FROM ({latest})")
    share = count / total if total else 0.0
    return CheckResult(
        "features_not_as_of", share < 0.20, "critical",
        f"{count} of {total} feature snapshots ({share:.1%}) fell back to the "
        "mutable rating instead of an as-of one",
        count,
    )


def check_snapshot_before_match(conn) -> CheckResult:
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM feature_snapshots f JOIN matches m ON m.id = f.match_id
        WHERE DATE(f.created_at) > m.match_date
        """,
    )
    return CheckResult(
        "feature_snapshot_after_match", count == 0, "warning",
        f"{count} feature snapshots were built after their match day",
        count,
    )


def check_no_self_matches(conn) -> CheckResult:
    """A fixture where both sides are the same id is a draw placeholder.

    725 such rows existed, all of them TBD or Unknown Player. They carry no
    odds, predictions or results, but they distort every count taken over the
    matches table.
    """
    count = _count(conn, "SELECT COUNT(*) FROM matches WHERE player_a_id = player_b_id")
    examples = [
        row[0] for row in _rows(
            conn,
            "SELECT DISTINCT p.name FROM matches m JOIN players p ON p.id = m.player_a_id "
            "WHERE m.player_a_id = m.player_b_id LIMIT 5",
        )
    ]
    return CheckResult(
        "self_matches", count == 0, "warning",
        f"{count} fixtures list the same player on both sides",
        count, examples,
    )


def check_duplicate_fixtures(conn) -> CheckResult:
    rows = _rows(
        conn,
        """
        SELECT match_date, player_a_id, player_b_id, COUNT(*) k FROM matches
        WHERE player_a_id <> player_b_id
        GROUP BY 1, 2, 3 HAVING k > 1
        """,
    )
    return CheckResult(
        "duplicate_fixtures", not rows, "critical",
        f"{len(rows)} (date, player pair) combinations appear more than once",
        len(rows),
    )


def check_duplicate_identities(conn) -> CheckResult:
    """Unmerged duplicates split a player's history and starve the models.

    A player split 70/8/0 across three ids is rejected by the ace model's
    ten-match minimum while the data exists.
    """
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT LOWER(TRIM(name)) n FROM players
            WHERE canonical_player_id IS NULL
            GROUP BY 1 HAVING COUNT(*) > 1
        )
        """,
    )
    return CheckResult(
        "unmerged_duplicate_identities", count == 0, "warning",
        f"{count} normalised names still map to more than one unmerged player",
        count,
    )


def check_impossible_scorelines(conn) -> CheckResult:
    """Games and sets that cannot happen in a tennis match."""
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM match_results
        WHERE json_extract(score_json, '$.player_a_games') < 0
           OR json_extract(score_json, '$.player_b_games') < 0
           OR json_extract(score_json, '$.player_a_sets') > 3
           OR json_extract(score_json, '$.player_b_sets') > 3
           OR (json_extract(score_json, '$.player_a_sets') =
               json_extract(score_json, '$.player_b_sets')
               AND json_extract(score_json, '$.retired') IS NOT 1)
        """,
    )
    return CheckResult(
        "impossible_scoreline", count == 0, "critical",
        f"{count} results hold a scoreline that cannot occur",
        count,
    )


def check_winner_is_a_player_in_the_match(conn) -> CheckResult:
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM match_results r JOIN matches m ON m.id = r.match_id
        WHERE r.winner_player_id IS NOT NULL
          AND r.winner_player_id NOT IN (m.player_a_id, m.player_b_id)
        """,
    )
    return CheckResult(
        "winner_not_in_match", count == 0, "critical",
        f"{count} results name a winner who did not play the match",
        count,
    )


def check_prop_subject_plays_the_match(conn) -> CheckResult:
    """A player prop must belong to one of the two players on court."""
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM prop_tracker t JOIN matches m ON m.id = t.match_id
        WHERE t.subject_player_id IS NOT NULL
          AND t.subject_player_id NOT IN (m.player_a_id, m.player_b_id)
        """,
    )
    return CheckResult(
        "prop_subject_not_in_match", count == 0, "critical",
        f"{count} player props name a subject who is not in the fixture",
        count,
    )


def check_odds_are_pre_match(conn) -> CheckResult:
    """The scraper re-reads a match while it is played.

    One set-betting selection ranged 1.26 to 41.0 across its snapshots, and
    2,919 snapshots were fetched after match day. Any replay must take the
    earliest snapshot per selection.
    """
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM market_odds_snapshots s JOIN matches m ON m.id = s.match_id
        WHERE DATE(s.fetched_at) > m.match_date
        """,
    )
    return CheckResult(
        "post_match_odds_present", count == 0, "warning",
        f"{count} odds snapshots were fetched after their match day; "
        "backtests must use the earliest snapshot per selection",
        count,
    )


def check_settled_props_have_a_result(conn) -> CheckResult:
    """Graded props must have something to have been graded from.

    Serve-count props are the exception: they settle from the ace and
    double-fault columns on player_match_history, which exist for matches that
    have no match_results row at all, so requiring one here reports a defect
    that is not one.
    """
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM prop_tracker t
        JOIN matches m ON m.id = t.match_id
        WHERE t.result_status IN ('WON', 'LOST')
          AND NOT EXISTS (SELECT 1 FROM match_results r WHERE r.match_id = t.match_id)
          AND NOT EXISTS (
              SELECT 1 FROM player_match_history h
              WHERE h.match_date = m.match_date
                AND h.player_id IN (m.player_a_id, m.player_b_id)
                AND (h.ace_count IS NOT NULL OR h.double_fault_count IS NOT NULL)
          )
        """,
    )
    return CheckResult(
        "settled_without_result", count == 0, "critical",
        f"{count} props are graded WON/LOST with nothing to grade them from",
        count,
    )


def check_staked_props_are_gradeable(conn) -> CheckResult:
    """Never stake a market we cannot settle.

    ITF ace props settled at 0% for months while still being priced.
    """
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM prop_tracker
        WHERE stake_units > 0 AND result_status = 'PENDING'
          AND match_date < DATE('now', '-14 day')
        """,
    )
    return CheckResult(
        "stale_pending_stakes", count == 0, "warning",
        f"{count} staked props are still PENDING more than a fortnight after the match",
        count,
    )


def check_model_probability_has_signal(conn) -> CheckResult:
    """P == 0.5000 exactly is the combiner declining to have a view.

    It reached seven of the nine prop families as though it were a prediction.
    """
    total = _count(conn, "SELECT COUNT(*) FROM predictions WHERE model_probability IS NOT NULL")
    flat = _count(
        conn,
        "SELECT COUNT(*) FROM predictions WHERE ABS(model_probability - 0.5) < 1e-12",
    )
    share = flat / total if total else 0.0
    return CheckResult(
        "model_probability_no_signal", share < 0.10, "warning",
        f"{flat} of {total} predictions ({share:.1%}) are exactly 0.5000, "
        "the no-Elo fallback",
        flat,
    )


# The day the `record_prop` guard landed. Rows written before it are history
# this check cannot fix and does not judge; rows written after it are the
# guard's own output, so an offender there is a regression.
POST_START_GUARD_FROM = "2026-08-27"


def check_new_props_are_recorded_before_the_match(conn) -> CheckResult:
    """Every prop written from now on must be provably pre-match.

    2026-08-26: 9,594 of 13,658 rows were written by ONE run on 2026-08-10 for
    match dates going back to 2026-05-10. Nothing complained, and the published
    ROI became the average of a real -23.38% and a +11.74% artefact. A row that
    cannot be timed is not a mild data gap -- the unverifiable rows were the
    ones carrying all the profit.

    Judged on rows RECORDED from POST_START_GUARD_FROM onward, not on a rolling
    match-date window. The 1,824 already-written offenders cannot be repaired --
    their pre-match prices are gone -- so a rolling window would block
    publication for a fortnight over history, and this is a critical check
    because a NEW offender means the guard in `record_prop` has been defeated.
    `start_time_utc` coverage has been 100% since 2026-08-17, so from here on
    an untimeable row is a live regression rather than a data gap. The historic
    rows are excluded from judgement by `evaluation.corpus`, not by this check.
    """
    total = _count(
        conn,
        "SELECT COUNT(*) FROM prop_tracker WHERE recorded_at >= ?",
        (POST_START_GUARD_FROM,),
    )
    bad = _count(
        conn,
        "SELECT COUNT(*) FROM prop_tracker WHERE recorded_at >= ? "
        "AND (is_point_in_time IS NULL OR is_point_in_time = 0)",
        (POST_START_GUARD_FROM,),
    )
    share = bad / total if total else 0.0
    return CheckResult(
        "props_recorded_before_match", share < 0.05, "critical",
        f"{bad} of {total} props recorded since {POST_START_GUARD_FROM[:10]} "
        f"({share:.1%}) were written after their match started or cannot be "
        "timed at all",
        bad,
    )


ALL_CHECKS = (
    check_features_are_as_of,
    check_snapshot_before_match,
    check_no_self_matches,
    check_duplicate_fixtures,
    check_duplicate_identities,
    check_impossible_scorelines,
    check_winner_is_a_player_in_the_match,
    check_prop_subject_plays_the_match,
    check_odds_are_pre_match,
    check_settled_props_have_a_result,
    check_staked_props_are_gradeable,
    check_model_probability_has_signal,
    check_new_props_are_recorded_before_the_match,
)


def run_checks(conn, checks=ALL_CHECKS) -> list[CheckResult]:
    return [check(conn) for check in checks]


def critical_failures(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.passed and r.severity == "critical"]


# Circuit vocabulary, not event identity. `ATP Challenger Singles` and
# `ATP Challenger Qualifiers` reduce to nothing once these are removed, which is
# exactly why they must never inherit a sibling's surface: the first attempt at
# this matched them to a Grass event by suffix-stripping alone.
_GENERIC_EVENT_TOKENS = frozenset({
    "atp", "wta", "itf", "utr", "challenger", "challengers", "futures",
    "singles", "doubles", "qualifiers", "qualifier", "qualifying", "q", "qs",
    "men", "mens", "women", "womens", "tennis", "tour", "main", "draw",
})


def tournament_event_key(name: str | None) -> str:
    """The part of a tournament name that identifies WHICH event it is.

    `ATP Challenger 75 Prague Q` -> `prague`. Numbers go too: the 75 in
    `Challenger 75` is a points tier, and `Challenger 100 Hagen` and
    `Challenger 75 Hagen` are the same venue on the same court.

    Returns "" when nothing identifying remains, which is the signal not to
    infer anything at all.
    """
    tokens = re.findall(r"[a-z]+|[0-9]+", str(name or "").lower())
    return " ".join(
        token for token in tokens
        if token not in _GENERIC_EVENT_TOKENS and not token.isdigit()
    )


def repair_surface_casing(conn, dry_run: bool = False) -> int:
    """Fold `tournament_levels.surface` to one spelling.

    Both live in the table -- `hard` on 1,766 rows and `Hard` on 48, `clay` on
    1,228 and `Clay` on 133 -- and every consumer that compares the string
    without folding gets a different answer depending on which feed wrote the
    row. `surface_elo_json` is keyed lower case, so lower case is the spelling
    that matches the data rather than merely being tidy.
    """
    count = _count(
        conn,
        "SELECT COUNT(*) FROM tournament_levels "
        "WHERE surface IS NOT NULL AND surface != LOWER(surface)",
    )
    if count and not dry_run:
        conn.execute(
            "UPDATE tournament_levels SET surface = LOWER(TRIM(surface)) "
            "WHERE surface IS NOT NULL AND surface != LOWER(TRIM(surface))"
        )
        conn.commit()
    return count


def repair_missing_tournament_surface(conn, dry_run: bool = False) -> dict:
    """Fill a NULL surface from a sibling event at the same venue.

    A Challenger's qualifying and doubles draws are played on the main draw's
    court, and the feeds spell them as separate competitions -- so
    `ATP Oeiras Challenger Qualifiers` has no surface while
    `ATP Oeiras Challenger` has Clay.

    This matters more than a tidy field: when the surface is unknown,
    `get_surface_elo` falls back to the OVERALL rating, so the surface component
    keeps its backbone weight while duplicating a component already in the
    blend. Recovery took tier-bettable fixtures with a known surface from 74.9%
    to 93.3% using only data already in the database.

    Run `repair_surface_casing` FIRST. Siblings that differ only in case count
    as disagreeing, which suppressed 44 further recoveries and left the
    ambiguous count at 82 instead of 38.

    Only unambiguous inheritance: the venue key must identify something, and
    every sibling carrying a surface must agree on it. There is no Challenger
    surface source in the repo -- the tennis-data index holds 162 tournaments
    and not one Challenger -- so this recovers what is already known and no
    more.
    """
    known: dict[str, set[str]] = {}
    for row in _rows(
        conn,
        """
        SELECT t.name, tl.surface FROM tournament_levels tl
        JOIN tournaments t ON t.id = tl.tournament_id
        WHERE tl.surface IS NOT NULL AND TRIM(tl.surface) != ''
        """,
    ):
        key = tournament_event_key(row[0])
        if key:
            known.setdefault(key, set()).add(str(row[1]))

    candidates = _rows(
        conn,
        """
        SELECT tl.id, tl.tournament_id, t.name FROM tournament_levels tl
        JOIN tournaments t ON t.id = tl.tournament_id
        WHERE tl.surface IS NULL OR TRIM(tl.surface) = ''
        """,
    )
    filled = 0
    ambiguous = 0
    unidentifiable = 0
    for row in candidates:
        key = tournament_event_key(row[2])
        if not key:
            unidentifiable += 1
            continue
        surfaces = known.get(key)
        if not surfaces:
            continue
        if len(surfaces) > 1:
            ambiguous += 1
            continue
        filled += 1
        if not dry_run:
            conn.execute(
                "UPDATE tournament_levels SET surface = ? WHERE id = ?",
                (next(iter(surfaces)), row[0]),
            )
    if not dry_run and filled:
        conn.commit()
    return {
        "filled": filled,
        "ambiguous_siblings": ambiguous,
        "no_identifying_token": unidentifiable,
        "still_unknown": len(candidates) - filled,
        "dry_run": bool(dry_run),
    }


def repair_impossible_scorelines(conn) -> int:
    """Flag stored results that end level on sets so settlement voids them.

    The parsers are fixed at both sources, but rows written before that are
    still in the table and still gradeable. Marking rather than deleting keeps
    the record of what the provider actually sent.
    """
    import json

    repaired = 0
    for row in conn.execute(
        """
        SELECT rowid, score_json FROM match_results
        WHERE json_extract(score_json, '$.player_a_sets') =
              json_extract(score_json, '$.player_b_sets')
          AND json_extract(score_json, '$.retired') IS NOT 1
        """
    ).fetchall():
        try:
            payload = json.loads(row[1])
        except (TypeError, ValueError):
            continue
        payload["retired"] = True
        payload["incomplete_scoreline"] = True
        conn.execute(
            "UPDATE match_results SET score_json = ? WHERE rowid = ?",
            (json.dumps(payload, sort_keys=True), row[0]),
        )
        repaired += 1
    conn.commit()
    return repaired


def repair_duplicate_fixtures(conn) -> dict:
    """Fold a fixture stored twice onto the copy the market actually priced.

    Two real matches existed as two `matches` rows each, from being ingested
    under different market_event_ids. The result landed on one row and the odds
    on the other, so the priced fixture could never settle.
    """
    summary = {"groups": 0, "rows_repointed": 0, "removed": 0}
    groups = conn.execute(
        """
        SELECT match_date, player_a_id, player_b_id, GROUP_CONCAT(id) ids
        FROM matches WHERE player_a_id <> player_b_id
        GROUP BY 1, 2, 3 HAVING COUNT(*) > 1
        """
    ).fetchall()
    for group in groups:
        ids = [int(value) for value in str(group[3]).split(",")]
        # Canonical = the row the market priced; ties break on the lowest id.
        scored = sorted(
            ids,
            key=lambda mid: (
                -_count(conn, "SELECT COUNT(*) FROM market_odds_snapshots WHERE match_id=?", (mid,)),
                mid,
            ),
        )
        canonical, duplicates = scored[0], scored[1:]
        placeholders = ",".join("?" for _ in duplicates)
        for table, column in (
            ("match_results", "match_id"),
            ("prop_tracker", "match_id"),
            ("predictions", "match_id"),
            ("feature_snapshots", "match_id"),
            ("market_odds_snapshots", "match_id"),
        ):
            cursor = conn.execute(
                f"UPDATE OR IGNORE {table} SET {column} = ? WHERE {column} IN ({placeholders})",
                (canonical, *duplicates),
            )
            summary["rows_repointed"] += cursor.rowcount or 0
            conn.execute(
                f"DELETE FROM {table} WHERE {column} IN ({placeholders})", tuple(duplicates)
            )
        conn.execute(
            f"DELETE FROM matches WHERE id IN ({placeholders})", tuple(duplicates)
        )
        summary["removed"] += len(duplicates)
        summary["groups"] += 1
    conn.commit()
    return summary
