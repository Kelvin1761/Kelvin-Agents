#!/usr/bin/env python3
"""
Monte Carlo Race Simulator v2.0 — Dual-Track Architecture
==========================================================
A statistical engine combining:
  Track 1: Softmax (Multinomial Logit) for win/place probabilities
  Track 2: Frame-by-frame MC simulation for pace dynamics

Methodology: Bolton-Chapman 1986, Bill Benter, Harville 1973.
Reads Logic.json, outputs MC_Results.json.

Supports both AU Racing and HKJC platforms.

Usage:
    python mc_simulator.py --input Race_1_Logic.json --platform au
    python mc_simulator.py --input Race_1_Logic.json --platform hkjc
    python mc_simulator.py --dir ./2026-04-17\ Cranbourne\ Race\ 1-8 --platform au
"""

import json
import argparse
import sys
import os
import re
from pathlib import Path

import numpy as np
# V2: skewnorm no longer used — using rng.normal() for symmetric noise

# ============================================================
# Constants
# ============================================================

N_SIMULATIONS = 10_000
SKEW_ALPHA = -1.5     # V2: Reduced from -3 for more realistic upset frequency
BASE_SIGMA = 12.0     # V2: Raised from 8.0 for wider variance
SIGMA_MIN = 5.0
SIGMA_MAX = 25.0      # V2: Raised from 16.0
PI_MIN = 5.0
PI_MAX = 80.0
RACE_DAY_FORM_SIGMA = 3.5  # V2: Per-horse random form shift per race

# V2: Softmax temperature by platform (calibrated against real favourite win rates)
# HKJC favourite ~30%, AU favourite ~28%
SOFTMAX_TEMPERATURE = {
    'hkjc': 11.0,
    'au': 10.0,
}

# V2.2: Market odds blending removed — pure Softmax model

# V2: Compressed PI range (14 points, was 26)
# Prevents PI gap from overwhelming noise in MC simulation
RATING_TO_BASE = {
    'S': 64, 'S-': 63, 'A+': 62, 'A': 61, 'A-': 60,
    'B+': 59, 'B': 58, 'B-': 57,
    'C+': 56, 'C': 55, 'C-': 54,
    'D+': 53, 'D': 52, 'D-': 50,
}

SCORE_TO_NUM = {
    '✅✅': 2.0, '✅': 1.0, '➖': 0.0, '❌': -1.0, '❌❌': -2.0,
}

# Running style profiles: (early_effort, mid_effort, late_effort, sprint_effort)
# Higher effort = faster but more energy drain
STYLE_PROFILES = {
    'A':   (0.95, 0.85, 0.80, 0.85),  # Front-runner: fast early, fades
    'B':   (0.70, 0.75, 0.85, 1.00),  # Closer: slow early, explosive late
    'C':   (0.85, 0.85, 0.85, 0.90),  # Sustained: even effort throughout
    'A/B': (0.82, 0.80, 0.83, 0.93),  # Versatile front-mid
    'B/C': (0.75, 0.80, 0.85, 0.95),  # Versatile mid-close
    'A/C': (0.88, 0.85, 0.83, 0.88),  # Versatile front-sustain
}

# V2: 3 phases (was 5) — reduces multiplicative PI compounding
PHASE_FRACTIONS = {
    'early':  0.35,  # Early positioning + cruise
    'mid':    0.35,  # Mid-race
    'sprint': 0.30,  # Final sprint
}

# SIP-02: Straight course 1000m — longer sprint emphasis
PHASE_FRACTIONS_STRAIGHT = {
    'early':  0.30,  # Sprint start
    'mid':    0.30,  # Sustain speed
    'sprint': 0.40,  # Extended final sprint
}


# SIP-03: Class-based sigma multiplier (lower class = more random)
def get_class_sigma_multiplier(class_info: str) -> float:
    """Lower classes have higher variance."""
    if '第五班' in str(class_info):
        return 1.2
    elif '第四班' in str(class_info):
        return 1.1
    return 1.0

# ============================================================
# Power Index Calculator
# ============================================================

