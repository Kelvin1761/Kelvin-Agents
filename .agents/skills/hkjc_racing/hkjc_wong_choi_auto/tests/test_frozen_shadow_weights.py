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
