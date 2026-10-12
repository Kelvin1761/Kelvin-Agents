"""Display counts follow active coefficients without changing numeric state."""
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from au_racing_engine.dimensions import MATRIX_WEIGHTS, ranking_dimension_numeral
from au_racing_engine.renderer import _ranking_dimension_label
from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.dimensions import MATRIX_LABELS


def test_default_six_dimension_text_is_unchanged():
    assert ranking_dimension_numeral() == '六'
    assert _ranking_dimension_label() == '六維排名'


def test_counts_active_coefficients_not_reference_or_zero_weight_entries():
    values = {**MATRIX_WEIGHTS, 'reference': 0, 'new': 0.2}
    before = copy.deepcopy(values)
    assert ranking_dimension_numeral(values) == '七'
    assert values == before
    assert ranking_dimension_numeral({'negative': -0.2, 'zero': 0}) == '一'
    assert ranking_dimension_numeral({}) == '零'
    assert ranking_dimension_numeral({str(i): 1 for i in range(11)}) == '11'


def test_current_matrix_labels_follow_registry_and_legacy_aliases_survive():
    engine = RacingEngine.__new__(RacingEngine)
    for key, label in MATRIX_LABELS.items():
        assert engine._matrix_label(key) == label
    assert engine._matrix_label('sectional') == '段速與引擎'
    assert engine._matrix_label('class_level') == '級數門檻'
    assert engine._matrix_label('unknown_legacy') == 'unknown_legacy'