def calc_power_index(horse: dict, platform: str, speed_map: dict) -> dict:
    """Calculate Power Index from Logic.json horse data. Returns breakdown dict."""
    rating = horse.get('final_rating', 'C')
    base = RATING_TO_BASE.get(rating, 44)

    # --- Matrix modifier (±15) ---
    matrix = horse.get('matrix', {})
    matrix_sum = 0.0
    for dim_name, dim_data in matrix.items():
        score_str = dim_data.get('score', '➖') if isinstance(dim_data, dict) else '➖'
        matrix_sum += SCORE_TO_NUM.get(score_str, 0.0)

    n_dims = max(len(matrix), 1)
    matrix_mod = (matrix_sum / n_dims) * (5.0 / 2.0)  # V2: Normalize to ±5 range (was ±8)
    matrix_mod = max(-5.0, min(5.0, matrix_mod))

    # --- Contextual modifiers (±10) ---
    ctx = 0.0

    # Barrier
    barrier = horse.get('barrier', 5)
    good_barrier = horse.get('good_barrier', False)
    if good_barrier:
        ctx += 2.5
    elif barrier and barrier > 10:
        ctx -= 2.0

    # Wet track
    wt_tier = horse.get('wet_track_tier', 2)
    if isinstance(wt_tier, int):
        ctx += {0: 0, 1: 3, 2: 0, 3: -1.5, 4: -3}.get(wt_tier, 0)

    # Race shape / positional consumption (replaces legacy EEM numeric model)
    eem = horse.get('eem_energy', {})
    drain_str = str(eem.get('cumulative_drain', '') if isinstance(eem, dict) else '')
    # Try numeric format first (legacy: '2.5/5.0')
    drain_val = None
    try:
        drain_val = float(drain_str.split('/')[0])
    except (ValueError, IndexError):
        pass
    if drain_val is not None:
        if drain_val <= 1.5:
            ctx += 2.0
        elif drain_val >= 3.5:
            ctx -= 3.0
        elif drain_val >= 2.8:
            ctx -= 1.0
    else:
        # Chinese text format: 高消耗/中等消耗/低消耗
        if '低消耗' in drain_str:
            ctx += 2.0
        elif '高消耗' in drain_str:
            ctx -= 2.5
        elif '中等消耗' in drain_str:
            ctx -= 0.5

    # Momentum
    momentum = str(horse.get('momentum_level', ''))
    if momentum == '穩':
        ctx += 1.0
    elif momentum in ('衰', '急跌'):
        ctx -= 2.0

    # Flags
    if horse.get('distance_wall', False):
        ctx -= 4.0
    if horse.get('long_spell', False):
        ctx -= 2.0
    uh = horse.get('underhorse', {})
    if isinstance(uh, dict) and uh.get('triggered', False):
        ctx += 3.0
    if horse.get('class_advantage_2bm', False):
        ctx += 3.0
    if horse.get('closer_cap_track', False):
        ctx -= 2.0

    # HKJC-specific: weight penalty (heavier = worse)
    # SIP-07: Non-linear weight reduction model
    if platform == 'hkjc':
        weight = horse.get('weight', 126)
        if isinstance(weight, (int, float)) and weight > 0:
            reduction = 126 - weight
            if abs(reduction) >= 7:
                ctx += reduction * 0.22  # Significant claim: boosted effect
            else:
                ctx += reduction * 0.15  # Standard effect
            # Short distance / AWT extra boost for weight reduction
            distance_val = horse.get('_race_distance', 1200)
            if isinstance(distance_val, (int, float)) and distance_val <= 1200 and reduction > 0:
                ctx += reduction * 0.03  # Modest sprint boost

    ctx = max(-6.0, min(6.0, ctx))  # V2: ±6 range (was ±10)

    # --- Pace modifier (calculated separately) ---
    pace_mod = 0.0  # Will be set by PaceEngine

    final_pi = float(np.clip(base + matrix_mod + ctx + pace_mod, PI_MIN, PI_MAX))

    return {
        'base': base,
        'matrix': round(matrix_mod, 1),
        'contextual': round(ctx, 1),
        'pace': round(pace_mod, 1),
        'final_pi': round(final_pi, 1),
    }


# ============================================================
# Dynamic Sigma Calibrator
# ============================================================

def calc_sigma(horse: dict) -> float:
    """V3: Calculate dynamic sigma using fields available in HKJC Logic.json.
    Infers stability, experience, and consistency from actual data."""
    sigma = BASE_SIGMA

    # --- Stability: check dedicated field first, then infer from last_6 ---
    stability = str(horse.get('stability_index', '')).lower()
    if stability in ('穩定', '穩'):
        sigma -= 3.0
    elif stability in ('衰退中', '急劇衰退', '低'):
        sigma += 3.0
    else:
        # Infer stability from last_6_finishes (e.g. '11-5-7-1-1-9')
        last_6 = str(horse.get('last_6_finishes', ''))
        if last_6 and last_6 != 'N/A':
            try:
                positions = [int(x) for x in last_6.split('-') if x.strip().isdigit()]
                if len(positions) >= 3:
                    # Coefficient of variation: high = volatile, low = stable
                    mean_pos = sum(positions) / len(positions)
                    if mean_pos > 0:
                        std_pos = (sum((p - mean_pos)**2 for p in positions) / len(positions)) ** 0.5
                        cv = std_pos / mean_pos
                        if cv < 0.25:  # Very consistent
                            sigma -= 2.5
                        elif cv < 0.40:  # Reasonably stable
                            sigma -= 1.0
                        elif cv > 0.70:  # Highly volatile
                            sigma += 2.5
                        elif cv > 0.55:  # Somewhat volatile
                            sigma += 1.5
            except (ValueError, ZeroDivisionError):
                pass

    # --- Long spell: check field or infer from days_since_last ---
    if horse.get('long_spell', False):
        sigma += 3.0
    else:
        days = horse.get('days_since_last', 0)
        if isinstance(days, (int, float)) and days > 60:
            sigma += 3.0
        elif isinstance(days, (int, float)) and days > 35:
            sigma += 1.5

    if horse.get('trial_illusion', False):
        sigma += 2.0
    if horse.get('is_2yo', False):
        sigma += 3.0
    wt = horse.get('wet_track_tier', 2)
    if isinstance(wt, int) and wt >= 4:
        sigma += 2.0

    # --- Positional consumption (replaces legacy eem_3_high_drain) ---
    eem = horse.get('eem_energy', {})
    drain_str = str(eem.get('cumulative_drain', '') if isinstance(eem, dict) else '')
    if '高消耗' in drain_str:
        sigma += 1.5

    # --- Experience: fewer starts = more volatile ---
    try:
        starts = int(horse.get('starts', 0))
        if starts > 0:
            if starts <= 2:
                sigma += 4.0
            elif starts <= 5:
                sigma += 2.0
            elif starts >= 20:
                sigma -= 1.0  # Veteran horse, more predictable
    except (ValueError, TypeError):
        pass

    # --- Consistency: count top-3 finishes in last_6 ---
    r3 = horse.get('recent_3_top3', None)
    if r3 is not None:
        try:
            if int(r3) >= 2:
                sigma -= 2.0
        except (ValueError, TypeError):
            pass
    else:
        # Infer from last_6_finishes
        last_6 = str(horse.get('last_6_finishes', ''))
        if last_6 and last_6 != 'N/A':
            try:
                positions = [int(x) for x in last_6.split('-') if x.strip().isdigit()]
                top3_count = sum(1 for p in positions if p <= 3)
                if top3_count >= 3:
                    sigma -= 2.5  # Very consistent performer
                elif top3_count >= 2:
                    sigma -= 1.5
            except ValueError:
                pass

    return float(np.clip(sigma, SIGMA_MIN, SIGMA_MAX))


