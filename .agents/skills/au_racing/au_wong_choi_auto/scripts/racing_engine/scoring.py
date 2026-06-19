#!/usr/bin/env python3
"""AU Wong Choi Auto scoring primitives."""
from __future__ import annotations
import re

FEATURE_KEYS = ("form_score","trial_score","sectional_score","pace_map_score","jockey_score","trainer_score","jockey_horse_fit_score","class_score","rating_score","weight_score","distance_score","track_score","formline_score","consistency_score","health_score","confidence_score")

MATRIX_WEIGHTS = {"stability":0.330,"sectional":0.105,"race_shape":0.234,"jockey_trainer":0.214,"class_weight":0.050,"track":0.067,"form_line":0.000}
_WEIGHT_FLOOR = {"stability":0.10}
_WEIGHT_CEILING = {"class_weight":0.15,"track":0.17}
SOFT_RACE_SHAPE_SCALE = 1.0

CLASS_MICRO_WEIGHTS = {
    "career0_base": 57.7,
    "career0_2yo_bonus": 0.84,
    "career5_placed_bonus": 2.31,
    "career5_unplaced_pen": 0.82,
    "career15_maiden_pen": -6.79,
    "career15_unplaced_pen": -1.4,
    "career15_placed_bonus": 5.42,
    "class_drop_bonus": 2.1,
    "class_up_pen": 0.0,
    "metro_prov_pen": -5.48,
    "rt_high_bonus": 3.58,
    "rt_low_pen": -3.26
}

CONSISTENCY_MICRO_WEIGHTS = {
    "career0_base": 52.4,
    "base": 64.6,
    "recent_place_bonus": 7.86,
    "recent_poor_pen": -2.7,
    "forgiveness_bonus": 1.49,
    "run_style_bonus": 5.2,
    "pi_stable_bonus": 5.71,
    "repeat_bonus": 2.7,
    "no_repeat_pen": -2.0
}

SECTIONAL_MICRO_WEIGHTS = {
    "base": 35.8,
    "trial_extreme_bonus": 0.0,
    "trial_excellent_bonus": 0.0,
    "trial_pass_bonus": 3.97,
    "pi_extreme_bonus": 28.1,
    "pi_excellent_bonus": 20.0,
    "pi_pass_bonus": 3.64,
    "l600_extreme_bonus": 15.07,
    "l600_excellent_bonus": 3.64,
    "peak_pi_bonus": 1.1,
    "trend_up_bonus": 1.93,
    "trend_down_pen": -5.56,
    "realization_bonus": 6.64,
    "forgiveness_bonus": 9.89
}

TRACK_MICRO_WEIGHTS = {
    "base": 62.9,
    "same_track_place_bonus": 5.0,
    "same_track_win_bonus": 2.4,
    "same_track_poor_pen1": -8.81,
    "same_track_poor_pen2": -0.81,
    "going_place_bonus": 0.8,
    "going_win_bonus": 3.77,
    "going_poor_pen1_wet": -4.75,
    "going_poor_pen1_dry": -3.46,
    "going_poor_pen2_wet": -4.14,
    "going_poor_pen2_dry": -7.08,
    "wet_unverified_pen": -6.4,
    "heavy_win_bonus": 3.87,
    "heavy_place_bonus": -2.88,
    "heavy_poor_pen": -5.94,
    "wet_bloodline_bonus": 4.18
}

FORMLINE_MICRO_WEIGHTS = {
    "elite_base": 82.5,
    "strong_base": 66.4,
    "med_strong_base": 61.8,
    "med_base": 68.3,
    "med_weak_base": 56.6,
    "weak_base": 53.6,
    "neutral_base": 54.9,
    "unknown_base": 64.8,
    "future_win_bonus": 5.9,
    "strong_opp_bonus": 3.3,
    "followup_higher_bonus": 2.4,
    "followup_same_bonus": 1.2,
    "followup_lower_pen": -3.6,
    "headwinner_bonus": 1.8
}

PACE_MICRO_WEIGHTS = {
    "base": 55.7,
    "modifier_cap_max": 4.05,
    "modifier_cap_min": -9.43,
    "modifier_multiplier": 1.1,
    "fallback_wide_pen": 0.0,
    "fallback_inside_bonus": 1.93
}
JOCKEY_MICRO_WEIGHTS = {
    "elite_bonus": 9.0,
    "solid_bonus": 5.77,
    "apprentice_fresh_bonus": -0.14
}

TRAINER_MICRO_WEIGHTS = {
    "elite_bonus": 10.59,
    "waller_debut_bonus": 5.52,
    "track_high_vol_high_place_bonus": 10.96,
    "track_med_vol_high_place_bonus": 4.29,
    "track_med_vol_med_place_bonus": 1.44,
    "track_low_place_pen": -0.52
}

FIT_MICRO_WEIGHTS = {
    "debut_top_trainer_bonus": 0.0,
    "young_top_jt_bonus": 0.0,
    "trial_ok_bonus": 3.38,
    "trial_ok_top_jt_bonus": 1.0,
    "current_formal_cap": 4.05,
    "current_formal_mult": 0.31,
    "current_basic_fit_bonus": 0.65,
    "current_high_fit_bonus": 1.47,
    "current_trial_cap": 2.57,
    "current_trial_mult": 3.8,
    "best_formal_cap": 4.23,
    "best_formal_mult": -0.06,
    "jockey_upgrade_vs_best_bonus": 1.06,
    "jockey_downgrade_vs_best_pen": 0.0,
    "latest_upgrade_bonus": 0.0,
    "latest_downgrade_pen": -4.11,
    "leave_proven_jockey_pen": -2.98,
    "combo_high_vol_high_place_bonus": 7.27,
    "combo_med_place_bonus": 1.53,
    "combo_low_place_pen": -1.0,
    "combo_win_bonus": 0.49,
    "combo_no_ride_good_place_bonus": 1.97,
    "trainer_track_top_jockey_bonus": 1.76,
    "signal_best_jockey_bonus": 3.85,
    "signal_upgrade_bonus": 9.95,
    "signal_downgrade_pen": -3.44
}

