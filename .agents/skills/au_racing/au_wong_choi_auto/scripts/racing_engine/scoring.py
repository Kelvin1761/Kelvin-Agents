#!/usr/bin/env python3
"""AU Wong Choi Auto scoring primitives."""
from __future__ import annotations
import re

FEATURE_KEYS = ("form_score","trial_score","sectional_score","pace_map_score","jockey_score","trainer_score","jockey_horse_fit_score","class_score","rating_score","weight_score","distance_score","track_score","formline_score","consistency_score","health_score","confidence_score","pace_figure_score")

# pace_figure = 8th dimension: field-relative L600-vs-benchmark ("實測段速") from
# racenet PuntingForm (AUC 0.60 vs old text-sectional 0.545). Neutral 60 where PF
# data absent → rank-neutral on no-PF races.
# 2026-07-03 段速 restructure ("swap"): the MEASURED pace figure is now the primary
# 段速 signal (0.143) and the old text-PI sectional dimension is demoted to 0.045 —
# it is near-noise (AUC 0.528 ceiling) but its "has timing data" floor still carries
# a mild winner signal, so it keeps a small weight rather than zero. Validated on
# TWO independent PF windows (05-22→06-13: GGP 89→91; 06-19→07-01 OOS: GGP 29→38)
# AND the full 687-race archive (gold 33→37, pass 285→297, champ +0.9pp, winT3
# +2.0pp, box4 +0.2pp; good −1 within noise). Direct stability-weight cuts were
# tested the same day and LOSE window A — the gain is from the 段速 restructure,
# not from de-weighting stability. Weights sum to exactly 1.0 (normalised from the
# tested 1.0475-sum config; ranking-identical, keeps grade thresholds honest).
# Rollback: pace_figure 0.05 config {"stability":0.3135,"sectional":0.09975,
# "race_shape":0.2223,"jockey_trainer":0.2033,"class_weight":0.0475,
# "track":0.06365,"form_line":0.000,"pace_figure":0.050}.
# 2026-07-10: sectional(0.04535)+pace_figure(0.14296) 合併為 pace_perf(0.18831)，
# 內部 leaf 權重精確折算 → 排名逐匹一致（見 matrix_mapper 註釋）。
# 2026-07-11: track_score 去重 —— 原本 race_shape 內含 30% track_score（有效
# track 影響 0.06367 + track 維度 0.06076 = 0.12443；draw 影響 0.21222×0.70=0.14855）。
# 拆乾淨：race_shape 變純 draw @0.14855、track 收晒全部 @0.12443。兩者相加同舊
# (0.21222+0.06076) 一樣 → 逐匹 rank-identical。其餘維度不變。
MATRIX_WEIGHTS = {"stability":0.29928,"pace_perf":0.18831,"race_shape":0.14855,"jockey_trainer":0.19408,"class_weight":0.04535,"track":0.12443,"form_line":0.000}
_WEIGHT_FLOOR = {"stability":0.10}
_WEIGHT_CEILING = {"class_weight":0.15,"track":0.17}

# ── Wet-form 7D feature (gated to Soft/Heavy races) ──
# A horse's career wet-going place record IS predictive of box-trifecta on wet
# tracks, where the dry 7D score under-rates proven wet performers. This is a
# per-horse going-suitability feature folded into the single ability_score
# (綜合戰力分) on wet races — NOT a post-hoc ranking bolt-on and NOT one of the
# retired report-only micro-modifiers. On dry races it is exactly 0, so the dry
# score is unchanged and stays == pure 7D.
# Walk-forward validated (held-out, expanding window): Soft box-trifecta
# 14.4% → 16.6% at scale 12 (robust plateau 6–12; Heavy unaffected). The going
# record is densely populated (92.7% of runners have ≥1 wet start).
WET_FORM_FEATURE_SCALE = 12.0   # points of ability per (shrunk_wet_place_rate − prior)
WET_FORM_SHRINK_A = 4.0         # pseudo-count for place-rate shrinkage toward prior
WET_FORM_PRIOR = 0.5            # global career wet place-rate (~0.496 measured)
WET_FORM_MAX_ABS = 5.0          # clamp the feature to a sane ±range


