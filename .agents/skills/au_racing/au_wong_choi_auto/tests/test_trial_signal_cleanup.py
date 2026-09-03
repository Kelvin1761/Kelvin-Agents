"""Trial terms removed 2026-09-03, and why they must not come back silently.

Both removals were measured at exactly 0.00000pp on gold, good_positional,
pass, champion and top-3 precision over 1,384 dev races (EXP-20260903-03). They
are kept out because the evidence was either duplicated or absent, not because
removing them helped. The frozen-feature golden cannot see `_trial_score` at
all, so these are the only guards.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine.scoring import TRIAL_MICRO_WEIGHTS  # noqa: E402


def _engine(**data):
    horse = {"horse_name": "T", "_data": {"trial_count": 6, **data}}
    return RacingEngine(horse, {"race_number": 1}, facts_section="")


def _factors(engine):
    engine._trial_score()
    return [a["factor"] for a in (engine.trial_detail or {}).get("adjustments", [])]


def test_density_bonus_is_gone_from_the_weight_table():
    """It duplicated preparation_score's 試閘交代密度足夠 on a strict subset."""
    assert "density_bonus" not in TRIAL_MICRO_WEIGHTS
    # The maiden-only extra is a different, non-duplicated term and stays.
    assert TRIAL_MICRO_WEIGHTS["density_maiden_bonus"] == 3.0


def test_trial_score_no_longer_pays_for_plain_trial_density(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(RacingEngine, "_trial_places", lambda self: [1, 2, 1, 3, 2, 1])
    monkeypatch.setattr(RacingEngine, "_career_starts", lambda self: 5)
    monkeypatch.setattr(RacingEngine, "_is_maiden_race", lambda self: False)
    assert "試閘密度高兼交代穩" not in _factors(engine)


def test_video_comments_cannot_move_the_trial_score(monkeypatch):
    """This source publishes no trial comments (15 of 77,336 rows).

    A future extractor that starts filling them must not silently switch six
    ±2-4 point terms back on without an A/B.
    """
    loud = {"restrained": 3, "competitive": 3, "weakened": 3,
            "led": 3, "improving": 3, "full_test": 3}
    monkeypatch.setattr(RacingEngine, "_trial_places", lambda self: [1, 2, 3])
    monkeypatch.setattr(RacingEngine, "_career_starts", lambda self: 5)
    monkeypatch.setattr(RacingEngine, "_is_maiden_race", lambda self: False)
    quiet_score, _, _ = _engine()._trial_score()
    loud_score, _, _ = _engine(trial_video_signals=loud)._trial_score()
    assert loud_score == quiet_score
    assert not any("試閘" in f and ("拑制" in f or "爭勝" in f or "轉弱" in f
                                    or "帶放" in f or "走勢" in f or "盡試" in f)
                   for f in _factors(_engine(trial_video_signals=loud)))
