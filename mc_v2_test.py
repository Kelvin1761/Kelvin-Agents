#!/usr/bin/env python3
"""
MC V2 A/B Test: Compare current engine vs proposed fixes.
Tests on ShaTin Race 5 data (14 horses, extreme case).
"""
import numpy as np
from scipy.stats import skewnorm
import math
import json

# Real PI data from ShaTin Race 5
HORSES_V1 = [
    {'name': '超開心',   'pi': 77.2, 'sigma': 8.0, 'style': 'A/B', 'barrier': 3},
    {'name': '睿智多寶', 'pi': 75.8, 'sigma': 8.0, 'style': 'A',   'barrier': 1},
    {'name': '君達得',   'pi': 73.7, 'sigma': 8.0, 'style': 'B',   'barrier': 5},
    {'name': '萬事勝利', 'pi': 63.5, 'sigma': 8.0, 'style': 'C',   'barrier': 7},
    {'name': '勤德天下', 'pi': 61.7, 'sigma': 8.0, 'style': 'C',   'barrier': 10},
    {'name': '家傳之寶', 'pi': 58.1, 'sigma': 8.0, 'style': 'A',   'barrier': 2},
    {'name': '江南勇士', 'pi': 54.6, 'sigma': 8.0, 'style': 'C',   'barrier': 8},
    {'name': '瑞祺威楓', 'pi': 53.5, 'sigma': 8.0, 'style': 'B',   'barrier': 12},
    {'name': '頌星',     'pi': 51.8, 'sigma': 8.0, 'style': 'C',   'barrier': 9},
    {'name': '挺秀弘利', 'pi': 49.8, 'sigma': 8.0, 'style': 'A',   'barrier': 6},
    {'name': '風捲殘雲', 'pi': 48.1, 'sigma': 8.0, 'style': 'B',   'barrier': 11},
    {'name': '飛躍星伴', 'pi': 45.9, 'sigma': 8.0, 'style': 'C',   'barrier': 14},
    {'name': '鴻圖大展', 'pi': 45.4, 'sigma': 8.0, 'style': 'C',   'barrier': 4},
    {'name': '熒光',     'pi': 44.0, 'sigma': 8.0, 'style': 'A',   'barrier': 13},
]

STYLE_PROFILES = {
    'A':   (0.95, 0.85, 0.80, 0.85),
    'B':   (0.70, 0.75, 0.85, 1.00),
    'C':   (0.85, 0.85, 0.85, 0.90),
    'A/B': (0.82, 0.80, 0.83, 0.93),
    'B/C': (0.75, 0.80, 0.85, 0.95),
    'A/C': (0.88, 0.85, 0.83, 0.88),
}

N_SIMS = 10000


def run_sim_v1(horses, n_sims, seed=42):
    """Current V1 engine: PI * effort * energy + skewnorm noise."""
    rng = np.random.default_rng(seed)
    counters = {h['name']: {'wins': 0, 'top3': 0, 'top4': 0, 'rank_sum': 0} for h in horses}

    for _ in range(n_sims):
        scores = {}
        for h in horses:
            profile = STYLE_PROFILES.get(h['style'], STYLE_PROFILES['C'])
            energy = 100.0
            cum_speed = 0.0
            for phase_idx in range(5):
                effort = profile[min(phase_idx, 3)]
                energy_factor = 0.6 + 0.4 * (energy / 100.0)
                base_speed = h['pi'] * effort * energy_factor
                noise = skewnorm.rvs(a=-3, loc=0, scale=h['sigma'] * 1.8, random_state=rng)
                cum_speed += base_speed + noise
                energy -= effort * 6.0
                energy = max(0, energy)
                if energy < 15:
                    cum_speed *= 0.997  # minor fatigue
            scores[h['name']] = cum_speed

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        for rank, (name, _) in enumerate(ranked):
            c = counters[name]
            c['rank_sum'] += rank + 1
            if rank == 0: c['wins'] += 1
            if rank < 3: c['top3'] += 1
            if rank < 4: c['top4'] += 1

    return {name: {
        'win_pct': round(c['wins'] / n_sims * 100, 1),
        'top3_pct': round(c['top3'] / n_sims * 100, 1),
        'top4_pct': round(c['top4'] / n_sims * 100, 1),
        'avg_rank': round(c['rank_sum'] / n_sims, 1),
    } for name, c in counters.items()}


