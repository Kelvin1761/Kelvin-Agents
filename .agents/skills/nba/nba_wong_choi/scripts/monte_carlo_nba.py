#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
monte_carlo_nba.py — NBA Props Monte Carlo Simulation Engine V2

Multi-factor adjusted distribution (NOT simple Normal(avg, sd)).
Adjusts the base distribution mean using pace, home/away, B2B,
matchup, and minutes projection factors before sampling.

V2 Upgrades:
  - Random seed for reproducibility
  - Continuity correction for integer milestones
  - Stat-specific distributions (beta-binomial for 3PM, Poisson for STL/BLK)
  - Shrinkage mean (L10 + season avg blending)
  - Category-aware simulation routing

Usage:
  python monte_carlo_nba.py --json '{"avg": 25.3, "sd": 5.2, "line": 24, "category": "PTS"}'
  python monte_carlo_nba.py --json '{...}' --seed 42 --n 20000

Version: 2.0.0
"""
import sys, io, json, math, argparse, random, hashlib

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

MC_MODEL_VERSION = "2.0"

# Use built-in random for portability (no numpy dependency)
def _normal_sample(mean, sd):
    """Sample from normal distribution using Box-Muller transform."""
    return random.gauss(mean, sd)


# ─── Stat-Specific Distribution Samplers ──────────────────────────────────────

def _sample_truncated_normal(mean, sd, n, rng=random):
    """PTS/REB/AST: truncated normal (floor at 0)."""
    return [max(0, rng.gauss(mean, sd)) for _ in range(n)]


def _sample_beta_binomial(mean, sd, n, rng=random):
    """3PM: shot attempts × make rate using beta-binomial.
    Models the inherent uncertainty in both shot attempts and shooting percentage."""
    est_attempts = max(3, round(mean / 0.36))  # ~36% 3P% league avg
    est_rate = min(0.95, max(0.05, mean / est_attempts))
    # Beta parameters from mean and variance
    var_rate = max(0.001, (sd / max(1, est_attempts)) ** 2)
    # Clamp to ensure valid beta parameters
    ratio = est_rate * (1 - est_rate) / var_rate - 1
    ratio = max(1.0, ratio)
    alpha = max(0.5, est_rate * ratio)
    beta_param = max(0.5, (1 - est_rate) * ratio)
    samples = []
    for _ in range(n):
        try:
            p = rng.betavariate(alpha, beta_param)
        except ValueError:
            p = est_rate
        made = sum(1 for _ in range(est_attempts) if rng.random() < p)
        samples.append(made)
    return samples


def _sample_poisson(mean, n, rng=random):
    """STL/BLK: low-count events using Poisson via inverse transform."""
    lam = max(0.1, mean)
    L = math.exp(-lam)
    samples = []
    for _ in range(n):
        k, p = 0, 1.0
        while p > L:
            k += 1
            p *= rng.random()
        samples.append(k - 1)
    return samples


def _sample_by_category(category, mean, sd, n, rng=random):
    """Route to the appropriate distribution for each stat type."""
    if category == "3PM":
        return _sample_beta_binomial(mean, sd, n, rng)
    elif category in ("STL", "BLK"):
        return _sample_poisson(mean, n, rng)
    else:  # PTS, REB, AST, and others
        return _sample_truncated_normal(mean, sd, n, rng)


def stable_seed(*parts):
    """Deterministic 32-bit seed from any parts (Python's hash() is salted)."""
    text = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


# ─── Shrinkage Mean ────────────────────────────────────────────────

def _shrinkage_mean(l10_avg, season_avg=None, l20_avg=None):
    """Blend L10 with longer-term data to reduce small-sample noise.
    L10 alone is noisy (10 games). Shrinking toward season average
    produces a more stable projection."""
    if l20_avg and season_avg:
        return l10_avg * 0.45 + l20_avg * 0.25 + season_avg * 0.20 + l10_avg * 0.10
    elif season_avg:
        return l10_avg * 0.65 + season_avg * 0.35
    else:
        return l10_avg  # No blending possible, use raw L10


# ─── Confidence Multiplier ─────────────────────────────────────────

def confidence_multiplier(cov):
    """Penalize EV for high-variance legs.
    High CoV = less confident in our probability estimate."""
    if not isinstance(cov, (int, float)):
        return 0.65
    if cov <= 0.15:
        return 1.00
    elif cov <= 0.25:
        return 0.85
    elif cov <= 0.35:
        return 0.65
    else:
        return 0.40


# ─── True EV Calculator ───────────────────────────────────────────

def ev_pct_calc(prob_pct, odds):
    """True EV%: (p × odds − 1) × 100"""
    if odds <= 0 or prob_pct <= 0:
        return 0.0
    p = prob_pct / 100
    return round((p * odds - 1) * 100, 2)


def monte_carlo_player_prop(avg, sd, line, n=10000,
                            pace_factor=1.0,
                            home_away_factor=1.0,
                            fatigue_factor=1.0,
                            matchup_factor=1.0,
                            minutes_factor=1.0,
                            usg_bonus=0.0,
                            season_phase="MID_SEASON",
                            category="PTS",
                            season_avg=None,
                            l20_avg=None,
                            cov=None,
                            odds=None,
                            seed=None,
                            rng=None):
    """
    Multi-factor Monte Carlo simulation V2 for a single player prop.

    V2 upgrades:
    - Stat-specific distributions (beta-binomial, Poisson, truncated normal)
    - Shrinkage mean (L10 + season avg blending)
    - Continuity correction for integer milestones
    - Seed for reproducibility
    - True EV + confidence-adjusted EV output

    Args:
        avg: L10 average for this stat
        sd: L10 standard deviation
        line: Sportsbet line (e.g., 10 for "10+")
        n: Number of simulations
        pace_factor: Matchup pace multiplier
        home_away_factor: Home/Away multiplier
        fatigue_factor: B2B fatigue multiplier
        matchup_factor: Opponent defense multiplier
        minutes_factor: Minutes projection multiplier
        usg_bonus: Absolute bonus from injured teammates' USG redistribution
        season_phase: NBA season phase
        category: Stat category (PTS, REB, AST, 3PM, STL, BLK)
        season_avg: Season-long average (for shrinkage)
        l20_avg: L20 average (for shrinkage)
        cov: Coefficient of variation (for confidence adjustment)
        odds: Decimal odds (for EV calculation)
        seed: Random seed for reproducibility (a private RNG; the global
              ``random`` state is no longer reseeded as a side effect)
        rng: Optional ``random.Random`` to draw from instead of ``seed``

    Returns:
        dict with mc_prob, mc_avg, mc_sd, distribution quartiles, EV metrics
    """
    if rng is None:
        rng = random.Random(seed) if seed is not None else random

    if sd <= 0:
        sd = avg * 0.15  # Fallback: assume 15% CoV if no SD

    # Season phase SD adjustment
    phase_sd_multiplier = {
        "EARLY_SEASON": 1.20,
        "MID_SEASON": 1.00,
        "LATE_REGULAR": 1.10,
        "PLAY_IN": 0.92,
        "PLAYOFFS": 0.85,
    }
    sd *= phase_sd_multiplier.get(season_phase, 1.0)

    # Shrinkage mean: blend L10 with longer-term data
    proj_avg = _shrinkage_mean(avg, season_avg=season_avg, l20_avg=l20_avg)

    # Adjust distribution mean with contextual factors
    adj_avg = proj_avg
    adj_avg *= pace_factor
    adj_avg *= home_away_factor
    adj_avg *= fatigue_factor
    adj_avg *= matchup_factor
    adj_avg *= minutes_factor
    adj_avg += usg_bonus

    # Sample using category-appropriate distribution
    samples = _sample_by_category(category, adj_avg, sd, n, rng)

    # Continuity correction for integer milestones:
    # Sportsbet "10+" means >= 10 (integer stat).
    # For continuous distributions, threshold = line - 0.5 aligns
    # the continuous approximation with the discrete condition.
    threshold = line - 0.5
    hits = sum(1 for v in samples if v >= threshold)

    mc_prob = round(hits / n * 100, 1)

    # Distribution statistics
    samples.sort()
    mc_avg = round(sum(samples) / n, 2)
    mc_med = round(samples[n // 2], 1)

    # Percentiles
    p10 = round(samples[int(n * 0.10)], 1)
    p25 = round(samples[int(n * 0.25)], 1)
    p75 = round(samples[int(n * 0.75)], 1)
    p90 = round(samples[int(n * 0.90)], 1)

    # EV calculations
    prob_edge_pp = None
    ev_pct_val = None
    confidence_adjusted_ev_pct = None
    if odds and odds > 0:
        implied_p = round(100 / odds, 2)
        prob_edge_pp = round(mc_prob - implied_p, 1)
        ev_pct_val = ev_pct_calc(mc_prob, odds)
        conf_mult = confidence_multiplier(cov) if cov is not None else 0.65
        confidence_adjusted_ev_pct = round(ev_pct_val * conf_mult, 2)

    result = {
        "mc_prob": mc_prob,
        "mc_avg": mc_avg,
        "mc_med": mc_med,
        "adj_avg": round(adj_avg, 2),
        "projected_avg": round(proj_avg, 2),
        "raw_avg": avg,
        "sd": sd,
        "line": line,
        "category": category,
        "season_phase": season_phase,
        "simulations": n,
        "p10": p10,
        "p25": p25,
        "p75": p75,
        "p90": p90,
        # V2 metadata
        "mc_seed": seed,
        "mc_model_version": MC_MODEL_VERSION,
    }

    # V2 EV fields
    if prob_edge_pp is not None:
        result["prob_edge_pp"] = prob_edge_pp
    if ev_pct_val is not None:
        result["ev_pct"] = ev_pct_val
    if confidence_adjusted_ev_pct is not None:
        result["confidence_adjusted_ev_pct"] = confidence_adjusted_ev_pct

    return result


def compute_context_factors(card, spread=None, is_b2b=False, is_home=None,
                            opp_pace=None, team_pace=None, opp_def_rank=None,
                            usg_bonus=0):
    """
    Compute contextual multipliers from player card data.
    
    Returns dict of multipliers to pass to monte_carlo_player_prop().
    All multipliers are centered around 1.0 (no effect).
    """
    factors = {
        "pace_factor": 1.0,
        "home_away_factor": 1.0,
        "fatigue_factor": 1.0,
        "matchup_factor": 1.0,
        "minutes_factor": 1.0,
        "usg_bonus": 0.0,
    }

    # Pace: Use combined matchup pace
    if opp_pace and team_pace:
        try:
            avg_pace = (float(team_pace) + float(opp_pace)) / 2
            pace_delta = avg_pace - 100.0
            factors["pace_factor"] = 1.0 + (pace_delta * 0.01)  # 1% per pace point
        except (ValueError, TypeError):
            pass
    elif opp_pace:
        try:
            pace_delta = float(opp_pace) - 100.0
            factors["pace_factor"] = 1.0 + (pace_delta * 0.005)
        except (ValueError, TypeError):
            pass

    # Home/Away
    if is_home is not None:
        home_ppg = card.get("home_ppg")
        road_ppg = card.get("road_ppg")
        if home_ppg and road_ppg and home_ppg != "N/A" and road_ppg != "N/A":
            try:
                h, r = float(home_ppg), float(road_ppg)
                if r > 0:
                    if is_home:
                        factors["home_away_factor"] = h / r  # Natural ratio
                    else:
                        factors["home_away_factor"] = r / h if h > 0 else 1.0
            except (ValueError, TypeError):
                pass
        else:
            factors["home_away_factor"] = 1.015 if is_home else 0.985

    # B2B Fatigue
    if is_b2b:
        factors["fatigue_factor"] = 0.97 if is_home else 0.95

    # Blowout / Minutes Floor
    if spread:
        try:
            s = abs(float(spread))
            if s >= 15:
                factors["minutes_factor"] = 0.90
            elif s >= 12:
                factors["minutes_factor"] = 0.94
            elif s >= 8.5:
                factors["minutes_factor"] = 0.97
        except (ValueError, TypeError):
            pass

    # Opponent Defense
    if opp_def_rank and isinstance(opp_def_rank, (int, float)):
        # Top defenses reduce output, bottom defenses increase it
        if opp_def_rank <= 5:
            factors["matchup_factor"] = 0.95
        elif opp_def_rank <= 10:
            factors["matchup_factor"] = 0.97
        elif opp_def_rank >= 26:
            factors["matchup_factor"] = 1.05
        elif opp_def_rank >= 21:
            factors["matchup_factor"] = 1.02

    # USG Redistribution
    if usg_bonus and isinstance(usg_bonus, (int, float)) and usg_bonus > 0:
        factors["usg_bonus"] = usg_bonus

    return factors


def run_monte_carlo_for_cards(all_cards, spread=None, is_b2b_map=None,
                              team_stats=None, meta=None, n=10000,
                              season_phase="MID_SEASON", seed=None):
    """
    Run Monte Carlo simulation for all player cards.

    ``seed`` (per game) makes the run reproducible: each leg draws from its
    own RNG seeded by (seed, player, team, category, line), so a leg's result
    does not depend on which other legs exist or their order.

    Returns list of MC results per player per line.
    """
    results = []
    is_b2b_map = is_b2b_map or {}
    team_stats = team_stats or {}
    
    away_abbr = meta.get("away", {}).get("abbr", "?") if meta else "?"
    home_abbr = meta.get("home", {}).get("abbr", "?") if meta else "?"

    for card in all_cards:
        team = card["team"]
        opponent = home_abbr if team == away_abbr else away_abbr
        is_home = (team == home_abbr)
        is_b2b = is_b2b_map.get(team, False)
        
        opp_stats = team_stats.get(opponent, {})
        team_stats_own = team_stats.get(team, {})
        opp_pace = opp_stats.get("PACE")
        team_pace = team_stats_own.get("PACE")
        opp_def_rank = opp_stats.get("DEF_RANK")
        usg_bonus = card.get("usg_bonus", 0)

        ctx = compute_context_factors(
            card, spread=spread, is_b2b=is_b2b, is_home=is_home,
            opp_pace=opp_pace, team_pace=team_pace,
            opp_def_rank=opp_def_rank, usg_bonus=usg_bonus)

        cat_map = {"points": "PTS", "threes_made": "3PM", "rebounds": "REB", "assists": "AST"}
        cl = cat_map.get(card["category"], card["category"])

        for line_key, la in card.get("line_analysis", {}).items():
            leg_seed = (
                stable_seed(seed, card["name"], team, cl, la["line"])
                if seed is not None else None
            )
            mc = monte_carlo_player_prop(
                avg=card["avg"], sd=card["sd"], line=la["line"], n=n,
                season_phase=season_phase,
                category=cl,
                cov=card.get("cov"),
                odds=float(la["odds"]),
                seed=leg_seed,
                **ctx)

            mc["player"] = card["name"]
            mc["team"] = team
            mc["category"] = cl
            mc["line_display"] = la["line_display"]
            mc["odds"] = la["odds"]
            mc["implied_prob"] = la["implied_prob"]
            mc["l10_hit"] = la["hit_l10"]
            mc["ten_factor_adj"] = la["estimated_prob"]
            mc["mc_edge"] = mc.get("prob_edge_pp", round(mc["mc_prob"] - la["implied_prob"], 1))
            results.append(mc)

    return results


# ─── SGM joint simulation (shadow) ───────────────────────────────────────────

SGM_SIM_VERSION = "sgm-joint-sim/v1"
# Shared-factor scales (per simulated game).  They are structural priors, not
# fitted values: no settled SGM sample exists yet to fit them on.
SGM_PACE_SD = 0.03          # both teams' counting stats
SGM_TEAM_SCORING_SD = 0.05  # one team's PTS / 3PM / AST
SGM_PLAYER_ROLE_SD = 0.08   # one player's minutes/usage, shared by his markets
SGM_MARGIN_SD = 12.0        # final margin around the spread
SGM_STARTER_MIN_AVG = 28.0  # starters lose minutes in blowouts
_TEAM_SCORING_CATEGORIES = {"PTS", "3PM", "AST"}
_CAT_LABEL = {"points": "PTS", "threes_made": "3PM", "rebounds": "REB", "assists": "AST"}


def _blowout_minutes(margin_abs):
    """Same table as compute_context_factors, applied to the *simulated* margin."""
    if margin_abs >= 15:
        return 0.90
    if margin_abs >= 12:
        return 0.94
    if margin_abs >= 8.5:
        return 0.97
    return 1.0


def _expected_blowout_minutes(mu, sd):
    """E[_blowout_minutes(|M|)] for M ~ N(mu, sd), exact for the step table."""
    def cdf(value):
        return 0.5 * (1 + math.erf((value - mu) / (sd * math.sqrt(2))))

    def p_abs_at_least(x):
        return (1 - cdf(x)) + cdf(-x)

    p15, p12, p85 = p_abs_at_least(15), p_abs_at_least(12), p_abs_at_least(8.5)
    return p15 * 0.90 + (p12 - p15) * 0.94 + (p85 - p12) * 0.97 + (1 - p85) * 1.0


def simulate_sgm_joint(combos, all_cards, spread=None, is_b2b_map=None,
                       team_stats=None, meta=None, n=10000,
                       season_phase="MID_SEASON", seed=0):
    """Joint hit probability of each combo from one set of simulated games.

    Every simulation draws game-level factors once (pace, final margin →
    starters' blowout minutes, each team's scoring level) and one role factor
    per player; every leg of every combo is then scored against the SAME
    simulated game, and a combo hits only when all its legs hit in that
    simulation.  Marginals use the same means/SDs/context as
    ``run_monte_carlo_for_cards`` (the spread-based deterministic minutes
    factor is replaced by the simulated margin).  Idiosyncratic SD is shrunk so
    the shared factors do not inflate each leg's total variance.

    Shadow only: callers must not use the result to choose or publish combos.
    Returns {combo_id: result}.
    """
    is_b2b_map = is_b2b_map or {}
    team_stats = team_stats or {}
    meta = meta or {}
    away = (meta.get("away") or {}).get("abbr", "?")
    home = (meta.get("home") or {}).get("abbr", "?")
    cards = {(card["name"], _CAT_LABEL.get(card["category"], card["category"])): card
             for card in all_cards}
    phase_sd = {"EARLY_SEASON": 1.20, "MID_SEASON": 1.00, "LATE_REGULAR": 1.10,
                "PLAY_IN": 0.92, "PLAYOFFS": 0.85}.get(season_phase, 1.0)
    common_var = SGM_PACE_SD ** 2 + SGM_TEAM_SCORING_SD ** 2 + SGM_PLAYER_ROLE_SD ** 2

    results = {}
    streams = {}  # (player, category) -> sampling spec
    combo_legs = {}
    for combo_id, legs in (combos or {}).items():
        if not legs:
            continue
        specs = []
        status = "ok"
        for leg in legs:
            key = (leg.get("player"), leg.get("category"))
            card = cards.get(key)
            if leg.get("market_type") not in (None, "player") and card is None:
                status = "unsupported_leg"
                break
            if card is None:
                status = "card_missing"
                break
            if key not in streams:
                team = card["team"]
                opponent = home if team == away else away
                ctx = compute_context_factors(
                    card, spread=None, is_b2b=is_b2b_map.get(team, False),
                    is_home=(team == home),
                    opp_pace=team_stats.get(opponent, {}).get("PACE"),
                    team_pace=team_stats.get(team, {}).get("PACE"),
                    opp_def_rank=team_stats.get(opponent, {}).get("DEF_RANK"),
                    usg_bonus=card.get("usg_bonus", 0))
                sd = card["sd"] if card["sd"] > 0 else card["avg"] * 0.15
                sd *= phase_sd
                mean = card["avg"]
                for factor in ("pace_factor", "home_away_factor", "fatigue_factor",
                               "matchup_factor", "minutes_factor"):
                    mean *= ctx[factor]
                mean += ctx["usg_bonus"]
                category = key[1]
                team_sd = SGM_TEAM_SCORING_SD if category in _TEAM_SCORING_CATEGORIES else 0.0
                factor_var = SGM_PACE_SD ** 2 + team_sd ** 2 + SGM_PLAYER_ROLE_SD ** 2
                idio = math.sqrt(max(sd ** 2 - (mean ** 2) * factor_var, (0.5 * sd) ** 2))
                streams[key] = {
                    "player": key[0], "category": category, "team": team,
                    "mean": mean, "sd": idio, "team_sd": team_sd,
                    "starter": float(card.get("min_avg") or 0) >= SGM_STARTER_MIN_AVG,
                }
            specs.append((key, float(leg.get("line_val") or 0) - 0.5))
        if status != "ok":
            results[str(combo_id)] = {"sim_status": status, "sim_model_version": SGM_SIM_VERSION}
            continue
        combo_legs[str(combo_id)] = specs

    if combo_legs:
        rng = random.Random(seed)
        try:
            mu_away = -float(spread) if spread not in (None, "", "?") else 0.0
        except (TypeError, ValueError):
            mu_away = 0.0
        margin_sd = SGM_MARGIN_SD * math.sqrt(0.6 ** 2 + 0.8 ** 2)
        # Blowout minutes are re-centred so each starter's average multiplier
        # equals the single-leg MC's deterministic spread factor: the
        # simulation adds co-movement, not a different marginal.
        blowout_scale = (
            _blowout_minutes(abs(mu_away)) / _expected_blowout_minutes(mu_away, margin_sd)
        )
        players = sorted({stream["player"] for stream in streams.values()})
        stream_keys = sorted(streams)
        joint = {cid: 0 for cid in combo_legs}
        leg_hits = {cid: [0] * len(specs) for cid, specs in combo_legs.items()}
        for _ in range(n):
            z_pace = rng.gauss(0, 1)
            z_team = {away: rng.gauss(0, 1), home: rng.gauss(0, 1)}
            z_margin = rng.gauss(0, 1)
            z_role = {player: rng.gauss(0, 1) for player in players}
            # The scoring shocks also move the margin, so a hot team, a big
            # margin and benched starters arrive together.
            margin = mu_away + SGM_MARGIN_SD * (
                0.6 * z_margin + 0.8 * (z_team[away] - z_team[home]) / math.sqrt(2))
            blowout = _blowout_minutes(abs(margin)) * blowout_scale
            pace = 1 + SGM_PACE_SD * z_pace
            values = {}
            for key in stream_keys:
                stream = streams[key]
                mult = pace * (1 + SGM_PLAYER_ROLE_SD * z_role[stream["player"]])
                mult *= 1 + stream["team_sd"] * z_team.get(stream["team"], 0.0)
                if stream["starter"]:
                    mult *= blowout
                values[key] = _sample_by_category(
                    stream["category"], max(0.0, stream["mean"] * mult), stream["sd"], 1, rng)[0]
            for cid, specs in combo_legs.items():
                all_hit = True
                for index, (key, threshold) in enumerate(specs):
                    if values[key] >= threshold:
                        leg_hits[cid][index] += 1
                    else:
                        all_hit = False
                if all_hit:
                    joint[cid] += 1
        for cid, specs in combo_legs.items():
            marginals = [hits / n for hits in leg_hits[cid]]
            independent = 1.0
            for value in marginals:
                independent *= value
            joint_prob = joint[cid] / n
            results[cid] = {
                "sim_status": "ok",
                "sim_model_version": SGM_SIM_VERSION,
                "sim_n": n,
                "sim_seed": seed,
                "sim_joint_prob": round(joint_prob, 4),
                "sim_independent_prob": round(independent, 4),
                "sim_leg_marginals": [round(value, 4) for value in marginals],
                "sim_correlation_lift": round(joint_prob / independent, 4) if independent > 0 else None,
            }
    return results


def context_inputs_status(team_stats, meta=None):
    """Which matchup inputs are really populated, and from which season.

    The MC header used to claim pace/defence were injected unconditionally;
    in the 2026-27 opener ``team_stats`` was ``{}`` so neither was.
    """
    meta = meta or {}
    teams = [t for t in (meta.get("away", {}).get("abbr"), meta.get("home", {}).get("abbr")) if t]
    teams = teams or list((team_stats or {}).keys())
    rows = [(team_stats or {}).get(t) or {} for t in teams]
    sources = meta.get("data_sources") or {}
    ts = sources.get("team_stats") or {}
    return {
        "pace": bool(rows) and all(r.get("PACE") for r in rows),
        "defence": bool(rows) and all(r.get("DEF_RANK") for r in rows),
        "data_season": ts.get("data_season") or meta.get("statistics_season"),
        "fallback_used": bool(ts.get("fallback_used")),
    }


def format_mc_section(mc_results, context_status=None):
    """Format Monte Carlo results as markdown section."""
    lines = []
    lines.append("")
    lines.append("### 📊 Monte Carlo 命中率模擬 (10,000 次)")
    lines.append("")
    lines.append("> 🐍 由 Python `monte_carlo_nba.py` 自動計算 | Multi-Factor Adjusted Distribution")
    if context_status is None:
        lines.append("> 唔係 Simple Normal(avg, sd) — 已注入主客、B2B、分鐘等情境因素")
    else:
        applied = ["主客", "B2B", "分鐘"]
        missing = []
        for key, label in (("pace", "Pace"), ("defence", "防守")):
            (applied if context_status.get(key) else missing).append(label)
        lines.append(f"> 唔係 Simple Normal(avg, sd) — 已注入 {'、'.join(applied)} 等情境因素")
        if missing:
            lines.append(f"> ⚠️ {'、'.join(missing)} 數據缺失，**冇**套用呢啲調整（對手球隊數據為空）")
        elif context_status.get("fallback_used"):
            lines.append(f"> ℹ️ Pace／防守數字來自上季 {context_status.get('data_season')}（新季未有足夠賽事），僅作參考")
    lines.append("")
    lines.append("| Player | Prop | Line | L10 命中 | 10-Factor | MC 命中 | 隱含勝率 | MC Edge |")
    lines.append("|--------|------|------|---------|-----------|--------|---------|---------|")
    
    # Sort by MC edge descending
    sorted_results = sorted(mc_results, key=lambda r: r["mc_edge"], reverse=True)
    
    for r in sorted_results[:20]:  # Top 20 for readability
        edge_str = f"+{r['mc_edge']}%" if r['mc_edge'] > 0 else f"{r['mc_edge']}%"
        edge_icon = "💎" if r['mc_edge'] >= 15 else ("✅" if r['mc_edge'] >= 5 else ("➖" if r['mc_edge'] >= 0 else "❌"))
        lines.append(f"| {r['player']} | {r['category']} | {r['line_display']} | "
                     f"{r['l10_hit']}% | {r['ten_factor_adj']}% | **{r['mc_prob']}%** | "
                     f"{r['implied_prob']}% | {edge_str} {edge_icon} |")
    
    lines.append("")
    
    # Distribution insight
    positive_mc = [r for r in mc_results if r['mc_edge'] >= 5]
    if positive_mc:
        best = max(positive_mc, key=lambda r: r['mc_edge'])
        lines.append(f"- **最強 MC 機會**: {best['player']} {best['category']} {best['line_display']} — MC Edge +{best['mc_edge']}%")
    else:
        lines.append("- **MC 提示**: 本場無顯著 +EV 機會 (Edge < 5%)")
    
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def format_inline_mc(mc_result):
    """
    Format a single MC result as an inline annotation for embedding in Leg analysis.
    Returns a single-line string like:
    📊 **MC 模擬 (10,000次)**: 命中率 **82.4%** | MC Edge: +22.5% 💎
    """
    if not mc_result:
        return ""
    prob = mc_result.get("mc_prob", 0)
    edge = mc_result.get("mc_edge", 0)
    edge_str = f"+{edge}%" if edge > 0 else f"{edge}%"
    edge_icon = "💎" if edge >= 15 else ("✅" if edge >= 5 else ("➖" if edge >= 0 else "❌"))
    return f"📊 **MC 模擬 (10,000次)**: 命中率 **{prob}%** | MC Edge: {edge_str} {edge_icon}"


def build_mc_lookup(mc_results):
    """
    Build a lookup dict from MC results for quick access by player+category+line.
    Key format: "player_name|team|category|line_display"
    """
    lookup = {}
    for r in mc_results:
        key = f"{r['player']}|{r['team']}|{r['category']}|{r['line_display']}"
        lookup[key] = r
    return lookup


def monte_carlo_team_prop(home_off_rtg, home_def_rtg, away_off_rtg, away_def_rtg,
                          home_pace, away_pace, spread_line=None, total_line=None,
                          is_home_b2b=False, is_away_b2b=False,
                          n=10000, season_phase="MID_SEASON"):
    """
    Monte Carlo simulation for team-level props (Spread, Total O/U, ML).
    Uses offensive/defensive ratings + pace to estimate team scores.
    
    Returns dict with mc_home_score, mc_away_score, spread_cover_prob, total_over_prob, ml_home_prob.
    """
    league_avg_rtg = 112.0  # 2025-26 league average ORtg/DRtg baseline
    
    # Expected points per 100 possessions
    home_expected_per100 = (home_off_rtg + away_def_rtg) / 2
    away_expected_per100 = (away_off_rtg + home_def_rtg) / 2
    
    # Possessions estimate from pace
    game_pace = (home_pace + away_pace) / 2
    poss_factor = game_pace / 100.0
    
    home_expected = home_expected_per100 * poss_factor
    away_expected = away_expected_per100 * poss_factor
    
    # Home court advantage: ~+3 pts historically
    home_expected += 3.0
    
    # B2B fatigue penalty
    if is_home_b2b:
        home_expected -= 2.5
    if is_away_b2b:
        away_expected -= 2.5
    
    # SD for team scoring (typical NBA game-to-game SD ~11-13 points)
    base_sd = 12.0
    phase_sd_mult = {"EARLY_SEASON": 1.15, "MID_SEASON": 1.0, "LATE_REGULAR": 1.05,
                     "PLAY_IN": 0.95, "PLAYOFFS": 0.90}
    sd = base_sd * phase_sd_mult.get(season_phase, 1.0)
    
    # Simulate
    home_scores = [max(70, _normal_sample(home_expected, sd)) for _ in range(n)]
    away_scores = [max(70, _normal_sample(away_expected, sd)) for _ in range(n)]
    
    mc_home_avg = round(sum(home_scores) / n, 1)
    mc_away_avg = round(sum(away_scores) / n, 1)
    
    # ML probability
    home_wins = sum(1 for h, a in zip(home_scores, away_scores) if h > a)
    ml_home_prob = round(home_wins / n * 100, 1)
    ml_away_prob = round(100 - ml_home_prob, 1)
    
    result = {
        "mc_home_score": mc_home_avg,
        "mc_away_score": mc_away_avg,
        "ml_home_prob": ml_home_prob,
        "ml_away_prob": ml_away_prob,
        "season_phase": season_phase,
        "simulations": n,
    }
    
    # Spread cover probability (spread is relative to away team, e.g. -5.5 means home favored)
    if spread_line is not None:
        try:
            sl = float(spread_line)
            # If spread is -5.5 for home, away needs to be within 5.5
            # Spread cover (away perspective): away_score + spread > home_score
            away_covers = sum(1 for h, a in zip(home_scores, away_scores) if a + sl > h)
            result["spread_away_cover_prob"] = round(away_covers / n * 100, 1)
            result["spread_home_cover_prob"] = round(100 - result["spread_away_cover_prob"], 1)
        except (ValueError, TypeError):
            pass
    
    # Total O/U probability
    if total_line is not None:
        try:
            tl = float(total_line)
            overs = sum(1 for h, a in zip(home_scores, away_scores) if h + a > tl)
            result["total_over_prob"] = round(overs / n * 100, 1)
            result["total_under_prob"] = round(100 - result["total_over_prob"], 1)
        except (ValueError, TypeError):
            pass
    
    return result


def main():
    parser = argparse.ArgumentParser(description="NBA Monte Carlo Simulation Engine V2")
    parser.add_argument("--json", type=str, help="JSON config for single prop MC")
    parser.add_argument("--n", type=int, default=10000, help="Number of simulations")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.json:
        config = json.loads(args.json)
        result = monte_carlo_player_prop(
            avg=config.get("avg", 0),
            sd=config.get("sd", 0),
            line=config.get("line", 0),
            n=args.n,
            pace_factor=config.get("pace_factor", 1.0),
            home_away_factor=config.get("home_away_factor", 1.0),
            fatigue_factor=config.get("fatigue_factor", 1.0),
            matchup_factor=config.get("matchup_factor", 1.0),
            minutes_factor=config.get("minutes_factor", 1.0),
            usg_bonus=config.get("usg_bonus", 0.0),
            season_phase=config.get("season_phase", "MID_SEASON"),
            category=config.get("category", "PTS"),
            season_avg=config.get("season_avg"),
            l20_avg=config.get("l20_avg"),
            cov=config.get("cov"),
            odds=config.get("odds"),
            seed=args.seed,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Usage: python monte_carlo_nba.py --json '{\"avg\": 25, \"sd\": 5, \"line\": 24, \"category\": \"PTS\"}' --seed 42")


if __name__ == "__main__":
    main()
