# HKJC 全公式原碼附錄

由 formula_sources.py 抽取，數值直接來自當前 code；展示時移除行尾空白，SHA256對應原檔。
包含九維、初出馬、顯示尺、SIP、限幅、資料解析及中性回退。診斷分會註明；shadow 候選不等於現役。

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/dimensions.py

SHA256: `305d798c7bc163d45286be5afb9b76e15ac70e35756ae8d9cc3883f1a22e9080`

```python
"""HKJC rating-matrix dimension registry — the single source of truth.

Adding, removing or re-weighting a dimension happens HERE and nowhere else.
`scoring.MATRIX_WEIGHTS / DEBUT_MATRIX_WEIGHTS / MATRIX_DISPLAY_*`,
`matrix_mapper.MATRIX_FORMULAS`, `renderer.MATRIX_LABELS / MATRIX_ROLES`,
`engine_core.DIM_LABELS`, validation and the dashboard payload are all derived
from `DIMENSIONS`, so a new dimension needs one entry here plus its leaf
function — nothing else is hard-coded.

Why (2026-10-10 audit): the dimension set was copied into ten-plus places, and
the dashboard kept printing "六維" for a seven-dimension model for months.

Pure data: this module must not import scoring/engine_core (they import it).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DimensionSpec:
    key: str
    label: str                       # report / dashboard heading
    short_label: str                 # one-word label used in prose
    role: str                        # 核心 / 半核心 / 輔助
    leaves: tuple[tuple[str, float], ...]
    weight: float                    # standard runners (sums to 1 over non-centred)
    debut_weight: float = 0.0        # debut runners (DEBUT_MATRIX_WEIGHTS)
    display_centre: float = 60.0     # measured median → shown as 60
    display_gain: float = 1.0        # 10 / measured SD
    description: str = ""            # one sentence for the dashboard
    dashboard_keywords: tuple[str, ...] = field(default_factory=tuple)
    # Centred dimensions add weight × (score − 60) on top of the weighted mean
    # instead of sharing the sum-to-1 budget. Used when a former raw adjustment
    # becomes a visible dimension without changing any ranking.
    centred: bool = False


# Order = report display order (Kelvin: 騎練訊號 follows 狀態與穩定性).
DIMENSIONS: tuple[DimensionSpec, ...] = (
    DimensionSpec(
        key="stability", label="狀態與穩定性", short_label="穩定性", role="半核心",
        # 9D split (2026-10-10): trackwork moved to its own dimension; the old
        # 0.5 / 0.4 shares are renormalised so the composite is unchanged.
        leaves=(("form_score", 0.5 / 0.9), ("consistency_score", 0.4 / 0.9)),
        weight=0.08847, debut_weight=0.135, display_centre=56.39, display_gain=0.8642,
        description="近仗名次、逐仗輸距同狀態走勢。",
        dashboard_keywords=("狀態", "穩定", "近績"),
    ),
    DimensionSpec(
        key="trainer_signal", label="騎練訊號", short_label="騎練訊號", role="核心",
        leaves=(("jockey_score", 0.55), ("trainer_score", 0.45)),
        weight=0.2362, debut_weight=0.30, display_centre=60.5, display_gain=2.1261,
        description="騎師同練馬師實績，加人馬、組合、路程情境。",
        dashboard_keywords=("騎練", "騎師", "練馬師"),
    ),
    DimensionSpec(
        key="sectional", label="段速表現", short_label="段速", role="核心",
        leaves=(("speed_score", 1.00),),
        weight=0.1285, debut_weight=0.0, display_centre=60.0, display_gain=1.1137,
        description="末段 400 米、完成時間水平同段速走勢。",
        dashboard_keywords=("段速", "速度"),
    ),
    DimensionSpec(
        key="race_shape", label="檔位與走位（不含步速）", short_label="形勢檔位", role="半核心",
        leaves=(("race_shape_context_score", 1.00),),
        weight=0.2737, debut_weight=0.20, display_centre=63.0, display_gain=0.9852,
        description="檔位、走位匹配同近仗消耗。",
        dashboard_keywords=("檔位", "走位", "形勢"),
    ),
    DimensionSpec(
        key="horse_health", label="馬匹健康 / 新鮮感", short_label="健康新鮮", role="輔助",
        leaves=(("risk_score", 0.611), ("weight_score", 0.389)),
        weight=0.0404, debut_weight=0.30, display_centre=66.9, display_gain=2.8841,
        description="醫療紀錄、距上仗日數同體重變化。",
        dashboard_keywords=("健康", "新鮮"),
    ),
    DimensionSpec(
        key="trackwork", label="晨操狀態", short_label="晨操", role="輔助",
        leaves=(("trackwork_trend_score", 1.00),),
        # Former 10% share of stability (0.0983 × 0.10). Display ruler measured on
        # 4,545 runners (2026-04 → 10): median 63.70, SD 9.59.
        weight=0.00983, debut_weight=0.015, display_centre=63.7, display_gain=1.0428,
        description="近 21 日快操、試閘同操練趨勢。",
        dashboard_keywords=("晨操", "操練", "試閘"),
    ),
    DimensionSpec(
        key="distance_fit", label="同程表現", short_label="同程", role="輔助",
        leaves=(("distance_fit_score", 1.00),),
        # Former independent same-distance raw adjustment (+0.43 / −0.17):
        # leaf = 60 + adjustment / 0.02, contribution = 0.02 × (leaf − 60).
        weight=0.02, debut_weight=0.0, display_centre=60.0, display_gain=0.7375,
        description="同程往績：有冇喺今仗路程上過名。",
        dashboard_keywords=("同程", "路程"),
        centred=True,
    ),
    DimensionSpec(
        key="form_line", label="賽績線", short_label="賽績線", role="輔助",
        leaves=(("formline_strength_score", 1.00),),
        weight=0.0801, debut_weight=0.0, display_centre=80.0, display_gain=0.8153,
        description="之前交手對手之後嘅表現。",
        dashboard_keywords=("賽績線", "對手"),
    ),
    DimensionSpec(
        key="class_advantage", label="級數優勢", short_label="班次優勢", role="輔助",
        leaves=(("class_score", 0.75), ("weight_score", 0.25)),
        weight=0.1428, debut_weight=0.05, display_centre=64.8, display_gain=1.8311,
        description="班次經驗同讓磅官評分（負磅）。",
        dashboard_keywords=("級數", "班次"),
    ),
)

BY_KEY = {spec.key: spec for spec in DIMENSIONS}

# Transition shim for the rank-neutral 7D → 9D split (2026-10-10). The 7D
# stability dimension was round(0.5·form + 0.4·consistency + 0.1·trackwork, 2).
# Splitting it into two separately rounded dimensions moved 2 of 351 races by
# one adjacent place. To stay exact, the 9D stability value is derived from the
# old rounded 7D value minus trackwork's share, so
#   0.08847 · stability + 0.00983 · trackwork == 0.0983 · old_stability.
# Remove this (and its use in matrix_mapper) when trackwork is rebuilt (Phase 4).
LEGACY_STABILITY_SPLIT = {
    "parent": "stability",
    "child": "trackwork",
    "legacy_leaves": (("form_score", 0.50), ("consistency_score", 0.40), ("trackwork_trend_score", 0.10)),
    "child_share": 0.10,
}

# Summation / iteration orders inherited from the pre-registry dicts. Float sums
# depend on order, so these keep the composite bit-identical. A dimension missing
# from an order tuple is appended after it (new dimensions need no edit here).
_WEIGHT_ORDER = ("sectional", "trainer_signal", "stability", "race_shape",
                 "class_advantage", "horse_health", "form_line")
_DEBUT_ORDER = ("trainer_signal", "horse_health", "race_shape", "stability", "class_advantage")
_FORMULA_ORDER = ("stability", "sectional", "race_shape", "trainer_signal",
                  "horse_health", "form_line", "class_advantage")


def _ordered(order: tuple[str, ...]) -> list[DimensionSpec]:
    known = [BY_KEY[key] for key in order if key in BY_KEY]
    return known + [spec for spec in DIMENSIONS if spec.key not in order]


def weights() -> dict[str, float]:
    """Sum-to-1 weights (centred dimensions excluded)."""
    return {spec.key: spec.weight for spec in _ordered(_WEIGHT_ORDER) if not spec.centred}


def centred_weights() -> dict[str, float]:
    return {spec.key: spec.weight for spec in DIMENSIONS if spec.centred}


def all_keys() -> tuple[str, ...]:
    return tuple(spec.key for spec in DIMENSIONS)


def debut_weights() -> dict[str, float]:
    return {spec.key: spec.debut_weight for spec in _ordered(_DEBUT_ORDER) if spec.debut_weight}


def formulas() -> dict[str, tuple[tuple[str, float], ...]]:
    return {spec.key: spec.leaves for spec in _ordered(_FORMULA_ORDER)}


def labels() -> dict[str, str]:
    return {spec.key: spec.label for spec in DIMENSIONS}


def short_labels() -> dict[str, str]:
    return {spec.key: spec.short_label for spec in DIMENSIONS}


def roles() -> dict[str, str]:
    return {spec.key: spec.role for spec in DIMENSIONS}


def display_centres() -> dict[str, float]:
    return {spec.key: spec.display_centre for spec in DIMENSIONS}


def display_gains() -> dict[str, float]:
    return {spec.key: spec.display_gain for spec in DIMENSIONS}


def dashboard_manifest() -> list[dict]:
    """What the dashboard needs to render every dimension without hard-coding."""
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "short_label": spec.short_label,
            "role": spec.role,
            "weight": spec.weight,
            "centred": spec.centred,
            "debut_weight": spec.debut_weight,
            "description": spec.description,
            "keywords": list(spec.dashboard_keywords),
        }
        for spec in DIMENSIONS
    ]
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/scoring.py

SHA256: `8e880dcef8d84b676049c3d56bc34793855bf48de662459b1551cbe501d1f470`

```python
#!/usr/bin/env python3
"""
racing_engine/scoring.py — Core Scoring Framework
"""

from . import dimensions
from abc import ABC, abstractmethod
import os
import re


# Bump whenever a production matrix/formula change is intentionally promoted.
# Persisted with every scored race so forward results can be attributed to the
# exact model that made the pre-race prediction.
SCORING_CONTRACT_VERSION = (
    "HKJC_9D_CONTRACT_2026_10_10_REGISTRY_TRACKWORK_DISTANCE_FIT_"
    "RACE_SHAPE_ROBUST_WINSOR10_PIT_RAIL_DRAW_V2_DISTANCE_COMPONENT_V1"
)


HAPPY_VALLEY_RACE_SHAPE_V3_SURFACE_GAIN = 0.45
RACE_SHAPE_ROBUST_DEVIATION_CAP = 10.0
def active_race_shape_robustness_profile():
    """Return the whole-field shape robustness policy with emergency rollback."""
    value = os.environ.get("WC_HKJC_RACE_SHAPE_ROBUSTNESS", "winsor10").strip().lower()
    return "legacy_unbounded" if value in {"legacy", "legacy_unbounded", "off"} else "winsor10"

def active_happy_valley_race_shape_profile():
    """Return the live HV formula, with an explicit emergency rollback.

    The default is the user-accepted experimental V3 formula.  Operations can
    restore the prior V2 formula without editing a prediction artifact by
    setting ``WC_HKJC_HV_RACE_SHAPE_PROFILE=legacy_v2`` before the run.  The
    selected value is persisted in the scoring run contract.
    """
    value = os.environ.get("WC_HKJC_HV_RACE_SHAPE_PROFILE", "v3_surface").strip().lower()
    return "legacy_v2" if value == "legacy_v2" else "v3_surface"


def race_shape_contract_manifest():
    return {
        "sha_tin": "legacy_55_draw_25_historical_fit_20_trip",
        "happy_valley": active_happy_valley_race_shape_profile(),
        "happy_valley_v3_formula": "draw+0.45*(pit_surface-60)",
        "happy_valley_surface_gain": HAPPY_VALLEY_RACE_SHAPE_V3_SURFACE_GAIN,
        "happy_valley_fit_weight": 0.0,
        "happy_valley_trip_weight": 0.0,
        "field_tempo": "withheld_insufficient_reliability",
        "debut": "locked_legacy_formula",
        "draw_context": "pit_venue_rail_distance_band_draw_group_relative_cap4",
        "draw_context_venue_partition": "sha_tin_and_happy_valley_never_pool",
        "draw_context_minimums": {"runners": 100, "races": 20, "shrink_runners": 60},
        "rollback_env": "WC_HKJC_HV_RACE_SHAPE_PROFILE=legacy_v2",
        "whole_field_robustness": active_race_shape_robustness_profile(),
        "whole_field_robust_formula": "meeting_median+clip(shape-meeting_median,-10,+10)",
        "whole_field_robust_cap": RACE_SHAPE_ROBUST_DEVIATION_CAP,
        "whole_field_rollback_env": "WC_HKJC_RACE_SHAPE_ROBUSTNESS=legacy_unbounded",
        "whole_field_evidence_status": "user_accepted_experimental_live",
        "evidence_status": "user_accepted_experimental_live",
    }


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
MATRIX_WEIGHTS = dimensions.weights()
# Centred dimensions: composite += weight × (score − 60). See dimensions.py.
CENTRED_MATRIX_WEIGHTS = dimensions.centred_weights()
MATRIX_KEYS_ALL = dimensions.all_keys()

# Same-distance evidence is a distance-suitability signal, not evidence that a
# horse has a class edge.  These micro values deliberately preserve the former
# production contribution while the signal is moved out of class_score.  The
# resulting raw-score adjustment is independently displayed and capped by the
# two signal values (roughly +0.43 / -0.17 after the class dimension blend).
DISTANCE_SUITABILITY_MICRO_WEIGHTS = {
    "same_dist_place_bonus": 4.0,
    "same_dist_unplaced_pen": -1.55,
}

# EXP-20261007-05.  The component is a within-horse residual rather than a raw
# same-distance place rate, so general ability is not counted a second time.
# Sha Tin AWT stays shadow-only because archived AWT surface labels do not yet
# provide enough point-in-time coverage for a defensible live weight.
DISTANCE_SUITABILITY_V2_PROFILES = {
    "HV_TURF": {"weight": 0.08, "cap": 6.0, "variant": "exact_blend"},
    "ST_TURF": {"weight": 0.02, "cap": 4.0, "variant": "exact_blend"},
    "ST_AWT": {"weight": 0.0, "cap": 4.0, "variant": "exact_blend"},
}


def distance_suitability_contract_manifest():
    return {
        "source": "point_in_time_same_distance_record",
        "route": "independent_visible_adjustment_outside_class_score",
        "signal_micro": dict(DISTANCE_SUITABILITY_MICRO_WEIGHTS),
        "v2_shadow_profiles": {key: dict(value) for key, value in DISTANCE_SUITABILITY_V2_PROFILES.items()},
        "legacy_equivalent_class_component_weight": 0.75,
        "legacy_equivalent_outer_weight": MATRIX_WEIGHTS["class_advantage"],
        "ranking_policy": "v1_live_v2_prospective_shadow_pending_primary_gate",
    }


# Machine-readable metadata for the generated model explanation.  The actual
# calculation remains in engine_core so this cannot become a second formula.
RANKING_ADJUSTMENTS = (
    {
        "key": "race_shape_robustness",
        "label": "全場 race-shape 極端值修正",
        "formula": "同場中位數 + clip（race-shape − 同場中位數，−10，+10）；全場同式、不鎖名次",
        "missing": "整場冇有效 race-shape = 不套用；可用 WC_HKJC_RACE_SHAPE_ROBUSTNESS=legacy_unbounded 回退",
    },
)

