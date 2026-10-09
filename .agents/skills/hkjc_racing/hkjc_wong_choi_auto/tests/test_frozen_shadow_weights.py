"""A frozen prospective arm must not follow live weights (EXP-20260928-10)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine import engine_core  # noqa: E402

REGISTERED_T02 = {
    "sectional": 0.1285, "trainer_signal": 0.2362, "stability": 0.1183,
    "race_shape": 0.2537, "class_advantage": 0.1428, "horse_health": 0.0404,
    "form_line": 0.0801,
}


def test_t02_is_the_registered_vector_and_sums_to_one():
    assert engine_core._WEIGHT_REFIT_T02 == REGISTERED_T02
    assert abs(sum(REGISTERED_T02.values()) - 1.0) < 1e-9


def test_t02_does_not_move_when_live_weights_change():
    import importlib
    moved = dict(engine_core.MATRIX_WEIGHTS, race_shape=0.2416, trainer_signal=0.2683)
    try:
        with patch("hkjc_racing_engine.scoring.MATRIX_WEIGHTS", moved):
            assert importlib.reload(engine_core)._WEIGHT_REFIT_T02 == REGISTERED_T02
    finally:
        importlib.reload(engine_core)


def test_every_registered_weight_arm_is_absolute_and_sums_to_one():
    expected = {
        "weight_rollback_0809": {"sectional": 0.1285, "trainer_signal": 0.2362, "stability": 0.0983,
                                 "race_shape": 0.2737, "class_advantage": 0.1428,
                                 "horse_health": 0.0404, "form_line": 0.0801},
        "race_shape_w200": {"sectional": 0.1356, "trainer_signal": 0.2605, "stability": 0.1150,
                            "race_shape": 0.2000, "class_advantage": 0.1618,
                            "horse_health": 0.0426, "form_line": 0.0845},
        "race_shape_w170": {"sectional": 0.1407, "trainer_signal": 0.2702, "stability": 0.1193,
                            "race_shape": 0.1700, "class_advantage": 0.1679,
                            "horse_health": 0.0442, "form_line": 0.0877},
    }
    for name, vector in expected.items():
        assert engine_core._WEIGHT_ARMS[name] == vector
        assert abs(sum(vector.values()) - 1.0) < 1e-9
        assert name in engine_core._WEIGHT_SHADOW_PROFILES
    assert abs(sum(engine_core.MATRIX_WEIGHTS.values()) - 1.0) < 1e-9
