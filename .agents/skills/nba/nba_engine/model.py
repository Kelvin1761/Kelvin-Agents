"""Leg probabilities: the market, the C layer, and the price-free season-rate model S.

Every number here is frozen by an experiment; the constants live in config.json.

* market  = 1/price (Sportsbet one-sided milestone price, vig included)
* C       = logit p = a_stat + beta*logit(market) + gamma*logit(L10 hit rate)   (EXP-20261022-03)
* S       = P(X >= line), X ~ NB(mu, k);  mu = projected minutes x per-minute rate x opponent
            factor; previous-season games down-weighted early in a season    (EXP-20261025-13, -26-07)

All inputs are ESPN: the per-game ``season_log`` and the opponent ``allowed`` table the
extractor writes. Functions return None when a leg cannot be scored; they never raise on
bad data.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

STATS = ("PTS", "REB", "AST", "FG3M")
LOG_FIELDS = ("MIN", "PTS", "REB", "AST", "FG3M", "FGA", "FG3A", "FTA", "FGM", "FTM")


@lru_cache(maxsize=None)
def config(path: str | None = None) -> dict:
    return json.loads(Path(path or Path(__file__).with_name("config.json")).read_text(encoding="utf-8"))


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def _clip(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


def market_prob(price) -> float | None:
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    return 1.0 / price if math.isfinite(price) and price > 1.0 else None


def c_prob(stat: str, price, hit_l10: float | None, cfg: dict | None = None) -> float | None:
    """C layer. `hit_l10` is a fraction in [0, 1]."""
    c = (cfg or config())["c_layer"]
    m = market_prob(price)
    if m is None or hit_l10 is None or stat not in c["intercepts"] or not 0 <= hit_l10 <= 1:
        return None
    z = (c["intercepts"][stat] + c["beta_market"] * _logit(_clip(m, *c["clip_market"]))
         + c["gamma_l10"] * _logit(_clip(hit_l10, *c["clip_l10"])))
    return _sigmoid(z)


def nb_tail(line: float, mu: float, k: float) -> float:
    """P(X >= line) for NB with mean mu, variance mu + mu^2/k; line a positive integer."""
    p = k / (k + mu)
    term = cdf = p ** k
    for x in range(1, int(line)):
        term *= (x + k - 1) / x * (1 - p)
        cdf += term
    return _clip(1.0 - cdf, 0.0, 1.0)


def _games(season_log: dict) -> list[dict] | None:
    """Usable games, newest first: not preseason, MIN > 0, every field finite and >= 0."""
    try:
        dates = list(season_log["dates"])
        cols = {f: [float(v) for v in season_log[f]] for f in LOG_FIELDS}
        kinds = list(season_log.get("season_types") or [""] * len(dates))
        seasons = list(season_log.get("seasons") or [None] * len(dates))
        teams = list(season_log.get("teams") or [None] * len(dates))
    except (KeyError, TypeError, ValueError):
        return None
    if (any(len(v) != len(dates) for v in (*cols.values(), kinds, seasons, teams))
            or dates != sorted(dates, reverse=True) or len(set(dates)) != len(dates)):
        return None
    return [{"date": dates[i], "season": seasons[i], "team": teams[i], **{f: cols[f][i] for f in cols}}
            for i in range(len(dates))
            if "pre" not in str(kinds[i]).lower() and cols["MIN"][i] > 0
            and all(math.isfinite(cols[f][i]) and cols[f][i] >= 0 for f in cols)]


def season_mu(season_log: dict, stat: str, opponent: dict, season: str, team: str,
              cfg: dict | None = None) -> tuple[float, float] | None:
    """(mu, k) of the S model, or None. `opponent` = package['opponent_context'][opp]."""
    s = (cfg or config())["season_rate"]
    if stat not in STATS or not isinstance(season_log, dict) or not season:
        return None
    if not isinstance(opponent, dict) or opponent.get("status") != "available":
        return None
    try:
        allowed = [float(v) for v in opponent["allowed"][stat]]
        league = float(opponent["league_avg"][stat])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(league) and league > 0 and all(math.isfinite(a) and a >= 0 for a in allowed)):
        return None
    games = _games(season_log)
    if games is None or len(games) < s["min_games"]:
        return None
    previous = [g["season"] != season for g in games]
    moved = False
    if any(previous):
        last_team = next(g["team"] for g, p in zip(games, previous) if p)
        if last_team is None:
            return None
        from nba_schedule import canonical_team_abbr
        moved = canonical_team_abbr(last_team) != canonical_team_abbr(team)
    weight, moved_factor = s["previous_season_weight"][stat]
    f = [weight * (moved_factor if moved else 1.0) if p else 1.0 for p in previous]

    mins = [g["MIN"] for g in games]
    wm = [0.5 ** (i / s["minutes_half_life"]) * f[i] for i in range(len(games))]
    wr = [0.5 ** (i / s["rate_half_life"]) * f[i] for i in range(len(games))]
    minutes = sum(w * m for w, m in zip(wm, mins)) / sum(wm)
    total_minutes = sum(x * m for x, m in zip(f, mins))
    prior = s["prior_minutes"]

    def total(values):
        return sum(x * v for x, v in zip(f, values))

    def rate(values):
        return ((sum(w * v for w, v in zip(wr, values)) + prior * total(values) / total_minutes)
                / (sum(w * m for w, m in zip(wr, mins)) + prior))

    col = lambda name: [g[name] for g in games]  # noqa: E731
    if stat == "PTS":
        eff = s["efficiency_prior"]
        two_att = [g["FGA"] - g["FG3A"] for g in games]
        two_made = [g["FGM"] - g["FG3M"] for g in games]
        e2 = (total(two_made) + eff["two"][0] * eff["two"][1]) / (total(two_att) + eff["two"][1])
        e3 = (total(col("FG3M")) + eff["three"][0] * eff["three"][1]) / (total(col("FG3A")) + eff["three"][1])
        eft = (total(col("FTM")) + eff["ft"][0] * eff["ft"][1]) / (total(col("FTA")) + eff["ft"][1])
        mu = minutes * (rate(two_att) * e2 * 2 + rate(col("FG3A")) * e3 * 3 + rate(col("FTA")) * eft)
    else:
        mu = minutes * rate(col(stat))
    shrink = s["opponent_shrink_games"]
    mu *= ((sum(allowed) + shrink * league) / (len(allowed) + shrink)) / league
    base_k, (scale, power), ref = s["dispersion_k"][stat], s["dispersion"][stat], s["dispersion_ref"][stat]
    k = base_k * scale * (max(mu, 0.3) / ref) ** power
    return max(mu, 0.05), k


def s_prob(season_log, stat, line, opponent, season, team, cfg=None) -> float | None:
    try:
        line = float(line)
    except (TypeError, ValueError):
        return None
    if not line.is_integer() or line < 1:
        return None
    fit = season_mu(season_log, stat, opponent, season, team, cfg)
    return None if fit is None else nb_tail(line, *fit)