DEBUT_MATRIX_WEIGHTS = dimensions.debut_weights()

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
MATRIX_DISPLAY_CENTRES = dimensions.display_centres()  # 實測中位 → 讀者睇到嘅 60
MATRIX_DISPLAY_GAINS = dimensions.display_gains()  # 10.0 / 實測 SD → 每個維度同一個離散度
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
# 2026-10-10（EXP-20261010-04）：以前呢度仲有 `trend_lighter_bonus` +4／`trend_heavier_pen` −4，
# 讀嘅係**馬匹體重**趨勢唔係負磅，而 risk_score 已經計體重（方向相反）。量過之後剷走：
# 負磅分只計讓磅，分界用實際負磅（負磅 − 見習減磅）。
WEIGHT_MICRO_WEIGHTS = {
    "base": 64.0,
    "light_weight_base": 54.0,   # ≤120 磅：讓磅官睇低佢
    "heavy_weight_base": 70.0,   # ≥132 磅：讓磅官睇好佢，而且抹得唔夠
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
    # 最快第一段（K=4 分段，EXP-20261016-52 預先登記；Kelvin 2026-10-16 決定上線，**未證實**，
    # forward 退回條件見 EXP-20261016-53）
    "first_section_fast_bonus": 4.0,
    "first_section_quick_bonus": 2.0,
    "first_section_slowish_pen": -1.0,
    "first_section_slow_pen": -2.0,
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

# 完成時間趨勢 ±5（FINISH_TREND_MICRO_WEIGHTS）已於 2026-10-16 剷走（EXP-20261016-16，§7）：
# 引擎搵「進步」但 Facts 寫「📈改善中」，+5 由 2026-06-19 接線起從未觸發，上線嘅只係單邊 −5；
# 同一個完成時間偏差已經由 SpeedScorer 嘅「步速修正等級」計分。

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
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/matrix_mapper.py

SHA256: `1da521a47df6acb41ed0f5457f7e7f95ac5fe47bfbbe836c9a2fc8739e34010a`

```python
from . import dimensions
from .scoring import clip_score, score_band


# Leaf composition per dimension lives in dimensions.py (single source of truth).
# History of the leaf choices (track_going removed 2026-07-10, confidence removed
# 2026-07-11, margin_trend removed 2026-07-08) is in git and docs/experiments.
MATRIX_FORMULAS = dimensions.formulas()


def matrix_formula_manifest():
    """JSON-safe representation shared by run metadata and validation."""
    return {
        key: [
            {"feature": feature, "weight": weight}
            for feature, weight in components
        ]
        for key, components in MATRIX_FORMULAS.items()
    }


def map_features_to_matrix(features):
    scores = map_features_to_matrix_scores(features)
    return {key: score_band(score) for key, score in scores.items()}


def map_features_to_matrix_scores(features):
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
        score = sum(_component_score(features, name) * weight for name, weight in components)
        matrix_scores[key] = round(clip_score(score), 2)
    split = dimensions.LEGACY_STABILITY_SPLIT
    if split and split["parent"] in matrix_scores and split["child"] in matrix_scores:
        legacy = round(clip_score(sum(
            _component_score(features, name) * weight for name, weight in split["legacy_leaves"]
        )), 2)
        share = split["child_share"]
        matrix_scores[split["parent"]] = round(
            (legacy - share * matrix_scores[split["child"]]) / (1.0 - share), 6
        )
    return matrix_scores


def _component_score(features, name):
    if name == "race_shape_context_score" and name not in features:
        return clip_score(features.get("draw_score", 60))
    return clip_score(features.get(name, 60))
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/features/form.py

SHA256: `517d86f54ea62e9d1c003b4ac74242aa0ea377223b5ed8df3b81c711a5010ade`

```python
from hkjc_racing_engine import scoring
from hkjc_racing_engine.scoring import BaseScorer

class FormScorer(BaseScorer):
    def compute(self):
        data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
        form = self.horse_data.get("last_6_finishes", "N/A")

        scores = []
        ranks = []  # keep the actual finishing positions so the note can be specific

        # 1. Parse local form
        if form != "N/A" and form != "" and str(form).replace("-", "").replace("N/A", "").strip():
            parts = str(form).replace("-", " ").replace(",", " ").split()
            for p in parts:
                try:
                    if "/" in p:
                        rank = int(p.split("/")[0])
                    else:
                        rank = int(p)
                    if rank <= 0:
                        continue
                    ranks.append(rank)
                    if rank == 1: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_1", 100))
                    elif rank == 2: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_2", 85))
                    elif rank == 3: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_3", 75))
                    elif rank <= 5: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_4_5", 60))
                    else: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_other", 40))
                except ValueError:
                    continue

        # 2. Add overseas form if available.
        # PDF 往績表係「包括本會及海外賽績」— 同近6場日期相同嘅 rows 其實係本地賽事，
        # 直接跳過，唔好當海外計多次。
        local_count = len(scores)
        local_dates = str(data.get("recent_6_detail", "") or "")
        pdf_races = data.get("pdf_overseas_races", [])
        if pdf_races:
            for r in pdf_races:
                race_date = str(r.get("date", "")).strip()
                if race_date and race_date not in ("-", "N/A") and race_date in local_dates:
                    continue
                rank_str = str(r.get("rank", ""))
                try:
                    rank = int(rank_str.split("/")[0]) if "/" in rank_str else int(rank_str)
                    if rank <= 0:
                        continue
                    if rank == 1: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_1", 100))
                    elif rank == 2: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_2", 85))
                    elif rank == 3: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_3", 75))
                    elif rank <= 5: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_4_5", 60))
                    else: scores.append(scoring.FORM_MICRO_WEIGHTS.get("rank_other", 40))
                except ValueError:
                    continue

        if scores:
            weighted_sum = 0
            total_weight = 0
            for i, s in enumerate(scores[:6]):
                weight = 1.0 / (i + 1)
                weighted_sum += s * weight
                total_weight += weight
            self.score = weighted_sum / total_weight

            # Build a SPECIFIC Chinese note (finishes + top3/win counts). No filler
            # like 越近仗權重越高 (計法解釋唔幫到落注)。海外賽績唔混入呢句 —
            # 由 engine 嘅「海外往績判讀」獨立交代。
            used = ranks[:6]
            wins = sum(1 for r in ranks if r == 1)
            top3 = sum(1 for r in ranks if r <= 3)
            poor = sum(1 for r in ranks if r >= 8)
            bits = [f"近{len(used)}仗名次 {'-'.join(str(r) for r in used)}"] if used else []
            detail = []
            if wins:
                detail.append(f"{wins}冠")
            if top3:
                detail.append(f"{top3}次前三")
            if poor:
                detail.append(f"{poor}次八名以後")
            if detail:
                bits.append("、".join(detail))
            # 只計實際入咗近6仗計分窗嘅海外場數，唔好報大數
            overseas_used = max(0, min(len(scores), 6) - local_count)
            if overseas_used:
                if not used:
                    bits.append(f"未有香港賽績，以{overseas_used}仗海外賽績計（明細見海外往績）")
                else:
                    bits.append(f"另計{overseas_used}仗海外賽績（明細見海外往績）")
            self.reason = "；".join(bits)
            return self.score, self.reason

        self.score = 60.0
        self.reason = "No recent form (Neutral)"
        return self.score, self.reason
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/features/speed.py

SHA256: `c3796d00b12091781066c7a6a8e87d8c0eb380a550ba53d959351af850ad0ffa`

```python
from hkjc_racing_engine import scoring
from hkjc_racing_engine.scoring import BaseScorer, clip_score, parse_float

def first_section_delta(min_delta):
    """近 6 仗最快第一段（Δ1 對標準，負 = 快）→ 段速分加減。None = 冇證據。"""
    m = parse_float(min_delta)
    if m is None:
        return None, ""
    w = scoring.SPEED_MICRO_WEIGHTS
    if m < -0.3:
        return w["first_section_fast_bonus"], "第一段曾快過標準 >0.3s"
    if m < 0:
        return w["first_section_quick_bonus"], "第一段曾快過標準"
    if m < 0.3:
        return 0.0, "第一段接近標準"
    if m < 0.6:
        return w["first_section_slowish_pen"], "第一段偏慢"
    return w["first_section_slow_pen"], "第一段明顯慢"


class SpeedScorer(BaseScorer):
    def _data(self):
        return self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}

    def compute(self):
        score, note = self._compute_core()
        # 最快第一段（EXP-20261016-52/53，Kelvin 2026-10-16 決定上線，未證實）：喺所有返回路徑之後加，
        # 唔計入 signals —— 同 A/B arm 一模一樣，排名可以同 arm 逐場對數。
        m = self._data().get("first_section_min_delta")
        delta, why = first_section_delta(m)
        if delta is None:
            return score, note
        self.detail = list(getattr(self, "detail", []) or []) + [
            {"factor": "最快第一段", "value": f"{float(m):+.2f}s", "delta": round(delta, 2), "why": why}]
        return clip_score(score + delta), note

    def _compute_core(self):
        data = self._data()
        signals = 0
        strong_signals = 0
        score = 60.0
        reasons = []
        # 逐項結構化明細（同騎練訊號一致）：每個訊號 factor / 原始值 / ±分 / 白話
        self.detail = []

        def add(factor, value, delta, why):
            score_ref[0] += delta
            self.detail.append({"factor": factor, "value": value, "delta": round(delta, 2), "why": why})
        score_ref = [score]  # 用 list 令內層 add 可改到

        raw_l400 = parse_float(data.get("raw_l400"))
        if raw_l400 is not None:
            signals += 1
            reasons.append(f"L400={raw_l400:.2f}")
            if raw_l400 <= 22.4:
                add("L400 絕對值", f"{raw_l400:.2f}s", scoring.SPEED_MICRO_WEIGHTS.get("l400_22_4_bonus", 8.0), "末段極快（≤22.4s）")
                strong_signals += 1
            elif raw_l400 <= 23.0:
                add("L400 絕對值", f"{raw_l400:.2f}s", scoring.SPEED_MICRO_WEIGHTS.get("l400_23_0_bonus", 5.0), "末段快（≤23.0s）")
                strong_signals += 1
            elif raw_l400 <= 23.6:
                add("L400 絕對值", f"{raw_l400:.2f}s", scoring.SPEED_MICRO_WEIGHTS.get("l400_23_6_bonus", 2.0), "末段偏快（≤23.6s）")
            elif raw_l400 >= 24.6:
                add("L400 絕對值", f"{raw_l400:.2f}s", scoring.SPEED_MICRO_WEIGHTS.get("l400_24_6_pen", -5.0), "末段慢（≥24.6s）")
                strong_signals += 1
            elif raw_l400 >= 24.0:
                add("L400 絕對值", f"{raw_l400:.2f}s", scoring.SPEED_MICRO_WEIGHTS.get("l400_24_0_pen", -2.0), "末段偏慢（≥24.0s）")
            else:
                add("L400 絕對值", f"{raw_l400:.2f}s", 0.0, "末段一般（23.6–24.0s）")

        finish_time_level = str(data.get("finish_time_adj_level") or "").strip()
        if finish_time_level:
            signals += 1
            reasons.append(f"步速修正={finish_time_level}")
            lvl = finish_time_level.lstrip("✅⚠️❌➖ ").strip()
            if "仍具競爭力" in finish_time_level:
                add("步速修正等級", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_competitive_bonus", 8.0), "對標準仍具競爭力")
                strong_signals += 1
            elif "持續快於標準" in finish_time_level:
                add("步速修正等級", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_faster_bonus", 6.0), "持續快於標準")
                strong_signals += 1
            elif "略快於標準" in finish_time_level:
                add("步速修正等級", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_slightly_faster_bonus", 4.0), "略快於標準")
            elif "接近平均" in finish_time_level:
                add("步速修正等級", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_avg_bonus", 1.0), "接近標準平均")
            elif "仍偏慢" in finish_time_level:
                add("步速修正等級", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_slow_pen", -4.0), "修正後仍偏慢")
                strong_signals += 1
            elif "明顯落後" in finish_time_level:
                add("步速修正等級", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_far_behind_pen", -8.0), "修正後明顯落後")
                strong_signals += 1

        energy_trend = str(data.get("energy_trend") or "").strip()
        if energy_trend:
            signals += 1
            reasons.append(f"能量={energy_trend}")
            etail = energy_trend.split("趨勢:")[-1].strip() if "趨勢" in energy_trend else energy_trend
            # NOTE: scoring intentionally keys on the source 趨勢 LABEL, not the raw
            # first-vs-last numbers (ML-tested; numbers REGRESSED). Do not "fix".
            if "上升" in energy_trend and "✅" in energy_trend:
                add("能量趨勢", etail, scoring.SPEED_MICRO_WEIGHTS.get("energy_up_bonus", 4.0), "能量上升")
                strong_signals += 1
            elif "穩定" in energy_trend:
                add("能量趨勢", etail, scoring.SPEED_MICRO_WEIGHTS.get("energy_steady_bonus", 1.5), "能量穩定")
            elif "下降" in energy_trend and "⚠️" in energy_trend:
                add("能量趨勢", etail, scoring.SPEED_MICRO_WEIGHTS.get("energy_down_pen", -4.0), "能量下降")
                strong_signals += 1

        l400_trend = str(data.get("l400_trend") or "").strip()
        if l400_trend:
            signals += 1
            reasons.append(f"L400趨勢={l400_trend}")
            ltail = l400_trend.split("趨勢:")[-1].strip() if "趨勢" in l400_trend else l400_trend
            if "上升" in l400_trend and "✅" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_up_bonus", 3.0), "末段速度走勢改善")
                strong_signals += 1
            elif "穩定" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_steady_bonus", 1.5), "末段速度平穩")
            elif "波動" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_fluctuate_pen", -1.0), "末段速度波動")
            elif "衰退中" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_decline_pen", -4.0), "末段速度衰退")
                strong_signals += 1

        engine_type = str(data.get("engine_type") or "").strip()
        if engine_type:
            signals += 1
            reasons.append(f"引擎={engine_type}")
            etype = engine_type.split("|")[0].strip()
            if "漸進加速型" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_progressive_bonus", 3.0), "漸進加速型")
                strong_signals += 1
            elif "均速型" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_steady_bonus", 1.5), "均速型")
            elif "混合型" in engine_type and "信心: 低" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_mixed_low_conf_pen", -2.0), "混合型＋低信心")
            elif "快開慢收型" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_fast_slow_pen", -2.5), "快開慢收型")
                strong_signals += 1
            if "信心: 低" in engine_type:
                add("引擎信心", "低", scoring.SPEED_MICRO_WEIGHTS.get("engine_low_conf_pen", -1.0), "剖面樣本不足")

        distance_text = str(data.get("best_distance") or "").strip()
        distance = str(self.race_context.get("distance") or "").replace("m", "").strip()
        if distance_text and distance:
            signals += 1
            if distance_text.startswith(f"{distance}m") or f"今仗 {distance}m =" in distance_text:
                add("路程配合", f"{distance}m", scoring.SPEED_MICRO_WEIGHTS.get("dist_match_bonus", 1.5), "今程有往績")
                reasons.append(f"路程配合={distance}m")
            elif "未跑過" in distance_text:
                add("路程配合", f"{distance}m 未跑過", scoring.SPEED_MICRO_WEIGHTS.get("dist_unproven_pen", -1.5), "今程未有往績")
                reasons.append("路程=未跑過")

        score = score_ref[0]

        if signals < 2:
            pdf_races = data.get("pdf_overseas_races", [])
            if pdf_races:
                ovr_score = 60.0
                ovr_reasons = []
                for r in pdf_races:
                    rank_str = str(r.get("rank", ""))
                    cls_str = str(r.get("class_level", "")).upper()
                    try:
                        rank = int(rank_str.split("/")[0]) if "/" in rank_str else int(rank_str)
                    except ValueError:
                        continue

                    if rank <= 3:
                        if "G1" in cls_str or "1級" in cls_str:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_g1_bonus", 6.0)
                            ovr_reasons.append("G1上名")
                        elif "G2" in cls_str or "2級" in cls_str:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_g2_bonus", 4.0)
                            ovr_reasons.append("G2上名")
                        elif "G3" in cls_str or "3級" in cls_str:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_g3_bonus", 3.0)
                            ovr_reasons.append("G3上名")
                        else:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_place_bonus", 1.0)
                            ovr_reasons.append("海外上名")

                if ovr_reasons:
                    final_score = clip_score(ovr_score)
                    self.detail = [{"factor": "海外賽績替代", "value": "、".join(set(ovr_reasons)),
                                    "delta": round(final_score - 60.0, 2), "why": "本地段速資料不足，用海外上名替代"}]
                    return final_score, f"海外賽績速度替代指標 ({', '.join(set(ovr_reasons))})"

            self.detail = [{"factor": "資料不足", "value": f"有效訊號 {signals}/6", "delta": 0.0,
                            "why": "本地段速資料不足兩項，速度分中性60"}]
            return 60.0, "Sectional data incomplete"

        final_score = clip_score(score)
        if final_score >= 76:
            bucket = "Strong race sectional profile"
        elif final_score >= 68:
            bucket = "Positive race sectional profile"
        elif final_score >= 62:
            bucket = "Fair race sectional profile"
        elif final_score >= 60:
            bucket = "Neutral race sectional profile"
        else:
            bucket = "Weak race sectional profile"

        signal_tag = f"signals={signals}"
        if strong_signals:
            signal_tag += f", strong={strong_signals}"
        reasons.append(signal_tag)
        return final_score, f"{bucket} ({'; '.join(reasons)})"
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/features/jockey.py

SHA256: `3c6edeb1908223182ebe55d52ceb13f452e982c64ec0ce115065aa26ba8fdf7b`

```python
from hkjc_racing_engine import scoring
from hkjc_racing_engine.scoring import BaseScorer
from hkjc_racing_engine.features.tier_loader import score_tier


def real_overseas_rows(pdf_races):
    """Drop placeholder rows (all-dash) so an empty overseas table is not treated
    as real overseas history. The PDF extractor emits stub rows of '-' that were
    spuriously bumping unknown jockeys/trainers to the 70 'overseas' tier."""
    rows = []
    for r in pdf_races or []:
        if isinstance(r, dict) and any(
            str(r.get(k, "-")).strip() not in ("-", "", "N/A", "--")
            for k in ("class_level", "rank", "time", "margin")
        ):
            rows.append(r)
    return rows


def continuous_rating(group, raw_name, *, as_of_date=None):
    """兩季實績連續評分（EB shrink）——主要來源；搵唔到先退返層級表。
    香港樣本少（客串騎師／新戰力，例如布浩榮 33 騎、韋紀力 38 騎）就同
    層級先驗做 Bayesian blend，數據儲夠自動過渡去純實績。
    Returns (score, reason) or None."""
    try:
        from hkjc_racing_engine.live_priors import get_jt_ratings, JT_RATING_PARAMS
        hit = get_jt_ratings(as_of_date=as_of_date).lookup(group, raw_name)
    except Exception:
        hit = None
    if hit is None:
        return None
    score = float(hit["score"])
    starts = float(hit["starts"])
    prior_score, _ = score_tier(group, raw_name, "", as_of_date=as_of_date)
    # 只有「有已知先驗」（層級表有列＝客串名將/新加盟戰力）嘅細樣本先 blend；
    # 無先驗嘅細樣本騎師照用純實績（backtest：無差別拉向60會蝕 good/single）。
    if starts < JT_RATING_PARAMS["blend_below"] and float(prior_score) != 60.0:
        w = starts / (starts + JT_RATING_PARAMS["blend_k"])
        score = w * score + (1 - w) * float(prior_score)
        reason = (
            f"香港樣本僅{int(starts)}仗（勝率{hit['win_rate']:.0f}%、上名率{hit['place_rate']:.0f}%），"
            f"混合層級先驗後實績評分{score:.1f}"
        )
        return score, reason
    # 練馬師上季有衰減（season_weights），starts 係加權數，講明先唔誤導
    span = "兩季加權" if group == "trainer" and min(JT_RATING_PARAMS["season_weights"]["trainer"]) < 1.0 else "兩季"
    reason = (
        f"{span}{int(starts)}仗：勝率{hit['win_rate']:.0f}%、"
        f"上名率{hit['place_rate']:.0f}%，實績評分{score:.1f}"
    )
    return score, reason


class JockeyScorer(BaseScorer):
    def compute(self):
        rated = continuous_rating(
            "jockey",
            self.horse_data.get("jockey", ""),
            as_of_date=(self.race_context or {}).get("race_date"),
        )
        if rated is not None:
            self.score, self.reason = rated
            return self.score, self.reason
        self.score, self.reason = score_tier(
            "jockey", self.horse_data.get("jockey", ""), "Neutral Jockey",
            as_of_date=(self.race_context or {}).get("race_date"),
        )

        if self.score == 60.0:
            data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
            pdf_races = real_overseas_rows(data.get("pdf_overseas_races", []))
            if pdf_races:
                has_g1 = any("G1" in str(r.get("class_level", "")).upper() or "1級" in str(r.get("class_level", "")) for r in pdf_races)
                if has_g1:
                    self.score = scoring.JOCKEY_MICRO_WEIGHTS.get("overseas_g1_base", 85.0)
                    self.reason = "Overseas Jockey (G1 Level)"
                else:
                    self.score = scoring.JOCKEY_MICRO_WEIGHTS.get("overseas_base", 70.0)
                    self.reason = "Overseas Jockey"

        return self.score, self.reason
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/features/trainer.py

SHA256: `802761d2f436e419b735e9405f44ef09bb43f212338e69502bb9cf1167a9f0ee`

```python
from hkjc_racing_engine import scoring
from hkjc_racing_engine.scoring import BaseScorer
from hkjc_racing_engine.features.tier_loader import score_tier
from hkjc_racing_engine.features.jockey import real_overseas_rows

class TrainerScorer(BaseScorer):
    def compute(self):
        from hkjc_racing_engine.features.jockey import continuous_rating
        rated = continuous_rating(
            "trainer",
            self.horse_data.get("trainer", ""),
            as_of_date=(self.race_context or {}).get("race_date"),
        )
        if rated is not None:
            self.score, self.reason = rated
            return self.score, self.reason
        as_of_date = (self.race_context or {}).get("race_date")
        self.score, self.reason = score_tier(
            "trainer", self.horse_data.get("trainer", ""), "Neutral Trainer", as_of_date=as_of_date
        )

        if self.score == 60.0:
            data = self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}
            pdf_races = real_overseas_rows(data.get("pdf_overseas_races", []))
            if pdf_races:
                has_g1 = any("G1" in str(r.get("class_level", "")).upper() or "1級" in str(r.get("class_level", "")) for r in pdf_races)
                if has_g1:
                    self.score = scoring.TRAINER_MICRO_WEIGHTS.get("overseas_g1_base", 85.0)
                    self.reason = "Overseas Trainer (G1 Level)"
                else:
                    has_g23 = any("G2" in str(r.get("class_level", "")).upper() or "2級" in str(r.get("class_level", "")) or "G3" in str(r.get("class_level", "")).upper() or "3級" in str(r.get("class_level", "")) for r in pdf_races)
                    if has_g23:
                        self.score = scoring.TRAINER_MICRO_WEIGHTS.get("overseas_g23_base", 75.0)
                        self.reason = "Overseas Trainer (G2/G3 Level)"
                    else:
                        jockey_score, _ = score_tier(
                            "jockey", self.horse_data.get("jockey", ""), "Neutral Jockey",
                            as_of_date=as_of_date,
                        )
                        if jockey_score > 60.0:
                            self.score = jockey_score
                            self.reason = "Overseas Trainer (Aligns with Jockey Tier)"
                        else:
                            self.score = scoring.TRAINER_MICRO_WEIGHTS.get("overseas_base", 70.0)
                            self.reason = "Overseas Trainer"

        return self.score, self.reason
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/features/tier_loader.py

SHA256: `5036ed97395d3f2f8a558459e0b5f98357ea5ecdcbd9c76751375fa80d1d4a04`

```python
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def load_tiers():
    # Resolve relative to this module (…/scripts/racing_engine/features/) so the
    # loader works regardless of the process working directory. Was hardcoded as
    # a CWD-relative path, which raised FileNotFoundError unless run from repo root.
    skill_root = Path(__file__).resolve().parents[3]  # hkjc_wong_choi_auto/
    path = skill_root / "resources" / "05_jockey_trainer_tiers.json"
    return json.loads(path.read_text(encoding="utf-8"))


def tiers_available(as_of_date) -> bool:
    """Point-in-time gate for the hand-maintained tier table.

    ``05_jockey_trainer_tiers.json`` is undated and edited in place, i.e. it is
    always "today's tiers".  Live cards (race date today or later) may use it.
    A historical replay may use it only when the file declares an ``as_of_date``
    on or before the race date; otherwise it is neutral (EXP-20261015-02).
    Unknown race dates are fail-closed.
    """
    from hkjc_racing_engine.live_priors import _parse_as_of_date, is_live_race_date
    if is_live_race_date(as_of_date):
        return True
    requested = _parse_as_of_date(as_of_date)
    table_date = _parse_as_of_date(load_tiers().get("as_of_date"))
    return requested is not None and table_date is not None and table_date <= requested


HISTORICAL_TIER_REASON = "歷史回放：層級表冇該日版本，中性60"


def score_tier(group, raw_name, default_reason, *, as_of_date=None, live=False):
    """Tier lookup.  Pass ``as_of_date`` (the race date) on every scoring path;
    ``live=True`` is only for explicit live-card callers without a context."""
    if not live and not tiers_available(as_of_date):
        return 60.0, HISTORICAL_TIER_REASON
    name = str(raw_name or "").upper()
    for tier in load_tiers().get(group, []):
        if any(str(item).upper() in name for item in tier.get("names", [])):
            score = float(tier["score"])
            # Be explicit when materialized two-season ratings are unavailable:
            # this is the audited tier fallback, not a live empirical estimate.
            reason = f"層級後備實績評分{score:.1f}（{tier['reason']}）"
            return score, reason
    return 60.0, default_reason
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/features/draw.py

SHA256: `a5bb2bd94a47a7c0d4366c735c78661cfb5109bec2ac411e9e00ded8fc9de637`

```python
import re
from hkjc_racing_engine import scoring
from hkjc_racing_engine.rail_draw_context import rail_draw_context_adjustment
from hkjc_racing_engine.scoring import BaseScorer

# 檔位評分 = 位置先驗公式（1-4檔好 / 直路8+好）。
# ⚠️ 2026-07-05 backtest（RICH 131場 + 高覆蓋 60場，harness 重現 production baseline）：
#    將 HKJC 官方檔位數據入評分——無論用 verdict tier(有利/中性/不利)、上位率+35、
#    上位率 steep、定 hybrid——喺 benchmark(good/min) 全部輸畀呢個位置先驗
#    （高覆蓋組 good −5~−7pp、min −5~−8pp），甚至同「一律 neutral」差唔多。
#    原因：官方檔位上位率係細樣本+混質雜訊；排名只需穩定嘅位置梯度，馬匹實力由其餘
#    6 個 7D 維度負責。同 2026-07-02 ML 結論一致。故評分保留先驗；HKJC 官方數據
#    只用於「顯示」(數據判讀 _draw_stats_note + 詳細分析 draw_verdict)，不入評分。
# 舊 _get_draw_bias() 讀自家 draw_bias_stats.csv 亦已移除。

class DrawScorer(BaseScorer):
    def compute(self):
        draw = self.horse_data.get("barrier") or self.horse_data.get("draw")
        try:
            draw_num = int(draw)
        except (ValueError, TypeError):
            return 60.0, "Invalid Draw"

        venue = self.race_context.get("venue", "")
        track = self.race_context.get("track", "")
        dist_str = str(self.race_context.get("distance") or "0")
        m = re.search(r"(\d+)", dist_str)
        distance = int(m.group(1)) if m else 0

        v = str(venue).strip()
        v_low = v.lower().replace(" ", "")
        venue_norm = "沙田" if ("沙田" in v or "shatin" in v_low or v.upper() == "ST") else "跑馬地"
        track_norm = "AWT" if "awt" in str(track).lower() or "dirt" in str(track).lower() or "泥" in str(track) else "Turf"

        is_straight = distance == 1000 and track_norm == "Turf" and venue_norm == "沙田"
        if is_straight:
            p_high = scoring.DRAW_MICRO_WEIGHTS.get("straight_draw_8_plus", 75.0)
            p_mid = scoring.DRAW_MICRO_WEIGHTS.get("straight_draw_5_7", 65.0)
            p_low = scoring.DRAW_MICRO_WEIGHTS.get("straight_draw_1_4", 50.0)
            prior_score = p_high if draw_num >= 8 else (p_mid if draw_num >= 5 else p_low)
        else:
            p_high = scoring.DRAW_MICRO_WEIGHTS.get("turn_draw_1_4", 75.0)
            p_mid = scoring.DRAW_MICRO_WEIGHTS.get("turn_draw_5_8", 65.0)
            p_low = scoring.DRAW_MICRO_WEIGHTS.get("turn_draw_9_plus", 50.0)
            prior_score = p_high if draw_num <= 4 else (p_mid if draw_num <= 8 else p_low)

        is_debut = bool(
            self.horse_data.get("is_debut")
            or self.horse_data.get("debut_runner")
            or self.horse_data.get("career_tag") == "DEBUT"
        )
        context = rail_draw_context_adjustment(self.race_context, draw_num)
        adjustment = float(context.get("adjustment", 0.0)) if not is_debut else 0.0
        self.score = scoring.clip_score(prior_score + adjustment)
        self.reason = (
            f"Prior formula + PIT venue/rail adjustment {adjustment:+.2f}"
            if context.get("applied") and not is_debut
            else "Prior formula"
        )

        return self.score, self.reason
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/rail_draw_context.py

SHA256: `8b0fa9bc79fab37e38860caade2b7a6468dd81089c8397eae470733277833017`

```python
"""Point-in-time rail-relative draw context for the prospective HKJC shadow."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import numpy as np
import pandas as pd

from wongchoi_paths import HK_RACING, is_materialized_file


DATASET = (
    HK_RACING
    / "HKJC_Race_Results_Database"
    / "comprehensive_stats"
    / "rail_draw_results.csv"
)
SHRINK_RUNNERS = 60.0
MIN_RUNNERS = 100
MIN_RACES = 20
ADJUSTMENT_CAP = 4.0
_RAILS = {"A", "A+3", "B", "B+2", "C", "C+3"}


def _integer(value) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def _venue(value) -> str:
    text = str(value or "").replace(" ", "")
    low = text.casefold()
    if "跑馬地" in text or "happyvalley" in low or text.upper() == "HV":
        return "跑馬地"
    if "沙田" in text or "shatin" in low or text.upper() == "ST":
        return "沙田"
    return ""


def _draw_group(value) -> str:
    draw = _integer(value)
    if 1 <= draw <= 4:
        return "inner"
    if 5 <= draw <= 8:
        return "middle"
    if draw >= 9:
        return "outer"
    return "unknown"


def _distance_band(value) -> str:
    distance = _integer(value)
    if 1 <= distance <= 1200:
        return "sprint"
    if distance <= 1650:
        return "middle"
    if distance > 1650:
        return "route"
    return "unknown"


@lru_cache(maxsize=4)
def _read_dataset(path_text: str, modified_ns: int, size: int) -> pd.DataFrame:
    del modified_ns, size
    frame = pd.read_csv(path_text)
    required = {
        "Date", "RaceNo", "Venue", "Track", "Distance", "Rail",
        "FieldSize", "Draw", "Place",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame = frame[frame["Track"].astype(str).eq("Turf")].copy()
    frame["Date"] = frame["Date"].astype(str).str[:10]
    frame["VenueNorm"] = frame["Venue"].map(_venue)
    frame["RailNorm"] = frame["Rail"].astype(str).str.replace(" ", "", regex=False).str.upper()
    frame["DrawGroup"] = frame["Draw"].map(_draw_group)
    frame["DistanceBand"] = frame["Distance"].map(_distance_band)
    field = pd.to_numeric(frame["FieldSize"], errors="coerce").clip(lower=1)
    frame["Residual"] = (
        pd.to_numeric(frame["Place"], errors="coerce").fillna(0.0)
        - np.minimum(3.0, field) / field
    )
    frame["RaceId"] = (
        frame["Date"] + "|" + frame["VenueNorm"] + "|" + frame["RaceNo"].astype(str)
    )
    return frame


def _dataset(path: Path) -> pd.DataFrame:
    if not is_materialized_file(path):
        return pd.DataFrame()
    try:
        info = path.stat()
        return _read_dataset(str(path), info.st_mtime_ns, info.st_size)
    except (OSError, UnicodeError, pd.errors.ParserError):
        return pd.DataFrame()


def rail_draw_context_adjustment(
    race_context: dict,
    barrier,
    *,
    dataset_path: Path | None = None,
) -> dict:
    """Return a bounded pre-race adjustment relative to the generic draw prior."""
    venue = _venue(race_context.get("venue") or race_context.get("racecourse"))
    track_text = " ".join(
        str(race_context.get(key) or "")
        for key in ("track", "surface", "track_type", "venue")
    ).upper()
    rail = str(
        race_context.get("rail")
        or race_context.get("course_rail")
        or race_context.get("course_config")
        or race_context.get("course")
        or ""
    ).replace(" ", "").upper()
    band = _distance_band(race_context.get("distance"))
    group = _draw_group(barrier)
    cutoff = str(race_context.get("race_date") or "")[:10]
    base = {
        "applied": False,
        "adjustment": 0.0,
        "venue": venue,
        "rail": rail,
        "distance_band": band,
        "draw_group": group,
        "cell_runners": 0,
        "cell_races": 0,
        "parent_runners": 0,
        "cutoff": cutoff,
        "formula": "rail excess minus venue-distance parent; shrink=60; cap=±4",
    }
    if (
        not venue or rail not in _RAILS or band == "unknown" or group == "unknown"
        or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", cutoff)
        or any(token in track_text for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))
    ):
        base["reason"] = "missing_or_ineligible_context"
        return base
    history = _dataset(dataset_path or DATASET)
    if history.empty:
        base["reason"] = "rail_history_unavailable"
        return base
    history = history[history["Date"] < cutoff]
    cell = history[
        history["VenueNorm"].eq(venue)
        & history["RailNorm"].eq(rail)
        & history["DistanceBand"].eq(band)
        & history["DrawGroup"].eq(group)
    ]
    parent = history[
        history["VenueNorm"].eq(venue)
        & history["DistanceBand"].eq(band)
        & history["DrawGroup"].eq(group)
    ]
    cell_races = int(cell["RaceId"].nunique())
    base.update(
        cell_runners=int(len(cell)),
        cell_races=cell_races,
        parent_runners=int(len(parent)),
    )
    if len(cell) < MIN_RUNNERS or cell_races < MIN_RACES or len(parent) < MIN_RUNNERS:
        base["reason"] = "insufficient_point_in_time_sample"
        return base
    cell_excess = float(cell["Residual"].sum()) / (len(cell) + SHRINK_RUNNERS)
    parent_excess = float(parent["Residual"].sum()) / (len(parent) + SHRINK_RUNNERS)
    adjustment = float(np.clip(100.0 * (cell_excess - parent_excess), -ADJUSTMENT_CAP, ADJUSTMENT_CAP))
    base.update(
        applied=abs(adjustment) >= 0.01,
        adjustment=round(adjustment, 4),
        cell_shrunk_excess=round(cell_excess, 6),
        parent_shrunk_excess=round(parent_excess, 6),
        reason="stable_point_in_time_rail_cell",
    )
    return base
```

## .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_racing_engine/live_priors.py

SHA256: `c11bc333a0fa5d52612f56bc72ddc916cb2b884b1508b374ada49b36ce973281`

```python
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING, is_materialized_file
STATS_ROOT = HK_RACING / "HKJC_Race_Results_Database" / "comprehensive_stats"
TRAINER_RECENCY_PATH = STATS_ROOT / "experimental" / "trainer_recency_90d_stats.csv"


def _parse_as_of_date(value) -> date | None:
    text = str(value or "").strip().replace("/", "-")
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


_UNKNOWN_DATE_WARNED = False


def _warn_unknown_race_date() -> None:
    """Flag (once per process) that a race was scored without a race date."""
    global _UNKNOWN_DATE_WARNED
    if _UNKNOWN_DATE_WARNED:
        return
    _UNKNOWN_DATE_WARNED = True
    import sys
    print(
        "⚠️ temporal guard: race_date 未知（Logic 冇 race_date、資料夾冇 YYYY-MM-DD 前綴）"
        " —— 最新季度騎練統計／層級表一律當中性（fail-closed）。",
        file=sys.stderr,
    )


def is_live_race_date(as_of_date) -> bool:
    """True only for a known race date that is today or later (live card).

    Unknown dates are NOT live: an archived Logic without ``race_date`` used to
    be treated as live and silently read the latest-season snapshots (fail-open,
    EXP-20261015-02).
    """
    requested = _parse_as_of_date(as_of_date)
    if requested is None:
        _warn_unknown_race_date()
        return False
    return requested >= date.today()


def temporal_source_is_safe(source, as_of_date=None) -> bool:
    """Reject current/full-season priors when replaying a historical race.

    Live/current-date scoring may use the latest materialized pre-race files.
    Historical scoring requires an explicitly injected point-in-time source
    whose cutoff matches that meeting date.  An unknown race date is unsafe
    (fail-closed) and is flagged on stderr.
    """
    requested = _parse_as_of_date(as_of_date)
    if requested is None:
        # No date = cannot prove the race is live.  Allowing it let every
        # caller that skipped `race_date` read the full-season snapshot,
        # including the race's own result (騎練分 in-race AUC +0.016,
        # EXP-20261014-10).  Fail closed and say so once per process.
        _warn_missing_as_of_date()
        return False
    if requested >= date.today():
        return True
    if requested is None:
        return False
    mode = str(getattr(source, "temporal_mode", "") or "")
    source_date = _parse_as_of_date(getattr(source, "as_of_date", None))
    return mode == "point_in_time" and source_date == requested


_MISSING_AS_OF_WARNED = False


def _warn_missing_as_of_date() -> None:
    global _MISSING_AS_OF_WARNED
    if _MISSING_AS_OF_WARNED:
        return
    _MISSING_AS_OF_WARNED = True
    print(
        "⚠️ HKJC 騎練 prior：race_context 冇 race_date，當歷史場次處理（中性）。"
        "live 評分要經 orchestrator 寫入 race_date。",
        file=sys.stderr,
    )


class EmbeddedLogicPrior:
    """Aggregates embedded in archived Logic files carry no as-of provenance."""

    temporal_mode = "embedded_logic_aggregate"
    as_of_date = None


EMBEDDED_LOGIC_PRIOR = EmbeddedLogicPrior()


class EmptyRatings:
    temporal_mode = "historical_guard_neutral"
    as_of_date = None

    @staticmethod
    def lookup(group: str, raw_name: str):
        del group, raw_name
        return None


class EmptyTrainerSignalPriors:
    temporal_mode = "historical_guard_neutral"
    as_of_date = None

    def __init__(self) -> None:
        self.combo = {}
        self.jockey_distance = {}
        self.trainer_distance = {}
        self.jockey_change = {}


_EMPTY_RATINGS = EmptyRatings()
_EMPTY_TRAINER_SIGNAL_PRIORS = EmptyTrainerSignalPriors()


def empty_trainer_signal_priors() -> EmptyTrainerSignalPriors:
    """Return the shared neutral object used by the historical-date guard."""
    return _EMPTY_TRAINER_SIGNAL_PRIORS

_SEASON_STATS_RE = re.compile(r"^\d{2}_\d{2}$")
_FALLBACK_SEASONS = ("24_25", "25_26")


def _season_stats_dirs(root: Path = STATS_ROOT) -> list[Path]:
    """Return every materialized stats season instead of freezing at 25/26.

    The two historical seasons remain the safe fallback when a cloud-backed
    directory cannot be listed.  Newly generated seasons are picked up by the
    next scoring process without changing model weights.
    """
    try:
        found = sorted(
            path for path in root.iterdir()
            if path.is_dir() and _SEASON_STATS_RE.fullmatch(path.name)
        )
    except OSError:
        found = []
    if found:
        return found
    return [root / season for season in _FALLBACK_SEASONS]


def _general_prior_paths(relative_path: str) -> list[Path]:
    return [season_dir / relative_path for season_dir in _season_stats_dirs()]


GENERAL_PRIOR_FILES = {
    "combo": _general_prior_paths("general_pre_race_priors/jockey_trainer_combo_priors.csv"),
    "jockey_distance": _general_prior_paths("jockey_distance_stats.csv"),
    "trainer_distance": _general_prior_paths("trainer_distance_stats.csv"),
    "jockey_change": _general_prior_paths("general_pre_race_priors/jockey_change_priors.csv"),
    "jockey_draw": _general_prior_paths("jockey_draw_performance.csv"),
}


# 所有已生成賽季 master stats → 逐個騎師/練馬師連續實績評分（取代舊人手層級表做主要來源）。
# ML 驗證（2026-07-08，15賽日/153場 10/5 train-test）：以下參數（A7 組合）
# FULL gold 3.9→6.5 / good 22.9→27.5 / champ 24.8→27.5 / t3c 54.2→55.6 / min 持平，
# 代價 single 87.6→84.3。負面縮放（騎師×0.5、練馬師×0.25＋floor 58）係保 single
# 嘅關鍵；再狠嘅版本 TEST 倒退。
JT_RATING_PARAMS = {
    "k": 100.0,            # EB shrink 樣本
    "a_place": 0.5,        # 上名率超額 → 分數
    "b_win": 0.6,          # 勝率超額 → 分數
    "jockey_neg_scale": 0.5,
    "trainer_neg_scale": 0.25,
    "trainer_floor": 58.0,
    # 兩季 EB：按「季齡」加權（本季、上季），兩季前唔用。
    # 練馬師上季×0.3：馬房狀態季節性強（例：沈集成 24/25 勝率7.8% → 25/26 12.5%
    # 爭榜首），本季加權先反映到；backtest TEST 完全一致、TRAIN 只 1-2 場雜訊差。
    # 騎師唔衰減（測過上季 .5 無得益）。
    # ⚠️ 2026-10-10（EXP-20261010-01）：之前寫死標籤 "24_25" 做舊季，換季之後
    # 25/26 同 26/27 都當 ×1.0、24/25 仲喺度，「本季加權」靜靜失效。
    "season_weights": {"trainer": (1.0, 0.3), "jockey": (1.0, 1.0)},
    # 細樣本×層級先驗 Bayesian blend：預設熄（blend_below=0）。
    # Backtest 證實開咗會蝕 TEST good −3.7pp（主要係布浩榮呢類「有tier但HK數據差」
    # 被拉高）。真正一次性客串本身無 master-stats row → 已自動 fallback 層級表/海外
    # G1 邏輯；有少量數據嘅新騎師交俾 EB shrink（自然貼近60中性）。
    "blend_below": 0.0,
    "blend_k": 100.0,
}

def season_tag_for_date(day) -> str:
    """HKJC season tag ("26_27") for a date; the season turns over in August."""
    if isinstance(day, str):
        day = date.fromisoformat(day[:10])
    start = day.year if day.month >= 8 else day.year - 1
    return f"{start % 100:02d}_{(start + 1) % 100:02d}"


def _current_season_tag() -> str:
    """Season the live snapshot is scored in (patched by replay tests)."""
    return season_tag_for_date(date.today())


def season_weight(group: str, season_tag: str, current_tag: str) -> float:
    """Weight for one season's J/T record by its age relative to ``current_tag``."""
    weights = JT_RATING_PARAMS["season_weights"][group]
    try:
        age = int(current_tag[:2]) - int(str(season_tag)[:2])
    except (TypeError, ValueError):
        return 0.0
    return float(weights[age]) if 0 <= age < len(weights) else 0.0


def _master_stats_paths(group: str) -> list[tuple[Path, str]]:
    return [
        (season_dir / f"{group}_master_stats.csv", season_dir.name)
        for season_dir in _season_stats_dirs()
    ]


MASTER_STATS_FILES = {
    "jockey": _master_stats_paths("jockey"),
    "trainer": _master_stats_paths("trainer"),
}


def _is_materialized_file(path: Path) -> bool:
    """Compatibility alias for the shared cloud-materialization check."""
    return is_materialized_file(path)


def _read_prior_csv(path: Path, required_columns: tuple[str, ...]) -> pd.DataFrame | None:
    if not _is_materialized_file(path):
        return None
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, UnicodeError, pd.errors.ParserError):
        return None
    if any(column not in frame.columns for column in required_columns):
        return None
    return frame


