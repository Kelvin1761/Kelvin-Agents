from __future__ import annotations

from tennis_wc.model.history import active_clause

import math
from collections import defaultdict

from tennis_wc.store.db import get_connection
from tennis_wc.model.features.elo import elo_probability


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
