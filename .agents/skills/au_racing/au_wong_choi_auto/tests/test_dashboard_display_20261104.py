"""EXP-20261104-01：dashboard 顯示修正 —— leaf 標籤由 registry 推導、試閘備戰有判讀、直路賽劇本冇「首彎」。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from au_racing_engine.dimensions import LEAF_SPECS  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402


def engine(venue="Flemington", distance="1000m", data=None):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 2, "_data": data or {},
             "tactical_plan": {"race_scenario": "出閘後可憑2檔主動守住前列，首彎前以省位切入為先，入直路前保持走位主動權。"}}
    return RacingEngine(horse, {"distance": distance, "meeting_intelligence": {"venue": venue}})


def test_every_leaf_label_comes_from_the_registry():
    eng = engine()
    for spec in LEAF_SPECS:
        assert eng._feature_label(spec.key) == spec.label


def test_straight_course_script_has_no_turn():
    text = engine()._tactical_scenario_text()
    assert "首彎" not in text and "入直路前" not in text
    assert "首彎前" in engine(distance="1600m")._tactical_scenario_text()


def test_preparation_has_its_own_reading_and_evidence():
    auto = engine(data={"trial_count": 3, "trial_top3_count": 2}).analyze_horse()
    prep = auto["matrix_reasoning"]["preparation"]
    assert "試閘密度" in prep["text"]
    assert any(line.startswith("試閘密度加分") for line in prep["anchors"])
    assert {c["label"] for c in prep["components"]} == {"試閘備戰分", "試閘 L600 分"}
