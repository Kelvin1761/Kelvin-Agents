"""AU dimension/leaf metadata; isolated from HKJC and any fitted profile.

Safety defaults preserve the legacy comparison and are not assertions that
all engine no-evidence exits equal60. Leaf provenance policies remain owned
by the engine until their semantic audit is complete.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os

REGISTRY_SCHEMA_VERSION = "au/dimensions-v1"
SCORING_CONTRACT_VERSION = "au/raw-matrix-preparation-v2"
CLASS_SCORE_LIVE = os.environ.get("WC_AU_CLASS_SCORE_LIVE", "1") != "0"
CLASS_SCORE_LIVE_WEIGHT = 0.15

@dataclass(frozen=True)
class LeafSpec:
    key: str
    label: str
    legacy_ability_order: int | None
    report_only: bool
    counts_as_evidence: bool
    safety_default: float = 60.0
    shown_in_report: bool = True

@dataclass(frozen=True)
class DimensionSpec:
    key: str
    label: str
    leaves: tuple[tuple[str, float], ...]
    coefficient: float | None = None
    ranking_order: int | None = None
    shown_in_report: bool = True
    reasoning_components: tuple[str, ...] = ()
    reasoning_score_default: float | None = None

LEAF_SPECS = (
    LeafSpec('form_score', '近績分', 0, False, True),
    # EXP-20261016-01 F6: trial performance removed (user decision); report-only, not evidence.
    LeafSpec('trial_score', '試閘分', None, True, False),
    LeafSpec('sectional_score', '段速分', None, True, False),
    LeafSpec('pace_map_score', '檔位分', 4, False, False),
    LeafSpec('jockey_score', '騎師分', 5, False, True),
    LeafSpec('trainer_score', '練馬師分', 6, False, True),
    LeafSpec('jockey_horse_fit_score', '人馬配搭分', 7, False, True),
    LeafSpec('class_score', '級數分', None, True, False),
    LeafSpec('rating_score', 'Rating 分', 8, False, True),
    LeafSpec('weight_score', '負磅分', None, True, False),
    LeafSpec('distance_score', '路程分', None, True, False),
    LeafSpec('track_score', '同場／地況往績分', 9, False, True),
    LeafSpec('formline_score', '賽績線分', None, True, False),
    LeafSpec('consistency_score', '穩定性分', None, True, False),
    LeafSpec('performance_quality_score', '表現質素分', 1, False, True),
    LeafSpec('health_score', '備戰完整度分', None, True, False),
    LeafSpec('confidence_score', '信心分', None, True, False),
    LeafSpec('pace_figure_score', 'L600 環境分', 2, False, True),
    LeafSpec('preparation_score', '試閘備戰分', 10, False, False),
)

DIMENSION_SPECS = (
    DimensionSpec('stability', '狀態與穩定性', (('form_score', 0.6), ('performance_quality_score', 0.4)), 0.37099725005319806, 0),
    # EXP-20261016-01 F6: trial_score left pace_perf. Coefficient = 0.12093934478578448 × 0.941744,
    # so pace_figure's contribution to the composite is unchanged.
    DimensionSpec('pace_perf', '速度考驗背景', (('pace_figure_score', 1.0),), 0.12093934478578448 * 0.941744, 1, reasoning_components=('pace_figure_score', 'sectional_score'), reasoning_score_default=60.0),
    DimensionSpec('race_shape', '檔位形勢', (('pace_map_score', 1.0),), None, None),
    DimensionSpec('jockey_trainer', '騎練訊號', (('jockey_score', 0.333333), ('trainer_score', 0.285714), ('jockey_horse_fit_score', 0.380952)), 0.6626585553070451, 2),
    DimensionSpec('class_weight', '官方評分對位', (("rating_score", 0.70),) + ((("class_score", CLASS_SCORE_LIVE_WEIGHT),) if CLASS_SCORE_LIVE else ()), 0.3826193901797637, 3, reasoning_components=('class_score', 'rating_score', 'weight_score')),
    DimensionSpec('track', '場地與地況適性', (('track_score', 1.0),), 0.14114297066700832, 4),
    DimensionSpec('form_line', '賽績線', (('formline_score', 1.0),), None, None, reasoning_components=('formline_score', 'form_score')),
    DimensionSpec('preparation', '試閘備戰', (('preparation_score', 1.0),), 0.25244110196132946, 5),
 )

def validate_registry(leaf_specs, dimension_specs):
    """Reject ambiguous/invalid structure before deriving any consumer maps.

    Ranking, report and evidence roles remain independent; this is not a
    model-performance, provenance or source-availability gate.
    """
    def identity(spec, kind):
        if not isinstance(spec.key, str) or not spec.key.isidentifier():
            raise ValueError(f"Invalid {kind} key: {spec.key!r}")
        if not isinstance(spec.label, str) or not spec.label.strip():
            raise ValueError(f"Missing {kind} label: {spec.key}")

    def finite(value, field, score=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Invalid finite registry number: {field}")
        if score and not 0 <= value <= 100:
            raise ValueError(f"Registry score outside 0–100: {field}")

    def order(value, field, used):
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value in used:
            raise ValueError(f"Invalid/duplicate registry order: {field}")
        used.add(value)

    leaves = set()
    ability_order = set()
    for leaf in leaf_specs:
        if not isinstance(leaf, LeafSpec):
            raise ValueError("Registry leaf must be a LeafSpec")
        identity(leaf, "leaf")
        if leaf.key in leaves:
            raise ValueError(f"Duplicate leaf key: {leaf.key}")
        leaves.add(leaf.key)
        order(leaf.legacy_ability_order, leaf.key, ability_order)
        for flag in (leaf.report_only, leaf.counts_as_evidence, leaf.shown_in_report):
            if not isinstance(flag, bool):
                raise ValueError(f"Invalid leaf role flag: {leaf.key}")
        finite(leaf.safety_default, leaf.key + ".safety_default", score=True)
    dimensions = set()
    ranking_order = set()
    for spec in dimension_specs:
        if not isinstance(spec, DimensionSpec):
            raise ValueError("Registry dimension must be a DimensionSpec")
        identity(spec, "dimension")
        if spec.key in dimensions:
            raise ValueError(f"Duplicate dimension key: {spec.key}")
        dimensions.add(spec.key)
        if not isinstance(spec.shown_in_report, bool):
            raise ValueError(f"Invalid dimension report flag: {spec.key}")
        if (spec.coefficient is None) != (spec.ranking_order is None):
            raise ValueError(f"Coefficient/ranking order must be paired: {spec.key}")
        if spec.coefficient is not None:
            finite(spec.coefficient, spec.key + ".coefficient")
        order(spec.ranking_order, spec.key, ranking_order)
        if not isinstance(spec.leaves, (tuple, list)) or not spec.leaves:
            raise ValueError(f"Dimension needs leaf components: {spec.key}")
        components = set()
        for pair in spec.leaves:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(f"Invalid leaf component pair: {spec.key}")
            key, weight = pair
            if key not in leaves or key in components:
                raise ValueError(f"Unknown/duplicate leaf component: {spec.key}/{key}")
            components.add(key)
            finite(weight, spec.key + "/" + key)
        if not isinstance(spec.reasoning_components, (tuple, list)) or any(key not in leaves for key in spec.reasoning_components):
            raise ValueError(f"Unknown reasoning component: {spec.key}")
        if spec.reasoning_score_default is not None:
            finite(spec.reasoning_score_default, spec.key + ".reasoning_default", score=True)


validate_registry(LEAF_SPECS, DIMENSION_SPECS)

FEATURE_KEYS = tuple(spec.key for spec in LEAF_SPECS)
FEATURE_LABELS = {spec.key: spec.label for spec in LEAF_SPECS}
ABILITY_FEATURE_KEYS = tuple(spec.key for spec in sorted(
    (spec for spec in LEAF_SPECS if spec.legacy_ability_order is not None),
    key=lambda spec: spec.legacy_ability_order))
REPORT_ONLY_FEATURE_KEYS = tuple(spec.key for spec in LEAF_SPECS if spec.report_only)
THIN_EVIDENCE_SCORED_LEAVES = tuple(key for key in ABILITY_FEATURE_KEYS
    if next(spec for spec in LEAF_SPECS if spec.key == key).counts_as_evidence)
SAFETY_DEFAULTS = {spec.key: spec.safety_default for spec in LEAF_SPECS if spec.counts_as_evidence}
MATRIX_FORMULAS = {spec.key: spec.leaves for spec in DIMENSION_SPECS}
MATRIX_LABELS = {spec.key: spec.label for spec in DIMENSION_SPECS if spec.shown_in_report}
MATRIX_WEIGHTS = {spec.key: spec.coefficient for spec in sorted(
    (spec for spec in DIMENSION_SPECS if spec.ranking_order is not None),
    key=lambda spec: spec.ranking_order)}

def ranking_dimension_numeral(weights=None):
    """Display the number of nonzero ranking coefficients without changing them."""
    coefficients = MATRIX_WEIGHTS if weights is None else weights
    count = sum(float(value) != 0.0 for value in coefficients.values())
    numerals = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")
    return numerals[count] if count < len(numerals) else str(count)


def contributes_to_score(leaf_key):
    return any(spec.coefficient is not None and spec.coefficient != 0 and
               any(key == leaf_key and weight != 0 for key, weight in spec.leaves)
               for spec in DIMENSION_SPECS)


def registry_snapshot():
    """Capture registry semantics, not a complete serving/PIT audit."""
    payload = {
        "schema": REGISTRY_SCHEMA_VERSION,
        "scoring_contract": SCORING_CONTRACT_VERSION,
        "safety_default_semantics": "legacy_comparison_only; engine owns missing provenance",
        "leaves": [{**asdict(spec), "contributes_to_score": contributes_to_score(spec.key)}
                   for spec in LEAF_SPECS],
        "dimensions": [asdict(spec) for spec in DIMENSION_SPECS],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return {**payload, "registry_sha256": digest}
