#!/usr/bin/env python3
"""
monte_carlo_core.py — Shared Monte Carlo Core Engine for Horse Racing

Professional-grade 3-layer composite model:
  Layer 1: Speed Rating (L400 sectional data)
  Layer 2: Energy Efficiency (EEM consumption data)
  Layer 3: Contextual Adjustments (8+ dimensions)

Shared by HKJC and AU Monte Carlo engines.

Version: 2.0.0
"""
import sys, io, json, random, math

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def _skewed_sample(mean, sd, skew=0.3):
    """Sample from skew-normal distribution.
    skew > 0 = positive skew (more likely to underperform).
    Reflects real racing: horses blow up more often than career bests.
    """
    if abs(skew) < 0.01:
        return random.gauss(mean, sd)
    delta = skew / math.sqrt(1 + skew**2)
    u0 = random.gauss(0, 1)
    v = random.gauss(0, 1)
    u = delta * abs(u0) + math.sqrt(1 - delta**2) * v
    return mean + sd * u


def weighted_stats(values, days_ago_list=None, half_life=120):
    """Compute exponentially decay-weighted mean and SD.
    Industry standard: 120-day half-life for horse form.
    Args:
        values: list of float metric values
        days_ago_list: list of int (days since each value), same order as values
        half_life: decay half-life in days (default 120)
    Returns: (weighted_mean, weighted_sd)
    """
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0] * 0.03
    if days_ago_list and len(days_ago_list) == len(values):
        lam = math.log(2) / half_life
        weights = [math.exp(-lam * d) for d in days_ago_list]
    else:
        weights = [1.0] * len(values)
    w_sum = sum(weights)
    w_mean = sum(v * w for v, w in zip(values, weights)) / w_sum
    w_var = sum(w * (v - w_mean)**2 for v, w in zip(values, weights)) / w_sum
    w_sd = math.sqrt(w_var) if w_var > 0 else w_mean * 0.03
    return round(w_mean, 3), round(max(w_sd, 0.05), 3)


def compute_stability_index(positions, top_n=6):
    """
    Compute position stability from last N finishes.
    Higher = more consistent = lower variance bonus.
    Returns: float 0.0 (chaotic) to 1.0 (robot-consistent)
    """
    if not positions or len(positions) < 2:
        return 0.5  # neutral
    # Calculate coefficient of variation of finishing positions
    avg_pos = sum(positions) / len(positions)
    if avg_pos == 0:
        return 0.5
    variance = sum((p - avg_pos) ** 2 for p in positions) / len(positions)
    sd = math.sqrt(variance)
    cov = sd / avg_pos
    # Invert: low CoV = high stability
    stability = max(0.0, min(1.0, 1.0 - cov))
    return round(stability, 3)


def compute_formline_adj(finishes):
    """
    Compute form trend adjustment from recent finishes.
    Returns: float adjustment (-0.03 to +0.03)
    """
    if not finishes or len(finishes) < 3:
        return 0.0
    recent = finishes[-3:]
    # All top 3 finishes = strong form
    if all(f <= 3 for f in recent):
        return 0.03
    # Improving trend
    if recent[-1] < recent[-2] < recent[-3]:
        return 0.02
    # Deteriorating
    if recent[-1] > recent[-2] > recent[-3]:
        return -0.02
    # Recent winner
    if recent[-1] == 1:
        return 0.015
    return 0.0


def compute_freshness_factor(days_since_last):
    """
    Compute freshness multiplier based on days since last race.
    Returns: float multiplier (0.92 to 1.03)
    """
    if days_since_last is None:
        return 1.0
    d = int(days_since_last)
    if d < 10:
        return 0.95   # Too quick turnaround
    if d < 14:
        return 0.97
    if d <= 21:
        return 1.01   # Sweet spot
    if d <= 42:
        return 1.02   # Well-rested
    if d <= 70:
        return 1.0    # Mild concern
    if d <= 90:
        return 0.97   # Long break
    return 0.92        # Very long layoff


def compute_weight_adj(weight, field_avg_weight=None, weight_gain=0, is_hkjc=True):
    """
    Compute weight adjustment.
    HKJC: weight in lbs (113-133 typical)
    AU: weight in kg (54-62 typical)
    """
    adj = 0.0
    if is_hkjc:
        if weight >= 133:
            adj -= 0.02  # Top weight
        if weight <= 115:
            adj += 0.01  # Light weight advantage
        if weight_gain >= 6:
            adj -= 0.01  # Significant weight gain
    else:
        if weight >= 62:
            adj -= 0.02
        if weight <= 54:
            adj += 0.01
        if weight_gain >= 3:
            adj -= 0.01
    return adj


def compute_barrier_adj(barrier, field_size, track_bias_benefit=False):
    """
    Compute barrier draw adjustment.
    Large barriers = disadvantage (track-dependent).
    """
    adj = 0.0
    if field_size <= 0:
        return 0.0
    barrier_pct = barrier / field_size
    if barrier_pct >= 0.85:
        adj -= 0.03  # Extreme outside
    elif barrier_pct >= 0.75:
        adj -= 0.02  # Wide barrier
    elif barrier_pct <= 0.15:
        adj += 0.01  # Inside rail advantage (can be negative in some track biases)
    
    if track_bias_benefit:
        adj += 0.015  # Bias-favoured position
    
    return adj


