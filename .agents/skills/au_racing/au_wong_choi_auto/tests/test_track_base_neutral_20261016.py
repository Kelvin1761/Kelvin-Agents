"""EXP-20261016-70 T5x：track base 62.9 → 60，consistency −4 門檻跟住 60 → 57.1。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine.engine_core import TRACK_WEAK_THRESHOLD, RacingEngine  # noqa: E402
from au_racing_engine.scoring import TRACK_MICRO_WEIGHTS  # noqa: E402


def engine(track_line="", going_line=""):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0,
             "_data": {"track_stats_line": track_line, "going_stats_line": going_line}}
    return RacingEngine(horse, {"race_class": "BM64", "distance": "1400m",
                                "meeting_intelligence": {"venue": "Flemington", "going": "Good 4"}})


def test_no_track_evidence_is_neutral_sixty():
    assert engine()._track_score()[0] == pytest.approx(60.0)


def test_threshold_moves_with_the_base():
    # 舊：base 62.9、門檻 60 → 差 2.9；新：base 60、門檻 57.1 → 同樣差 2.9
    assert TRACK_MICRO_WEIGHTS["base"] - TRACK_WEAK_THRESHOLD == pytest.approx(2.9)


def test_one_unplaced_start_does_not_trip_the_weak_track_rule():
    score = engine("1:0-0-0")._track_score()[0]
    assert score == pytest.approx(60.0 + TRACK_MICRO_WEIGHTS["same_track_poor_pen2"])
    assert score >= TRACK_WEAK_THRESHOLD


def test_two_unplaced_starts_still_trip_it():
    assert engine("2:0-0-0")._track_score()[0] < TRACK_WEAK_THRESHOLD
