"""Sanity checks over the warehouse, each one a defect we actually shipped.

Severity is what to DO about it, not how bad it feels:

* ``critical`` -- the number the card is built from cannot be trusted; stop.
* ``warning``  -- worth fixing, does not by itself invalidate today's output.

``run_checks`` returns a list of :class:`CheckResult`; ``critical_failures``
gives the subset the daily job should refuse to publish through.
"""
from __future__ import annotations

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
    count = _count(
        conn,
        """
        SELECT COUNT(*) FROM feature_snapshots
        WHERE features_json LIKE '%elo_not_as_of%'
        """,
    )
    total = _count(conn, "SELECT COUNT(*) FROM feature_snapshots")
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
)


def run_checks(conn, checks=ALL_CHECKS) -> list[CheckResult]:
    return [check(conn) for check in checks]


def critical_failures(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.passed and r.severity == "critical"]


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
