from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.engine_core import RacingEngine  # noqa: E402


CTX = {
    "race_class": "Group 1, Weight For Age",
    "distance": "1400m",
    "field_summary": {"count": 11},
    "meeting_intelligence": {"venue": "Randwick", "going": "Soft 6"},
}


def engine(*places: int) -> RacingEngine:
    rows = []
    for index, place in enumerate(places, start=1):
        # Facts table column 8 is the finishing position consumed by
        # RacingEngine._trial_places().
        rows.append(
            f"| {index} | 試閘 | 2026-08-{15-index:02d} | Randwick | "
            f"850m | Good | - | {place} | - |"
        )
    horse = {
        "horse_name": "Aeliana",
        "horse_number": "9",
        "barrier": 11,
        "weight": 57.0,
        "jockey": "Nash Rawiller",
        "trainer": "Chris Waller",
        "career_race_starts": 18,
        "_data": {"trial_count": len(places)},
    }
    return RacingEngine(horse, dict(CTX), facts_section="\n".join(rows))


def test_observed_non_top3_trials_are_below_neutral_and_flagged() -> None:
    subject = engine(8, 4, 6)
    score, note, _source = subject._trial_score()
    assert score == pytest.approx(56.0)
    assert "trial_no_recent_top3" in subject.risk_flags
    assert "有 0 次前列" in note


def test_missing_trial_data_stays_distinct_from_observed_poor_trials() -> None:
    subject = engine()
    score, _note, _source = subject._trial_score()
    assert score == pytest.approx(60.0)
    assert "trial_no_recent_top3" not in subject.risk_flags


def test_any_recent_top3_trial_clears_the_poor_trial_flag() -> None:
    subject = engine(8, 3, 6)
    score, _note, _source = subject._trial_score()
    assert score > 56.0
    assert "trial_no_recent_top3" not in subject.risk_flags
