from __future__ import annotations

from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import rate, shrink_rate


ELO_BUCKETS = ["ELO_2100_PLUS", "ELO_2000_PLUS", "ELO_1900_PLUS", "ELO_1800_PLUS", "ELO_BELOW_1800", "UNKNOWN"]


def classify_elo_bucket(elo: float | None) -> str:
    if elo is None:
        return "UNKNOWN"
    if elo >= 2100:
        return "ELO_2100_PLUS"
    if elo >= 2000:
        return "ELO_2000_PLUS"
    if elo >= 1900:
        return "ELO_1900_PLUS"
    if elo >= 1800:
        return "ELO_1800_PLUS"
    return "ELO_BELOW_1800"


def nested_elo_buckets(elo: float | None) -> list[str]:
    if elo is None:
        return ["UNKNOWN"]
    buckets: list[str] = []
    if elo >= 2100:
        buckets.append("ELO_2100_PLUS")
    if elo >= 2000:
        buckets.append("ELO_2000_PLUS")
    if elo >= 1900:
        buckets.append("ELO_1900_PLUS")
    if elo >= 1800:
        buckets.append("ELO_1800_PLUS")
    if elo < 1800:
        buckets.append("ELO_BELOW_1800")
    return buckets


def calculate_player_elo_bucket_stats(
    player_id: int,
    surface: str | None,
    as_of_date: date,
    time_window: str,
) -> dict:
    start = "0001-01-01"
    if time_window == "LAST_52_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 364).isoformat()
    if time_window == "LAST_26_WEEKS":
        start = date.fromordinal(as_of_date.toordinal() - 182).isoformat()
    query = """
        SELECT *
        FROM player_match_history
        WHERE player_id = ? AND match_date >= ? AND match_date < ?
    """
    params: list = [player_id, start, as_of_date.isoformat()]
    if surface:
        query += " AND lower(surface) = lower(?)"
        params.append(surface)
    with get_connection() as conn:
        rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    prior = rate(sum(1 for row in rows if row["won"]), len(rows)) or 0.5
    buckets = {bucket: [] for bucket in ELO_BUCKETS}
    for row in rows:
        for bucket in nested_elo_buckets(row.get("opponent_elo")):
            buckets[bucket].append(row)
    results = {}
    for bucket, bucket_rows in buckets.items():
        matches = len(bucket_rows)
        wins = sum(1 for row in bucket_rows if row["won"])
        raw_rate = rate(wins, matches)
        results[bucket] = {
            "matches": matches,
            "wins": wins,
            "losses": matches - wins,
            "win_rate": raw_rate,
            "shrinked_win_rate": shrink_rate(raw_rate, matches, prior) if raw_rate is not None else None,
            "sample_size": matches,
            "warnings": ["low_sample"] if matches < 10 else [],
        }
    return results