_PRIOR_SOURCE_MANIFEST: list[dict] | None = None
_PRIOR_SOURCE_MANIFEST_KEY: tuple[str, ...] | None = None


def prior_source_manifest() -> list[dict]:
    """Small reproducibility manifest; never forces a cloud download."""
    global _PRIOR_SOURCE_MANIFEST, _PRIOR_SOURCE_MANIFEST_KEY
    paths = {path for group in GENERAL_PRIOR_FILES.values() for path in group}
    paths.update(path for group in MASTER_STATS_FILES.values() for path, _weight in group)
    cache_key = tuple(sorted(str(path) for path in paths))
    if _PRIOR_SOURCE_MANIFEST is not None and _PRIOR_SOURCE_MANIFEST_KEY == cache_key:
        return [dict(row) for row in _PRIOR_SOURCE_MANIFEST]
    rows = []
    for path in sorted(paths):
        try:
            info = path.stat()
            materialized = _is_materialized_file(path)
            size = info.st_size
            modified_ns = info.st_mtime_ns
        except OSError:
            materialized = False
            size = 0
            modified_ns = 0
        try:
            label = str(path.relative_to(STATS_ROOT))
        except ValueError:
            label = path.name
        rows.append(
            {
                "source": label,
                "materialized": materialized,
                "size": size,
                "modified_ns": modified_ns,
            }
        )
    _PRIOR_SOURCE_MANIFEST = rows
    _PRIOR_SOURCE_MANIFEST_KEY = cache_key
    return [dict(row) for row in rows]