# ============================================================
# Running Style Detector
# ============================================================

def detect_style(horse: dict, speed_map: dict) -> str:
    """Detect running style from analytical_breakdown or speed_map position."""
    name = horse.get('horse_name', '')
    hnum = None
    # Try to find horse number
    for field in ('horse_number', '_horse_num'):
        if field in horse:
            hnum = str(horse[field])
            break

    # Check speed_map position
    if speed_map:
        leaders = [str(x) for x in speed_map.get('leaders', [])]
        on_pace = [str(x) for x in speed_map.get('on_pace', [])]
        closers = [str(x) for x in speed_map.get('closers', [])]

        if hnum:
            if hnum in leaders:
                return 'A'
            if hnum in closers:
                return 'B'
            if hnum in on_pace:
                return 'A/B'

    # Fallback: check analytical_breakdown
    ab = horse.get('analytical_breakdown', {})
    engine_str = ''
    if isinstance(ab, dict):
        engine_str = str(ab.get('engine_distance', ''))

    tac = horse.get('tactical_plan', {})
    if isinstance(tac, dict):
        pos = str(tac.get('expected_position', '')).lower()
        if any(k in pos for k in ('前領', '放頭', '領放')):
            return 'A'
        if any(k in pos for k in ('後段', '後追', '包尾')):
            return 'B'
        if any(k in pos for k in ('居中前',)):
            return 'A/C'
        if any(k in pos for k in ('居中後', '居中')):
            return 'C'

    return 'C'  # Default: sustained


# ============================================================
# Pace Engine
# ============================================================

def calc_pace_modifiers(horses_data: list, speed_map: dict) -> dict:
    """
    Calculate pace-related Power Index modifiers for each horse.
    Models the Speed Duel Effect and track bias.

    Reads predicted_pace (5-tier: Very Slow / Slow / Normal / Fast / Very Fast)
    and pace_volatility (Stable / Volatile / Chaotic) from speed_map.

    Returns {horse_name: pace_modifier}.
    """
    mods = {}
    if not speed_map:
        return {h['horse_name']: 0.0 for h in horses_data}

    leaders = speed_map.get('leaders', [])
    n_leaders = len(leaders)
    track_bias = str(speed_map.get('track_bias', ''))

    # Read pace label — support both predicted_pace (new) and expected_pace (legacy)
    pace_raw = str(speed_map.get('predicted_pace',
                   speed_map.get('expected_pace', 'Normal'))).lower().strip()

    # Map to numeric index for graduated modifiers
    pace_map = {
        'very fast': 2, 'fast': 1, 'normal': 0, 'slow': -1, 'very slow': -2,
        # Legacy labels (backward compat)
        'chaotic': 2, 'moderate': 0, 'crawl': -2,
    }
    pace_idx = pace_map.get(pace_raw, 0)

    # Inner rail collapse detection
    rail_collapse = any(k in track_bias for k in ('崩潰', '爛地', '內欄', 'deteriorat'))

    for h in horses_data:
        mod = 0.0
        style = h.get('_style', 'C')
        barrier = h.get('barrier', 5)

        # --- Speed Duel Effect ---
        if style == 'A':  # Front runner
            if n_leaders >= 4:
                mod -= 6.0   # Severe burn-up
            elif n_leaders >= 3:
                mod -= 4.0   # Significant burn
            elif n_leaders == 1:
                mod += 3.0   # Lone leader advantage

            # Pace pressure on front runners (graduated)
            if pace_idx >= 2:      # Very Fast
                mod -= 2.0
            elif pace_idx >= 1:    # Fast
                mod -= 1.0
            elif pace_idx <= -1:   # Slow / Very Slow — leader controls
                mod += 1.5

        elif style == 'B':  # Closer
            if n_leaders >= 3:
                mod += 3.0   # Benefits from speed collapse
            elif n_leaders <= 1 and pace_idx <= 0:
                mod -= 2.5   # No pace to run into

            # Closers benefit from fast pace (graduated)
            if pace_idx >= 2:      # Very Fast
                mod += 3.0
            elif pace_idx >= 1:    # Fast
                mod += 2.0
            elif pace_idx <= -1:   # Slow — closers suffer
                mod -= 1.0

        elif style in ('A/B', 'A/C'):  # On-pace / versatile
            if pace_idx >= 2:
                mod -= 0.5   # Slight penalty in very fast pace
            elif pace_idx <= -2:
                mod += 0.5   # Slight benefit in very slow pace

        # --- Track bias ---
        if rail_collapse:
            if isinstance(barrier, int) and barrier <= 3 and style == 'A':
                mod -= 3.0   # Inside front-runner on collapsed rail
            elif isinstance(barrier, int) and barrier >= 8:
                mod += 1.5   # Outside draw avoids bad rail

        if '前領有利' in track_bias or 'speed favoring' in track_bias.lower():
            if style == 'A':
                mod += 2.5
            elif style == 'B':
                mod -= 2.0

        mods[h['horse_name']] = round(max(-8.0, min(8.0, mod)), 1)

    return mods


