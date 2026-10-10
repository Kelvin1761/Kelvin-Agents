"""dimensions.py is the single source of truth for the HKJC rating matrix.

2026-10-10: the dimension set used to be copied into ten-plus places and the
dashboard printed "六維" for a seven-dimension model for months. These tests
pin every consumer to the registry and prove a new dimension needs only a
registry entry (plus its leaf function).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_racing_engine import dimensions  # noqa: E402


def test_consumers_derive_from_registry():
    from hkjc_racing_engine import engine_core, matrix_mapper, renderer, scoring, validation

    keys = {spec.key for spec in dimensions.DIMENSIONS}
    assert set(scoring.MATRIX_WEIGHTS) | set(scoring.CENTRED_MATRIX_WEIGHTS) == keys
    assert not set(scoring.MATRIX_WEIGHTS) & set(scoring.CENTRED_MATRIX_WEIGHTS)
    assert set(matrix_mapper.MATRIX_FORMULAS) == keys
    assert set(renderer.MATRIX_LABELS) == keys
    assert set(renderer.MATRIX_ROLES) == keys
    assert set(scoring.MATRIX_DISPLAY_CENTRES) == keys
    assert set(scoring.MATRIX_DISPLAY_GAINS) == keys
    assert set(engine_core.RacingEngine.DIM_LABELS) == keys
    assert set(validation.MATRIX_KEYS) == keys
    assert set(scoring.DEBUT_MATRIX_WEIGHTS) <= keys


def test_weights_sum_to_one():
    assert abs(sum(dimensions.weights().values()) - 1.0) < 1e-9
    assert abs(sum(dimensions.debut_weights().values()) - 1.0) < 1e-9


def test_leaf_weights_sum_to_one_per_dimension():
    for spec in dimensions.DIMENSIONS:
        assert abs(sum(w for _name, w in spec.leaves) - 1.0) < 1e-9, spec.key


def test_dashboard_manifest_matches_registry():
    manifest = dimensions.dashboard_manifest()
    assert [item["key"] for item in manifest] == [spec.key for spec in dimensions.DIMENSIONS]
    assert all(item["label"] and item["description"] for item in manifest)


def test_plug_in_dimension_reaches_every_consumer(monkeypatch):
    """Adding one DimensionSpec is enough for weights, formulas, labels and validation."""
    extra = dimensions.DimensionSpec(
        key="plug_in_test", label="插件測試", short_label="插件", role="輔助",
        leaves=(("form_score", 1.0),), weight=0.0, description="測試用",
    )
    monkeypatch.setattr(dimensions, "DIMENSIONS", dimensions.DIMENSIONS + (extra,))
    monkeypatch.setattr(dimensions, "BY_KEY", {s.key: s for s in dimensions.DIMENSIONS})
    import hkjc_racing_engine.scoring as scoring
    import hkjc_racing_engine.matrix_mapper as mapper
    import hkjc_racing_engine.renderer as renderer
    import hkjc_racing_engine.validation as validation
    try:
        for module in (scoring, mapper, renderer, validation):
            importlib.reload(module)
        assert "plug_in_test" in scoring.MATRIX_WEIGHTS
        assert "plug_in_test" in mapper.MATRIX_FORMULAS
        assert renderer.MATRIX_LABELS["plug_in_test"] == "插件測試"
        assert "plug_in_test" in validation.MATRIX_KEYS
        scores = mapper.map_features_to_matrix_scores({"form_score": 72.0})
        assert scores["plug_in_test"] == 72.0
    finally:
        monkeypatch.undo()
        for module in (scoring, mapper, renderer, validation):
            importlib.reload(module)


def test_9d_split_preserves_every_leaf_coefficient():
    """The 7D → 9D split moved trackwork and same-distance into their own
    dimensions without changing any leaf's effective coefficient."""
    standard = {}
    debut = {}
    for spec in dimensions.DIMENSIONS:
        for leaf, share in spec.leaves:
            standard[leaf] = standard.get(leaf, 0.0) + spec.weight * share
            debut[leaf] = debut.get(leaf, 0.0) + spec.debut_weight * share
    assert abs(standard["form_score"] - 0.0983 * 0.50) < 1e-12
    assert abs(standard["consistency_score"] - 0.0983 * 0.40) < 1e-12
    assert abs(standard["trackwork_trend_score"] - 0.0983 * 0.10) < 1e-12
    assert abs(debut["form_score"] - 0.15 * 0.50) < 1e-12
    assert abs(debut["consistency_score"] - 0.15 * 0.40) < 1e-12
    assert abs(debut["trackwork_trend_score"] - 0.15 * 0.10) < 1e-12
    assert dimensions.BY_KEY["distance_fit"].centred
    assert "distance_fit" not in dimensions.weights()


def test_transparency_rows_add_up_to_final_raw_after_orchestrator_adjustments():
    """Dashboard strip = 60 + Σ impact + adjustments must equal the final raw
    score, including the race_shape cap and SIP boosts the orchestrator applies
    after the engine built the rows."""
    import hkjc_auto_orchestrator as orch
    from hkjc_racing_engine.scoring import MATRIX_WEIGHTS

    horses = {}
    for number, shape in enumerate((40.0, 60.0, 95.0), start=1):
        matrix = {spec.key: 62.0 for spec in dimensions.DIMENSIONS}
        matrix["race_shape"] = shape
        matrix["distance_fit"] = 60.0
        raw = sum(matrix[k] * w for k, w in MATRIX_WEIGHTS.items())
        rows = [{"key": spec.key, "label": spec.label, "weight": spec.weight,
                 "score": 0, "contribution": 0} for spec in dimensions.DIMENSIONS]
        horses[str(number)] = {"python_auto": {
            "matrix_scores": matrix, "ability_score_raw": raw,
            "ability_score": orch.to_display_scale(raw), "grade": "B",
            "shadow_profiles": {}, "reason_codes": [],
            "sip_flags": [{"boost": 1.0}] if number == 2 else [],
            "grade_transparency": {"rows": rows},
        }}
    horses["2"]["python_auto"]["ability_score_raw"] += 1.0
    orch.HKJCAutoOrchestrator._apply_mainline_shape_robustness(horses)
    orch._refresh_grade_transparency(horses)
    for horse in horses.values():
        auto = horse["python_auto"]
        gt = auto["grade_transparency"]
        total = 60.0 + sum(r["impact"] for r in gt["rows"]) + sum(a["raw"] for a in gt["adjustments"])
        assert abs(total - auto["ability_score_raw"]) < 0.01
