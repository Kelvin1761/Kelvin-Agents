"""EXP-20261016-70 T5x：track base 62.9 → 60（冇場地證據 = 中性）。

舊 consistency −4 門檻（57.1）已經隨兩條「−4」情境扣分一齊剷走（EXP-20261103-10）。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine import track_going  # noqa: E402


def engine(track_line="", going_line=""):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0,
             "_data": {"track_stats_line": track_line, "going_stats_line": going_line}}
    return RacingEngine(horse, {"race_class": "BM64", "distance": "1400m",
                                "meeting_intelligence": {"venue": "Flemington", "going": "Good 4"}})


def test_no_track_evidence_is_neutral_sixty():
    assert engine()._track_score()[0] == pytest.approx(60.0)


def test_one_unplaced_start_is_a_small_penalty():
    score = engine("1:0-0-0")._track_score()[0]
    assert score == pytest.approx(60.0 + track_going.WEIGHTS["same_nil_one"])