# ============================================================
# Frame-by-Frame Race Simulation Engine
# ============================================================

class HorseState:
    """State of a horse during a single simulation run."""
    __slots__ = ('name', 'power', 'sigma', 'style_profile', 'energy',
                 'position', 'cumulative_speed', 'barrier', 'lane',
                 'drafting', 'blocked')

    def __init__(self, name, power, sigma, style_key, barrier):
        self.name = name
        self.power = power
        self.sigma = sigma
        self.style_profile = STYLE_PROFILES.get(style_key, STYLE_PROFILES['C'])
        self.energy = 100.0  # Full energy at start
        self.position = 0.0  # Distance covered
        self.cumulative_speed = 0.0
        self.barrier = barrier
        self.lane = barrier  # Approximate track position (1=rail)
        self.drafting = False
        self.blocked = False


def simulate_single_race(horses: list, rng: np.random.Generator,
                         distance: int, rail_collapse: bool,
                         is_straight: bool = False) -> list:
    """
    V2: Simulate one race with ADDITIVE model.
    PI is location parameter (not multiplier) — prevents exponential compounding.
    Returns list of (horse_name, total_performance) sorted best-first.
    """
    n = len(horses)
    if n == 0:
        return []

    # Initialize horse states
    states = []
    for h in horses:
        s = HorseState(
            name=h['name'],
            power=h['power_index'],
            sigma=h['sigma'],
            style_key=h['style'],
            barrier=h.get('barrier', 5),
        )
        states.append(s)

    # V2: Race-day form — random shift per horse per race
    day_forms = {s.name: rng.normal(0, RACE_DAY_FORM_SIGMA) for s in states}

    # SIP-02: Use straight course phases if applicable
    phases = PHASE_FRACTIONS_STRAIGHT if is_straight else PHASE_FRACTIONS
    active_phases = {k: v for k, v in phases.items() if v > 0}

    # Run through each phase
    for phase_idx, (phase_name, frac) in enumerate(active_phases.items()):
        for s in states:
            effort_mult = s.style_profile[min(phase_idx, len(s.style_profile) - 1)]

            # V2 ADDITIVE MODEL: PI + effort_bonus + energy_bonus + day_form + noise
            # (was: PI * effort * energy_factor + noise — multiplicative)
            effort_bonus = (effort_mult - 0.85) * 12.0  # ±1.8 range
            energy_bonus = (s.energy - 50) * 0.04        # ±2.0 range

            # Noise: normal distribution (V2: symmetric, was skew-normal)
            noise = rng.normal(0, s.sigma)

            phase_speed = s.power + day_forms[s.name] + effort_bonus + energy_bonus + noise

            # Drafting bonus: mid-pack horses save energy
            if effort_mult < 0.82 and s.energy > 50:
                phase_speed += 0.8
                s.energy += 1.0

            # Rail collapse penalty (later phases)
            if rail_collapse and phase_idx >= 1 and s.lane <= 2:
                phase_speed -= 3.0
                s.energy -= 3.0

            # Barrier effects at start
            if phase_name == 'early':
                if is_straight:
                    if s.barrier >= 8:
                        phase_speed += 1.0
                    elif s.barrier <= 3:
                        phase_speed -= 0.5
                else:
                    if s.barrier > 10:
                        phase_speed -= 1.5

            # Energy depletion
            depletion = effort_mult * 8.0
            if phase_name == 'sprint':
                depletion *= 1.5
            s.energy = max(0, s.energy - depletion)

            # Fatigue cliff
            if s.energy < 15:
                phase_speed -= 3.0

            s.cumulative_speed += max(0, phase_speed)

    # Sort by cumulative speed (higher = better finish)
    results = [(s.name, s.cumulative_speed) for s in states]
    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ============================================================
# Monte Carlo Engine
# ============================================================

def run_monte_carlo(horses: list, distance: int, rail_collapse: bool,
                    n_sims: int = N_SIMULATIONS, seed: int = 42,
                    is_straight: bool = False) -> dict:
    """
    Run N Monte Carlo simulations and aggregate results.
    horses: list of {name, power_index, sigma, style, barrier}
    Returns dict of results per horse.
    """
    rng = np.random.default_rng(seed)
    n = len(horses)

    counters = {h['name']: {'wins': 0, 'top3': 0, 'top4': 0, 'rank_sum': 0} for h in horses}

    for _ in range(n_sims):
        result = simulate_single_race(horses, rng, distance, rail_collapse, is_straight)
        for rank, (name, _) in enumerate(result):
            c = counters[name]
            c['rank_sum'] += rank + 1
            if rank == 0:
                c['wins'] += 1
            if rank < 3:
                c['top3'] += 1
            if rank < 4:
                c['top4'] += 1

    output = {}
    for name, c in counters.items():
        w = c['wins']
        wp = w / n_sims
        output[name] = {
            'win_pct': round(wp * 100, 1),
            'top3_pct': round(c['top3'] / n_sims * 100, 1),
            'top4_pct': round(c['top4'] / n_sims * 100, 1),
            'avg_rank': round(c['rank_sum'] / n_sims, 1),
            'ci_95': round(1.96 * np.sqrt(wp * (1 - wp) / n_sims) * 100, 1),
            'predicted_win_odds': round(n_sims / max(w, 1), 1),
            'predicted_place_odds': round(n_sims / max(c['top3'], 1), 1),
        }

    # V2: No squashing — MC results kept raw for pace dynamics
    # Win probabilities are now computed via Softmax (see calc_win_probabilities)
    return output