def compute_risk_penalty(risk_markers):
    """
    Apply risk penalty from override rules.
    risk_markers: int count of risk flags
    """
    if risk_markers >= 4:
        return -0.15
    if risk_markers == 3:
        return -0.10
    if risk_markers == 2:
        return -0.05
    return 0.0


def monte_carlo_race(horses, n=10000, speed_weight=0.35, energy_weight=0.25,
                     pace_scenario=None):
    """
    Run Monte Carlo simulation for a single race.
    
    Each horse dict should contain:
        name: str
        mean_speed: float (L400 average, lower = faster)
        sd_speed: float (L400 standard deviation)
        mean_energy: float (energy efficiency average)
        sd_energy: float (energy efficiency SD)
        stability_idx: float (0-1)
        trainer_win_rate: float (season win rate)
        jockey_win_rate: float (season win rate)
        days_since_last: int
        finishes: list[int] (recent finish positions)
        class_advantage: float (-0.05 to +0.05)
        weight: float
        field_size: int
        barrier: int
        risk_markers: int
        track_bias_benefit: bool
        forgiveness_bonus: bool
        weight_gain: float
        same_venue_dist_wins: int
    
    NOTE: For speed, LOWER = FASTER. We negate speed in composite
    so that higher composite = better.
    
    Returns: dict {horse_name: {win_pct, top3_pct, top4_pct, avg_rank}}
    """
    results = {h['name']: {'win': 0, 'top3': 0, 'top4': 0, 'rank_sum': 0} for h in horses}
    field_size = len(horses)
    
    for _ in range(n):
        performances = {}
        _field_shock = random.gauss(0, 0.015)  # Shared environment noise
        for h in horses:
            # ── Layer 1: Speed Rating Distribution ──
            mean_speed = h.get('mean_speed', 23.0)
            sd_speed = h.get('sd_speed', 0.5)
            if sd_speed <= 0:
                sd_speed = mean_speed * 0.03  # Fallback 3% CoV
            speed = _skewed_sample(mean_speed, sd_speed, skew=0.3)
            
            # ── Layer 2: Energy Efficiency Distribution ──
            mean_energy = h.get('mean_energy', 100.0)
            sd_energy = h.get('sd_energy', 5.0)
            if sd_energy <= 0:
                sd_energy = mean_energy * 0.05  # Fallback 5% CoV
            energy = _skewed_sample(mean_energy, sd_energy, skew=0.2)
            
            # ── Layer 3: Contextual Adjustments ──
            
            # 3a. Stability (core dimension)
            stability_idx = h.get('stability_idx', 0.5)
            stability_mult = 1.0
            if stability_idx > 0.7:
                stability_mult = 1.03
            elif stability_idx > 0.5:
                stability_mult = 1.01
            
            # 3b. Trainer/Jockey signal (semi-core dimension)
            trainer_wr = h.get('trainer_win_rate', 0.15)
            jockey_wr = h.get('jockey_win_rate', 0.10)
            trainer_mult = 1.0 + (trainer_wr - 0.15) * 0.5
            jockey_mult = 1.0 + (jockey_wr - 0.10) * 0.3
            
            # 3c. Pace Scenario Interaction
            pace_adj = 0.0
            if pace_scenario:
                style = h.get('running_style', 'mid_pack')
                _pace_matrix = {
                    'Fast':     {'leader': -0.06, 'on_pace': -0.03, 'mid_pack': 0.02, 'closer': 0.06},
                    'Moderate': {'leader': 0.0,   'on_pace': 0.0,   'mid_pack': 0.0,  'closer': 0.0},
                    'Crawl':    {'leader': 0.04,  'on_pace': 0.02,  'mid_pack': -0.01, 'closer': -0.03},
                    'Chaotic':  {'leader': -0.03, 'on_pace': -0.01, 'mid_pack': 0.01, 'closer': 0.02},
                }
                pace_adj = _pace_matrix.get(pace_scenario, {}).get(style, 0.0)
                if pace_scenario == 'Chaotic':
                    pace_adj += random.gauss(0, 0.02)
            
            # 3d. Scenario (venue/distance suitability)
            scenario_adj = 0.0
            if h.get('same_venue_dist_wins', 0) >= 3:
                scenario_adj = 0.02
            if h.get('track_bias_benefit', False):
                scenario_adj += 0.01
            
            # 3d. Freshness
            freshness_mult = compute_freshness_factor(h.get('days_since_last'))
            
            # 3e. Formline trend
            formline_adj = compute_formline_adj(h.get('finishes', []))
            
            # 3f. Class advantage
            class_adj = h.get('class_advantage', 0.0)
            
            # 3g. Risk penalty (override rules)
            risk_penalty = compute_risk_penalty(h.get('risk_markers', 0))
            
            # 3h. Weight + Barrier
            is_hkjc = h.get('is_hkjc', True)
            weight_adj = compute_weight_adj(
                h.get('weight', 120 if is_hkjc else 57),
                weight_gain=h.get('weight_gain', 0),
                is_hkjc=is_hkjc)
            barrier_adj = compute_barrier_adj(
                h.get('barrier', 1), field_size,
                h.get('track_bias_benefit', False))
            
            # 3i. Forgiveness bonus
            forgiveness_adj = 0.03 if h.get('forgiveness_bonus', False) else 0.0
            
            # ── Composite Score ──
            # NOTE: For L400, LOWER is FASTER, so we negate speed component
            speed_component = (30.0 - speed) * speed_weight
            energy_component = energy * energy_weight / 100.0
            
            composite = speed_component + energy_component
            composite *= stability_mult
            composite *= trainer_mult * jockey_mult
            composite *= freshness_mult
            
            # Additive adjustments with cap (prevent compound amplification)
            total_adj = (pace_adj + scenario_adj + formline_adj + class_adj
                        + risk_penalty + weight_adj + barrier_adj
                        + forgiveness_adj)
            total_adj = max(-0.25, min(0.25, total_adj))
            composite *= (1 + total_adj)
            
            # Field-wide environmental shock (runner correlation)
            composite *= (1 + _field_shock)
            
            performances[h['name']] = composite
        
        # Rank all horses (higher composite = better)
        ranked = sorted(performances, key=performances.get, reverse=True)
        results[ranked[0]]['win'] += 1
        for i, name in enumerate(ranked):
            results[name]['rank_sum'] += (i + 1)
            if i < 3:
                results[name]['top3'] += 1
            if i < 4:
                results[name]['top4'] += 1
    
    # Convert to percentages with 95% CI
    for name in results:
        win_p = results[name]['win'] / n
        top3_p = results[name]['top3'] / n
        ci_95 = 1.96 * math.sqrt(win_p * (1 - win_p) / n) * 100
        win_pct = round(win_p * 100, 1)
        top3_pct = round(top3_p * 100, 1)
        results[name] = {
            'win_pct': win_pct,
            'top3_pct': top3_pct,
            'top4_pct': round(results[name]['top4'] / n * 100, 1),
            'avg_rank': round(results[name]['rank_sum'] / n, 1),
            'ci_95': round(ci_95, 1),
            'predicted_win_odds': round(100 / win_pct, 1) if win_pct > 0 else 999.0,
            'predicted_place_odds': round(100 / top3_pct, 1) if top3_pct > 0 else 999.0,
        }
    
    return results


