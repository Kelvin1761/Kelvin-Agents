#!/usr/bin/env python3
"""
racing_engine/scoring.py — Core Scoring Framework
"""

from abc import ABC, abstractmethod
import re


# Bump whenever a production matrix/formula change is intentionally promoted.
# Persisted with every scored race so forward results can be attributed to the
# exact model that made the pre-race prediction.
SCORING_CONTRACT_VERSION = "HKJC_7D_CONTRACT_2026_08_13_CURRENT_MATRIX"


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

# 2026-07-10 場地分全移除後重新歸一：段速維度只剩純速度分，維度權重由 0.1849
# 下調至 0.65×0.1849（保留原速度影響力），其餘維度按比例放大令總和＝1。
# 排名等效於「段速=速度×0.65 + 場地60×0.35」舊結構（場地嗰 0.35 只乘 constant，
# 對排名零貢獻）。pit_backtest：gold/min/champ 不變、single/t3c 微升。
MATRIX_WEIGHTS = {
    "sectional": 0.1285,
    "trainer_signal": 0.2362,
    "stability": 0.0983,
    "race_shape": 0.2737,
    "class_advantage": 0.1428,
    "horse_health": 0.0404,
    "form_line": 0.0801,
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

# ── 顯示尺（DISPLAY SCALE）──────────────────────────────────────────────────
# 加權總分係七個維度嘅**加權平均**，所以永遠困喺各維度自己嘅範圍之內。實測
# 3,438 個 runner（27 個場次，2026-04-12→2026-09-06）：
#     min 49.99 | p10 57.39 | 中位 63.16 | p90 68.85 | max 76.59 | SD 4.393
# 即係 `GRADE_THRESHOLDS` 由 A(80) 一路到 S+(96) 六級**數學上到唔到** —— 27 個
# 場次冇一匹馬過 80，只有四匹過 76。原因唔係「冇好馬」，係兩個最重維度自己封頂：
# `race_shape` 27.4% 權重但觀測上限 73.8，`class_advantage` 14.3% 但上限 65.0，
# 合共 41.7% 權重永久由每匹馬身上扣走約 12 分。
#
# 2026-09-06 沙田第3場：嘉應高昇（官方評分 142 vs 全場次高 109、近 6 仗
# 1-1-1-1-1-1 全部一／二級賽）攞 75.1 分＝全日 120 匹最高分，但印出嚟係
# 「B+ 中上游」。排名啱，個數字讀落唔啱。
#
# 呢個仿射變換**只係顯示尺**：slope > 0 而且全體同一條式，所以場內排序
# bit-identical（由 tests/test_display_scale.py 守住），亦唔加任何資訊。
#   anchor 64.0    = B-「中游，基本競爭力存在」，對正實測中位數
#   target_sd 10.0 = 對正 4 分一級嘅階梯（±2.5 SD ≈ 48–96 全幅）
# 原始加權總分保留喺 `ability_score_raw`，所以歷史數字、golden、SIP 門檻同
# backtest 全部仍然可以喺同一把尺上面比較。
DISPLAY_SCALE = {
    "centre": 63.16,       # 實測中位
    "observed_sd": 4.393,  # 實測 SD
    "target_sd": 10.0,     # 目標 SD（階梯設計值）
    "anchor": 64.0,        # 中位馬應該讀到嘅分
    "sample": 3438,
}
DISPLAY_SLOPE = DISPLAY_SCALE["target_sd"] / DISPLAY_SCALE["observed_sd"]


# ── 維度顯示尺（MATRIX_DISPLAY_*）────────────────────────────────────────────
# 七個維度嘅原始分**唔係同一把尺**，但報告一路將佢哋並排印成 0–100，再用同一套
# band 門檻（✅✅ 85 / ✅ 70 / ➖ 55 / ❌ 40）判定。實測 3,438 匹：
#
#   維度            權重    原始全距        SD     中位   永遠出唔到嘅 band
#   檔位與走位      27.4%  39.1–82.0  10.15    63.0   ✅✅
#   騎練訊號        23.6%  51.0–79.0   4.70    60.5   ✅✅ ❌❌
#   級數優勢        14.3%  52.8–76.6   5.46    64.8   ✅✅ ❌❌
#   段速表現        12.8%  33.6–85.5   8.98    60.0   （全部到得）
#   狀態與穩定性     9.8%  37.2–96.0  10.63    57.0   （全部到得）
#   賽績線           8.0%  58.0–96.0  12.26    80.0   ❌ ❌❌
#   馬匹健康         4.0%  55.2–73.7   3.47    66.9   ✅✅ ❌ ❌❌
#
# 即係：**七個維度有五個永遠出唔到 ✅✅**；`馬匹健康` 整個詞彙只有 {✅, ➖}
# ——連一匹真係有醫療問題嘅馬都印唔出 ❌；`賽績線` 反過來永遠出唔到 ❌。
# 而「60 = 中性／冇證據」呢個合約喺 leaf 層本身就唔成立（`馬匹健康` 中位 66.9、
# `賽績線` 中位 80.0），所以只做拉伸唔夠，要連中心一齊校返。
#
# 觸發呢次量度嘅個案（2026-09-06 R3 嘉應高昇）：
#   級數優勢 60.0 → 全體第 21 百分位（真係低，原因見 EXP-20260904-01）
#   馬匹健康 64.4 → 全體第 25 百分位（133 日長休 + 頂磅，唔係「中性」；
#                  修好距今日數之後係 61.3 = 第 8 百分位）
#   檔位與走位 69.4 → 全體第 **75** 百分位，但印住「➖ 中性」，差 0.6 分就 ✅
#
# 同 `DISPLAY_SCALE` 一樣，呢個只係**顯示尺**：`matrix_scores` 保持原始值餵綜合
# 分同所有分析工具，顯示值另存 `matrix_scores_display`，排名 bit-identical
# （由 tests/test_dimension_display_scale.py 守住）。
MATRIX_DISPLAY_CENTRES = {          # 實測中位 → 讀者睇到嘅 60
    "race_shape": 63.0,
    "trainer_signal": 60.5,
    "class_advantage": 64.8,
    "sectional": 60.0,
    "stability": 57.0,
    "form_line": 80.0,
    "horse_health": 66.9,
}
MATRIX_DISPLAY_GAINS = {            # 10.0 / 實測 SD → 七個維度同一個離散度
    "race_shape": 0.9852,
    "trainer_signal": 2.1261,
    "class_advantage": 1.8311,
    "sectional": 1.1137,
    "stability": 0.9406,
    "form_line": 0.8153,
    "horse_health": 2.8841,
}
MATRIX_DISPLAY_TARGET_SD = 10.0
MATRIX_DISPLAY_SAMPLE = 3438


def to_dimension_display(dimension, raw):
    """維度原始分 → 顯示分。單調遞增，所以唔改任何排序。"""
    value = parse_float(raw)
    if value is None:
        return None
    centre = MATRIX_DISPLAY_CENTRES.get(dimension)
    gain = MATRIX_DISPLAY_GAINS.get(dimension)
    if centre is None or gain is None:
        return clip_score(value)
    return clip_score(60.0 + gain * (value - centre))


def dimension_display_manifest():
    """JSON-safe，入 run contract —— 改咗個尺即係改咗每份報告嘅維度分同 band。"""
    return {
        "target_sd": MATRIX_DISPLAY_TARGET_SD,
        "sample": MATRIX_DISPLAY_SAMPLE,
        "dimensions": {
            key: {"centre": MATRIX_DISPLAY_CENTRES[key], "gain": MATRIX_DISPLAY_GAINS[key]}
            for key in sorted(MATRIX_DISPLAY_CENTRES)
        },
    }


def to_display_scale(raw):
    """原始加權總分 → 顯示分。單調遞增，所以唔改任何排序。"""
    value = parse_float(raw)
    if value is None:
        return None
    return clip_score(DISPLAY_SCALE["anchor"] + DISPLAY_SLOPE * (value - DISPLAY_SCALE["centre"]))


def from_display_scale(display):
    """顯示分 → 原始加權總分（`to_display_scale` 嘅逆函數，未 clip 之前）。"""
    value = parse_float(display)
    if value is None:
        return None
    return DISPLAY_SCALE["centre"] + (value - DISPLAY_SCALE["anchor"]) / DISPLAY_SLOPE


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

# 負磅方向：2026-09-04 調轉（EXP-20260904-09）。
#
# 舊版當「輕磅係好事」（≤120 磅 70 分、≥132 磅 54 分），量出嚟場內 AUC 0.4630 ——
# 即係比擲毫更差，方向係反嘅。原因係香港負磅唔係外生嘅負擔，而係讓磅官對馬匹
# 能力嘅**意見**：贏得多就加評分、加負磅。所以頂磅馬係全場公認最好嘅馬。
#
# 讓磅官抹得唔夠：實測斜率 0.389 分/kg vs 慣例 0.5 —— 即係加磅加得唔夠狠。
# 控制住模型自己嘅排名之後，頂磅馬喺模型排名 4+ 嗰批上名率 +8.7pp，
# 95% CI [+3.1, +14.3]（n=254 vs 2246）；排名 1-3 嗰批 −2.4pp、CI 跨零
# —— 即係呢個訊號嘅價值喺「執返模型自己睇低嘅好馬」，唔係加強首選。
#
# 提醒：`trend_lighter_bonus` / `trend_heavier_pen` 兩項讀嘅係 `weight_trend`，
# 嗰個係**排位體重**趨勢，唔係負磅。呢個係 leaf 內嘅類別混淆，未測過，
# 所以呢次唔動；要改就要獨立量度。
WEIGHT_MICRO_WEIGHTS = {
    "base": 64.0,
    "light_weight_base": 54.0,   # ≤120 磅：讓磅官睇低佢
    "heavy_weight_base": 70.0,   # ≥132 磅：讓磅官睇好佢，而且抹得唔夠
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
    """Parse an HKJC 「(a-b-c-d)」 record tuple.

    The four numbers are **(冠-亞-季-其餘)** — `inject_hkjc_fact_anchors.compute_stats`
    builds them with `pos = min(finish, 4)`, so slot 4 counts every finish worse
    than third. `starts` is therefore the SUM, never the fourth number.

    This used to read the tuple as `(wins, seconds, thirds, starts)`. A horse
    that is six-for-six at the distance reads 同程 (6-0-0-0) → the old code saw
    `starts=0`, so every "does this horse have a same-distance sample?" test
    failed for exactly the horses with a perfect same-distance record
    (2026-09-06 R3 嘉應高昇: 6 wins from 6 at 1200m → distance_score 66
    「樣本有限」 instead of 72, same_distance_signal 60 instead of 72).
    """
    if not value:
        return None
    text = str(value)
    match = re.search(r"\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
    if not match:
        return None
    wins, seconds, thirds, rest = (int(part) for part in match.groups())
    return {
        "wins": wins,
        "seconds": seconds,
        "thirds": thirds,
        "starts": wins + seconds + thirds + rest,
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

# 配備訊號（2026-07-10 pit backtest，15 賽日 153 場）：
#   除去配備 −3 於 TRAIN/TEST 齊升（FULL min +0.7、gold +0.7、single +0.6，
#   零回退；−1/−2/−3 同方向、單調）→ 入分。
#   初戴（任何/淨眼罩/晨操預演 gated）全部 NULL 或過擬合（TRAIN 升 TEST 唔升）
#   → 只做顯示。詳見 memory hkjc-gear-module-spec。
GEAR_SIGNAL_WEIGHTS = {
    "gear_removed_pen": -3.0,
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