# ============================================================
# V2: Softmax Win Probabilities (Bolton-Chapman / Benter)
# ============================================================

def calc_win_probabilities(pi_breakdown: dict, platform: str) -> dict:
    """
    V2.2: Pure Softmax (Multinomial Logit) win probabilities.
    Based on Bolton-Chapman 1986 methodology.
    """
    T = SOFTMAX_TEMPERATURE.get(platform, 11.0)
    names = list(pi_breakdown.keys())
    pis = np.array([pi_breakdown[n]['final_pi'] for n in names])

    scaled = pis / T
    exp_vals = np.exp(scaled - np.max(scaled))  # numerical stability
    softmax_probs = exp_vals / np.sum(exp_vals) * 100

    return {name: round(p, 1) for name, p in zip(names, softmax_probs)}


# ============================================================
# V2: Harville Place Probabilities
# ============================================================

def calc_place_probabilities(win_probs: dict) -> dict:
    """
    Harville formula (1973): derive top-3 (place) probability from win probabilities.
    P(j finishes 2nd | i wins) = P_j / (1 - P_i)
    """
    names = list(win_probs.keys())
    result = {}

    for target in names:
        pt = win_probs[target] / 100.0
        p_top3 = pt  # Win = automatic top3

        # P(target 2nd) = Σ P(j wins) * P(target 2nd | j wins)
        for j in names:
            if j == target:
                continue
            pj = win_probs[j] / 100.0
            denom1 = 1.0 - pj
            if denom1 > 1e-9:
                p_2nd_given_j = pj * (pt / denom1)
                p_top3 += p_2nd_given_j

                # P(target 3rd) = Σ Σ P(j wins, k 2nd) * P(target 3rd | j,k)
                for k in names:
                    if k in (target, j):
                        continue
                    pk = win_probs[k] / 100.0
                    denom2 = 1.0 - pj - pk
                    if denom2 > 1e-9:
                        p_top3 += pj * (pk / denom1) * (pt / denom2)

        result[target] = round(min(p_top3 * 100, 99.9), 1)

    return result


# ============================================================
# V2: Top-4 Probability (extended Harville)
# ============================================================

def calc_top4_probabilities(win_probs: dict, place_probs: dict) -> dict:
    """Approximate top-4 probability from win + place probabilities.
    Uses scaled ratio: top4 ≈ place_pct * (4/3) capped at 99.9%.
    """
    result = {}
    for name in win_probs:
        place_pct = place_probs.get(name, 0)
        # Scale up by 4/3 ratio (4 slots vs 3 slots)
        top4_approx = min(place_pct * (4.0 / 3.0), 99.9)
        result[name] = round(top4_approx, 1)
    return result

# ============================================================
# V2.1: MC Pace Dynamics Feedback
# ============================================================

def calc_pace_feedback(mc_raw: dict, pi_breakdown: dict) -> dict:
    """
    V2.1: Extract pace dynamics from MC sim and feed back as PI adjustments.
    Compares MC rank (dynamic) vs PI rank (static).
    If MC sim consistently ranks a horse higher/lower than PI,
    it indicates pace dynamics favour/disfavour that horse.
    Returns: dict of {name: pi_adjustment}
    """
    if not mc_raw or not pi_breakdown:
        return {}

    # PI ranking
    pi_sorted = sorted(pi_breakdown.items(), key=lambda x: x[1]['final_pi'], reverse=True)
    pi_rank = {name: i + 1 for i, (name, _) in enumerate(pi_sorted)}

    # MC ranking (by win_pct from raw MC sim)
    mc_sorted = sorted(mc_raw.items(), key=lambda x: x[1].get('win_pct', 0), reverse=True)
    mc_rank = {name: i + 1 for i, (name, _) in enumerate(mc_sorted)}

    adjustments = {}
    for name in pi_breakdown:
        pr = pi_rank.get(name, 99)
        mr = mc_rank.get(name, 99)
        rank_diff = pr - mr  # positive = MC ranks higher than PI (pace helps)

        # Only apply meaningful adjustments (>2 rank positions difference)
        if abs(rank_diff) > 2:
            # Cap adjustment at ±3 PI points
            adj = max(-3.0, min(3.0, rank_diff * 0.8))
            adjustments[name] = round(adj, 1)

    return adjustments


# V2.2: Market odds extraction removed — pure model-driven probabilities


# ============================================================
# Platform Adapters
# ============================================================

