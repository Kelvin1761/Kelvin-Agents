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


# ---------------------------------------------------------------------------
# S_v2 (EXP-20261025-13). Separate model id: v1 stays frozen for EXP-20261025-12.
# Constants chosen on 2025-26 regular-season TUNE only (2025-12-01..2026-02-28).
MODEL_ID_V2 = "nba_season_rate_S_v2"
V2_MIN_HALF_LIFE = 3.0
V2_RATE_HALF_LIFE = 20.0
V2_PRIOR_MINUTES = 30.0
V2_OPP_SHRINK_GAMES = 10.0
# k = DISPERSION_K[stat] * scale * (max(mu, 0.3) / ref) ** power
V2_DISPERSION = {"PTS": (1.25, 1.0), "REB": (1.6, 0.0), "AST": (1.6, 0.5), "FG3M": (0.8, 0.0)}
V2_DISPERSION_REF = {"PTS": 15.0, "REB": 6.0, "AST": 4.0, "FG3M": 2.0}
# PTS efficiencies shrink to league-typical rates with these attempt priors.
V2_EFFICIENCY_PRIOR = {"two": (0.54, 100.0), "three": (0.36, 100.0), "ft": (0.78, 50.0)}
V2_FIELDS = ("MIN", "PTS", "REB", "AST", "FG3M", "FGA", "FG3A", "FTA", "FGM", "FTM")


def season_rate_prob_v2(season_log, stat, line, opponent):
    """S_v2: S_v1 + opponent-allowed adjustment + PTS shot decomposition + fitted dispersion.

    ``opponent`` is ``package["opponent_context"][team]`` from the extractor. Returns
    (probability or None, status, inputs). Never raises on bad data.
    """
    if not isinstance(season_log, dict) or not season_log.get("dates"):
        return None, "no_season_log", None
    if stat not in DISPERSION_K:
        return None, "stat_unsupported", None
    if not isinstance(opponent, dict) or opponent.get("status") != "available":
        return None, "no_opponent_context", None
    try:
        line = float(line)
        dates = list(season_log["dates"])
        cols = {name: [float(v) for v in season_log[name]] for name in V2_FIELDS}
        kinds = list(season_log.get("season_types") or [""] * len(dates))
        allowed = [float(v) for v in opponent["allowed"][stat]]
        league = float(opponent["league_avg"][stat])
    except (KeyError, TypeError, ValueError):
        return None, "invalid_inputs", None
    if (not line.is_integer() or line < 1 or any(len(v) != len(dates) for v in cols.values())
            or len(kinds) != len(dates) or dates != sorted(dates, reverse=True)
            or len(set(dates)) != len(dates) or not (math.isfinite(league) and league > 0)
            or not all(math.isfinite(a) and a >= 0 for a in allowed)):
        return None, "invalid_inputs", None
    keep = [i for i in range(len(dates))
            if "pre" not in str(kinds[i]).lower() and cols["MIN"][i] > 0
            and all(math.isfinite(cols[n][i]) and cols[n][i] >= 0 for n in V2_FIELDS)]
    inputs = {"games": len(keep), "last_game_date": dates[0],
              "seasons": sorted(set(season_log.get("seasons") or [])),
              "opponent_games": len(allowed), "league_source": opponent.get("league_source")}
    if len(keep) < MIN_GAMES:
        return None, "insufficient_games", inputs
    h = {n: [cols[n][i] for i in keep] for n in V2_FIELDS}
    mins = h["MIN"]
    wm = [0.5 ** (i / V2_MIN_HALF_LIFE) for i in range(len(mins))]
    wr = [0.5 ** (i / V2_RATE_HALF_LIFE) for i in range(len(mins))]
    minutes = sum(w * m for w, m in zip(wm, mins)) / sum(wm)
    total_minutes = sum(mins)

    def rate(values):
        return ((sum(w * v for w, v in zip(wr, values)) + V2_PRIOR_MINUTES * sum(values) / total_minutes)
                / (sum(w * m for w, m in zip(wr, mins)) + V2_PRIOR_MINUTES))

    if stat == "PTS":
        two_att = [a - b for a, b in zip(h["FGA"], h["FG3A"])]
        two_made = [a - b for a, b in zip(h["FGM"], h["FG3M"])]
        (p2, n2), (p3, n3), (pf, nf) = (V2_EFFICIENCY_PRIOR[k] for k in ("two", "three", "ft"))
        e2 = (sum(two_made) + p2 * n2) / (sum(two_att) + n2)
        e3 = (sum(h["FG3M"]) + p3 * n3) / (sum(h["FG3A"]) + n3)
        eft = (sum(h["FTM"]) + pf * nf) / (sum(h["FTA"]) + nf)
        mu = minutes * (rate(two_att) * e2 * 2 + rate(h["FG3A"]) * e3 * 3 + rate(h["FTA"]) * eft)
    else:
        mu = minutes * rate(h[stat])
    opp_factor = ((sum(allowed) + V2_OPP_SHRINK_GAMES * league) / (len(allowed) + V2_OPP_SHRINK_GAMES)) / league
    mu *= opp_factor
    scale, power = V2_DISPERSION[stat]
    k = DISPERSION_K[stat] * scale * (max(mu, 0.3) / V2_DISPERSION_REF[stat]) ** power
    mu = max(mu, 0.05)
    inputs.update(minutes=round(minutes, 2), mu=round(mu, 3), k=round(k, 4), opp_factor=round(opp_factor, 4))
    return round(_nb_sf(line, mu, k), 4), "ok", inputs
