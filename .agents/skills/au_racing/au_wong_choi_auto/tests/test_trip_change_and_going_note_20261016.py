"""EXP-20261016-71 F2（大幅增減程 −5）同 EXP-20261016-72 A（地況扣分集中一處）。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine.scoring import TRACK_MICRO_WEIGHTS as W  # noqa: E402


def engine(distance="1200m", runs=None, going="Good 4", going_line=""):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0,
             "_data": {"form_quality_runs": runs or [], "going_stats_line": going_line}}
    return RacingEngine(horse, {"race_class": "BM64", "distance": distance,
                                "meeting_intelligence": {"venue": "Flemington", "going": going}})


@pytest.mark.parametrize("last,penalised", [(1600, True), (800, True), (1500, False), (1000, False)])
def test_trip_change_threshold(last, penalised):
    eng = engine("1200m", [{"distance": last}])
    fq, note = eng._trip_change_adjustment(66.0, "")
    assert fq == pytest.approx(61.0 if penalised else 66.0)
    assert ("大幅" in note) is penalised


def test_no_runs_no_change():
    assert engine("1200m", [])._trip_change_adjustment(66.0, "x") == (66.0, "x")


def test_wet_adjustments_reported_once_with_same_total():
    line = "好地: 3:1-0-0 | 軟地: 2:0-0-0 | 重地: 0:0-0-0"
    eng = engine(going="Soft 7", going_line=line)
    parts, note = eng._going_adjustment(eng._going_stats(), "軟地", "soft7plus")
    assert [d for d, _ in parts] == [W["going_poor_pen1_wet"], W["wet_unverified_pen"]]
    assert note.count("地況適應") == 1 and "爛地實績未經驗證" in note