class JockeyTrainerRatings:
    """{name: {score, starts, win_rate, place_rate}}，EB shrink 連續評分。"""

    def __init__(self) -> None:
        self.temporal_mode = "latest_season_snapshot"
        self.as_of_date = None
        self.jockey = self._build("jockey")
        self.trainer = self._build("trainer")

    def _build(self, group: str) -> dict[str, dict]:
        p = JT_RATING_PARAMS
        col = "Jockey" if group == "jockey" else "Trainer"
        neg_scale = p["jockey_neg_scale"] if group == "jockey" else p["trainer_neg_scale"]
        floor = 0.0 if group == "jockey" else p["trainer_floor"]
        frames = []
        current = _current_season_tag()
        for path, tag in MASTER_STATS_FILES[group]:
            season_w = season_weight(group, tag, current)
            if season_w <= 0:
                continue
            df_season = _read_prior_csv(path, (col, "Wins", "Starts", "Places"))
            if df_season is None:
                continue
            for c in ("Wins", "Starts", "Places"):
                df_season[c] = pd.to_numeric(df_season[c], errors="coerce").fillna(0.0) * season_w
            frames.append(df_season[[col, "Wins", "Starts", "Places"]])
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        df = df.groupby(col)[["Wins", "Starts", "Places"]].sum().reset_index()
        total_starts = float(df["Starts"].sum()) or 1.0
        g_win = float(df["Wins"].sum()) / total_starts
        g_place = float(df["Places"].sum()) / total_starts
        out: dict[str, dict] = {}
        for row in df.to_dict(orient="records"):
            starts = float(row["Starts"] or 0.0)
            if starts <= 0:
                continue
            win_sh = (float(row["Wins"]) + p["k"] * g_win) / (starts + p["k"])
            place_sh = (float(row["Places"]) + p["k"] * g_place) / (starts + p["k"])
            delta = p["b_win"] * (win_sh - g_win) * 100 + p["a_place"] * (place_sh - g_place) * 100
            if delta < 0:
                delta *= neg_scale
            score = 60.0 + delta
            if floor:
                score = max(score, floor)
            out[str(row[col]).strip()] = {
                "score": max(0.0, min(100.0, score)),
                "starts": starts,
                "win_rate": float(row["Wins"]) / starts * 100.0,
                "place_rate": float(row["Places"]) / starts * 100.0,
            }
        return out

    def lookup(self, group: str, raw_name: str) -> dict | None:
        table = self.jockey if group == "jockey" else self.trainer
        name = str(raw_name or "").strip()
        if not name:
            return None
        hit = table.get(name)
        if hit is not None:
            return hit
        for key, value in table.items():
            if key and (key in name or name in key):
                return value
        return None


_JT_RATINGS: JockeyTrainerRatings | None = None
_RECENCY_TRAINER_RATINGS = None


def get_jt_ratings(as_of_date=None):
    global _JT_RATINGS
    if _JT_RATINGS is None:
        _JT_RATINGS = JockeyTrainerRatings()
    if not temporal_source_is_safe(_JT_RATINGS, as_of_date):
        return _EMPTY_RATINGS
    return _JT_RATINGS


