#!/usr/bin/env python3
"""
racing_engine/scoring.py — Core Scoring Framework
"""

from abc import ABC, abstractmethod
import re


FEATURE_KEYS = (
    "form_score",
    "speed_score",
    "class_score",
    "jockey_score",
    "trainer_score",
    "draw_score",
    "distance_score",
    "track_going_score",
    "weight_score",
    "consistency_score",
    "risk_score",
    "confidence_score",
)

MATRIX_WEIGHTS = {
    "sectional": 0.1849,
    "trainer_signal": 0.2209,
    "stability": 0.0919,
    "race_shape": 0.2560,
    "class_advantage": 0.1335,
    "horse_health": 0.0378,
    "form_line": 0.0749,
}

DEBUT_MATRIX_WEIGHTS = {
    "trainer_signal": 0.30,
    "horse_health": 0.30,
    "race_shape": 0.20,
    "stability": 0.15,
    "class_advantage": 0.05,
}

RACE_SHAPE_CONTEXT_WEIGHTS = {
    "sha_tin_draw": 0.55,
    "sha_tin_draw_position_fit": 0.25,
    "sha_tin_trip_consumption": 0.20,
    "non_sha_tin_delta_floor": -10.0,
    "non_sha_tin_delta_cap": 7.0,
}

RACE_SHAPE_FIT_WEIGHTS = {
    "base": 60.0,
    "match_bonus": 12.0,
    "mismatch_pen": -14.0,
    "active_slot_pen": -6.0,
    "pi_up_bonus": 5.0,
    "pi_micro_up_bonus": 2.0,
    "pi_down_pen": -5.0,
    "pi_micro_down_pen": -2.0,
}

RACE_SHAPE_TRIP_CONSUMPTION_SCORES = {
    "低消耗": 70.0,
    "中低": 66.0,
    "中等": 60.0,
    "高": 52.0,
    "極高": 46.0,
}

RACE_SHAPE_CONTEXT_DELTA_WEIGHTS = {
    "match_bonus": 4.0,
    "mismatch_pen": -8.0,
    "active_slot_pen": -3.0,
    "pi_up_bonus": 2.0,
    "pi_down_pen": -2.0,
    "high_conf_bonus": 0.8,
    "low_conf_pen": -0.8,
    "recent_low_consumption_bonus": 1.0,
    "recent_high_consumption_pen": -1.2,
    "recent_extreme_consumption_pen": -2.0,
}

GRADE_THRESHOLDS = (
    (96, "S+"),
    (92, "S"),
    (88, "S-"),
    (84, "A+"),
    (80, "A"),
    (76, "A-"),
    (72, "B+"),
    (68, "B"),
    (64, "B-"),
    (60, "C+"),
    (56, "C"),
    (52, "C-"),
    (48, "D"),
    (0, "E"),
)

CLASS_MICRO_WEIGHTS = {
    "established_bonus": 4.0,
    "starts_20_bonus": 5.12,
    "starts_8_pen": -2.0,
    "season_place_3_bonus": 4.39,
    "season_place_0_pen": -4.0,
    "same_dist_place_bonus": 4.0,
    "same_dist_unplaced_pen": -1.55
}

DISTANCE_MICRO_WEIGHTS = {
    "similar_place_base": 62.0,
    "debut_base": 58.0,
    "unproven_base": 56.0,
    "direct_match_place_base": 72.0,
    "direct_match_small_sample_base": 66.0,
    "same_dist_unplaced_base": 54.0,
    "neutral_base": 60.0
}

TRACK_MICRO_WEIGHTS = {
    "favorable_base": 66.0,
    "unfavorable_base": 58.0,
    "neutral_base": 60.0
}

WEIGHT_MICRO_WEIGHTS = {
    "base": 64.0,
    "light_weight_base": 70.0,
    "heavy_weight_base": 54.0,
    "trend_lighter_bonus": 4.0,
    "trend_heavier_pen": -4.0
}

CONSISTENCY_MICRO_WEIGHTS = {
    "debut_base": 58.0,
    "debut_prep_mult": 0.35,
    "base": 58.0,
    "place_mult": 7.0,
    "poor_mult": 5.0,
    "good_form_base": 66.0,
    "neutral_base": 60.0
}

RISK_MICRO_WEIGHTS = {
    "base": 68.0,
    "medical_unknown_pen": -6.59,
    "debut_pen": -5.0,
    "draw_pressure_pen": -5.0,
    "distance_unproven_pen": -3.39
}

CONFIDENCE_MICRO_WEIGHTS = {
    "base": 48.0,
    "present_mult": 6.0,
    "jockey_combo_bonus": 5.0,
    "debut_pen": -2.77,
    "high_risk_pen": -5.0
}

DRAW_MICRO_WEIGHTS = {
    "straight_draw_8_plus": 77.45,
    "straight_draw_5_7": 65.0,
    "straight_draw_1_4": 50.0,
    "turn_draw_1_4": 75.0,
    "turn_draw_5_8": 65.0,
    "turn_draw_9_plus": 49.06,
    "stats_base_add": 40.35
}

JOCKEY_MICRO_WEIGHTS = {
    "overseas_g1_base": 85.0,
    "overseas_base": 70.0
}