def load_logic_json(filepath: str) -> dict:
    """Load and return Logic.json data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_horses_au(data: dict) -> tuple:
    """Extract horse data from AU Logic.json format."""
    ra = data.get('race_analysis', {})
    speed_map = ra.get('speed_map', {})
    verdict = ra.get('verdict', {})
    dist_str = str(ra.get('distance', '1200m'))
    distance = int(re.search(r'(\d+)', dist_str).group(1)) if re.search(r'(\d+)', dist_str) else 1200

    horses_raw = data.get('horses', {})
    horses = []
    for hnum, hdata in horses_raw.items():
        hdata['_horse_num'] = hnum
        style = detect_style(hdata, speed_map)
        hdata['_style'] = style
        horses.append(hdata)

    return horses, speed_map, verdict, distance


def extract_horses_hkjc(data: dict) -> tuple:
    """Extract horse data from HKJC Logic.json format."""
    ra = data.get('race_analysis', {})
    speed_map = ra.get('speed_map', {})
    verdict = ra.get('verdict', {})
    dist_str = str(ra.get('distance', '1200m'))
    distance = int(re.search(r'(\d+)', dist_str).group(1)) if re.search(r'(\d+)', dist_str) else 1200

    horses_raw = data.get('horses', {})
    horses = []
    for hnum, hdata in horses_raw.items():
        hdata['_horse_num'] = hnum
        style = detect_style(hdata, speed_map)
        hdata['_style'] = style
        horses.append(hdata)

    return horses, speed_map, verdict, distance


# ============================================================
# Concordance Checker
# ============================================================

def calc_concordance(mc_results: dict, verdict: dict, horses_raw: list = None) -> dict:
    """Compare MC top4 with Logic verdict top4."""
    mc_sorted = sorted(mc_results.items(), key=lambda x: x[1]['win_pct'], reverse=True)
    mc_top4 = [name for name, _ in mc_sorted[:4]]

    # Build horse_num -> name lookup
    num_to_name = {}
    if horses_raw:
        for h in horses_raw:
            hnum = str(h.get('_horse_num', ''))
            hname = h.get('horse_name', '')
            if hnum and hname:
                num_to_name[hnum] = hname

    logic_top4_raw = verdict.get('top4', [])
    logic_top4 = []
    for item in logic_top4_raw:
        if isinstance(item, dict):
            # HKJC format: {'horse_num': '5', 'reason': '...'}
            hnum = str(item.get('horse_num', item.get('horse_number', '')))
            hname = item.get('horse_name', num_to_name.get(hnum, f'#{hnum}'))
            logic_top4.append(hname)
        elif isinstance(item, str):
            # Could be a string-serialized dict or a horse name
            if item.startswith('{') and 'horse_num' in item:
                try:
                    import ast
                    d = ast.literal_eval(item)
                    hnum = str(d.get('horse_num', ''))
                    hname = num_to_name.get(hnum, f'#{hnum}')
                    logic_top4.append(hname)
                except Exception:
                    logic_top4.append(item)
            else:
                logic_top4.append(item)

    overlap = len(set(mc_top4) & set(logic_top4))

    # Divergence alerts
    alerts = []
    for name, stats in mc_results.items():
        if stats['win_pct'] > 15 and name not in logic_top4:
            alerts.append(f"{name} has {stats['win_pct']}% MC win but NOT in Logic top4")

    # SIP-08: Action-required alerts when concordance is low
    action_alerts = []
    if overlap <= 2:
        action_alerts.append(
            f"⚠️ LOW_CONCORDANCE: Logic-MC overlap = {overlap}/4. Expand to Top6."
        )
        # Identify MC-only horses with significant win%
        mc_only = []
        for name, stats in mc_results.items():
            if name not in logic_top4 and stats['win_pct'] > 10:
                mc_only.append({'name': name, 'win_pct': stats['win_pct']})
        mc_only.sort(key=lambda x: x['win_pct'], reverse=True)
        for m in mc_only[:2]:  # Max 2 additions
            action_alerts.append(
                f"📋 FORCE_REVIEW: {m['name']} has MC {m['win_pct']}% but NOT in Logic Top4"
            )

    # SIP-03: Overconfidence alert
    mc_sorted_check = sorted(mc_results.items(), key=lambda x: x[1]['win_pct'], reverse=True)
    if len(mc_sorted_check) >= 2:
        top2_combined = mc_sorted_check[0][1]['win_pct'] + mc_sorted_check[1][1]['win_pct']
        if top2_combined > 60:
            action_alerts.append(
                f"⚠️ OVERCONFIDENCE: Top2 combined = {top2_combined:.1f}%. Consider expanding to Top6."
            )

    return {
        'logic_top4': logic_top4,
        'mc_top4': mc_top4,
        'overlap': overlap,
        'mc_top6': [name for name, _ in mc_sorted[:6]],  # V2.1
        'overlap_top6': len(set([name for name, _ in mc_sorted[:6]]) & set(logic_top4)),
        'divergence_alerts': alerts,
        'action_alerts': action_alerts,
        'concordance_level': 'HIGH' if overlap >= 3 else 'LOW',
    }


# ============================================================
# Main Pipeline
# ============================================================

def process_race(filepath: str, platform: str) -> dict:
    """Process a single Logic.json file and return MC results."""
    data = load_logic_json(filepath)

    if platform == 'hkjc':
        horses_raw, speed_map, verdict, distance = extract_horses_hkjc(data)
    else:
        horses_raw, speed_map, verdict, distance = extract_horses_au(data)

    # Extract race metadata for SIP adjustments
    ra = data.get('race_analysis', {})
    class_info = str(ra.get('race_class', ''))
    track_str = str(ra.get('track', ''))

    # SIP-02: Detect straight course
    # HKJC: 1000m at Sha Tin is ALWAYS the straight course (no turns)
    # Logic.json may not have 'track' field, so we detect by distance + platform
    is_straight = False
    if platform == 'hkjc' and distance <= 1000:
        # All 1000m HKJC turf races are straight course at Sha Tin
        # Only exception would be AWT (全天候), but 1000m AWT doesn't exist at ST
        is_straight = True
    elif distance <= 1000 and ('草地' in track_str and '直路' in track_str):
        is_straight = True

    # SIP-03: Class-based sigma multiplier
    class_sigma_mult = get_class_sigma_multiplier(class_info)

    # SIP-05: Detect class drop cluster
    n_s_grades = 0
    top4_raw = verdict.get('top4', []) if isinstance(verdict, dict) else []
    for t in top4_raw:
        if isinstance(t, dict) and str(t.get('grade', '')).startswith('S'):
            n_s_grades += 1
    class_drop_cluster = (n_s_grades >= 4)

    # Inject race distance into horse data for SIP-07 weight calc
    for h in horses_raw:
        h['_race_distance'] = distance

    # Step 1: Calculate Power Index + Sigma for each horse
    pi_breakdown = {}
    for h in horses_raw:
        name = h.get('horse_name', f"Horse_{h.get('_horse_num', '?')}")
        pi_info = calc_power_index(h, platform, speed_map)
        sigma = calc_sigma(h)

        # SIP-03: Apply class sigma multiplier
        sigma *= class_sigma_mult

        # SIP-02: Straight course sigma boost (+40%)
        if is_straight:
            sigma *= 1.4

        sigma = float(np.clip(sigma, SIGMA_MIN, SIGMA_MAX))
        pi_breakdown[name] = {**pi_info, 'sigma': round(sigma, 1)}

    # Step 2: Calculate pace modifiers
    pace_mods = calc_pace_modifiers(horses_raw, speed_map)

    # Step 3: Apply pace modifiers to PI
    for h in horses_raw:
        name = h.get('horse_name', '')
        if name in pi_breakdown and name in pace_mods:
            pi_breakdown[name]['pace'] = pace_mods[name]
            new_pi = pi_breakdown[name]['base'] + pi_breakdown[name]['matrix'] + \
                     pi_breakdown[name]['contextual'] + pace_mods[name]
            pi_breakdown[name]['final_pi'] = round(float(np.clip(new_pi, PI_MIN, PI_MAX)), 1)

    # SIP-02: Straight course — extra burn penalty for front-runners
    if is_straight:
        leaders = speed_map.get('leaders', []) if speed_map else []
        n_leaders = len(leaders)
        if n_leaders >= 4:
            for h in horses_raw:
                name = h.get('horse_name', '')
                if h.get('_style') == 'A' and name in pi_breakdown:
                    pi_breakdown[name]['final_pi'] = max(
                        PI_MIN, pi_breakdown[name]['final_pi'] - 4.0
                    )

    # SIP-05: Class drop cluster — dilute class advantage bonus
    if class_drop_cluster:
        for name, pi in pi_breakdown.items():
            # Reduce contextual bonus by 30% for all horses in cluster scenario
            if pi.get('contextual', 0) > 0:
                reduced = pi['contextual'] * 0.7
                diff = pi['contextual'] - reduced
                pi['contextual'] = round(reduced, 1)
                pi['final_pi'] = round(pi['final_pi'] - diff, 1)

    # Step 4: Build simulation input
    track_bias = str(speed_map.get('track_bias', ''))
    rail_collapse = any(k in track_bias for k in ('崩潰', '爛地', '內欄', 'deteriorat'))

    sim_horses = []
    for h in horses_raw:
        name = h.get('horse_name', '')
        pi = pi_breakdown.get(name, {})
        sim_horses.append({
            'name': name,
            'power_index': pi.get('final_pi', 44.0),
            'sigma': pi.get('sigma', BASE_SIGMA),
            'style': h.get('_style', 'C'),
            'barrier': h.get('barrier', 5),
        })

    # Step 5: Run Monte Carlo (for pace dynamics + avg_rank)
    mc_raw = run_monte_carlo(sim_horses, distance, rail_collapse, is_straight=is_straight)

    # Step 5b: V2.1 — Pace dynamics feedback into PI
    pace_fb = calc_pace_feedback(mc_raw, pi_breakdown)
    if pace_fb:
        for name, adj in pace_fb.items():
            if name in pi_breakdown:
                old_pi = pi_breakdown[name]['final_pi']
                pi_breakdown[name]['final_pi'] = round(
                    float(np.clip(old_pi + adj, PI_MIN, PI_MAX)), 1
                )
                pi_breakdown[name]['pace_feedback'] = adj

    # Step 6: V2.2 Pure Softmax win probabilities
    win_probs = calc_win_probabilities(pi_breakdown, platform)
    place_probs = calc_place_probabilities(win_probs)
    top4_probs = calc_top4_probabilities(win_probs, place_probs)

    # Step 7: Build backward-compatible 'results' dict
    # Uses Softmax win%, Harville place%, MC avg_rank
    results_compat = {}
    for name in win_probs:
        mc_data = mc_raw.get(name, {})
        wp = win_probs[name]
        pp = place_probs.get(name, 0)
        t4p = top4_probs.get(name, 0)
        results_compat[name] = {
            'win_pct': wp,
            'top3_pct': pp,
            'top4_pct': t4p,
            'avg_rank': mc_data.get('avg_rank', 0),
            'ci_95': round(1.96 * np.sqrt(wp/100 * (1-wp/100) / N_SIMULATIONS) * 100, 1),
            'predicted_win_odds': round(100 / max(wp, 0.1), 1),
            'predicted_place_odds': round(100 / max(pp, 0.1), 1),
        }

    # Step 8: Concordance (using Softmax-based top4 + top6)
    concordance = calc_concordance(results_compat, verdict, horses_raw)

    # Step 9: Build output — V2.1 with top6
    sm_sorted = sorted(win_probs.items(), key=lambda x: x[1], reverse=True)
    top4_matrix = [name for name, _ in sm_sorted[:4]]
    top6_matrix = [name for name, _ in sm_sorted[:6]]

    return {
        'simulations': N_SIMULATIONS,
        'engine_version': 'mc_v2.2_pure_softmax',
        'platform': platform,
        'horses_count': len(sim_horses),
        'distance': distance,
        'is_straight_course': is_straight,
        'class_drop_cluster': class_drop_cluster,
        'methodology': {
            'win_probability': 'softmax_multinomial_logit',
            'place_probability': 'harville_formula',
            'pace_dynamics': 'frame_by_frame_mc_v2_additive',
            'pace_feedback': bool(pace_fb),
            'temperature': SOFTMAX_TEMPERATURE.get(platform, 11.0),
        },
        'parameters': {
            'base_sigma': BASE_SIGMA,
            'skew_alpha': SKEW_ALPHA,
            'temperature': SOFTMAX_TEMPERATURE.get(platform, 11.0),
            'class_sigma_multiplier': class_sigma_mult,
            'straight_sigma_boost': 1.4 if is_straight else 1.0,
            'n_phases': len(PHASE_FRACTIONS_STRAIGHT if is_straight else PHASE_FRACTIONS),
            'race_day_form_sigma': RACE_DAY_FORM_SIGMA,
        },
        'power_index_breakdown': pi_breakdown,
        'win_probabilities': win_probs,
        'place_probabilities': place_probs,
        'results': results_compat,  # Backward compatible
        'mc_raw': mc_raw,  # Raw MC sim results for pace analysis
        'pace_feedback': pace_fb,  # V2.1: pace adjustments applied
        'top4_matrix': top4_matrix,
        'top6_matrix': top6_matrix,  # V2.1: expanded selection
        'concordance': concordance,
    }


def process_directory(dirpath: str, platform: str):
    """Process all Logic.json files in a directory."""
    p = Path(dirpath)
    logic_files = sorted(p.glob('Race_*_Logic.json'))

    if not logic_files:
        print(f"No Logic.json files found in {dirpath}")
        return

    print(f"Found {len(logic_files)} races in {p.name}")
    print(f"Platform: {platform.upper()}")
    print(f"Simulations per race: {N_SIMULATIONS:,}")
    print("=" * 60)

    for lf in logic_files:
        race_num = re.search(r'Race_(\d+)', lf.name)
        rn = race_num.group(1) if race_num else '?'
        print(f"\n--- Race {rn} ---")

        try:
            result = process_race(str(lf), platform)

            # Write MC_Results.json
            out_path = lf.parent / lf.name.replace('_Logic.json', '_MC_Results.json')
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            # Print summary
            conc = result['concordance']
            pace_fb = result.get('pace_feedback', {})
            print(f"  Horses: {result['horses_count']}")
            print(f"  MC Top4: {result['top4_matrix']}")
            print(f"  MC Top6: {result.get('top6_matrix', [])}")
            print(f"  Logic Top4: {conc['logic_top4']}")
            print(f"  Concordance: {conc['overlap']}/4")
            if pace_fb:
                print(f"  Pace feedback: {pace_fb}")
            if conc['divergence_alerts']:
                for alert in conc['divergence_alerts']:
                    print(f"  ⚠️  {alert}")

            # Win% summary
            sorted_r = sorted(result['results'].items(), key=lambda x: x[1]['win_pct'], reverse=True)
            for name, stats in sorted_r[:5]:
                pi = result['power_index_breakdown'].get(name, {})
                pfb = pace_fb.get(name, '')
                pfb_str = f' pf={pfb:+.1f}' if pfb else ''
                print(f"  {name:<22} PI={pi.get('final_pi', '?'):<5} Win={stats['win_pct']:>5.1f}%  σ={pi.get('sigma', '?')}{pfb_str}")

            print(f"  ✅ Written: {out_path.name}")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Monte Carlo Race Simulator v2.1 (Dual-Track + Enhanced)')
    parser.add_argument('--input', '-i', help='Single Logic.json file')
    parser.add_argument('--dir', '-d', help='Directory containing Logic.json files')
    parser.add_argument('--platform', '-p', choices=['au', 'hkjc'], default='au',
                        help='Platform: au or hkjc')
    parser.add_argument('--sims', '-n', type=int, default=N_SIMULATIONS,
                        help=f'Number of simulations (default: {N_SIMULATIONS})')

    args = parser.parse_args()

    n_sims = args.sims if args.sims else N_SIMULATIONS

    if args.dir:
        process_directory(args.dir, args.platform)
    elif args.input:
        result = process_race(args.input, args.platform)
        out_name = Path(args.input).name.replace('_Logic.json', '_MC_Results.json')
        out_path = Path(args.input).parent / out_name
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Written: {out_path}")
        print(json.dumps(result['concordance'], indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