def run_sim_v2_additive(horses, n_sims, seed=42):
    """V2 Additive: PI + effort_bonus + energy_bonus + normal noise."""
    rng = np.random.default_rng(seed)
    counters = {h['name']: {'wins': 0, 'top3': 0, 'top4': 0, 'rank_sum': 0} for h in horses}

    for _ in range(n_sims):
        scores = {}
        for h in horses:
            profile = STYLE_PROFILES.get(h['style'], STYLE_PROFILES['C'])
            energy = 100.0
            cum_speed = 0.0

            # Race-day form (random shift per horse per race)
            day_form = rng.normal(0, 3.5)

            for phase_idx in range(3):  # 3 phases instead of 5
                effort = profile[min(phase_idx, 3)]
                effort_bonus = (effort - 0.85) * 12.0  # ±1.8 range
                energy_bonus = (energy - 50) * 0.04     # ±2.0 range

                noise = rng.normal(0, h['sigma'])

                phase_speed = h['pi'] + day_form + effort_bonus + energy_bonus + noise
                cum_speed += phase_speed

                energy -= effort * 8.0
                energy = max(0, energy)
                if energy < 15:
                    cum_speed -= 3.0

            scores[h['name']] = cum_speed

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        for rank, (name, _) in enumerate(ranked):
            c = counters[name]
            c['rank_sum'] += rank + 1
            if rank == 0: c['wins'] += 1
            if rank < 3: c['top3'] += 1
            if rank < 4: c['top4'] += 1

    return {name: {
        'win_pct': round(c['wins'] / n_sims * 100, 1),
        'top3_pct': round(c['top3'] / n_sims * 100, 1),
        'top4_pct': round(c['top4'] / n_sims * 100, 1),
        'avg_rank': round(c['rank_sum'] / n_sims, 1),
    } for name, c in counters.items()}


def softmax_approach(horses, temperature):
    """Industry standard: Softmax with temperature."""
    pis = np.array([h['pi'] for h in horses])
    scaled = pis / temperature
    exp_vals = np.exp(scaled - np.max(scaled))
    probs = exp_vals / np.sum(exp_vals) * 100
    return {h['name']: {'win_pct': round(p, 1)} for h, p in zip(horses, probs)}


def harville_place(win_probs):
    """Harville formula: derive top3 probability from win probabilities."""
    names = list(win_probs.keys())
    n = len(names)
    top3_probs = {name: 0.0 for name in names}

    for i, name_i in enumerate(names):
        pi = win_probs[name_i] / 100
        # P(i finishes top3) = sum over all permutations where i is in top3
        # Simplified: P(top3) ≈ 1 - product of (1 - p_conditional) for 3 slots
        # Harville approximation:
        top3_probs[name_i] = pi  # Wins = definitely top3

        # Add probability of finishing 2nd (given someone else wins)
        for j, name_j in enumerate(names):
            if j == i:
                continue
            pj = win_probs[name_j] / 100
            # P(j wins, i 2nd) = pj * pi / (1 - pj)
            if pj < 1.0:
                top3_probs[name_i] += pj * (pi / (1 - pj))

                # P(j wins, k 2nd, i 3rd)
                for k, name_k in enumerate(names):
                    if k == i or k == j:
                        continue
                    pk = win_probs[name_k] / 100
                    if (1 - pj) > 0 and (1 - pj - pk) > 0:
                        top3_probs[name_i] += pj * (pk / (1 - pj)) * (pi / (1 - pj - pk))

    return {name: round(min(p * 100, 99.9), 1) for name, p in top3_probs.items()}


