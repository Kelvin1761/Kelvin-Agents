from __future__ import annotations

import math
from collections import defaultdict

from tennis_wc.database.db import get_connection
from tennis_wc.features.elo import elo_probability


def elo_k_factor(matches_played: int) -> float:
    """
    Match-count-decayed K (Sackmann-style): new players move fast, established
    players are stable. Tuned on 11.5k historical matches (c/(n+5)^0.4) — it
    beats a flat K=32 on Brier and log-loss and reduces the systematic
    under-rating of strong favourites. Shared by the calibration scorer and the
    production Elo builder so both agree.
    """
    return ELO_K_BASE / ((matches_played + ELO_K_OFFSET) ** ELO_K_EXPONENT)


ELO_K_BASE = 120.0
ELO_K_OFFSET = 5.0
ELO_K_EXPONENT = 0.4


def calibrate_sackmann_elo(
    start_date: str,
    end_date: str,
    initial_rating: float = 1500.0,
    k_factor: float | None = None,
) -> dict:
    """
    Walk-forward calibration check for the deterministic Sackmann Elo model.

    This does not use market odds and does not estimate betting ROI. It checks
    whether the Elo probability assigned to the actual winner is reasonably
    calibrated over historical matches. When ``k_factor`` is None (default) the
    match-count-decayed K is used; pass a float to force a flat K (e.g. for
    A/B comparisons).
    """
    rows = _winner_rows(start_date, end_date)
    overall: dict[int, float] = defaultdict(lambda: initial_rating)
    by_surface: dict[int, dict[str, float]] = defaultdict(dict)
    overall_matches: dict[int, int] = defaultdict(int)
    surface_matches: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    records = []

    def k_for(played: int) -> float:
        return float(k_factor) if k_factor is not None else elo_k_factor(played)

    for row in rows:
        winner_id = int(row["player_id"])
        loser_id = int(row["opponent_id"])
        surface = _normalise_surface(row["surface"])

        winner_overall = overall[winner_id]
        loser_overall = overall[loser_id]
        winner_surface = by_surface[winner_id].get(surface, winner_overall) if surface else winner_overall
        loser_surface = by_surface[loser_id].get(surface, loser_overall) if surface else loser_overall

        p_overall = elo_probability(winner_overall, loser_overall)
        p_surface = elo_probability(winner_surface, loser_surface)
        p_winner = _clamp(0.65 * p_surface + 0.35 * p_overall)
        records.append(
            {
                "date": row["match_date"],
                "surface": surface or "unknown",
                "tour": row["tour"],
                "tournament_level": row["tournament_level"],
                "winner_probability": p_winner,
                "favorite_probability": max(p_winner, 1 - p_winner),
                "favorite_won": p_winner >= 0.5,
            }
        )

        expected = elo_probability(winner_overall, loser_overall)
        k_winner = k_for(overall_matches[winner_id])
        k_loser = k_for(overall_matches[loser_id])
        overall[winner_id] = winner_overall + k_winner * (1 - expected)
        overall[loser_id] = loser_overall + k_loser * (0 - (1 - expected))
        overall_matches[winner_id] += 1
        overall_matches[loser_id] += 1

        if surface:
            surface_expected = elo_probability(winner_surface, loser_surface)
            ks_winner = k_for(surface_matches[winner_id][surface])
            ks_loser = k_for(surface_matches[loser_id][surface])
            by_surface[winner_id][surface] = winner_surface + ks_winner * (1 - surface_expected)
            by_surface[loser_id][surface] = loser_surface + ks_loser * (0 - (1 - surface_expected))
            surface_matches[winner_id][surface] += 1
            surface_matches[loser_id][surface] += 1

    return {
        "start_date": start_date,
        "end_date": end_date,
        "matches": len(records),
        "brier_score": _round(_avg((1 - row["winner_probability"]) ** 2 for row in records)),
        "favorite_brier_score": _round(
            _avg((_actual(row["favorite_won"]) - row["favorite_probability"]) ** 2 for row in records)
        ),
        "log_loss": _round(_avg(-math.log(_clamp(row["winner_probability"])) for row in records)),
        "favorite_accuracy": _round(_avg(1.0 if row["favorite_won"] else 0.0 for row in records)),
        "average_winner_probability": _round(_avg(row["winner_probability"] for row in records)),
        "average_favorite_probability": _round(_avg(row["favorite_probability"] for row in records)),
        "calibration_bins": _calibration_bins(records),
        "by_surface": _group(records, "surface"),
        "by_tour": _group(records, "tour"),
        "by_tournament_level": _group(records, "tournament_level"),
        "note": "Historical odds are not used here; ROI/CLV validation still requires market snapshots.",
    }


def _winner_rows(start_date: str, end_date: str) -> list[dict]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT provider_match_id, player_id, opponent_id, tour, match_date, surface, tournament_level
                FROM player_match_history
                WHERE source_provider = 'jeff_sackmann'
                  AND won = 1
                  AND match_date BETWEEN ? AND ?
                ORDER BY match_date, provider_match_id
                """,
                (start_date, end_date),
            ).fetchall()
        ]


def _calibration_bins(records: list[dict]) -> list[dict]:
    buckets: dict[str, list[float]] = defaultdict(list)
    outcomes: dict[str, list[float]] = defaultdict(list)
    for row in records:
        probability = row["favorite_probability"]
        lower = int(probability * 10) / 10
        upper = min(lower + 0.1, 1.0)
        key = f"{lower:.1f}-{upper:.1f}"
        buckets[key].append(probability)
        outcomes[key].append(_actual(row["favorite_won"]))
    return [
        {
            "bin": key,
            "matches": len(values),
            "avg_predicted_favorite_probability": _round(_avg(values)),
            "actual_favorite_win_rate": _round(_avg(outcomes[key])),
            "calibration_error": _round(abs((_avg(outcomes[key]) or 0) - (_avg(values) or 0))),
        }
        for key, values in sorted(buckets.items())
    ]


def _group(records: list[dict], key: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        grouped[str(row[key])].append(row)
    return [
        {
            key: bucket,
            "matches": len(items),
            "brier_score": _round(_avg((1 - row["winner_probability"]) ** 2 for row in items)),
            "favorite_brier_score": _round(
                _avg((_actual(row["favorite_won"]) - row["favorite_probability"]) ** 2 for row in items)
            ),
            "favorite_accuracy": _round(_avg(1.0 if row["favorite_won"] else 0.0 for row in items)),
            "avg_winner_probability": _round(_avg(row["winner_probability"] for row in items)),
            "avg_favorite_probability": _round(_avg(row["favorite_probability"] for row in items)),
        }
        for bucket, items in sorted(grouped.items())
    ]


def _normalise_surface(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().lower() or None


def _avg(values) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _clamp(value: float, low: float = 0.001, high: float = 0.999) -> float:
    return max(low, min(high, value))


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _actual(value: bool) -> float:
    return 1.0 if value else 0.0