SPEED_MICRO_WEIGHTS = {
    "base": 60.0,
    "l400_22_4_bonus": 8.62,
    "l400_23_0_bonus": 4.55,
    "l400_23_6_bonus": 3.03,
    "l400_24_0_pen": -0.73,
    "l400_24_6_pen": -5.64,
    "finish_competitive_bonus": 6.52,
    "finish_faster_bonus": 6.0,
    "finish_slightly_faster_bonus": 4.0,
    "finish_avg_bonus": 1.42,
    "finish_slow_pen": -4.0,
    "finish_far_behind_pen": -8.0,
    "energy_up_bonus": 1.96,
    "energy_steady_bonus": 2.78,
    "energy_down_pen": -2.74,
    "l400_trend_up_bonus": 3.0,
    "l400_trend_steady_bonus": 0.58,
    "l400_trend_fluctuate_pen": -1.0,
    "l400_trend_decline_pen": -4.0,
    "engine_progressive_bonus": 3.03,
    "engine_steady_bonus": 1.5,
    "engine_mixed_low_conf_pen": -2.0,
    "engine_fast_slow_pen": -2.5,
    "engine_low_conf_pen": 0.0,
    "dist_match_bonus": 1.5,
    "dist_unproven_pen": -1.5,
    "overseas_g1_bonus": 6.0,
    "overseas_g2_bonus": 4.0,
    "overseas_g3_bonus": 1.63,
    "overseas_place_bonus": 1.0
}

TRAINER_MICRO_WEIGHTS = {
    "overseas_g1_base": 85.0,
    "overseas_g23_base": 75.0,
    "overseas_base": 70.0
}

FORM_MICRO_WEIGHTS = {
    "rank_1": 100.0,
    "rank_2": 85.0,
    "rank_3": 75.0,
    "rank_4_5": 60.0,
    "rank_other": 40.0
}

TRAINER_SIGNAL_CONTEXT_WEIGHTS = {
    "horse_history_strong": 4.0,
    "horse_history_supportive": 2.0,
    "horse_history_zero_place": -4.0,
    "horse_history_weak": -2.0,
    "combo_elite": 4.0,
    "combo_positive": 2.0,
    "combo_negative": -2.0,
    "jockey_distance_elite": 3.0,
    "jockey_distance_positive": 1.5,
    "jockey_distance_negative": -2.0,
    "trainer_distance_elite": 2.0,
    "trainer_distance_positive": 1.0,
    "trainer_distance_negative": -1.5,
    "jockey_change_negative": -1.5,
    "combo_jockey_share": 0.55,
    "combo_trainer_share": 0.45,
}

HORSE_HEALTH_CONTEXT_WEIGHTS = {
    "base": 68.0,
    "medical_clear_bonus": 2.0,
    "medical_issue_pen": -12.0,
    "medical_recovery_bonus": 6.0,
    "medical_unknown_pen": -5.0,
    "days_le_7_stable_bonus": 2.0,
    "days_le_7_unstable_pen": -1.0,
    "days_le_21_bonus": 2.0,
    "days_le_45_bonus": 1.0,
    "days_gt_75_pen": -3.0,
    "weight_micro_bonus": 1.0,
    "weight_sharp_change_pen": -5.0,
    "weight_drop_pen": -3.0,
    "weight_gain_pen": -2.0,
    "span_le_12_bonus": 3.0,
    "span_le_18_bonus": 1.5,
    "span_le_32_pen": -2.0,
    "span_gt_32_pen": -4.0,
    # 晨操訊號已統一由 stability 嘅 trackwork_trend_score 獨家計分
    # （2026-07-08 backtest 確認：health/risk 嘅 trackwork 罰分全部移除後零倒退）。
}




class BaseScorer(ABC):
    def __init__(self, horse_data, race_context):
        self.horse_data = horse_data
        self.race_context = race_context
        self.score = 60.0  # Neutral base
        self.reason = ""

    @abstractmethod
    def compute(self):
        """Must return (score, reason)"""
        pass


def clip_score(value, default=60.0):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def compute_grade(ability_score):
    score = clip_score(ability_score, 0)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "E"


def parse_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None




def parse_record(value):
    if not value:
        return None
    text = str(value)
    match = re.search(r"\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
    if not match:
        return None
    wins, seconds, thirds, starts = (int(part) for part in match.groups())
    return {
        "wins": wins,
        "seconds": seconds,
        "thirds": thirds,
        "starts": starts,
        "places": wins + seconds + thirds,
    }




def score_band(score):
    score = clip_score(score)
    if score >= 85:
        return "✅✅"
    if score >= 70:
        return "✅"
    if score >= 55:
        return "➖"
    if score >= 40:
        return "❌"
    return "❌❌"

# Finish-time deviation TREND (vs HKJC standard) applied to the sectional matrix
# dim. ML-validated add-on signal: +/-5 lifted min/single/top3 on the held-out
# backtest split with no metric regressing (stable across magnitudes 3-6).
FINISH_TREND_MICRO_WEIGHTS = {
    "improving": 5.0,
    "declining": -5.0,
}

TRACKWORK_MICRO_WEIGHTS = {
    # 1. LLM 綜合文字指標 (Text-based trend)
    "rebound_base": 66.0,    # 翻案復刻
    "improving_base": 70.0,  # 加強
    "slowing_base": 46.24,   # 放緩 (ML Optimized: Harsher penalty)
    "neutral_base": 60.0,    # 中性
    
    # 2. 真實操練次數指標 (Raw exercise numerical multipliers)
    "gallop_weight": 0.5,    # 每課快操加分
    "trial_weight": 1.0,     # 每課大閘加分
    "trotting_weight": 0.1,  # 每課踱步加分
    "swimming_weight": 0.05, # 每課游水加分
    "activity_cap": 8.0,     # 活躍度加分上限 (防操過籠)
    "activity_floor": -4.0   # 活躍度扣分下限
}
