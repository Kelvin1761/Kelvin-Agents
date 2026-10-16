"""EXP-20261016-75 P2：試閘「前列」按試閘場內百分位（≤ 40%），唔再用絕對前三。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.engine_core import RacingEngine  # noqa: E402


def engine(trials):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0,
             "jockey": "Some Rider", "trainer": "Some Stable", "_data": {"fg_trials": trials}}
    return RacingEngine(horse, {"race_class": "BM64", "distance": "1200m", "field_summary": {"count": 10}})


def test_third_of_four_is_not_front_but_third_of_ten_is():
    assert engine([{"finish_pos": 3, "starters": 4}])._formguide_trial_counts() == (1, 0)
    assert engine([{"finish_pos": 3, "starters": 10}])._formguide_trial_counts() == (1, 1)


def test_missing_field_size_keeps_absolute_rule():
    assert engine([{"finish_pos": 3, "starters": None}, {"finish_pos": 4, "starters": None}])._formguide_trial_counts() == (2, 1)


def test_two_front_trials_earn_the_bonus_with_honest_wording():
    eng = engine([{"finish_pos": 1, "starters": 8}, {"finish_pos": 2, "starters": 8}])
    eng._jockey_horse_fit_score()
    factors = [a for a in eng.jt_fit_detail["adjustments"] if a["factor"] == "試閘交代密度足夠"]
    assert factors and "往績表試閘" in factors[0]["evidence"] and "近期" not in factors[0]["evidence"]


def test_without_formguide_trials_old_rule_applies():
    eng = engine(None)
    eng.data["trial_count"] = 3
    eng.data["trial_top3_count"] = 2
    eng._jockey_horse_fit_score()
    assert any(a["factor"] == "試閘交代密度足夠" for a in eng.jt_fit_detail["adjustments"])
