"""EXP-20261009-15: draw × habitual early speed, applied at race level."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hkjc_auto_orchestrator as orch  # noqa: E402
from hkjc_racing_engine.scoring import MATRIX_WEIGHTS, to_display_scale  # noqa: E402


def _horse(barrier, early, raw=63.16):
    matrix = {key: 60.0 for key in MATRIX_WEIGHTS}
    return {
        "barrier": str(barrier),
        "_data": {"habitual_early_position": early},
        "python_auto": {
            "ability_score_raw": raw,
            "ability_score": round(to_display_scale(raw), 2),
            "matrix_scores": matrix,
            "shadow_profiles": {},
        },
    }


def _race():
    # barriers 1..8; habitual early: forward ones at 0.1, back ones at 0.9
    early = {1: 0.1, 2: 0.9, 3: 0.1, 4: 0.9, 5: 0.1, 6: 0.9, 7: 0.1, 8: 0.9}
    return {str(b): _horse(b, e) for b, e in early.items()}


def test_wide_forward_gains_and_wide_backmarker_loses():
    horses = _race()
    orch.HKJCAutoOrchestrator._apply_early_draw_interaction(horses)
    adj = {k: h["python_auto"]["early_draw_adjustment"]["raw_adjustment"] for k, h in horses.items()}
    assert adj["7"] > 0          # wide (7), habitual leader
    assert adj["8"] < 0          # wide (8), habitual back-marker
    assert adj["7"] > adj["1"]   # inner runners are not the ones that move most
    for h in horses.values():
        auto = h["python_auto"]
        assert auto["early_draw_adjustment"]["active"] is True
        rollback = auto["shadow_profiles"]["early_draw_rollback"]
        assert abs(rollback["ability_score_raw"] + auto["early_draw_adjustment"]["raw_adjustment"]
                   - auto["ability_score_raw"]) < 1e-3


def test_too_few_runners_with_a_habit_is_a_no_op():
    horses = _race()
    for key in ("1", "2", "3", "4", "5"):
        horses[key]["_data"]["habitual_early_position"] = None
    orch.HKJCAutoOrchestrator._apply_early_draw_interaction(horses)
    for h in horses.values():
        assert h["python_auto"]["early_draw_adjustment"]["raw_adjustment"] == 0.0
        assert h["python_auto"]["early_draw_adjustment"]["active"] is False


def test_pure_weight_arm_receives_the_same_delta():
    horses = _race()
    arm = {"profile": "race_shape_w200", "applied": True, "ability_score_raw": 63.16,
           "ability_score": round(to_display_scale(63.16), 2), "fixed_raw_adjustment": 0.0,
           "weights": dict(MATRIX_WEIGHTS), "matrix_scores": {k: 60.0 for k in MATRIX_WEIGHTS}}
    horses["7"]["python_auto"]["shadow_profiles"]["race_shape_w200"] = dict(arm)
    orch.HKJCAutoOrchestrator._apply_early_draw_interaction(horses)
    auto = horses["7"]["python_auto"]
    shadow = auto["shadow_profiles"]["race_shape_w200"]
    delta = auto["early_draw_adjustment"]["raw_adjustment"]
    assert abs(shadow["ability_score_raw"] - (63.16 + delta)) < 1e-6
    assert abs(shadow["fixed_raw_adjustment"] - delta) < 1e-6


def test_weight_arm_gets_the_mainline_shape_cap(monkeypatch):
    monkeypatch.setattr(orch, "active_race_shape_robustness_profile", lambda: "winsor10")
    horses = {}
    for number, shape in enumerate((60.0, 61.0, 62.0, 95.0), start=1):
        matrix = {key: 60.0 for key in MATRIX_WEIGHTS}
        matrix["race_shape"] = shape
        raw = sum(matrix[k] * w for k, w in MATRIX_WEIGHTS.items())
        arm_weights = {**MATRIX_WEIGHTS}
        horses[str(number)] = {"python_auto": {
            "ability_score_raw": raw, "ability_score": round(to_display_scale(raw), 2),
            "matrix_scores": dict(matrix),
            "shadow_profiles": {"weight_rollback_0809": {
                "profile": "weight_rollback_0809", "applied": True, "weights": arm_weights,
                "matrix_scores": dict(matrix), "ability_score_raw": raw,
                "ability_score": round(to_display_scale(raw), 2), "fixed_raw_adjustment": 0.0}},
        }}
    orch.HKJCAutoOrchestrator._apply_mainline_shape_robustness(horses)
    capped = horses["4"]["python_auto"]
    arm = capped["shadow_profiles"]["weight_rollback_0809"]
    assert capped["matrix_scores"]["race_shape"] < 95.0
    assert arm["matrix_scores"]["race_shape"] == capped["matrix_scores"]["race_shape"]
    assert abs(arm["ability_score_raw"] - capped["ability_score_raw"]) < 1e-3


def test_debut_shape_cap_uses_debut_weight(monkeypatch):
    from hkjc_racing_engine.scoring import DEBUT_MATRIX_WEIGHTS
    from hkjc_racing_engine.validation import validate_logic_data  # noqa: F401
    monkeypatch.setattr(orch, "active_race_shape_robustness_profile", lambda: "winsor10")
    horses = {}
    for number, shape in enumerate((65.0, 65.0, 65.0, 49.06), start=1):
        horses[str(number)] = {"python_auto": {
            "ability_score_raw": 60.0, "ability_score": round(to_display_scale(60.0), 2),
            "matrix_scores": {**{k: 60.0 for k in MATRIX_WEIGHTS}, "race_shape": shape},
            "reason_codes": ["debut_class_unknown"] if number == 4 else [],
            "shadow_profiles": {}}}
    orch.HKJCAutoOrchestrator._apply_mainline_shape_robustness(horses)
    debut = horses["4"]["python_auto"]
    moved = debut["matrix_scores"]["race_shape"] - 49.06
    assert abs(debut["race_shape_robustness"]["raw_adjustment"] - DEBUT_MATRIX_WEIGHTS["race_shape"] * moved) < 1e-3