def get_dynamic_matrix_weights(race_context):
    weights = dict(MATRIX_WEIGHTS)
    field_summary = race_context.get("field_summary",{})
    field_count = int(field_summary.get("count",0))
    going = str(race_context.get("going","") or "").lower()
    race_class = str(race_context.get("race_class","") or "").lower()
    if field_count >= 13:
        weights["race_shape"] -= 0.02; weights["sectional"] -= 0.01; weights["stability"] += 0.02; weights["form_line"] += 0.01
    elif field_count >= 9:
        weights["race_shape"] -= 0.01; weights["sectional"] -= 0.005; weights["stability"] += 0.01; weights["form_line"] += 0.005
    elif field_count > 0 and field_count <= 8:
        weights["race_shape"] += 0.04; weights["sectional"] += 0.03; weights["stability"] -= 0.02; weights["form_line"] -= 0.02

    if "soft" in going or "heavy" in going:
        weights["race_shape"] -= 0.005; weights["track"] += 0.01; weights["stability"] -= 0.005
    elif "good" in going or "firm" in going:
        weights["sectional"] += 0.05; weights["track"] -= 0.02

    if "bm" in race_class:
        bm_tokens = tuple(f"bm{n}" for n in range(50,100))
        if any(t in race_class for t in ("bm58", "bm64", "bm68", "bm70")):
            weights["stability"] += 0.03
            weights["jockey_trainer"] += 0.02
            weights["class_weight"] -= 0.02
        elif any(t in race_class for t in bm_tokens): 
            weights["class_weight"] += 0.005
    for key in weights:
        weights[key] = max(0.0, weights[key])
    total = sum(weights.values())
    if total > 0:
        for key in weights: weights[key] = weights[key] / total
    for key, floor_val in _WEIGHT_FLOOR.items():
        if weights[key] < floor_val: weights[key] = floor_val
    for key, ceil_val in _WEIGHT_CEILING.items():
        if weights[key] > ceil_val: weights[key] = ceil_val
    for key in weights: weights[key] = round(weights[key],4)
    return weights

def soft_race_shape_modifier(race_context, matrix_scores):
    context = race_context or {}
    going = f"{context.get('going', '')} {context.get('condition', '')}".lower()
    if "soft" not in going:
        return 0.0
    race_shape = clip_score((matrix_scores or {}).get("race_shape", 60.0))
    return round(((race_shape - 60.0) / 10.0) * SOFT_RACE_SHAPE_SCALE, 4)

PLACE_TIGHTENING_FEATURE_WEIGHTS = {"form_score":0.103,"trial_score":0.179,"trainer_score":0.204,"jockey_horse_fit_score":0.170,"consistency_score":0.143,"distance_score":-0.033,"confidence_score":0.027,"weight_score":-0.141,"sectional_score":0.05}
PLACE_TIGHTENING_SCALE = 1.4
PLACE_TIGHTENING_MAX_ABS_BONUS = 4.0
GRADE_THRESHOLDS = ((96,"S+"),(92,"S"),(88,"S-"),(84,"A+"),(80,"A"),(76,"A-"),(72,"B+"),(68,"B"),(64,"B-"),(60,"C+"),(56,"C"),(52,"C-"),(48,"D"),(0,"E"))

def clip_score(value, default=60.0):
    try: score = float(value)
    except (TypeError, ValueError): score = default
    return max(0.0, min(100.0, score))

def compute_grade(ability_score):
    score = clip_score(ability_score,0)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold: return grade
    return "E"

def score_band(score):
    score = clip_score(score)
    if score >= 85: return "✅✅"
    if score >= 70: return "✅"
    if score >= 55: return "➖"
    if score >= 40: return "❌"
    return "❌❌"

def parse_float(value):
    if isinstance(value,(int,float)): return float(value)
    if not value: return None
    match = re.search(r"-?\d+(?:\.\d+)?",str(value))
    return float(match.group(0)) if match else None

def parse_numbers(text):
    if not text: return []
    return [int(m.group(0)) for m in re.finditer(r"\d+",str(text))]

def parse_record_line(line):
    if not line: return {"starts":0,"wins":0,"seconds":0,"thirds":0,"places":0}
    nums = parse_numbers(str(line))
    if len(nums) >= 4:
        wins = nums[1]
        seconds = nums[2]
        thirds = nums[3]
        return {
            "starts": nums[0],
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "places": wins + seconds + thirds,
        }
    if len(nums) >= 3:
        wins = nums[1]
        places = nums[1] + nums[2]
        return {"starts":nums[0],"wins":wins,"seconds":nums[2],"thirds":0,"places":places}
    return {"starts":0,"wins":0,"seconds":0,"thirds":0,"places":0}

def parse_recent_finishes(text):
    if not text: return None
    nums = parse_numbers(str(text))
    if nums: return [n for n in nums if 1 <= n <= 24]
    return None

def safe_ratio(numerator, denominator):
    if not denominator: return 0.0
    return min(1.0, max(0.0, numerator / denominator))
