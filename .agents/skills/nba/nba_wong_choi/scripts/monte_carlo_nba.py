#!/usr/bin/env python3
"""
monte_carlo_nba.py — NBA Props Monte Carlo Simulation Engine

Multi-factor adjusted distribution (NOT simple Normal(avg, sd)).
Adjusts the base distribution mean using pace, home/away, B2B,
matchup, and minutes projection factors before sampling.

Usage:
  # Called automatically by generate_nba_reports.py
  # Or standalone:
  python monte_carlo_nba.py --json '{"avg": 25.3, "sd": 5.2, "line": 24, ...}'

Version: 1.0.0
"""
import sys, io, json, math, argparse, random

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Use built-in random for portability (no numpy dependency)
def _normal_sample(mean, sd):
    """Sample from normal distribution using Box-Muller transform."""
    return random.gauss(mean, sd)


def monte_carlo_player_prop(avg, sd, line, n=10000,
                            pace_factor=1.0,
                            home_away_factor=1.0,
                            fatigue_factor=1.0,
                            matchup_factor=1.0,
                            minutes_factor=1.0,
                            usg_bonus=0.0,
                            season_phase="MID_SEASON"):
    """
    Multi-factor Monte Carlo simulation for a single player prop.
    
    Unlike simple Normal(avg, sd), this adjusts the distribution mean
    using contextual factors BEFORE sampling.
    
    Args:
        avg: L10 average for this stat
        sd: L10 standard deviation
        line: Sportsbet line (e.g., 10 for "10+")
        n: Number of simulations
        pace_factor: Matchup pace multiplier (e.g., 1.05 for fast game)
        home_away_factor: Home/Away multiplier (e.g., 1.02 for home)
        fatigue_factor: B2B fatigue multiplier (e.g., 0.97 for B2B away)
        matchup_factor: Opponent defense multiplier (e.g., 0.96 for elite D)
        minutes_factor: Minutes projection multiplier (e.g., 0.95 for blowout)
        usg_bonus: Absolute bonus from injured teammates' USG redistribution
    
    Returns:
        dict with mc_prob, mc_avg, mc_sd, distribution quartiles
    """
    if sd <= 0:
        sd = avg * 0.15  # Fallback: assume 15% CoV if no SD

    # Season phase SD adjustment
    phase_sd_multiplier = {
        "EARLY_SEASON": 1.20,   # Higher variance: new rosters, unknown rotations
        "MID_SEASON": 1.00,     # Default
        "LATE_REGULAR": 1.10,   # Slight increase: rest/tanking variance
        "PLAY_IN": 0.92,        # Tighter: high stakes
        "PLAYOFFS": 0.85,       # Much tighter: stars play full minutes, focused effort
    }
    sd *= phase_sd_multiplier.get(season_phase, 1.0)

    # Adjust distribution mean with contextual factors
    adj_avg = avg
    adj_avg *= pace_factor
    adj_avg *= home_away_factor
    adj_avg *= fatigue_factor
    adj_avg *= matchup_factor
    adj_avg *= minutes_factor
    adj_avg += usg_bonus

    hits = 0
    samples = []
    for _ in range(n):
        value = _normal_sample(adj_avg, sd)
        value = max(0, value)  # Floor at 0 (can't have negative stats)
        samples.append(value)
        if value >= line:
            hits += 1

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

    return {
        "mc_prob": mc_prob,
        "mc_avg": mc_avg,
        "mc_med": mc_med,
        "adj_avg": round(adj_avg, 2),
        "raw_avg": avg,
        "sd": sd,
        "line": line,
        "simulations": n,
        "p10": p10,
        "p25": p25,
        "p75": p75,
        "p90": p90,
    }


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
                              team_stats=None, meta=None, n=10000):
    """
    Run Monte Carlo simulation for all player cards.
    
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
            mc = monte_carlo_player_prop(
                avg=card["avg"], sd=card["sd"], line=la["line"], n=n,
                **ctx)
            
            mc["player"] = card["name"]
            mc["team"] = team
            mc["category"] = cl
            mc["line_display"] = la["line_display"]
            mc["odds"] = la["odds"]
            mc["implied_prob"] = la["implied_prob"]
            mc["l10_hit"] = la["hit_l10"]
            mc["ten_factor_adj"] = la["estimated_prob"]
            mc["mc_edge"] = round(mc["mc_prob"] - la["implied_prob"], 1)
            results.append(mc)

    return results


def format_mc_section(mc_results):
    """Format Monte Carlo results as markdown section."""
    lines = []
    lines.append("")
    lines.append("### 📊 Monte Carlo 命中率模擬 (10,000 次)")
    lines.append("")
    lines.append("> 🐍 由 Python `monte_carlo_nba.py` 自動計算 | Multi-Factor Adjusted Distribution")
    lines.append("> 唔係 Simple Normal(avg, sd) — 已注入 Pace、主客、B2B、防守、分鐘等情境因素")
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
    parser = argparse.ArgumentParser(description="NBA Monte Carlo Simulation Engine")
    parser.add_argument("--json", type=str, help="JSON config for single prop MC")
    parser.add_argument("--n", type=int, default=10000, help="Number of simulations")
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
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Usage: python monte_carlo_nba.py --json '{\"avg\": 25, \"sd\": 5, \"line\": 24}'")


if __name__ == "__main__":
    main()
