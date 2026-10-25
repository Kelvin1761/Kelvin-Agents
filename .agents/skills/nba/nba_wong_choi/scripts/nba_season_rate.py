"""Season-rate independent model S (EXP-20261025-11). SHADOW ONLY.

mu = projected minutes x per-minute production, X ~ NB(mu, k_stat), p = P(X >= line).
Uses the full dated history the extractor stores as ``gamelog["season_log"]`` instead
of L10 alone. No price, C or result enters. Constants are the frozen protocol values
(minutes half-life 6 games, rate half-life 15 games, 30-minute shrink to the stored
history's rate, k fitted on 2025-26 regular season only). Never used for selection.
"""
from __future__ import annotations

import math

MODEL_ID = "nba_season_rate_S_v1"
MIN_HALF_LIFE = 6.0
RATE_HALF_LIFE = 15.0
PRIOR_MINUTES = 30.0
MIN_GAMES = 5
DISPERSION_K = {"PTS": 6.2792, "REB": 10.1371, "AST": 10.1828, "FG3M": 8.0216}


def _nb_sf(line, mu, k):
    """P(X >= line) for NB with mean mu and variance mu + mu^2/k (integer line >= 1)."""
    p = k / (k + mu)
    term = p ** k  # P(X = 0)
    cdf = term
    for x in range(1, int(line)):
        term *= (x + k - 1) / x * (1 - p)
        cdf += term
    return min(1.0, max(0.0, 1.0 - cdf))


def season_rate_prob(season_log, stat, line):
    """Return (probability or None, status, inputs). Never raises on bad data."""
    if not isinstance(season_log, dict) or not season_log.get("dates"):
        return None, "no_season_log", None
    if stat not in DISPERSION_K:
        return None, "stat_unsupported", None
    try:
        line = float(line)
        mins = [float(m) for m in season_log["MIN"]]
        vals = [float(v) for v in season_log[stat]]
        dates = list(season_log["dates"])
    except (KeyError, TypeError, ValueError):
        return None, "invalid_inputs", None
    if not line.is_integer() or line < 1 or not (len(mins) == len(vals) == len(dates)):
        return None, "invalid_inputs", None
    if dates != sorted(dates, reverse=True) or len(set(dates)) != len(dates):
        return None, "invalid_inputs", None
    kinds = list(season_log.get("season_types") or [""] * len(dates))
    if len(kinds) != len(dates):
        return None, "invalid_inputs", None
    # Preseason minutes are not representative; the study used RS + play-in + playoffs.
    games = [(m, v) for m, v, kind in zip(mins, vals, kinds)
             if "pre" not in str(kind).lower()
             and math.isfinite(m) and math.isfinite(v) and m > 0 and v >= 0]
    inputs = {"games": len(games), "last_game_date": dates[0],
              "seasons": sorted(set(season_log.get("seasons") or []))}
    if len(games) < MIN_GAMES:
        return None, "insufficient_games", inputs
    wm = [0.5 ** (i / MIN_HALF_LIFE) for i in range(len(games))]
    wr = [0.5 ** (i / RATE_HALF_LIFE) for i in range(len(games))]
    minutes = sum(w * m for w, (m, _) in zip(wm, games)) / sum(wm)
    rate_all = sum(v for _, v in games) / sum(m for m, _ in games)
    rate = ((sum(w * v for w, (_, v) in zip(wr, games)) + PRIOR_MINUTES * rate_all)
            / (sum(w * m for w, (m, _) in zip(wr, games)) + PRIOR_MINUTES))
    mu = max(minutes * rate, 0.05)
    inputs.update(minutes=round(minutes, 2), rate_per_min=round(rate, 5), mu=round(mu, 3))
    return round(_nb_sf(line, mu, DISPERSION_K[stat]), 4), "ok", inputs
