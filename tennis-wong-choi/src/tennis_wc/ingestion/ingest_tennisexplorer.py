"""Import lower-tier results (ITF / UTR / Challenger) into ``match_results``.

The props board is dominated by tiers no wired-up result source covers, so
their props never settled and never became evidence.  See
:mod:`tennis_wc.providers.tennisexplorer_provider` for the measurements.

Matching is strict on purpose.  A scoreboard row is only accepted when exactly
one stored fixture on that date clears the pair-name threshold; a tie between
two fixtures is counted as ``ambiguous`` and skipped rather than resolved by
"best score wins", because the loser of that comparison would be settled
against somebody else's match.
"""
from __future__ import annotations

from datetime import date, timedelta
import json

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.ingestion.name_matching import match_pair_score
from tennis_wc.providers.tennisexplorer_provider import (
    ParsedResult,
    TennisExplorerResultsProvider,
)

PROVIDER_NAME = "tennisexplorer"
# Both names must be a strong match; `match_pair_score` sums two 0-1 scores.
MIN_PAIR_SCORE = 1.84
# A second candidate this close to the best one makes the choice a coin flip.
AMBIGUITY_MARGIN = 0.02


def ingest_tennisexplorer_results(
    start_date: str, end_date: str | None = None, provider=None
) -> dict:
    """Fetch and store completed results for each date in the range."""
    provider = provider or TennisExplorerResultsProvider()
    summary = {
        "dates": 0,
        "rows_parsed": 0,
        "rows_skipped": 0,
        "imported": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "errors": [],
    }
    for match_date in _date_range(start_date, end_date or start_date):
        summary["dates"] += 1
        try:
            results, skipped = provider.fetch_results_for_date(match_date)
        except Exception as exc:  # noqa: BLE001 - one bad day must not stop the rest
            summary["errors"].append({"date": match_date, "error": str(exc)})
            continue
        summary["rows_parsed"] += len(results)
        summary["rows_skipped"] += skipped
        stored = _store_results(match_date, results)
        for key in ("imported", "unmatched", "ambiguous"):
            summary[key] += stored[key]
    return summary


def _store_results(match_date: str, results: list[ParsedResult]) -> dict:
    counts = {"imported": 0, "unmatched": 0, "ambiguous": 0}
    if not results:
        return counts
    now = utc_now()
    # The board is dated in AEST and the scoreboard in European time, so a
    # match routinely sits on either side of midnight between the two.  Widen
    # the candidate pool by a day each way; the ambiguity guard below is what
    # keeps the wider pool safe.
    window = _date_range(
        (date.fromisoformat(match_date) - timedelta(days=1)).isoformat(),
        (date.fromisoformat(match_date) + timedelta(days=1)).isoformat(),
    )
    with get_connection() as conn:
        fixtures = conn.execute(
            f"""
            SELECT m.id, m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name
            FROM matches m
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            WHERE m.match_date IN ({",".join("?" for _ in window)})
            """,
            tuple(window),
        ).fetchall()
        if not fixtures:
            counts["unmatched"] += len(results)
            return counts
        for result in results:
            fixture, direction, verdict = _best_fixture(result, fixtures)
            if verdict != "ok":
                counts[verdict] += 1
                continue
            payload = _oriented_payload(result, direction)
            winner_is_a = (
                result.player_a_sets > result.player_b_sets
            ) == (direction == "direct")
            winner_player_id = (
                fixture["player_a_id"] if winner_is_a else fixture["player_b_id"]
            )
            conn.execute(
                """
                INSERT INTO match_results
                    (match_id, winner_player_id, score_json, source_provider,
                     raw_response_id, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                ON CONFLICT(match_id, source_provider) DO UPDATE SET
                    winner_player_id = excluded.winner_player_id,
                    score_json = excluded.score_json,
                    created_at = excluded.created_at
                """,
                (
                    fixture["id"],
                    winner_player_id,
                    json.dumps(payload, sort_keys=True),
                    PROVIDER_NAME,
                    now,
                ),
            )
            counts["imported"] += 1
    return counts


def _best_fixture(result: ParsedResult, fixtures) -> tuple:
    best = None
    best_score = 0.0
    best_direction = None
    runner_up = 0.0
    for fixture in fixtures:
        score, direction = match_pair_score(
            result.player_a_name,
            result.player_b_name,
            fixture["player_a_name"],
            fixture["player_b_name"],
        )
        if score > best_score:
            runner_up = best_score
            best, best_score, best_direction = fixture, score, direction
        elif score > runner_up:
            runner_up = score
    if best is None or best_score < MIN_PAIR_SCORE:
        return None, None, "unmatched"
    if best_score - runner_up < AMBIGUITY_MARGIN:
        return None, None, "ambiguous"
    return best, best_direction, "ok"


def _oriented_payload(result: ParsedResult, direction: str) -> dict:
    """Return the scoreline in the stored fixture's player_a/player_b order."""
    payload = result.score_payload()
    if direction != "swapped":
        return payload
    flipped = dict(payload)
    flipped["player_a_sets"], flipped["player_b_sets"] = (
        payload["player_b_sets"],
        payload["player_a_sets"],
    )
    flipped["player_a_games"], flipped["player_b_games"] = (
        payload["player_b_games"],
        payload["player_a_games"],
    )
    flipped["sets"] = [
        {
            "player_a_games": item["player_b_games"],
            "player_b_games": item["player_a_games"],
        }
        for item in payload["sets"]
    ]
    return flipped


def _date_range(start_date: str, end_date: str) -> list[str]:
    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    values = []
    while current <= end:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values