def _parse_wet_record(going_stats_line):
    """Career (soft+heavy) starts & places from the 軟地/重地 segments of going_stats_line."""
    starts = places = 0
    for label in ("軟地", "重地"):
        match = re.search(rf"{label}:\s*([^|]+)", going_stats_line or "")
        if not match:
            continue
        nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if len(nums) >= 4:
            starts += nums[0]
            places += nums[1] + nums[2] + nums[3]
        elif nums:
            starts += nums[0]
    return starts, places


def wet_form_feature(going, going_stats_line):
    """Per-horse wet-going-suitability contribution to ability_score (綜合戰力分).

    Returns 0.0 on dry (Good/Firm) going so the score stays == pure 7D. On Soft/Heavy
    going, returns scale·(shrunk_wet_place_rate − prior), clamped to ±WET_FORM_MAX_ABS.
    A horse with no wet starts shrinks to the prior → 0 (neutral)."""
    g = str(going or "").lower()
    if "soft" not in g and "heavy" not in g:
        return 0.0
    starts, places = _parse_wet_record(going_stats_line)
    rate = (places + WET_FORM_SHRINK_A * WET_FORM_PRIOR) / (starts + WET_FORM_SHRINK_A)
    value = WET_FORM_FEATURE_SCALE * (rate - WET_FORM_PRIOR)
    return round(max(-WET_FORM_MAX_ABS, min(WET_FORM_MAX_ABS, value)), 4)

# 2026-07-11 修：career5_unplaced_pen 由 +0.82（語義反轉——變數叫「懲罰」卻加分，
# ML 殘骸）改為 −0.82 對稱；class_up_pen 保持 0（ML 已推零，代碼側已停止出死 note）。
CLASS_MICRO_WEIGHTS = {
    "career0_base": 57.7,
    "career0_2yo_bonus": 0.84,
    "career5_placed_bonus": 2.31,
    "career5_unplaced_pen": -0.82,
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
    # forgiveness_bonus (1.49) 2026-07-10 退出計分：A/B 移除對排名零影響（box4 微升），
    # 寬恕背景改為報告純顯示解讀，唔再入分。
    # margin_trend_bonus 2026-07-10 新增（用戶提出，HK 亦有用）：近2仗平均輸距 vs 之前
    # 改善/惡化 ≥2L → ±3。A/B：全檔 GGP +1、A窗 +1、winT3 +0.6pp，無指標倒退。
    "margin_trend_bonus": 3.0,
    "run_style_bonus": 5.2,
    "pi_stable_bonus": 5.71,
    "repeat_bonus": 2.7,
    "no_repeat_pen": -2.0
}

# 2026-07-10 噪音剪裁（702場 A/B，PF backfill 之後）：
# - trial_extreme/excellent/pass 補償 REMOVED — 原本非單調（最快試閘 +0、較慢反而 +3.97，
#   ML search 殘骸）；三個修法測齊，「完全移除」最好（GGP +2）兼 timing 上游斷供後本身已啞。
# - peak_pi_bonus / trend_up / trend_down REMOVED — ablation 全指標零變化（純惰性）。
# - realization / forgiveness / pi tiers / l600 峰值 KEPT — 移除有實測損失。
SECTIONAL_MICRO_WEIGHTS = {
    "base": 35.8,
    "pi_extreme_bonus": 28.1,
    "pi_excellent_bonus": 20.0,
    "pi_pass_bonus": 3.64,
    "l600_extreme_bonus": 15.07,
    "l600_excellent_bonus": 3.64,
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
    # 2026-07-11 修：乾地「1 戰零上名」原本 −7.08，罰得重過「2 戰零上名」(−3.46)，
    # 非單調（樣本越少罰越重，不合理，ML 殘骸）。改 −3.0，令 1 戰 ≤ 2 戰。A/B rank-neutral。
    "going_poor_pen2_dry": -3.0,
    "wet_unverified_pen": -6.4,
    "heavy_win_bonus": 3.87,
    # 2026-07-11 修：heavy_place_bonus 原本 −2.88（符號反轉——重地曾上名嘅馬反被扣分，
    # 而 note 竟寫「具備重地作戰能力」；同 best_formal_mult 同款 ML 殘骸）。改 +2.0，
    # 令重地階梯單調：曾贏 +3.87 > 曾上名 +2.0 > 零上名 −5.94。A/B rank-neutral（Heavy good↔pass 互抵）。
    "heavy_place_bonus": 2.0,
    "heavy_poor_pen": -5.94,
    "wet_bloodline_bonus": 4.18
}