def print_results(title, results, horses):
    """Print formatted results."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

    sorted_r = sorted(results.items(), key=lambda x: x[1]['win_pct'], reverse=True)
    for name, stats in sorted_r:
        pi = next(h['pi'] for h in horses if h['name'] == name)
        t3 = stats.get('top3_pct', '-')
        t4 = stats.get('top4_pct', '-')
        ar = stats.get('avg_rank', '-')
        print(f"  {name:12s}  PI={pi:5.1f}  Win={stats['win_pct']:5.1f}%  "
              f"Top3={t3}  Top4={t4}  AvgRank={ar}")

    win_pcts = [s['win_pct'] for s in results.values()]
    top1 = max(win_pcts)
    sorted_wins = sorted(win_pcts, reverse=True)
    top4 = sum(sorted_wins[:4])
    bot_half = sum(sorted_wins[7:])
    last = min(win_pcts)
    p_norm = [w / 100 for w in win_pcts if w > 0]
    entropy = -sum(p * math.log2(p) for p in p_norm if p > 0) if p_norm else 0
    max_ent = math.log2(len(horses))
    norm_ent = entropy / max_ent if max_ent > 0 else 0

    print(f"\n  Summary: Top1={top1:.1f}% Top4={top4:.1f}% Bot50%={bot_half:.1f}% "
          f"Last={last:.1f}% Entropy={norm_ent:.3f}")
    print(f"  Target:  Top1=25-35% Top4=55-65% Bot50%=15-25% Last=1-3% Entropy=0.80+")


# ============================================================
# Run all approaches
# ============================================================

print("ShaTin Race 5 — 14 horses, 1600m")
print(f"PI Range: {min(h['pi'] for h in HORSES_V1):.1f} - {max(h['pi'] for h in HORSES_V1):.1f} "
      f"(span={max(h['pi'] for h in HORSES_V1) - min(h['pi'] for h in HORSES_V1):.1f})")

# V1 Current
r1 = run_sim_v1(HORSES_V1, N_SIMS)
print_results("V1 CURRENT (PI*effort + skewnorm, sigma=8, 5 phases)", r1, HORSES_V1)

# V2a: Additive model, same PIs, sigma=12, 3 phases
horses_v2a = [dict(h, sigma=12.0) for h in HORSES_V1]
r2a = run_sim_v2_additive(horses_v2a, N_SIMS)
print_results("V2a ADDITIVE (PI+noise, sigma=12, 3 phases, day_form)", r2a, HORSES_V1)

# V2b: Compressed PIs (50-64 range) + additive + sigma=12
old_min, old_max = 44.0, 77.2
new_min, new_max = 50, 64
horses_v2b = []
for h in HORSES_V1:
    new_pi = (h['pi'] - old_min) / (old_max - old_min) * (new_max - new_min) + new_min
    horses_v2b.append(dict(h, pi=round(new_pi, 1), sigma=12.0))
r2b = run_sim_v2_additive(horses_v2b, N_SIMS)
print_results("V2b COMPRESSED PI (50-64) + ADDITIVE + sigma=12", r2b, horses_v2b)

# V2c: Softmax T=10 (industry standard)
r_soft10 = softmax_approach(HORSES_V1, temperature=10.0)
print_results("SOFTMAX T=10 (Industry Bolton-Chapman)", r_soft10, HORSES_V1)

# V2d: Softmax T=12
r_soft12 = softmax_approach(HORSES_V1, temperature=12.0)
print_results("SOFTMAX T=12", r_soft12, HORSES_V1)

# V2e: HYBRID — MC sim for ranking dynamics + Softmax for final probs
# Run MC sim with compressed PI, then apply softmax to the raw win counts
print(f"\n{'='*70}")
print("  V2e HYBRID: MC simulation (compressed) → Softmax post-process")
print(f"{'='*70}")
# Use V2b raw win counts as "utility scores", then softmax
raw_wins = {name: stats['win_pct'] for name, stats in r2b.items()}
# Convert to softmax with T=1.2 (mild smoothing)
win_vals = np.array(list(raw_wins.values()))
for T in [0.8, 1.0, 1.2, 1.5, 2.0]:
    scaled = win_vals / T
    exp_vals = np.exp(scaled - np.max(scaled))
    probs = exp_vals / np.sum(exp_vals) * 100
    sorted_p = sorted(probs, reverse=True)
    top1 = sorted_p[0]
    top4 = sum(sorted_p[:4])
    bot_half = sum(sorted_p[7:])
    last = sorted_p[-1]
    p_norm = [w / 100 for w in probs if w > 0]
    entropy = -sum(p * math.log2(p) for p in p_norm if p > 0) if p_norm else 0
    norm_ent = entropy / math.log2(14)
    print(f"  T={T:.1f}  Top1={top1:.1f}% Top4={top4:.1f}% Bot50%={bot_half:.1f}% "
          f"Last={last:.1f}% Entropy={norm_ent:.3f}")
