"""A set-weight age allowance must not become a handicap ability signal."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from au_racing_engine.engine_core import RacingEngine


def engine(title, weight=58):
    return RacingEngine({'horse_name':'Test', 'weight':weight, '_data':{}},
                        {'race_class':title, 'field_summary':{
                            'weighted_count':9, 'avg_weight':56.89, 'weight_stdev':1.24}})


@pytest.mark.parametrize('title', [
    'RACING AND SPORTS Fillies and Mares Maiden Plate', 'MDN-SW',
    'Class 1 SW + P', 'Weight-for-age Stakes', 'WFA', 'Set Weights',
])
def test_non_handicap_conditions_do_not_infer_ability_from_weight(title):
    assert engine(title)._handicap_weight_proxy() == (None, '')


@pytest.mark.parametrize('title', ['Ipswich Maiden Handicap', 'Swifts BM64 Handicap',
                                 'MAIDEN HCP', 'Benchmark 72 Handicap'])
def test_sponsor_substrings_do_not_turn_handicaps_into_set_weight_races(title):
    assert engine(title)._handicap_weight_proxy()[0] > 60


def test_age_weight_difference_cannot_raise_maiden_plate_rating(monkeypatch):
    heavy, light = engine('Fillies and Mares Maiden Plate',58), engine('Fillies and Mares Maiden Plate',55.5)
    for e in (heavy,light):
        monkeypatch.setattr(e, '_class_score', lambda: (60,'','test'))
    assert heavy._rating_score()[0] == light._rating_score()[0] == 60