def format_mc_table(mc_results, top4_picks=None):
    """
    Format MC results as a markdown table.
    
    Args:
        mc_results: dict from monte_carlo_race()
        top4_picks: optional list of horse names from matrix Top 4
    
    Returns: string markdown section
    """
    lines = []
    lines.append("")
    lines.append("#### 📊 Monte Carlo 概率模擬 (10,000 次)")
    lines.append("")
    lines.append("> 🐍 由 Python `monte_carlo_core.py` 自動計算，基於 L400 段速 + EEM 能量 + 8 維度矩陣因素")
    lines.append("")
    lines.append("| 排名 | 馬名 | 勝出率 | ±95%CI | MC獨贏 | Top 3 率 | MC位置 | Top 4 率 | 平均名次 | 吻合 |")
    lines.append("|------|------|--------|--------|--------|---------|--------|---------|---------|------|")
    
    # Sort by win_pct descending
    sorted_names = sorted(mc_results, key=lambda n: mc_results[n]['win_pct'], reverse=True)
    top4_set = set(top4_picks or [])
    
    for i, name in enumerate(sorted_names):
        r = mc_results[name]
        match = "✅" if name in top4_set else "—"
        rank_icon = ["🥇", "🥈", "🥉", "4️⃣"][i] if i < 4 else f"{i+1}"
        ci_str = f"±{r.get('ci_95', 0)}%"
        win_odds = f"${r.get('predicted_win_odds', 0)}"
        place_odds = f"${r.get('predicted_place_odds', 0)}"
        lines.append(f"| {rank_icon} | {name} | {r['win_pct']}% | {ci_str} | {win_odds} | {r['top3_pct']}% | "
                     f"{place_odds} | {r['top4_pct']}% | {r['avg_rank']} | {match} |")
    
    lines.append("")
    
    # Concordance analysis
    if top4_picks:
        mc_top4 = set(sorted_names[:4])
        overlap = mc_top4 & top4_set
        concordance = len(overlap)
        lines.append(f"**吻合度：** Top 4 同 Matrix 排名 {concordance}/4 吻合 "
                     f"{'✅ 高度一致' if concordance >= 3 else ('⚠️ 部分分歧' if concordance >= 2 else '❌ 重大分歧')}")
        if concordance < 4:
            mc_only = mc_top4 - top4_set
            matrix_only = top4_set - mc_top4
            if mc_only:
                lines.append(f"- **MC 獨有**: {', '.join(mc_only)}")
            if matrix_only:
                lines.append(f"- **Matrix 獨有**: {', '.join(matrix_only)}")
    
    lines.append("")
    lines.append("---")
    return "\n".join(lines)
