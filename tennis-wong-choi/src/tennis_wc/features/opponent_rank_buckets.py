from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import avg, med, parse_date, rate, shrink_rate, utc_now


RANK_BUCKETS = ["TOP_10", "TOP_25", "TOP_50", "TOP_100", "RANK_101_200", "RANK_201_PLUS", "UNKNOWN"]


def get_opponent_rank_at_match_date(opponent_id: int, match_date: date) -> int | None:
    """
    Look up the opponent's historical ranking at the date of the match.
    Use nearest ranking date before or on match_date. Never substitute current ranking.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT rank
            FROM rankings_history
            WHERE player_id = ? AND ranking_date <= ?
            ORDER BY ranking_date DESC
            LIMIT 1
            """,
            (opponent_id, match_date.isoformat()),
        ).fetchone()
    return int(row["rank"]) if row else None


def classify_rank_bucket(rank: int | None) -> str:
    if rank is None:
        return "UNKNOWN"
    if rank <= 10:
        return "TOP_10"
    if rank <= 25:
        return "TOP_25"
    if rank <= 50:
        return "TOP_50"
    if rank <= 100:
        return "TOP_100"
    if rank <= 200:
        return "RANK_101_200"
    return "RANK_201_PLUS"


def nested_rank_buckets(rank: int | None) -> list[str]:
    if rank is None:
        return ["UNKNOWN"]
    buckets: list[str] = []
    if rank <= 10:
        buckets.append("TOP_10")
    if rank <= 25:
        buckets.append("TOP_25")
    if rank <= 50:
        buckets.append("TOP_50")
    if rank <= 100:
        buckets.append("TOP_100")
    if 101 <= rank <= 200:
        buckets.append("RANK_101_200")
    if rank > 200:
        buckets.append("RANK_201_PLUS")
    return buckets


def _window_start(as_of_date: date, time_window: str) -> str:
    if time_window == "CAREER":
        return "0001-01-01"
    days = 364 if time_window == "LAST_52_WEEKS" else 182
    return date.fromordinal(as_of_date.toordinal() - days).isoformat()


def calculate_player_rank_bucket_stats(
    player_id: int,
    surface: str | None,
    as_of_date: date,
    time_window: str,
) -> dict:
    """
    Calculate player's win rate against opponent ranking buckets.
    Uses only matches before as_of_date and historical opponent ranking at match date.
    """
    query = """
        SELECT *
        FROM player_match_history
        WHERE player_id = ? AND match_date < ? AND match_date >= ?
    """
    params: list = [player_id, as_of_date.isoformat(), _window_start(as_of_date, time_window)]
    if surface:
        query += " AND lower(surface) = lower(?)"
        params.append(surface)
    with get_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]

    total_wins = sum(1 for row in rows if row["won"])
    prior = rate(total_wins, len(rows)) or 0.5
    buckets = {bucket: [] for bucket in RANK_BUCKETS}
    missing = 0
    for row in rows:
        rank = get_opponent_rank_at_match_date(row["opponent_id"], parse_date(row["match_date"]))
        if rank is None:
            missing += 1
        for bucket in nested_rank_buckets(rank):
            buckets[bucket].append((row, rank))

    results: dict[str, dict] = {}
    now = utc_now()
    with get_connection() as conn:
        for bucket, bucket_rows in buckets.items():
            matches = len(bucket_rows)
            wins = sum(1 for row, _ in bucket_rows if row["won"])
            raw_rate = rate(wins, matches)
            shrinked = shrink_rate(raw_rate, matches, prior) if raw_rate is not None else None
            ranks = [rank for _, rank in bucket_rows if rank is not None]
            avg_elo = avg(row.get("opponent_elo") for row, _ in bucket_rows)
            warnings = []
            if matches < 10:
                warnings.append("low_sample")
            if missing:
                warnings.append("missing_historical_rank")
            results[bucket] = {
                "matches": matches,
                "wins": wins,
                "losses": matches - wins,
                "win_rate": raw_rate,
                "shrinked_win_rate": shrinked,
                "avg_opponent_rank": avg(ranks),
                "median_opponent_rank": med(ranks),
                "avg_opponent_elo": avg_elo,
                "sample_size": matches,
                "warnings": warnings,
            }
            conn.execute(
                """
                INSERT INTO player_opponent_rank_bucket_stats (
                    player_id, tour, surface, bucket, time_window, matches, wins, losses,
                    win_rate, shrinked_win_rate, avg_opponent_rank, median_opponent_rank,
                    avg_opponent_elo, source_match_count, calculated_at, created_at, updated_at
                )
                VALUES (?, COALESCE((SELECT tour FROM players WHERE id = ?), 'ATP'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, tour, surface, bucket, time_window) DO UPDATE SET
                    matches = excluded.matches,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    win_rate = excluded.win_rate,
                    shrinked_win_rate = excluded.shrinked_win_rate,
                    avg_opponent_rank = excluded.avg_opponent_rank,
                    median_opponent_rank = excluded.median_opponent_rank,
                    avg_opponent_elo = excluded.avg_opponent_elo,
                    source_match_count = excluded.source_match_count,
                    calculated_at = excluded.calculated_at,
                    updated_at = excluded.updated_at
                """,
                (
                    player_id,
                    player_id,
                    surface,
                    bucket,
                    time_window,
                    matches,
                    wins,
                    matches - wins,
                    raw_rate,
                    shrinked,
                    avg(ranks),
                    med(ranks),
                    avg_elo,
                    matches,
                    now,
                    now,
                    now,
                ),
            )
    return results
