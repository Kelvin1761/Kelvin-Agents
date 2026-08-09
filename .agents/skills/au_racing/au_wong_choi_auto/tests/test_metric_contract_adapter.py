import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_metric_contract import ranked_performance  # noqa: E402


def _rows(actual_positions):
    return [
        {"horse_number": index, "actual_pos": position}
        for index, position in enumerate(actual_positions, 1)
    ]


def test_gold_is_actual_top3_captured_inside_model_top4():
    result = ranked_performance(_rows([1, 4, 2, 3, 5]))

    assert result["gold"] is True
    assert result["gold_strict"] is False
    assert result["good_positional"] is False
    assert result["pass"] is True


def test_good_requires_model_first_and_second_both_to_place():
    result = ranked_performance(_rows([1, 2, 4, 3, 5]))

    assert result["good_positional"] is True
    assert result["pass"] is True


def test_pass_requires_any_two_of_model_top3_not_one():
    one_hit = ranked_performance(_rows([4, 1, 5, 2, 3]))
    two_hits = ranked_performance(_rows([4, 1, 2, 3, 5]))

    assert one_hit["pass"] is False
    assert two_hits["pass"] is True
