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
    # Leaf mix for debut runners when it differs from `leaves` (only needed when
    # a rank-neutral move gives debut and standard runners different shares).
    debut_leaves: tuple[tuple[str, float], ...] | None = None


# 負磅分喺「級數優勢」（2026-11-05 由健康搬入，總權重不變）：負磅係讓磅官對
# 能力嘅評價，唔係健康訊號。權重寫成「搬之前嘅數」嘅組合，令來源一眼睇到：
#   健康  = 0.0404 × 61.1%（風險分嗰份）
#   級數  = 0.1428 + 0.0404 × 38.9%（負磅分嗰份搬入）
#   級數內班次份額 = 0.1428 × 75% ÷ 級數權重；初出馬同理（0.05／0.30）。
_HEALTH_WEIGHT, _HEALTH_DEBUT_WEIGHT = 0.0404 * 0.611, 0.30 * 0.611
_CLASS_WEIGHT = 0.1428 + 0.0404 * 0.389
_CLASS_DEBUT_WEIGHT = 0.05 + 0.30 * 0.389
_CLASS_SHARE = 0.1428 * 0.75 / _CLASS_WEIGHT
_CLASS_DEBUT_SHARE = 0.05 * 0.75 / _CLASS_DEBUT_WEIGHT


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
        leaves=(("risk_score", 1.00),),
        weight=_HEALTH_WEIGHT, debut_weight=_HEALTH_DEBUT_WEIGHT,
        # Display ruler re-measured after the merge on 5,365 runners (2026-11-05):
        # median 69.00, SD 4.711 (risk_score alone).
        display_centre=69.0, display_gain=2.1228,
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
        key="class_advantage", label="評分與經驗", short_label="評分經驗", role="輔助",
        # 2026-11-11 由「級數優勢」改名（EXP-20261111-13）：內容係讓磅官官方評分＋經驗／季內交代，
        # 冇量班次。內部 key 唔改（存檔、harness、數據合約都用緊）。
        # 初出馬之前健康佔 0.30，所以搬入嚟嘅負磅份額大好多，要用另一個組合。
        leaves=(("class_score", _CLASS_SHARE), ("weight_score", 1.0 - _CLASS_SHARE)),
        debut_leaves=(("class_score", _CLASS_DEBUT_SHARE), ("weight_score", 1.0 - _CLASS_DEBUT_SHARE)),
        weight=_CLASS_WEIGHT, debut_weight=_CLASS_DEBUT_WEIGHT,
        # Display ruler re-measured after the merge on 5,365 runners (2026-11-05):
        # median 63.24, SD 4.840.
        display_centre=63.24, display_gain=2.0662,
        description="讓磅官官方評分（距全場最高幾多分）同經驗／季內交代。",
        dashboard_keywords=("評分", "經驗", "級數", "班次"),
    ),
)

BY_KEY = {spec.key: spec for spec in DIMENSIONS}

def weights() -> dict[str, float]:
    """Sum-to-1 weights (centred dimensions excluded)."""
    return {spec.key: spec.weight for spec in DIMENSIONS if not spec.centred}


def centred_weights() -> dict[str, float]:
    return {spec.key: spec.weight for spec in DIMENSIONS if spec.centred}


def all_keys() -> tuple[str, ...]:
    return tuple(spec.key for spec in DIMENSIONS)


def debut_weights() -> dict[str, float]:
    return {spec.key: spec.debut_weight for spec in DIMENSIONS if spec.debut_weight}


def formulas() -> dict[str, tuple[tuple[str, float], ...]]:
    return {spec.key: spec.leaves for spec in DIMENSIONS}


def debut_formulas() -> dict[str, tuple[tuple[str, float], ...]]:
    return {spec.key: spec.debut_leaves or spec.leaves for spec in DIMENSIONS}


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