class RecencyTrainerRatings:
    """Shadow-only 90-day date-decayed trainer master ratings."""

    temporal_mode = "latest_recency_snapshot"

    def __init__(self) -> None:
        self.as_of_date = None
        self.latest_result_date = None
        self.half_life_days = None
        self.trainer = self._build()

    def _build(self) -> dict[str, dict]:
        required = (
            "Trainer", "Wins", "Starts", "Places", "AsOfDate",
            "LatestResultDate", "HalfLifeDays",
        )
        frame = _read_prior_csv(TRAINER_RECENCY_PATH, required)
        if frame is None or frame.empty:
            return {}
        self.as_of_date = str(frame["AsOfDate"].iloc[0])
        self.latest_result_date = str(frame["LatestResultDate"].iloc[0])
        self.half_life_days = int(float(frame["HalfLifeDays"].iloc[0]))
        for column in ("Wins", "Starts", "Places"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        total = float(frame["Starts"].sum()) or 1.0
        global_win = float(frame["Wins"].sum()) / total
        global_place = float(frame["Places"].sum()) / total
        params = JT_RATING_PARAMS
        output = {}
        for row in frame.to_dict("records"):
            starts = float(row["Starts"] or 0.0)
            if starts <= 0:
                continue
            win_shrunk = (float(row["Wins"]) + params["k"] * global_win) / (starts + params["k"])
            place_shrunk = (float(row["Places"]) + params["k"] * global_place) / (starts + params["k"])
            delta = (
                params["b_win"] * (win_shrunk - global_win) * 100.0
                + params["a_place"] * (place_shrunk - global_place) * 100.0
            )
            if delta < 0:
                delta *= params["trainer_neg_scale"]
            score = max(float(params["trainer_floor"]), 60.0 + delta)
            output[str(row["Trainer"]).strip()] = {
                "score": max(0.0, min(100.0, score)),
                "starts": starts,
                "win_rate": float(row["Wins"]) / starts * 100.0,
                "place_rate": float(row["Places"]) / starts * 100.0,
                "as_of_date": self.as_of_date,
                "latest_result_date": self.latest_result_date,
                "half_life_days": self.half_life_days,
            }
        return output

    def lookup(self, raw_name: str) -> dict | None:
        name = str(raw_name or "").strip()
        if not name:
            return None
        hit = self.trainer.get(name)
        if hit is not None:
            return hit
        for key, value in self.trainer.items():
            if key and (key in name or name in key):
                return value
        return None


def get_recency_trainer_rating(raw_name: str, *, as_of_date=None) -> dict | None:
    """Return the registered shadow rating; historical latest-file use is blocked."""
    global _RECENCY_TRAINER_RATINGS
    if _RECENCY_TRAINER_RATINGS is None:
        _RECENCY_TRAINER_RATINGS = RecencyTrainerRatings()
    source = _RECENCY_TRAINER_RATINGS
    if not temporal_source_is_safe(source, as_of_date):
        return None
    return source.lookup(raw_name)


class TrainerSignalPriors:
    def __init__(self) -> None:
        self.temporal_mode = "latest_season_snapshot"
        self.as_of_date = None
        self.combo = self._load_grouped(GENERAL_PRIOR_FILES["combo"], ["Jockey", "Trainer"])
        self.jockey_distance = self._load_grouped(GENERAL_PRIOR_FILES["jockey_distance"], ["Jockey", "Distance"])
        self.trainer_distance = self._load_grouped(GENERAL_PRIOR_FILES["trainer_distance"], ["Trainer", "Distance"])
        self.jockey_change = self._load_jockey_change()

    def _load_grouped(self, paths: list[Path], keys: list[str]) -> dict[tuple[str, ...], dict]:
        required = tuple(keys) + ("Wins", "Starts", "Places")
        frames = [frame for path in paths if (frame := _read_prior_csv(path, required)) is not None]
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        for column in ("Wins", "Starts", "Places"):
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
        grouped = df.groupby(keys, dropna=False)[["Wins", "Starts", "Places"]].sum().reset_index()
        records: dict[tuple[str, ...], dict] = {}
        for row in grouped.to_dict(orient="records"):
            starts = float(row.get("Starts", 0.0) or 0.0)
            wins = float(row.get("Wins", 0.0) or 0.0)
            places = float(row.get("Places", 0.0) or 0.0)
            key = tuple(str(row[item]).strip() for item in keys)
            records[key] = {
                "starts": starts,
                "wins": wins,
                "places": places,
                "win_rate": (wins / starts * 100.0) if starts else 0.0,
                "place_rate": (places / starts * 100.0) if starts else 0.0,
            }
        return records

    def _load_jockey_change(self) -> dict[bool, dict]:
        required = ("JockeyChanged", "Wins", "Starts", "Places")
        frames = [
            frame
            for path in GENERAL_PRIOR_FILES["jockey_change"]
            if (frame := _read_prior_csv(path, required)) is not None
        ]
        if not frames:
            return {}
        df = pd.concat(frames, ignore_index=True)
        df["Wins"] = pd.to_numeric(df["Wins"], errors="coerce").fillna(0.0)
        df["Starts"] = pd.to_numeric(df["Starts"], errors="coerce").fillna(0.0)
        df["Places"] = pd.to_numeric(df["Places"], errors="coerce").fillna(0.0)
        grouped = df.groupby("JockeyChanged", dropna=False)[["Wins", "Starts", "Places"]].sum().reset_index()
        records: dict[bool, dict] = {}
        for row in grouped.to_dict(orient="records"):
            changed = str(row["JockeyChanged"]).strip().lower() == "true"
            starts = float(row["Starts"] or 0.0)
            wins = float(row["Wins"] or 0.0)
            places = float(row["Places"] or 0.0)
            records[changed] = {
                "starts": starts,
                "wins": wins,
                "places": places,
                "win_rate": (wins / starts * 100.0) if starts else 0.0,
                "place_rate": (places / starts * 100.0) if starts else 0.0,
            }
        return records
```

## engine_core.py：計分方法及傳遞依賴

抽取 63 個方法。

### _class_score（第 246 行）

```python
def _class_score(self, _features):
        if self._is_debut():
            self.reason_codes.append("debut_class_unknown")
            return 60, "初出馬未有正式班際賽績，級數優勢暫按中性60分。", "career_tag"
        score = 60
        notes = []
        starts = parse_float(self._value("career_race_starts") or self.horse_data.get("career_race_starts"))
        season = self._season_record()
        career_tag = self._clean(self._value("career_tag") or self.horse_data.get("career_tag") or "")
        if career_tag == "ESTABLISHED":
            score += scoring.CLASS_MICRO_WEIGHTS.get("established_bonus", 4.0)
            notes.append("已建立賽駒")
        if starts is not None:
            if starts >= 20:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_20_bonus", 4.0)
                notes.append("經驗充足")
            elif starts <= 8:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_8_pen", -2.0)
                notes.append("樣本薄")
        # A new season's 0-0-0-0 is no evidence, not an unsuccessful campaign.
        if season and season["starts"] > 0:
            if season["places"] >= 3:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_3_bonus", 4.0)
                notes.append("季內有交代")
            elif season["places"] == 0:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_0_pen", -4.0)
                self.risk_flags.append("class_edge_unproven")
                notes.append("季內未上名")
        # 短而準：分數行頭，訊號做 tag；無訊號＝各項中性
        note = f"班次分{clip_score(score):.0f}：" + ("、".join(notes) if notes else "經驗／季內均中性")
        return clip_score(score), note, "career_context"
```

### _distance_suitability_adjustment（第 278 行）

```python
def _distance_suitability_adjustment(self, features, matrix_scores):
        """Keep V1 live and calculate surface-specific V2 as a shadow.

        New Logic carries a PIT within-horse residual: target-distance form
        minus the same horse's all-distance form on the same surface.  Older
        Logic has no V2 payload and therefore exposes no shadow.  The official
        adjustment remains the exact V1 migration, preserving reproducibility
        while new meetings collect genuinely unseen V2 outcomes.
        """
        neutral = {
            "raw_adjustment": 0.0,
            "signal": "neutral",
            "same_distance_starts": 0,
            "same_distance_places": 0,
            "note": "同程未有可入分實績，路程適性調整為0。",
        }
        if self._is_debut():
            neutral["signal"] = "debut_neutral"
            neutral["note"] = "初出馬未有同程正式賽績，路程適性調整為0。"
            return neutral

        v2 = self._distance_suitability_v2_component()
        v2_shadow = None
        if v2["available"]:
            profile = scoring.DISTANCE_SUITABILITY_V2_PROFILES[v2["surface"]]
            weight = float(profile["weight"])
            cap = float(profile["cap"])
            component = 60.0 + max(-cap, min(cap, float(v2["score"]) - 60.0))
            base_raw = float(self._ability_score(matrix_scores))
            candidate_raw = (1.0 - weight) * base_raw + weight * component
            adjustment = round(candidate_raw - base_raw, 6)
            v2_shadow = {
                "candidate_raw_adjustment": adjustment,
                "status": "prospective_shadow_pending_primary_gate",
                "score": round(float(v2["score"]), 2),
                "surface": v2["surface"],
                "source": v2["source"],
                "target_effective_n": v2["target_effective_n"],
                "surface_effective_n": v2["surface_effective_n"],
                "profile": dict(profile),
                "component_score": round(component, 2),
            }

        # V1 remains official until the prospective V2 primary gate passes.
        record = self._same_distance_record()
        if not record or record["starts"] <= 0:
            if v2_shadow is not None:
                neutral["v2_shadow"] = v2_shadow
            return neutral
        if record["places"] > 0:
            micro = scoring.DISTANCE_SUITABILITY_MICRO_WEIGHTS["same_dist_place_bonus"]
            signal = "same_distance_placed"
            note = "同程有上名實績，獨立路程適性調整為正面。"
        else:
            micro = scoring.DISTANCE_SUITABILITY_MICRO_WEIGHTS["same_dist_unplaced_pen"]
            signal = "same_distance_unplaced"
            note = "同程已有樣本但未上名，獨立路程適性調整為負面。"

        clean_class = float(features.get("class_score", 60.0))
        weight_score = float(features.get("weight_score", 60.0))
        clean_dimension = float(matrix_scores.get("class_advantage", 60.0))
        legacy_class = clip_score(clean_class + micro)
        legacy_dimension = round(clip_score(legacy_class * 0.75 + weight_score * 0.25), 2)
        raw_adjustment = round(
            (legacy_dimension - clean_dimension) * MATRIX_WEIGHTS["class_advantage"],
            6,
        )
        output = {
            "raw_adjustment": raw_adjustment,
            "signal": signal,
            "same_distance_starts": int(record["starts"]),
            "same_distance_places": int(record["places"]),
            "micro_signal": micro,
            "note": note,
        }
        if v2_shadow is not None:
            output["v2_shadow"] = v2_shadow
        return output
```

### _distance_suitability_v2_component（第 357 行）

```python
def _distance_suitability_v2_component(self):
        """Parse the deterministic V2 payload transported by Facts to Logic."""
        text = self._clean(self._value("distance_suitability_v2") or "")
        score_match = re.search(r"今場=.*?\s(\d+(?:\.\d+)?)分", text)
        target_match = re.search(r"目標有效樣本=(\d+(?:\.\d+)?)", text)
        surface_n_match = re.search(r"場地基準有效樣本=(\d+(?:\.\d+)?)", text)
        source_match = re.search(r"採用來源=([^|]+)", text)
        if self._is_happy_valley_context():
            surface = "HV_TURF"
        elif self._is_sha_tin_turf_context():
            surface = "ST_TURF"
        else:
            surface = "ST_AWT"
        score = parse_float(score_match.group(1)) if score_match else None
        return {
            "available": score is not None,
            "score": round(clip_score(score if score is not None else 60.0), 2),
            "surface": surface,
            "target_effective_n": round(float(parse_float(target_match.group(1)) or 0.0), 2) if target_match else 0.0,
            "surface_effective_n": round(float(parse_float(surface_n_match.group(1)) or 0.0), 2) if surface_n_match else 0.0,
            "source": source_match.group(1).strip() if source_match else "missing_neutral",
        }
```

### _distance_score（第 380 行）

```python
def _distance_score(self, _features):
        best_distance = self._value("best_distance")
        distance = str(self.race_context.get("distance") or "")
        text = self._text("best_distance", "season_stats", "course_record")
        # 同程往績一定要由「同程 (…)」讀。舊 code 用 parse_record(text) 掃第一個
        # 四元組，而 season_stats 個字串係「季內 (…) | 同程 (…) | 同場同程 (…)」
        # ——第一個係**季內**，所以路程分一路用緊季內成績做同程證據。09-06 全場
        # 季內 (0-0-0-0)（新季），六匹馬全部跌落「樣本有限 66 分」。
        record = self._same_distance_record()
        best_text = self._clean(best_distance or "")
        distance_token = distance.replace("m", "").strip()
        direct_match = best_text.startswith(f"{distance_token}m") or best_text.startswith(distance)
        # `season_stats` is now rebuilt from complete point-in-time history.
        # It must outrank the legacy `best_distance` sentence, which can still
        # say "未跑過" when the older six-run summary omitted earlier starts.
        if record and record["starts"] > 0:
            if record["places"] > 0:
                return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_place_base", 72.0), \
                    "完整歷史顯示同程已有上名紀錄，路程適性評為72分。", "season_stats"
            self.risk_flags.append("distance_record_weak")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("same_dist_unplaced_base", 54.0), \
                "完整歷史顯示同程有樣本但未見上名支持，路程分54分。", "season_stats"
        if "未跑過" in best_text:
            if "相近上名經驗" in best_text:
                return scoring.DISTANCE_MICRO_WEIGHTS.get("similar_place_base", 62.0), "今場路程未有直接實績，但相近路程有上名旁證，路程分62分。", "best_distance"
            if self._is_debut():
                self.reason_codes.append("debut_distance_unproven")
                return scoring.DISTANCE_MICRO_WEIGHTS.get("debut_base", 58.0), "初出馬未經今仗路程實戰驗證，路程分保守58分。", "career_tag"
            self.risk_flags.append("distance_unproven")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("unproven_base", 56.0), "今場路程未有直接實績，路程分56分。", "best_distance"
        if best_distance and distance and direct_match:
            starts = record["starts"] if record else None
            if starts and record["places"] > 0:
                return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_place_base", 72.0), f"路程資料見今仗距離及上名紀錄，路程適性評為72分。", "best_distance"
            return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_small_sample_base", 66.0), "最佳路程欄與今仗距離吻合，但樣本有限，路程分66分。", "best_distance"
        if self._is_debut():
            self.reason_codes.append("debut_distance_unproven")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("debut_base", 58.0), "初出馬未經今仗路程實戰驗證，路程分保守58分。", "career_tag"
        return scoring.DISTANCE_MICRO_WEIGHTS.get("neutral_base", 60.0), "路程證據不足，按中性60分。", "missing_neutral"
```

### _track_going_score（第 420 行）

```python
def _track_going_score(self, _features):
        # 場地適性一向中性 60。原因（2026-07-10 檢討 + pit_backtest 驗證）：
        #  1. HKJC 抽取根本冇真實地面適性數據（good/soft/course record 係 AU 承襲、恒空；
        #     race_results 個 Going 欄裝錯咗班次字串）。
        #  2. 之前用 track_bias（場地偏差）＋ draw_verdict 嚟計係「方向盲」——只 grep
        #     「不利」就扣分，唔理今匹馬實際排內定排外，令排內檔（本應受惠）嘅馬喺偏內
        #     場地都照扣；而且檔位／場地偏差已由「檔位與走位」維度正正經經計算，喺呢度
        #     再扣＝同一 draw 訊號扣兩次（double deduct）。
        #  中性化後 pit_backtest 零倒退、good/champ 反而微升（draw 訊號集中喺 race_shape
        #  一處，唔再互相污染）。段速維度靠 speed_score 差異區分，場地保持 0.35 權重
        #  只作壓縮（回測最佳），唔再引入方向盲扣分。
        return scoring.TRACK_MICRO_WEIGHTS.get("neutral_base", 60.0), \
            "HKJC 未有可靠場地適性數據；檔位／場地偏差已於「檔位與走位」維度計算，此處不重複扣分，中性60分。", \
            "policy_neutral"
```

### _weight_score（第 435 行）

```python
def _weight_score(self, _features):
        # 負磅分只計讓磅官嘅負磅（EXP-20261010-04）。馬匹體重趨勢係健康訊號，已經喺
        # risk_score 計（而且方向相反：轉輕喺健康扣分、喺度以前加分），所以唔再重複計。
        # 分界用實際負磅 = 負磅 − 見習減磅。
        weight = parse_float(self._value("weight_carried") or self._value("weight"))
        if weight is None:
            return 60, "負磅資料不足，負磅分60分。", "missing_neutral"
        allowance = parse_float(self._value("jockey_allowance")) or 0.0
        carried = weight - allowance
        claim = f"（負磅 {weight:.0f} 減見習 {allowance:.0f}）" if allowance else ""
        score = scoring.WEIGHT_MICRO_WEIGHTS.get("base", 64.0)
        note = f"今仗實際負磅{carried:.0f}磅{claim}，屬中游負磅，讓磅官冇特別意見，負磅分{score:.0f}分。"
        if carried <= 120:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("light_weight_base", 54.0)
            note = (f"今仗實際負磅{carried:.0f}磅{claim}較輕 —— 負磅係讓磅官嘅評分，輕磅即係"
                    f"官方評分低，負磅分{score:.0f}分。")
        elif carried >= 132:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("heavy_weight_base", 70.0)
            note = (f"今仗實際負磅{carried:.0f}磅{claim}屬頂磅 —— 讓磅官視佢為全場最好嘅馬，"
                    f"而實測加磅加得唔夠狠（0.389 分/kg vs 慣例 0.5），"
                    f"負磅分{score:.0f}分。")
        return clip_score(score), note, "weight_carried"
```

### _consistency_score（第 458 行）

```python
def _consistency_score(self, features):
        form = str(self.horse_data.get("last_6_finishes") or "")
        # 0 is a non-completion/status marker, not a finishing position.
        finishes = [int(item) for item in re.findall(r"\b\d+\b", form) if int(item) > 0][:6]
        if self._is_debut():
            prep = self._prep_score()
            score = scoring.CONSISTENCY_MICRO_WEIGHTS.get("debut_base", 58.0) + (prep - 60) * scoring.CONSISTENCY_MICRO_WEIGHTS.get("debut_prep_mult", 0.35)
            note = f"初出馬以晨操備戰穩定性代替正式近績，備戰分{prep:.0f}，穩定性分{score:.1f}。"
            return score, note, "trackwork_digest"
        if len(finishes) >= 3:
            places = sum(1 for rank in finishes if 1 <= rank <= 3)
            poor = sum(1 for rank in finishes if rank >= 8)
            score = scoring.CONSISTENCY_MICRO_WEIGHTS.get("base", 58.0) + places * scoring.CONSISTENCY_MICRO_WEIGHTS.get("place_mult", 7.0) - poor * scoring.CONSISTENCY_MICRO_WEIGHTS.get("poor_mult", 5.0)
            note = f"近{len(finishes)}仗有{places}次前三、{poor}次八名或以後，穩定性分{clip_score(score):.1f}。"
            return score, note, "last_6_finishes"
        if features.get("form_score", 60) >= 70:
            return scoring.CONSISTENCY_MICRO_WEIGHTS.get("good_form_base", 66.0), "近績樣本少但名次訊號正面，穩定性分66分。", "last_6_finishes"
        return scoring.CONSISTENCY_MICRO_WEIGHTS.get("neutral_base", 60.0), "近績樣本不足，穩定性分60分。", "missing_neutral"
```

### _is_foreign_runner（第 477 行）

```python
def _is_foreign_runner(self):
        """True for a visiting international runner: has real overseas race rows
        but no HKJC form. Such horses must NOT be penalised for missing HK-only
        data (medical/coverage) — absence here is 'data N/A', not 'bad news'."""
        pdf = self.data.get("pdf_overseas_races") or self.horse_data.get("pdf_overseas_races") or []
        real = any(
            isinstance(r, dict) and any(
                str(r.get(k, "-")).strip() not in ("-", "", "N/A", "--")
                for k in ("class_level", "rank", "time", "margin")
            )
            for r in pdf
        )
        if not real:
            return False
        hk_form = str(self._value("last_6_finishes") or "").strip()
        has_hk_form = hk_form not in ("", "N/A") and any(c.isdigit() for c in hk_form)
        return not has_hk_form
```

### _risk_score（第 562 行）

```python
def _risk_score(self, features):
        score = scoring.RISK_MICRO_WEIGHTS.get("base", 68.0)
        notes = []
        medical = self._text("medical_flags")
        foreign = self._is_foreign_runner()
        if "無醫療事故" in medical:
            notes.append("醫療欄未見事故")
        elif foreign:
            # Visiting runner with no HKJC medical record — treat as neutral, not a risk.
            notes.append("海外賽駒，本會醫療欄無記錄，按中性處理")
        else:
            score += scoring.RISK_MICRO_WEIGHTS.get("medical_unknown_pen", -8.0)
            self.risk_flags.append("medical_record_unknown")
            notes.append("醫療欄資料不足")
        if self._is_debut():
            score += scoring.RISK_MICRO_WEIGHTS.get("debut_pen", -5.0)
            self.risk_flags.append("debut_race_experience_unknown")
            notes.append("初出缺正式賽經驗")
        if features.get("draw_score", 60) < 55:
            score += scoring.RISK_MICRO_WEIGHTS.get("draw_pressure_pen", -5.0)
            self.risk_flags.append("draw_pressure")
            notes.append("檔位分偏低")
        if features.get("distance_score", 60) < 58:
            score += scoring.RISK_MICRO_WEIGHTS.get("distance_unproven_pen", -4.0)
            record = self._same_distance_record()
            if record and record["starts"] > 0:
                if "distance_record_weak" not in self.risk_flags:
                    self.risk_flags.append("distance_record_weak")
                notes.append("同程紀錄未見上名")
            else:
                self.risk_flags.append("distance_unproven")
                notes.append("路程證明不足")
        return clip_score(score), "、".join(notes) + f"，風險分{clip_score(score):.1f}。", "medical_flags"
```

### _confidence_score（第 596 行）

```python
def _confidence_score(self, features):
        present = 0
        important_sources = ("trackwork_digest", "draw_verdict", "weight_carried", "last_6_finishes", "season_stats")
        for key in important_sources:
            if self._value(key) not in (None, "", "N/A"):
                present += 1
        score = scoring.CONFIDENCE_MICRO_WEIGHTS.get("base", 48.0) + present * scoring.CONFIDENCE_MICRO_WEIGHTS.get("present_mult", 6.0)
        bits = [f"可用資料覆蓋{present}/{len(important_sources)}項"]
        if self._value("jockey_combo_block"):
            bonus = scoring.CONFIDENCE_MICRO_WEIGHTS.get("jockey_combo_bonus", 5.0)
            score += bonus
            bits.append(f"人馬組合檔案齊（+{bonus:.0f}）")
        if self._is_debut():
            pen = scoring.CONFIDENCE_MICRO_WEIGHTS.get("debut_pen", -4.0)
            score += pen
            bits.append(f"初出未有正式賽數據（{pen:.1f}）")
        if features.get("risk_score", 60) < 55:
            pen = scoring.CONFIDENCE_MICRO_WEIGHTS.get("high_risk_pen", -5.0)
            score += pen
            bits.append(f"風險分偏低再扣（{pen:.0f}）")
        if self._is_foreign_runner():
            # Don't dock a visiting runner for lacking HKJC-only coverage fields;
            # floor at neutral so foreign horses aren't structurally low-confidence.
            score = max(score, 60.0)
            note = f"海外賽駒，本會資料欄有限，信心分按中性floor處理為{clip_score(score):.1f}。"
            return clip_score(score), note, "data_coverage"
        note = "、".join(bits) + f"，信心分{clip_score(score):.1f}。"
        return clip_score(score), note, "data_coverage"
```

### _formline_strength_score（第 625 行）

```python
def _formline_strength_score(self):
        signal = self._formline_strength_signal()
        mapping = {
            "elite": 88,
            "strong": 78,
            "weak": 54,
            "neutral": 64,
            "unknown": 60,
        }
        note_map = {
            "elite": "之前對手質量高，賽績線強度屬高含金量。",
            "strong": "之前對手組合有基本強度，賽績線含金量屬正面。",
            "weak": "之前對手強度支持不足，賽績線含金量偏弱。",
            "neutral": "對手強度中性，賽績線含金量一般。",
            "unknown": "未有清晰對手強度資料，賽績線強度按中性處理。",
        }
        score = mapping[signal]
        higher = self._value("formline_higher_win_count")
        same = self._value("formline_same_win_count")
        lower = self._value("formline_lower_win_count")
        higher_count = int(parse_float(higher) or 0)
        same_count = int(parse_float(same) or 0)
        lower_count = int(parse_float(lower) or 0)
        bonus = min(8, higher_count * 3 + same_count * 1 - lower_count * 1)
        if higher_count:
            note_map[signal] += f" 對手後續有{higher_count}匹於更高班再贏，含金量可再上調。"
        elif same_count and not lower_count:
            note_map[signal] += f" 對手後續有{same_count}匹於同班再贏，證明基本線索有兌現。"
        elif lower_count and not higher_count:
            note_map[signal] += f" 對手後續主要在較低班再贏，提升幅度只宜保守。"
        final = clip_score(score + bonus)
        # 「碰過強敵」要今馬自己跑得埋堆先算數：若所有賽績線往績都冇跑近過
        # （≤6名兼落後≤5個馬位＝competitive ratio 0，例：次次被拋離十幾個馬位），
        # 則封頂 60——面對強陣但每次大敗，唔應照當高含金量。
        # pit 驗證（FL2_zero_cap）：good +0.7、champ +0.6、TEST 零變、零回退。
        fl = self._formline_summary()
        if fl and fl.get("opponents") and final > 60:
            ops = fl["opponents"]
            if not any(o["competitive"] for o in ops):
                final = 60.0
                note_map[signal] = "曾碰強陣但今馬每仗都跑唔近（大敗收場），賽績線含金量存疑，按中性60分。"
        return final, note_map[signal], "formline_strength"
```

### _trackwork_trend_score（第 695 行）

```python
def _trackwork_trend_score(self):
        trackwork = self._trackwork_markers()
        classification = trackwork["classification"]
        trend = trackwork["trend"]

        # 1. Text-based trend base score
        if classification == "翻案復刻":
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("rebound_base", 66.0)
            note = "操練訊號好過近績反映（馬房用狀態翻案部署），操練分由偏高起點計"
        elif "加強" in trend:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("improving_base", 70.0)
            note = "快操時間一課比一課快，備戰上緊"
        elif "放緩" in trend:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("slowing_base", 52.0)
            note = "快操時間趨慢，備戰力度回落，操練分要扣"
        else:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("neutral_base", 60.0)
            note = "操練節奏平穩，中性處理"

        # 2. Raw exercise numerical multipliers
        trackwork = self.horse_data.get("trackwork")
        summary = trackwork.get("summary") if isinstance(trackwork, dict) else {}
        if not isinstance(summary, dict):
            summary = {}

        def _count(key):
            try:
                return int(float(summary.get(key, 0) or 0))
            except (TypeError, ValueError):
                return 0

        gallops = _count("gallops_21d")
        trials = _count("trials_21d")
        trotting = _count("trotting_21d")
        swimming = _count("swimming_21d")

        gallop_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("gallop_weight", 0.5)
        trial_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("trial_weight", 1.0)
        trotting_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("trotting_weight", 0.1)
        swimming_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("swimming_weight", 0.05)

        activity_bonus = (gallops * gallop_w) + (trials * trial_w) + (trotting * trotting_w) + (swimming * swimming_w)

        # Apply cap and floor
        cap = scoring.TRACKWORK_MICRO_WEIGHTS.get("activity_cap", 8.0)
        floor = scoring.TRACKWORK_MICRO_WEIGHTS.get("activity_floor", -4.0)
        activity_bonus = max(floor, min(activity_bonus, cap))

        final_score = scoring.clip_score(base_score + activity_bonus)
        if activity_bonus > 2.0:
            note += f"；操練量充足（活躍度+{activity_bonus:.1f}）"
        elif activity_bonus < -1.0:
            note += f"；操練量偏少（活躍度-{abs(activity_bonus):.1f}）"

        return final_score, note, "trackwork_digest"
```

### _race_shape_context_score（第 751 行）

```python
def _race_shape_context_score(self, features):
        draw = float(features.get("draw_score", 60))
        barrier = str(self.horse_data.get("barrier") or self.horse_data.get("draw") or "").strip()
        # 走位匹配分 + 近仗消耗分：兩場地都計、都顯示（口徑一致）。分數組合方式先分場地。
        fit_score, fit_note = self._draw_position_fit_score()
        trip_score, trip_note = self._trip_consumption_score()
        fit_why = fit_note.replace("匹配面：", "").rstrip("。")
        trip_why = trip_note.rstrip("。")
        rail = self._rail_label()
        is_sha_tin = self._is_sha_tin_context()
        if is_sha_tin:
            w = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
            score = clip_score(draw * w["sha_tin_draw"] + fit_score * w["sha_tin_draw_position_fit"] + trip_score * w["sha_tin_trip_consumption"])
            combine = "沙田加權 檔位55%＋走位匹配25%＋近仗消耗20%"
        else:
            delta, _items = self._race_shape_context_delta()
            score = clip_score(draw + delta)
            combine = f"跑馬地以檔位為主，走位情境微調 {delta:+.0f}"
        legacy_score = score
        surface = None
        live_profile = "sha_tin_legacy" if is_sha_tin else "legacy_v2"
        if (
            self._is_happy_valley_context()
            and not self._is_debut()
            and scoring.active_happy_valley_race_shape_profile() == "v3_surface"
        ):
            surface = self._surface_performance_shadow_component()
            gain = scoring.HAPPY_VALLEY_RACE_SHAPE_V3_SURFACE_GAIN
            score = clip_score(draw + gain * (float(surface["score"]) - 60.0))
            live_profile = "v3_surface"
            combine = "跑馬地實驗主線：檔位＋個別谷草性能；歷史匹配／近仗消耗不入分"
        self.race_shape_detail = {
            "draw": round(draw, 1), "fit": round(fit_score, 1), "trip": round(trip_score, 1),
            "fit_why": fit_why, "trip_why": trip_why, "combine": combine, "rail": rail,
            "live_profile": live_profile,
            "legacy_score": round(float(legacy_score), 2),
            "surface_performance": surface,
            "field_tempo": "withheld_insufficient_reliability" if live_profile == "v3_surface" else None,
            "rail_draw_context": self._live_rail_draw_context(),
        }
        note = f"排{barrier}檔　{score:.0f}分" + (f"（{rail}賽道）" if rail else "")
        return score, note, "race_shape_context"
```

### _live_rail_draw_context（第 794 行）

```python
def _live_rail_draw_context(self):
        source = rail_draw_context_adjustment(
            self.race_context or {},
            self.horse_data.get("barrier") or self.horse_data.get("draw"),
        )
        if self._is_debut():
            source = dict(source)
            source["applied"] = False
            source["adjustment"] = 0.0
            source["reason"] = "debut_formula_locked"
        return source
```

### _rail_label（第 806 行）

```python
def _rail_label(self):
        """今場賽道（A/B/C/C+3 等），顯示用。由 race_context 讀（賽前 pipeline 注入）；
        冇就回 None。唔入計分。"""
        for k in ("rail", "course_rail", "course_config"):
            v = self._clean(str(self.race_context.get(k) or ""))
            if v and v not in ("N/A", "-", ""):
                return v
        return None
```

### _is_happy_valley_context（第 815 行）

```python
def _is_happy_valley_context(self):
        text = str(
            self.race_context.get("venue")
            or self.race_context.get("course")
            or self.race_context.get("racecourse")
            or ""
        )
        return any(token in text for token in ("HV", "Happy Valley", "HappyValley", "跑馬地"))
```

### _draw_position_fit_score（第 824 行）

```python
def _draw_position_fit_score(self):
        # `running_style` was a next-race positional forecast.  Recent HV
        # validation was only ~44-46% accurate, so it must not influence the
        # score.  Keep only observed historical lane/draw fit and position PI.
        text = self._text("draw_position_fit", "position_pi")
        weights = scoring.RACE_SHAPE_FIT_WEIGHTS
        score = weights["base"]
        details = []
        if "✅匹配" in text:
            score += weights["match_bonus"]
            details.append("檔位與歷史走位匹配")
        if "❌錯配" in text or "錯配!" in text:
            score += weights["mismatch_pen"]
            self.risk_flags.append("draw_position_mismatch")
            details.append("檔位與歷史走位有錯配")
        if "⚠️需主動切入" in text:
            score += weights["active_slot_pen"]
            self.risk_flags.append("needs_active_slotting")
            details.append("早段需要主動切入")
        if "上升軌" in text:
            score += weights["pi_up_bonus"]
            details.append("走位 PI 有上升軌")
        elif "微升" in text:
            score += weights["pi_micro_up_bonus"]
            details.append("走位 PI 微升")
        elif "衰退中" in text:
            score += weights["pi_down_pen"]
            details.append("走位 PI 衰退")
        elif "微跌" in text:
            score += weights["pi_micro_down_pen"]
            details.append("走位 PI 微跌")
        detail = "；".join(details) if details else "歷史檔位走位未見鮮明偏差"
        return clip_score(score), f"歷史匹配面：{detail}。"
```

### _trip_consumption_score（第 858 行）

```python
def _trip_consumption_score(self):
        text = self._clean(self._value("position_window") or "")
        mapping = scoring.RACE_SHAPE_TRIP_CONSUMPTION_SCORES
        scores = []
        labels = []
        for part in text.split("|")[:3]:
            part = part.strip()
            # 長標籤優先，否則「高」會搶先 match 走「極高」
            for label, score in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
                if label in part:
                    scores.append(score)
                    labels.append(label)
                    break
        if not scores:
            return 60.0, "近仗消耗未有清晰標籤，按中性處理。"
        score = sum(scores) / len(scores)
        return clip_score(score), f"近{len(scores)}仗走位消耗以{'、'.join(labels)}為主。"
```

### _race_shape_context_delta（第 876 行）

```python
def _race_shape_context_delta(self):
        # Do not use the low-accuracy next-race running-style forecast.  The
        # remaining inputs are all observations from completed prior races.
        text = self._text("draw_position_fit", "position_pi")
        weights = scoring.RACE_SHAPE_CONTEXT_DELTA_WEIGHTS
        delta = 0.0
        items = []  # 逐項 {factor, delta, why}
        def add(factor, d, why):
            nonlocal delta
            delta += d
            items.append({"factor": factor, "delta": round(d, 2), "why": why})
        if "✅匹配" in text:
            add("歷史走位匹配", weights["match_bonus"], "檔位與歷史走位匹配")
        if "❌錯配" in text or "錯配!" in text:
            self.risk_flags.append("draw_position_mismatch")
            add("歷史走位匹配", weights["mismatch_pen"], "檔位與歷史走位錯配")
        if "⚠️需主動切入" in text:
            self.risk_flags.append("needs_active_slotting")
            add("走位匹配", weights["active_slot_pen"], "需要主動切入")
        if "上升軌" in text:
            add("走位PI", weights["pi_up_bonus"], "走位 PI 上升")
        elif "衰退中" in text:
            add("走位PI", weights["pi_down_pen"], "走位 PI 衰退")
        recent = self._clean(self._value("position_window") or "").split("|")[0]
        if "低消耗" in recent:
            add("近仗消耗", weights["recent_low_consumption_bonus"], "最近走位低消耗")
        elif "極高" in recent:
            add("近仗消耗", weights["recent_extreme_consumption_pen"], "最近走位極高消耗")
        elif "高" in recent:
            add("近仗消耗", weights["recent_high_consumption_pen"], "最近走位高消耗")
        context_weights = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
        delta = max(context_weights["non_sha_tin_delta_floor"], min(context_weights["non_sha_tin_delta_cap"], delta))
        return delta, items
```

### _ability_score（第 910 行）

```python
def _ability_score(self, matrix_scores):
        if self._is_debut():
            base = sum(matrix_scores.get(key, 60.0) * weight for key, weight in DEBUT_MATRIX_WEIGHTS.items())
        else:
            base = sum(matrix_scores[key] * weight for key, weight in MATRIX_WEIGHTS.items())
        # Centred dimensions (同程表現) add weight × (score − 60); debut runners
        # have no same-distance record so their term is 0 by construction.
        return base + sum(
            weight * (float(matrix_scores.get(key, 60.0)) - 60.0)
            for key, weight in CENTRED_MATRIX_WEIGHTS.items()
        )
```

### _surface_performance_shadow_component（第 1099 行）

```python
def _surface_performance_shadow_component(self):
        """Read the deterministic PIT surface score transported by Facts→Logic.

        The source string is produced by `compute_surface_performance_shadow` and
        carries the target score, effective prior-only sample and provenance.  A
        missing/malformed value is neutral rather than guessed.
        """
        text = self._clean(self._value("surface_performance_shadow") or "")
        score_match = re.search(r"今場=.*?\s(\d+(?:\.\d+)?)分", text)
        target_match = re.search(r"今場=([^|]+?)\s+\d+(?:\.\d+)?分", text)
        target = target_match.group(1).strip() if target_match else ""
        sample_match = re.search(
            r"(?:^|\|)\s*" + re.escape(target) + r"\s+\d+(?:\.\d+)?分\(有效樣本(\d+(?:\.\d+)?)",
            text,
        ) if target else None
        source_match = re.search(r"採用來源=([^|]+)", text)
        score = parse_float(score_match.group(1)) if score_match else None
        effective_n = parse_float(sample_match.group(1)) if sample_match else None
        return {
            "score": round(clip_score(score if score is not None else 60.0), 2),
            "effective_n": round(float(effective_n or 0.0), 2),
            "source": source_match.group(1).strip() if source_match else "missing_neutral",
            "available": score is not None,
        }
```

### _apply_mainline_context（第 1449 行）

```python
def _apply_mainline_context(self, feature_scores, feature_notes):
        updated = dict(feature_scores)
        notes = {}
        sources = {}

        # 「已再參考XX調整騎練分」呢句唔append落sub note（用戶：無意義）——
        # 逐項調整已經喺「評分構成」下面逐行連證據列晒。
        updated, trainer_note = self._apply_trainer_signal_context(updated)
        if trainer_note:
            sources["jockey_score"] = "th01_trainer_context"
            sources["trainer_score"] = "th01_trainer_context"

        health_score, health_note = self._candidate_health_risk_score()
        if health_score is not None:
            updated["risk_score"] = clip_score(health_score)
            notes["risk_score"] = self._append_note(
                self._strip_embedded_score(feature_notes.get("risk_score"), "風險分"),
                f"{health_note}重算風險分{clip_score(health_score):.1f}。",
            )
            sources["risk_score"] = "th01_health_context"

        shadow = self._consistency_shadow_detail()
        if shadow is not None:
            updated["consistency_score"] = clip_score(shadow["score"])
            shift_txt = {"recovering": "，且近三仗名次好過再之前", "declining": "，但近三仗名次差過再之前"}.get(shadow["recent_shift"], "")
            notes["consistency_score"] = self._append_note(
                self._strip_embedded_score(feature_notes.get("consistency_score"), "穩定性分"),
                (
                    f"逐仗連輸距覆核：近{shadow['n']}仗有{shadow['close_runs']}仗跑近前列、"
                    f"{shadow['poor_runs']}仗明顯敗陣{shift_txt}，穩定性分定為{clip_score(shadow['score']):.1f}。"
                ),
            )
            sources["consistency_score"] = "cx01_consistency_context"

        return updated, notes, sources
```

### _strip_embedded_score（第 1486 行）

```python
def _strip_embedded_score(note, label):
        """覆蓋分數時，將原註解入面自述嘅舊分（例：「穩定性分66分」）清走，
        避免報告出現「穩定性分 76 ← ...穩定性分66分」呢種前後對唔上。"""
        text = str(note or "").strip()
        if not text:
            return text
        text = re.sub(rf"[，,、；;]?\s*{label}[為約]?\s*\d+(?:\.\d+)?\s*分?", "", text)
        text = re.sub(r"。{2,}", "。", text).strip(" ，,、；;")
        return text
```

### _apply_trainer_signal_context（第 1496 行）

```python
def _apply_trainer_signal_context(self, feature_scores):
        updated = dict(feature_scores)
        prior_stack = self._trainer_signal_priors()
        jockey = self._clean(self.horse_data.get("jockey"))
        trainer = self._clean(self.horse_data.get("trainer"))
        distance = str(self.race_context.get("distance") or "").replace("m", "").strip()

        jockey_base = clip_score(updated.get("jockey_score", 60.0))
        trainer_base = clip_score(updated.get("trainer_score", 60.0))
        jockey_adj = 0.0
        trainer_adj = 0.0
        triggers = []
        adjustments = []

        # 用戶要求：凡有數據嘅因子一律顯示（±0 都寫），等每個分點嚟都睇得晒
        horse_history = self._current_jockey_horse_record()
        if horse_history:
            history_adj = self._trainer_history_adjustment(horse_history)
            jockey_adj += history_adj
            if history_adj:
                triggers.append("人馬歷史")
            adjustments.append({
                "factor": "人馬歷史",
                "target": "騎師分",
                "delta": round(history_adj, 2),
                "evidence": (
                    f"{jockey or '今場騎師'}近期策騎此馬{int(horse_history['starts'])}次："
                    f"{int(horse_history['wins'])}勝、前三率{horse_history['place_rate']:.0f}%、平均{horse_history['avg_finish']:.1f}名"
                    + ("" if history_adj else "（未達加減分門檻，不加不減）")
                ),
            })

        prior = self._jockey_trainer_prior()
        if prior is None and jockey and trainer:
            prior = prior_stack.combo.get((jockey, trainer))
        combo_adj = self._trainer_combo_adjustment(prior)
        if combo_adj:
            j_share = combo_adj * scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_jockey_share"]
            t_share = combo_adj * scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_trainer_share"]
            jockey_adj += j_share
            trainer_adj += t_share
            triggers.append("騎練組合")
        if prior and float(prior.get("starts", 0) or 0) >= 10:
            c_starts = int(float(prior.get("starts", 0) or 0))
            c_win = float(prior.get("win_rate", 0) or 0)
            c_place = float(prior.get("place_rate", 0) or 0)
            elite_tag = "（馬房皇牌組合）" if (c_starts >= 40 and (c_win >= 14.0 or c_place >= 36.0)) else ""
            if combo_adj:
                tail = "（騎師分攤55%／練馬師45%）"
            elif c_starts < 40:
                tail = "（樣本未夠40仗，不加不減）"
            else:
                tail = "（表現屬中游，不加不減）"
            adjustments.append({
                "factor": "騎練組合",
                "target": "騎師分/練馬師分",
                "delta": round(combo_adj, 2),
                "evidence": (
                    f"{jockey}×{trainer} 拍檔{c_starts}仗："
                    f"勝率{c_win:.1f}%、上名率{c_place:.1f}%{elite_tag}{tail}"
                ),
            })

        if distance and jockey:
            distance_row = prior_stack.jockey_distance.get((jockey, distance))
            distance_adj = self._jockey_distance_adjustment(distance_row)
            jockey_adj += distance_adj
            if distance_adj:
                triggers.append("騎師同程")
            if distance_row and float(distance_row.get("starts", 0) or 0) > 0:
                d_starts = int(float(distance_row.get("starts", 0) or 0))
                tail = "" if distance_adj else (
                    "（樣本未夠80仗，不加不減）" if d_starts < 80 else "（表現屬中游，不加不減）"
                )
                adjustments.append({
                    "factor": "騎師同程",
                    "target": "騎師分",
                    "delta": round(distance_adj, 2),
                    "evidence": (
                        f"{jockey}於{distance}米往績{d_starts}仗："
                        f"勝率{float(distance_row.get('win_rate', 0) or 0):.1f}%、上名率{float(distance_row.get('place_rate', 0) or 0):.1f}%{tail}"
                    ),
                })

        if distance and trainer:
            trainer_row = prior_stack.trainer_distance.get((trainer, distance))
            trainer_distance_adj = self._trainer_distance_adjustment(trainer_row)
            trainer_adj += trainer_distance_adj
            if trainer_distance_adj:
                triggers.append("練馬師同程")
            if trainer_row and float(trainer_row.get("starts", 0) or 0) > 0:
                t_starts = int(float(trainer_row.get("starts", 0) or 0))
                tail = "" if trainer_distance_adj else (
                    "（樣本未夠80仗，不加不減）" if t_starts < 80 else "（表現屬中游，不加不減）"
                )
                adjustments.append({
                    "factor": "練馬師同程",
                    "target": "練馬師分",
                    "delta": round(trainer_distance_adj, 2),
                    "evidence": (
                        f"{trainer}於{distance}米往績{t_starts}仗："
                        f"勝率{float(trainer_row.get('win_rate', 0) or 0):.1f}%、上名率{float(trainer_row.get('place_rate', 0) or 0):.1f}%{tail}"
                    ),
                })

        if self._is_jockey_changed() is True:
            change_adj = self._jockey_change_adjustment(prior_stack.jockey_change)
            jockey_adj += change_adj
            if change_adj:
                triggers.append("換騎")
                keep = (prior_stack.jockey_change or {}).get(False) or {}
                adjustments.append({
                    "factor": "換騎",
                    "target": "騎師分",
                    "delta": round(change_adj, 2),
                    "evidence": (
                        f"全季統計沿用原騎（勝率{float(keep.get('win_rate', 0) or 0):.1f}%）平均好過換騎，"
                        "今仗屬換騎，作小幅折讓"
                    ),
                })

        if jockey_adj:
            updated["jockey_score"] = clip_score(updated.get("jockey_score", 60.0) + jockey_adj)
        if trainer_adj:
            updated["trainer_score"] = clip_score(updated.get("trainer_score", 60.0) + trainer_adj)

        self.trainer_signal_detail = {
            "jockey_base": round(jockey_base, 2),
            "jockey_final": round(clip_score(updated.get("jockey_score", 60.0)), 2),
            "trainer_base": round(trainer_base, 2),
            "trainer_final": round(clip_score(updated.get("trainer_score", 60.0)), 2),
            "adjustments": adjustments,
        }

        if not triggers:
            return updated, ""
        note = "已再參考" + "、".join(dict.fromkeys(triggers)) + "調整騎練分。"
        return updated, note
```

### _apply_health_only_v2（第 1635 行）

```python
def _apply_health_only_v2(self, base_score):
        return round(clip_score(base_score), 2)
```

### _apply_trainer_signal_v3（第 1638 行）

```python
def _apply_trainer_signal_v3(self, base_score):
        # 配備訊號（pit backtest 2026-07-10 驗證）：除去配備＝練馬師部署負面訊號，
        # 扣騎練訊號維度分。初戴類全部 out-of-sample NULL，維持顯示唔入分。
        gear = str(self._value("gear_change") or "")
        if "除去" in gear:
            delta = scoring.GEAR_SIGNAL_WEIGHTS["gear_removed_pen"]
            self.reason_codes.append("gear_removed")
            removed = self._gear_change_readable() or {}
            detail = getattr(self, "trainer_signal_detail", None)
            if isinstance(detail, dict):
                detail.setdefault("adjustments", []).append({
                    "factor": "除去配備",
                    "target": "騎練訊號",
                    "delta": round(delta, 2),
                    "evidence": (removed.get("value") or "今仗除去配備")
                    + "（歷史回測：除去配備平均走樣，扣3分）",
                })
            return round(clip_score(base_score + delta), 2)
        return round(clip_score(base_score), 2)
```

### _candidate_health_risk_score（第 1658 行）

```python
def _candidate_health_risk_score(self):
        score = scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["base"]
        medical = self._text("medical_flags")
        weight_trend = self._text("weight_trend")
        days = self._days_since_last()
        weight_span = self._weight_trend_span(weight_trend)

        if "✅ 無醫療事故記錄" in medical:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_clear_bonus"]
        elif medical and medical != "N/A":
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_issue_pen"]
            if self._has_recovery_evidence():
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_recovery_bonus"]
        else:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_unknown_pen"]

        if days is not None:
            if days <= 7:
                if weight_span is not None and weight_span <= 14.0:
                    score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_stable_bonus"]
                else:
                    score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_unstable_pen"]
            elif days <= 21:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_21_bonus"]
            elif days <= 45:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_45_bonus"]
            elif days > 75:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_gt_75_pen"]

        if any(token in weight_trend for token in ("急劇變化", "急增", "急減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_sharp_change_pen"]
        elif any(token in weight_trend for token in ("顯著轉輕", "大減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_drop_pen"]
        elif any(token in weight_trend for token in ("顯著轉重", "大增")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_gain_pen"]
        elif any(token in weight_trend for token in ("微增", "微減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_micro_bonus"]

        if weight_span is not None:
            if weight_span <= 12.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_12_bonus"]
            elif weight_span <= 18.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_18_bonus"]
            elif weight_span <= 32.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_32_pen"]
            else:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_gt_32_pen"]

        note = "已再綜合醫療紀錄、休賽日數同體重波幅，"
        return clip_score(score), note
```

### _last_race_iso（第 1734 行）

```python
def _last_race_iso(self):
        """最近一仗日期（ISO）。recent_6_detail 係「第1仗(DD/MM/YYYY …)」。"""
        m = re.search(r"第1仗\((\d{2})/(\d{2})/(\d{4})", self._text("recent_6_detail"))
        if not m:
            return None
        d, mo, y = m.group(1), m.group(2), m.group(3)
        try:
            return _dt.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return None
```

### _days_since_last（第 1745 行）

```python
def _days_since_last(self):
        """距今日數 —— 一定要（今仗日期 − 上仗日期），唔可以信 Logic 個欄位。

        `inject_hkjc_fact_anchors.compute_stats` 曾經寫 `races[0]['days_since']`
        落 Facts「休後復出」，而賽績檔嗰個 `日數:` 係**該仗同上一仗之間**嘅間隔
        （`[1] 26/04/2026 | 日數: 20` = 06/04→26/04 隔 20 日），唔係距今日數。
        錯咗一整格。連 `health_readout` 都自我矛盾——同兩行印住「上次出賽：
        2026年4月26日 / 距今：20日」。實測 3,438 個 runner 有 66.5% 個值係錯，
        但賽季中間錯得細（中位 +3 日，因為連續出賽嘅馬「上仗前間隔」≈「距今」）；
        季初／休賽後就錯得大：2026-09-06 一日中位 +41 日（嘉應高昇 20 vs 133），
        觸發 `days_gt_75_pen` 嘅馬由 2 匹變 28 匹（117 匹之中）。

        生成器已修，但 264 個歷史 Logic 仍然帶住舊值，所以引擎自己重算：
        `race_analysis.race_date`（live 由 skeleton 寫入，replay 由
        `rescore_backtest.resolve_meeting_context` 注入）減 recent_6_detail
        第1仗日期。兩邊有一邊缺就退回舊欄位，唔靜靜當 0。
        """
        as_of = str((self.race_context or {}).get("race_date") or "").strip()
        last = self._last_race_iso()
        if as_of and last:
            try:
                delta = (_dt.date.fromisoformat(as_of) - _dt.date.fromisoformat(last)).days
            except ValueError:
                delta = None
            if delta is not None and delta >= 0:
                return float(delta)
        return parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))
```

### _consistency_shadow_detail（第 1873 行）

```python
def _consistency_shadow_detail(self):
        """逐仗連輸距重算穩定性分，並回傳可以直接寫入報告嘅事實統計
        （幾多仗貼近前列、幾多仗明顯敗陣、近三仗係咪好過之前）。"""
        if self._is_debut():
            return None

        detail = self._text("recent_6_detail")
        runs = self._parse_recent_runs(detail)
        if not runs:
            return None

        weights = [1.00, 0.85, 0.70, 0.55, 0.45, 0.35]
        weighted_total = sum(weights[: len(runs)])
        close_credit = 0.0
        poor_debit = 0.0
        severe_debit = 0.0
        close_runs = 0
        poor_runs = 0

        for idx, run in enumerate(runs[:6]):
            weight = weights[idx]
            rank = run["rank"]
            margin = run["margin"]

            if 1 <= rank <= 3:
                close_credit += weight
                close_runs += 1
                continue
            if 1 <= rank <= 5 and margin is not None and margin <= 3.0:
                close_credit += weight * 0.75
                close_runs += 1
            elif 1 <= rank <= 7 and margin is not None and margin <= 2.5:
                close_credit += weight * 0.40
                close_runs += 1

            if rank >= 8 and margin is not None and margin >= 5.0:
                poor_debit += weight
                poor_runs += 1
            elif rank >= 6 and margin is not None and margin >= 7.0:
                poor_debit += weight * 0.70
                poor_runs += 1

            if rank >= 10 and margin is not None and margin >= 8.0:
                severe_debit += weight

        close_ratio = close_credit / weighted_total if weighted_total else 0.0
        poor_ratio = poor_debit / weighted_total if weighted_total else 0.0
        severe_ratio = severe_debit / weighted_total if weighted_total else 0.0

        # 輸距趨勢 nudge（收窄+4/擴大−4/波動−1）已移除：輸距本身經逐仗 close/poor
        # credit 計入，趨勢再加一次係同 form_line 重複；2026-07-08 backtest 兩邊
        # 一齊移除先零倒退（test gold/champ 反而升）。
        score = 58.0 + close_ratio * 18.0 - poor_ratio * 14.0 - severe_ratio * 10.0
        finish_positions = [run["rank"] for run in runs[:6]]
        recent_shift = ""
        if len(finish_positions) >= 5:
            recent_avg = sum(finish_positions[:3]) / 3.0
            older = finish_positions[3:6]
            older_avg = sum(older) / len(older)  # was /3.0 — undercounted when only 5 runs (2 elems)
            if recent_avg + 1.0 < older_avg:
                score += 3.0
                recent_shift = "recovering"
            elif recent_avg > older_avg + 1.0:
                score -= 3.0
                recent_shift = "declining"

        return {
            "score": clip_score(score),
            "n": len(runs[:6]),
            "close_runs": close_runs,
            "poor_runs": poor_runs,
            "recent_shift": recent_shift,
        }
```

### _parse_recent_runs（第 1947 行）

```python
def _parse_recent_runs(self, detail):
        runs = []
        for rank_text, margin_text in re.findall(r":\s*(\d+)名\s+([^|,]+)", str(detail or "")):
            try:
                rank = int(rank_text)
            except ValueError:
                continue
            if rank <= 0:
                continue
            runs.append(
                {
                    "rank": rank,
                    "margin": self._margin_to_float(margin_text.strip()),
                }
            )
        return runs
```

### _margin_to_float（第 1964 行）

```python
def _margin_to_float(self, value):
        text = str(value or "").strip()
        if not text or text in {"-", "--", "N/A"}:
            return None
        if "平頭馬" in text:
            return 0.0
        if "短馬頭位" in text:
            return 0.05
        if "頭位" in text:
            return 0.1
        if "頸位" in text:
            return 0.25
        if "多個馬位" in text:
            return 8.0

        total = 0.0
        matched = False
        for part in text.split("-"):
            part = part.strip()
            if not part:
                continue
            if "/" in part:
                numerator, denominator = part.split("/", 1)
                try:
                    total += float(numerator) / float(denominator)
                    matched = True
                except ValueError:
                    continue
                continue
            try:
                total += float(part)
                matched = True
            except ValueError:
                continue
        if matched:
            return total
        return None
```

### _has_recovery_evidence（第 2002 行）

```python
def _has_recovery_evidence(self):
        finishes = [int(item) for item in re.findall(r"\b\d+\b", str(self.horse_data.get("last_6_finishes") or ""))[:3]]
        if any(1 <= rank <= 3 for rank in finishes):
            return True
        finish_time_level = self._text("finish_time_adj_level")
        if "仍具競爭力" in finish_time_level or "持續快於標準" in finish_time_level:
            return True
        raw_l400 = parse_float(self._value("raw_l400"))
        return raw_l400 is not None and raw_l400 <= 23.4
```

### _weight_trend_span（第 2012 行）

```python
def _weight_trend_span(self, weight_trend):
        match = re.search(r"波幅(\d+(?:\.\d+)?)lb", str(weight_trend or ""))
        if match:
            return float(match.group(1))
        return None
```

### _trainer_history_adjustment（第 2018 行）

```python
def _trainer_history_adjustment(self, row):
        if row["starts"] >= 2 and (row["wins"] >= 1 or row["place_rate"] >= 50.0) and row["avg_finish"] <= 5.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_strong"]
        if row["starts"] >= 3 and row["place_rate"] >= 33.0 and row["avg_finish"] <= 5.5:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_supportive"]
        if row["starts"] >= 3 and row["place_rate"] == 0.0 and row["avg_finish"] >= 7.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_zero_place"]
        if row["starts"] >= 5 and row["place_rate"] <= 20.0 and row["avg_finish"] >= 6.5:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_weak"]
        return 0.0
```

### _trainer_combo_adjustment（第 2029 行）

```python
def _trainer_combo_adjustment(self, row):
        if not row:
            return 0.0
        starts = float(row.get("starts", 0.0) or 0.0)
        win_rate = float(row.get("win_rate", 0.0) or 0.0)
        place_rate = float(row.get("place_rate", 0.0) or 0.0)
        # Gate lowered 80→40: point-in-time backtest (18.8k runners,
        # all_race_results_master.csv) shows the jockey×trainer signal holds at
        # ≥40 starts — positive-combo top3 30.5% vs negative 18.4% (spread
        # +12.1pt vs +10.3pt at ≥80), while eligible combos rise 57→151 and
        # runner coverage ~2.6×. Lower samples (<40) start adding noise.
        if starts < 40:
            return 0.0
        if win_rate >= 14.0 or place_rate >= 36.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_elite"]
        if win_rate >= 11.0 or place_rate >= 30.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_positive"]
        if win_rate <= 7.0 and place_rate <= 23.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_negative"]
        return 0.0
```

### _jockey_distance_adjustment（第 2050 行）

```python
def _jockey_distance_adjustment(self, row):
        if not row:
            return 0.0
        starts = float(row.get("starts", 0.0) or 0.0)
        win_rate = float(row.get("win_rate", 0.0) or 0.0)
        place_rate = float(row.get("place_rate", 0.0) or 0.0)
        if starts < 80:
            return 0.0
        if win_rate >= 15.0 or place_rate >= 40.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_distance_elite"]
        if win_rate >= 10.0 or place_rate >= 30.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_distance_positive"]
        if win_rate <= 6.0 and place_rate <= 22.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_distance_negative"]
        return 0.0
```

### _trainer_distance_adjustment（第 2066 行）

```python
def _trainer_distance_adjustment(self, row):
        if not row:
            return 0.0
        starts = float(row.get("starts", 0.0) or 0.0)
        win_rate = float(row.get("win_rate", 0.0) or 0.0)
        place_rate = float(row.get("place_rate", 0.0) or 0.0)
        if starts < 80:
            return 0.0
        if win_rate >= 12.0 or place_rate >= 34.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["trainer_distance_elite"]
        if win_rate >= 9.0 or place_rate >= 28.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["trainer_distance_positive"]
        if win_rate <= 5.0 and place_rate <= 20.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["trainer_distance_negative"]
        return 0.0
```

### _jockey_change_adjustment（第 2082 行）

```python
def _jockey_change_adjustment(self, jockey_change_rows):
        keep = jockey_change_rows.get(False) if jockey_change_rows else None
        change = jockey_change_rows.get(True) if jockey_change_rows else None
        if not keep or not change:
            return 0.0
        if keep["win_rate"] >= change["win_rate"] + 1.0 and keep["place_rate"] >= change["place_rate"] + 3.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_change_negative"]
        return 0.0
```

### _is_jockey_changed（第 2091 行）

```python
def _is_jockey_changed(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        rows = self._recent_jockey_history_rows()
        if not current_jockey or not rows:
            return None
        latest = rows[0].get("jockey", "")
        return bool(latest and latest != current_jockey)
```

### _trainer_signal_priors（第 2099 行）

```python
def _trainer_signal_priors(self):
        global _TRAINER_SIGNAL_PRIORS
        if _TRAINER_SIGNAL_PRIORS is None:
            _TRAINER_SIGNAL_PRIORS = TrainerSignalPriors()
        # A latest/full-season snapshot is valid for a live card but leaks
        # future results when an archived race is replayed. Keep historical
        # scoring neutral unless the PIT harness injects a matching source.
        as_of_date = (self.race_context or {}).get("race_date")
        if not temporal_source_is_safe(_TRAINER_SIGNAL_PRIORS, as_of_date):
            return empty_trainer_signal_priors()
        return _TRAINER_SIGNAL_PRIORS
```

### _append_note（第 2111 行）

```python
def _append_note(self, base_note, extra_note):
        base = str(base_note or "").strip()
        extra = str(extra_note or "").strip()
        if not base:
            return extra or "資料不足，中性60分。"
        if not extra:
            return base
        return base + " " + extra
```

### _formline_summary（第 2216 行）

```python
def _formline_summary(self):
        """Concrete 賽績線: every past opponent IN `formline_table` — my finish +
        margin that day, whether the opponent went on to win (form validation)
        and at what class move. Opponents also in today's field are flagged
        同場對手.

        ⚠️ 呢個 docstring 一直寫住「EVERY notable past opponent」，但實際上係
        少於四成。`create_hkjc_logic_skeleton.parse_formline_table` 用
        `int(cols[1])` 做「係唔係數據行」嘅測試，而個表每場只有第一個對手嗰行
        帶 `#`，所以亞軍／季軍嘅續行全部被丟掉 —— 實測 37,265 條對手行只有
        14,580 條（39.1%）入到 Logic。2026-09-06 R3 嘉應高昇 11 條剩 5 條，
        而丟掉嗰批正正係兩隻 ✅✅ 超強組。已修（2026-09-04）；歷史 Logic 仍然
        帶住殘缺嘅表，要重建先補得返。"""
        table = self._value("formline_table")
        if not isinstance(table, list) or not table:
            return None

        def fin(row):
            m = re.match(r"\s*(\d+)", str(row.get("my_finish", "")))
            return int(m.group(1)) if m else 99

        def margin_behind(row):
            """今馬當日負幾多個馬位（正值=落後咁多；贏/領放=0）。
            my_finish 例：'13 (-11-3/4)'→11.75；'5 (-3/4)'→0.75；'1 (...)'→0。"""
            raw = str(row.get("my_finish", ""))
            mm = re.search(r"\(\s*(-?)\s*([\d\-/]+)", raw)
            if not mm:
                return None
            behind = mm.group(1) == "-"
            if not behind:
                return 0.0  # 贏或領放，唔算落後
            tok = mm.group(2)

            def _frac(s):
                if "/" in s:
                    a, b = s.split("/")
                    try:
                        return float(a) / float(b)
                    except (ValueError, ZeroDivisionError):
                        return 0.0
                try:
                    return float(s)
                except ValueError:
                    return 0.0
            parts = tok.split("-")  # '11-3/4' → ['11','3/4']；'3/4' → ['3/4']
            return sum(_frac(p) for p in parts if p)

        def opp_name(row):
            return re.sub(r"^\[\d+\]\s*", "", str(row.get("opponents", "")).split("(")[0]).strip()

        def opp_wins(row):
            m = re.search(r":\s*(\d+)\s*勝", str(row.get("next_performance", "")))
            return int(m.group(1)) if m else 0

        def best_class_rank(text):
            ranks = [self._class_num(tok) for tok in re.split(r"[ /、,]+", str(text or "")) if tok]
            ranks = [r for r in ranks if r is not None]
            return min(ranks) if ranks else None

        today_rank = self._class_num(self.race_context.get("race_class"))
        field = set(self.race_context.get("field_horse_names") or [])
        mine = self.horse_data.get("horse_name")

        opponents = []
        for r in table:
            nm = opp_name(r)
            if not nm:
                continue
            orank = best_class_rank(r.get("next_class"))
            move = ""
            if today_rank is not None and orank is not None:
                move = "升班" if orank < today_rank else ("降班" if orank > today_rank else "同班")
            opp_text = str(r.get("opponents", ""))
            om = re.search(r"\[(\d+)\]", opp_text)
            my_fin = fin(r)
            mgn = margin_behind(r)
            # 「跑得埋堆」先算數：今馬當日 ≤6 名 且 落後 ≤5 個馬位（貼近頭三名）。
            # 跑第13、負11-3/4＝根本冇同對手交手，唔當賽績線驗證（用戶反映）。
            competitive = (my_fin <= 6) and (mgn is None or mgn <= 5.0)
            opponents.append({
                "name": nm,
                "my_fin": my_fin,
                "my_margin": mgn,
                "competitive": competitive,
                "my_finish_raw": str(r.get("my_finish", "")).strip(),
                "wins": opp_wins(r),
                "next_class": str(r.get("next_class", "")).strip(),
                "move": move,
                "is_field": any(f and f != mine and f in opp_text for f in field),
                "opp_fin": (1 if "頭馬" in opp_text else (int(om.group(1)) if om else None)),
                "date": str(r.get("date", "")).strip(),
            })
        # 只計「今馬當日跑得埋堆」而對手其後又贏嘅場次先算已驗證。
        validated = sum(1 for o in opponents if o["wins"] >= 1 and o["competitive"])
        return {"opponents": opponents, "validated": validated, "n": len(table)}
```

### _gear_codes_to_names（第 2331 行）

```python
def _gear_codes_to_names(self, text):
        parts = [c.strip() for c in str(text or "").replace("＋", "/").split("/")
                 if c.strip() and c.strip() not in ("-", "無", "N/A")]
        out = []
        for p in parts:
            code = re.sub(r"\d+$", "", p.upper()).strip()
            out.append(self._GEAR_NAMES.get(code, p))
        return out
```

### _gear_change_readable（第 2340 行）

```python
def _gear_change_readable(self):
        """配備變動 → 白話（戴上／除下／維持＋中文配備名）。display-only。"""
        raw = self._clean(self._value("gear_change") or "")
        if not raw or raw in ("N/A", "-"):
            return None
        m = re.search(r"上仗\s*([^→|]+?)\s*→\s*今仗\s*([^|]+)", raw)
        if not m:
            return None
        prev_names = self._gear_codes_to_names(m.group(1))
        cur_names = self._gear_codes_to_names(m.group(2))
        added = [n for n in cur_names if n not in prev_names]
        removed = [n for n in prev_names if n not in cur_names]
        bits = []
        if added:
            bits.append("戴上" + "、".join(added))
        if removed:
            bits.append("除下" + "、".join(removed))
        if bits:
            value = "；".join(bits)
            trend = "配備有變"
            band = "➖"
        else:
            value = ("維持" + "＋".join(cur_names)) if cur_names else "冇配備"
            trend = ""
            band = "➖"
        return {"value": value, "trend": trend, "band": band, "reason": raw}
```

### _class_num（第 2383 行）

```python
def _class_num(self, text):
        """Unified class rank — LOWER number = HIGHER class. Graded races
        (一/二/三級賽 = Group 1/2/3) and 上市賽 (Listed) rank ABOVE all 班次,
        so a horse moving from 第二班 to 三級賽 is 升班, not a same-/down-grade."""
        t = str(text or "")
        gm = re.search(r"([一二三])級賽", t)
        if gm:
            return "一二三".index(gm.group(1)) + 1          # G1=1, G2=2, G3=3
        gm = re.search(r"(?:Group|Grade|G)\s*([123])", t, re.I)
        if gm:
            return int(gm.group(1))
        if "上市賽" in t or "表列賽" in t or re.search(r"\b(?:Listed|LR)\b", t, re.I):
            return 4                                         # Listed: just below Group 3
        cm = re.search(r"第([一二三四五六七])班", t)
        if cm:
            return 10 + "一二三四五六七".index(cm.group(1))   # 第一班=10 … 第七班=16
        cm = re.search(r"C(?:lass)?\s*([1-7])", t, re.I)
        if cm:
            return 9 + int(cm.group(1))                      # C1=10 … C7=16
        return None
```

### _prep_score（第 2910 行）

```python
def _prep_score(self):
        digest = self._value("trackwork_digest")
        numbers = re.findall(r"備戰分(\d+(?:\.\d+)?)", str(digest or ""))
        return float(numbers[-1]) if numbers else 60.0
```

### _current_jockey_horse_record（第 2915 行）

```python
def _current_jockey_horse_record(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        # SCORING uses the RECENCY window (current jockey's rides within the
        # horse's most recent races, i.e. the 近6場 history table) rather than the
        # full-career combo table. Point-in-time backtest over 16.8k runners shows
        # recency is the stronger predictor (corr 0.129 vs full-career 0.124;
        # strong-bucket top3 38.1% vs 36.4%). The full table is DISPLAY only.
        recent = self._recent_jockey_horse_record(current_jockey)
        if recent is not None:
            return recent
        if self._recent_jockey_history_rows():
            # Recency table present but current jockey absent → no recent signal.
            return None
        # Legacy fallback: no 近6場 table → use full combo table row.
        for row in self._jockey_combo_rows():
            if row["is_current"] or row["jockey"] == current_jockey:
                return {
                    "starts": row["starts"],
                    "wins": row["wins"],
                    "places": row["places"],
                    "avg_finish": row["avg_finish"],
                    "win_rate": row["win_rate"],
                    "place_rate": row["place_rate"],
                }
        return None
```

### _recent_jockey_horse_record（第 2941 行）

```python
def _recent_jockey_horse_record(self, current_jockey):
        """Current jockey's record over the horse's recent races (近6場 table).

        Returns None when no recency table exists (caller decides fallback) or
        when the current jockey has no completed run in that window.
        """
        rows = self._recent_jockey_history_rows()
        if not rows:
            return None
        finishes = []
        for row in rows:
            if self._clean(row["jockey"]) != current_jockey:
                continue
            match = re.search(r"\d+", str(row["finish"]))
            if not match:
                continue
            value = int(match.group(0))
            if value > 0:
                finishes.append(value)
        if not finishes:
            return None
        starts = len(finishes)
        wins = sum(1 for f in finishes if f == 1)
        shows = sum(1 for f in finishes if f <= 3)
        places = sum(1 for f in finishes if f <= 2)
        return {
            "starts": float(starts),
            "wins": float(wins),
            "places": float(places),
            "avg_finish": round(sum(finishes) / starts, 1),
            "win_rate": round(wins / starts * 100, 1),
            "place_rate": round(shows / starts * 100, 1),
        }
```

### _current_declared_jockey（第 2975 行）

```python
def _current_declared_jockey(self):
        block = str(self._value("jockey_combo_block") or "")
        match = re.search(r"今場騎師:\s*([^\n]+)", block)
        return match.group(1).strip() if match else ""
```

### _jockey_combo_rows（第 2980 行）

```python
def _jockey_combo_rows(self):
        block = str(self._value("jockey_combo_block") or "")
        rows = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]
            if len(cols) < 8:
                continue
            if cols[0] in {"騎師", "------", "#", "---"}:
                continue
            if cols[0].startswith("#") or cols[0].isdigit():
                continue
            jockey_col = cols[0]
            is_current = "← 今場" in jockey_col
            jockey_name = jockey_col.replace("← 今場", "").strip()
            try:
                rows.append(
                    {
                        "jockey": jockey_name,
                        "starts": float(cols[1]),
                        "wins": float(cols[2]),
                        "places": float(cols[4]),
                        "avg_finish": float(cols[5]),
                        "win_rate": float(re.search(r"-?\d+(?:\.\d+)?", cols[6]).group(0)),
                        "place_rate": float(re.search(r"-?\d+(?:\.\d+)?", cols[7]).group(0)),
                        "is_current": is_current,
                    }
                )
            except (AttributeError, ValueError):
                continue
        return rows
```

### _recent_jockey_history_rows（第 3014 行）

```python
def _recent_jockey_history_rows(self):
        block = str(self._value("jockey_combo_block") or "")
        rows = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]
            if len(cols) < 5:
                continue
            if cols[0] in {"#", "---"} or cols[0].startswith("---"):
                continue
            if not re.fullmatch(r"\d+", cols[0]):
                continue
            rows.append(
                {
                    "index": int(cols[0]),
                    "date": cols[1],
                    "jockey": cols[2],
                    "finish": cols[3],
                    "note": cols[4],
                }
            )
        rows.sort(key=lambda row: row["index"])
        return rows
```

### _jockey_trainer_prior（第 3116 行）

```python
def _jockey_trainer_prior(self):
        priors = self._value("jockey_trainer_combo_prior")
        if not isinstance(priors, dict):
            return None
        # Old orchestrators embedded this aggregate into Logic and some 2026-04/05
        # archives were rewritten after the races (same-day and future results).
        # Only a live card may trust it; replays use the guarded prior stack.
        as_of_date = (self.race_context or {}).get("race_date")
        if not temporal_source_is_safe(EMBEDDED_LOGIC_PRIOR, as_of_date):
            return None
        return priors
```

### _value（第 3137 行）

```python
def _value(self, key):
        if key in self.horse_data and self.horse_data.get(key) not in (None, ""):
            return self.horse_data.get(key)
        return self.data.get(key)
```

### _text（第 3142 行）

```python
def _text(self, *keys):
        return " ".join(str(self._value(key) or "") for key in keys)
```

### _is_debut（第 3145 行）

```python
def _is_debut(self):
        return bool(self.horse_data.get("is_debut") or self.horse_data.get("debut_runner") or self.horse_data.get("career_tag") == "DEBUT")
```

### _is_sha_tin_context（第 3148 行）

```python
def _is_sha_tin_context(self):
        value = self.race_context.get("venue") or self.race_context.get("course") or self.race_context.get("racecourse") or ""
        text = str(value)
        return text in {"ST", "Sha Tin", "ShaTin", "沙田"} or "沙田" in text or "ShaTin" in text or "Sha Tin" in text
```

### _is_sha_tin_turf_context（第 3153 行）

```python
def _is_sha_tin_turf_context(self):
        if not self._is_sha_tin_context():
            return False
        surface = " ".join(
            str(self.race_context.get(key) or "")
            for key in ("venue", "course", "track", "surface", "track_type")
        ).upper()
        return not any(token in surface for token in ("AWT", "ALL WEATHER", "全天候", "泥地"))
```

### _clean（第 3162 行）

```python
def _clean(self, value):
        text = str(value or "").strip()
        return "資料未完成，中性處理" if "[FILL" in text.upper() else text
```

### _season_record（第 3398 行）

```python
def _season_record(self):
        return parse_record(self.horse_data.get("season_stats") or self._value("season_stats_line"))
```

### _same_distance_record（第 3401 行）

```python
def _same_distance_record(self):
        """同程 (冠-亞-季-其餘) —— starts 係四項總和，唔係第四項（見 parse_record）。"""
        text = self._clean(self.horse_data.get("season_stats") or self._value("season_stats_line") or "")
        match = re.search(r"同程\s*\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
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
```

### _formline_strength_signal（第 3416 行）

```python
def _formline_strength_signal(self):
        text = self._clean(self._value("formline_strength") or "")
        if "極強" in text:
            return "elite"
        if "強" in text:
            return "strong"
        if "弱" in text:
            return "weak"
        if text and text != "N/A":
            return "neutral"
        return "unknown"
```

### _trackwork_markers（第 3773 行）

```python
def _trackwork_markers(self):
        digest = self._clean(self._value("trackwork_digest") or "")
        classification = ""
        trend = ""
        positive = ""
        risk = ""
        if digest:
            classification_match = re.search(r"分類為「([^」]+)」", digest)
            trend_match = re.search(r"操練趨勢([^。；]+)", digest)
            positive_match = re.search(r"正面訊號：([^；。]+)", digest)
            risk_match = re.search(r"風險訊號：([^；。]+)", digest)
            classification = classification_match.group(1) if classification_match else ""
            trend = f"操練趨勢{trend_match.group(1)}" if trend_match else ""
            positive = positive_match.group(1).strip() if positive_match else ""
            risk = risk_match.group(1).strip() if risk_match else ""
        return {
            "classification": classification,
            "trend": trend,
            "positive": positive,
            "risk": risk,
        }
```

## orchestrator：_apply_sip_enhancements

```python
def _apply_sip_enhancements(horses):
    """
    SIP-C: B- horse with light weight + good draw → +1.0 (原始尺) ability_score

    門檻同加幅一律用**原始加權總分**（`ability_score_raw`），唔用 grade 字串。
    原本寫 `grade == "B-"`，所以 `GRADE_THRESHOLDS` 一改，SIP 觸發嘅係另一批馬
    ——即係一個「純顯示」嘅改動會靜靜咁改排名。改用原始尺個窗（64 ≤ raw < 68，
    等同舊 B- 帶）之後，SIP 對顯示尺完全免疫，實測 210 個觸發 bit-identical。
    """
    weights = []
    for h_obj in horses.values():
        w = h_obj.get("weight")
        if w is not None:
            try:
                weights.append(int(w))
            except (ValueError, TypeError):
                pass
    if not weights:
        return
    field_median = sorted(weights)[len(weights) // 2]

    for h_num, h_obj in horses.items():
        auto = h_obj.get("python_auto", {})
        if not auto:
            continue
        grade = auto.get("grade", "")
        ability_score = auto.get("ability_score", 0)
        # 舊 Logic 冇 ability_score_raw，用逆函數還原（見 scoring.from_display_scale）。
        raw = auto.get("ability_score_raw")
        if raw is None:
            raw = from_display_scale(ability_score)
        raw = float(raw)
        weight = h_obj.get("weight")
        barrier = h_obj.get("barrier")
        try:
            weight_val = int(weight) if weight is not None else None
            barrier_val = int(barrier) if barrier is not None else None
        except (ValueError, TypeError):
            continue
        if weight_val is None or barrier_val is None:
            continue

        is_light = weight_val <= field_median
        is_good_draw = barrier_val <= 5
        boost = 0.0
        reasons = []

        fs = auto.get("feature_scores", {})
        speed = fs.get("speed_score", 0)
        form = fs.get("form_score", 0)
        consist = fs.get("consistency_score", 0)

        # 64 ≤ raw < 68 = 舊 GRADE_THRESHOLDS 嘅 B- 帶，喺原始尺上面表達。
        if 64.0 <= raw < 68.0 and is_light and is_good_draw:
            if speed >= 68 or (form >= 55 and consist >= 55):
                boost = 1.0
                reasons.append("輕磅+好檔+速度/穩定性(SIP-C)")

        if boost > 0:
            new_raw = round(raw + boost, 4)
            new_score = round(to_display_scale(new_raw), 2)
            auto["ability_score"] = new_score
            auto["ability_score_raw"] = new_raw
            auto["grade"] = compute_grade(new_score)
            sip_flag = {
                "reason": "; ".join(reasons),
                "boost": round(boost, 1),
                "boost_scale": "raw",
                "original_score": ability_score,
                "original_score_raw": round(raw, 4),
                "original_grade": grade,
            }
            auto.setdefault("sip_flags", []).append(sip_flag)
            # Every shadow is a counterfactual of the same horse, so the
            # post-matrix SIP adjustment must be identical on both sides.
            # Otherwise the shadow delta would accidentally test two changes.
            for shadow in (auto.get("shadow_profiles") or {}).values():
                try:
                    shadow_raw = round(float(shadow.get("ability_score_raw")) + boost, 4)
                except (TypeError, ValueError):
                    continue
                shadow_score = round(to_display_scale(shadow_raw), 2)
                shadow["ability_score_raw"] = shadow_raw
                shadow["ability_score"] = shadow_score
                shadow["ability_delta"] = round(shadow_score - new_score, 2)
                shadow["grade"] = compute_grade(shadow_score)
                shadow.setdefault("sip_flags", []).append(dict(sip_flag))
```

## orchestrator：_apply_mainline_shape_robustness

```python
def _apply_mainline_shape_robustness(horses):
        """Winsorize extreme whole-field shape deviations before official ranking."""
        if active_race_shape_robustness_profile() == "legacy_unbounded":
            return
        profile_name = "race_shape_legacy_unbounded"
        eligible = []
        for horse_num, horse in horses.items():
            auto = horse.get("python_auto", {})
            shadow = ((auto.get("shadow_profiles") or {}).get(profile_name) or {})
            matrix = auto.get("matrix_scores") or {}
            try:
                shape = float(matrix.get("race_shape"))
            except (TypeError, ValueError):
                continue
            eligible.append((str(horse_num), auto, shadow, shape))
        if not eligible:
            return
        ordered = sorted(item[3] for item in eligible)
        middle = len(ordered) // 2
        median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2.0
        )
        for _horse_num, auto, shadow, shape in eligible:
            cap = RACE_SHAPE_ROBUST_DEVIATION_CAP
            adjusted_shape = median + max(-cap, min(cap, shape - median))
            matrix_scores = dict(auto.get("matrix_scores") or {})
            matrix_scores["race_shape"] = round(adjusted_shape, 2)
            # Debutants are scored on DEBUT_MATRIX_WEIGHTS; using the live weight
            # here inflated their capped score and made the validator refuse the
            # whole race (SCORE-004, 18 archived races, gap = Δweight × cap).
            # Same debut rule as validation.py.
            is_debut = any("debut" in str(code).lower() for code in (auto.get("reason_codes") or []))
            shape_weight = (DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS)["race_shape"]
            raw_delta = shape_weight * (adjusted_shape - shape)
            ability_raw = round(float(auto.get("ability_score_raw", 60.0)) + raw_delta, 4)
            ability_score = round(to_display_scale(ability_raw), 2)
            applied = abs(adjusted_shape - shape) > 1e-9
            auto["matrix_scores"] = matrix_scores
            auto["ability_score_raw"] = ability_raw
            auto["ability_score"] = ability_score
            auto["grade"] = compute_grade(ability_score)
            auto["race_shape_robustness"] = {
                "profile": "winsor10",
                "applied": applied,
                "meeting_median": round(median, 2),
                "base_race_shape": round(shape, 2),
                "candidate_race_shape": round(adjusted_shape, 2),
                "raw_adjustment": round(raw_delta, 4),
                "cap": cap,
                "evidence_status": "user_accepted_experimental_live",
            }
            for candidate in (auto.get("shadow_profiles") or {}).values():
                try:
                    candidate["ability_delta"] = round(
                        float(candidate.get("ability_score", ability_score)) - ability_score,
                        2,
                    )
                except (TypeError, ValueError):
                    continue
            if shadow:
                shadow["applied"] = applied
                shadow["race_shape_components"] = {
                    "formula": "rollback=unbounded production race-shape",
                    "meeting_median": round(median, 2),
                    "legacy_race_shape": round(shape, 2),
                    "live_race_shape": round(adjusted_shape, 2),
                    "cap": cap,
                    "status": "experimental_live_rollback_comparator",
                }
                shadow["reason"] = (
                    "回退對照：保留未封頂race-shape。"
                    if applied
                    else "回退對照：本駒race-shape在同場中位±10內，兩式相同。"
                )
                shadow["evidence_status"] = "experimental_live_rollback_shadow"
```