# 2026-07-11 單調化修：原本 med_base 68.3 > strong 66.4 > med_strong 61.8（「中等對手」
# 基礎分竟高過「強對手」——form_line 權重=0 冇 gradient，ML search 留低嘅噪音）。
# 呢個維度純顯示（唔入排名），修正只為報告數字自洽：頂級 > 強 > 中強 > 中 > 中弱 > 弱。
FORMLINE_MICRO_WEIGHTS = {
    "elite_base": 82.5,
    "strong_base": 72.0,
    "med_strong_base": 66.0,
    "med_base": 62.0,
    "med_weak_base": 57.0,
    "weak_base": 53.0,
    "neutral_base": 58.0,
    "unknown_base": 60.0,
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
# apprentice_fresh_bonus (−0.14) 2026-07-11 刪除 — ML 殘骸負值兼 LY 普及層上線後
# token fallback 極少觸發。
JOCKEY_MICRO_WEIGHTS = {
    "elite_bonus": 9.0,
    "solid_bonus": 5.77
}

TRAINER_MICRO_WEIGHTS = {
    "elite_bonus": 10.59,
    "waller_debut_bonus": 5.52,
    "track_high_vol_high_place_bonus": 10.96,
    "track_med_vol_high_place_bonus": 4.29,
    "track_med_vol_med_place_bonus": 1.44,
    "track_low_place_pen": -0.52
}

# 2026-07-11 大剪裁（702場 A/B）：
# - 「歷來最佳配搭」family REMOVED — best_formal_mult 被 ML 推成負數（沿用最佳配搭
#   反而扣分，語義反轉 bug）；成族移除 GGP +2／A窗 +1／B窗平。
# - combo（同場館騎練組合）＋ misc（減磅/週期/首仗二出/-5未知馬房）兩族 REMOVED —
#   逐項 ablation 全指標零變化（惰性），改為 display-only notes。
# - 0 權重死支（debut_top_trainer/young_top_jt/latest_upgrade/jockey_downgrade_vs_best）刪除。
# - KEPT（有實測損失）：trial（−11 GGP if removed）、current（−6）、signal（−5）、latest pens。
FIT_MICRO_WEIGHTS = {
    "trial_ok_bonus": 3.38,
    "trial_ok_top_jt_bonus": 1.0,
    "current_formal_cap": 4.05,
    "current_formal_mult": 0.31,
    "current_basic_fit_bonus": 0.65,
    "current_high_fit_bonus": 1.47,
    "current_trial_cap": 2.57,
    "current_trial_mult": 3.8,
    "latest_downgrade_pen": -4.11,
    "leave_proven_jockey_pen": -2.98,
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
    # NOTE: dead code（引擎排名已唔用動態權重）；2026-07-10 sectional→pace_perf 改 key
    # 純為保持可 import（au_market_free_ablation 有引用）。
    if field_count >= 13:
        weights["race_shape"] -= 0.02; weights["pace_perf"] -= 0.01; weights["stability"] += 0.02; weights["form_line"] += 0.01
    elif field_count >= 9:
        weights["race_shape"] -= 0.01; weights["pace_perf"] -= 0.005; weights["stability"] += 0.01; weights["form_line"] += 0.005
    elif field_count > 0 and field_count <= 8:
        weights["race_shape"] += 0.04; weights["pace_perf"] += 0.03; weights["stability"] -= 0.02; weights["form_line"] -= 0.02

    if "soft" in going or "heavy" in going:
        weights["race_shape"] -= 0.005; weights["track"] += 0.01; weights["stability"] -= 0.005
    elif "good" in going or "firm" in going:
        weights["pace_perf"] += 0.05; weights["track"] -= 0.02

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
    """Finish positions from a recent-form string, newest conventions honoured.

    Handles both separated ("8-9-7-6") and compact ("2134") formats — the compact
    form previously parsed as one giant number and silently returned nothing,
    zeroing the consistency place/poor components for those horses. In compact
    form each digit is one run and "0" is the AU code for 10th-or-worse.
    """
    if not text: return None
    raw = str(text).strip()
    if re.fullmatch(r"\d{2,}", raw):
        return [int(ch) if ch != "0" else 10 for ch in raw]
    nums = parse_numbers(raw)
    if nums: return [n if n != 0 else 10 for n in nums if 0 <= n <= 24]
    return None

def safe_ratio(numerator, denominator):
    if not denominator: return 0.0
    return min(1.0, max(0.0, numerator / denominator))
