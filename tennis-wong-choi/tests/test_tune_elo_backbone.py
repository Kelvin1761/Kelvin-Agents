"""The backbone harness must reproduce production's read, lag and all.

2026-10-09: `elo_builder` stamps each PRE-match rating with the match date and
`rating_as_of` reads the latest row strictly before the date, so production
prices every match off the rating from before the player's previous match.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tennis_wc.features.elo import elo_probability

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "tune_elo_backbone", ROOT / "scripts" / "tune_elo_backbone.py")
harness = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = harness   # dataclasses resolve annotations through it
_spec.loader.exec_module(harness)

# (winner, loser, date, surface, level, tour)
SEQ = [
    (1, 2, "2026-01-01", None, "A", "ATP"),   # both debut: not scored
    (1, 3, "2026-01-02", None, "A", "ATP"),   # 3 debuts: not scored
    (1, 2, "2026-01-03", None, "A", "ATP"),   # scored
]


def test_production_lag_reads_the_rating_before_the_previous_match():
    lag = harness.walk(SEQ, harness.Params(lag=True))
    # Production on 01-03 reads player 1's row from 01-02, which holds the
    # rating BEFORE the 01-02 win, and player 2's row from 01-01: 1500.
    p = harness.Params()
    r1_after_d1 = 1500 + p.k(0) * 0.5
    expected = elo_probability(r1_after_d1, 1500.0)
    assert len(lag.p_winner) == 1
    assert abs(lag.p_winner[0] - expected) < 1e-9


def test_fixed_reads_the_rating_at_the_start_of_the_match_day():
    fixed = harness.walk(SEQ, harness.Params(lag=False))
    p = harness.Params()
    r1 = 1500 + p.k(0) * 0.5
    r2 = 1500 - p.k(0) * 0.5
    e = elo_probability(r1, 1500.0)
    r1 = r1 + p.k(1) * (1 - e)
    expected = elo_probability(r1, r2)
    assert abs(fixed.p_winner[0] - expected) < 1e-9


def test_variants_score_the_identical_match_set():
    a = harness.walk(SEQ, harness.Params(lag=True))
    b = harness.walk(SEQ, harness.Params(lag=False))
    assert a.keys == b.keys


def test_a_second_match_on_the_same_day_does_not_see_the_first():
    seq = [
        (1, 2, "2026-01-01", None, "A", "ATP"),
        (1, 2, "2026-01-02", None, "A", "ATP"),
        (1, 2, "2026-01-02", None, "A", "ATP"),   # same day: start-of-day read
    ]
    fixed = harness.walk(seq, harness.Params(lag=False))
    assert fixed.p_winner[0] == fixed.p_winner[1]


def test_final_ratings_match_the_builder_update_rule():
    """`verify` compares these against players.overall_elo."""
    out = harness.walk(SEQ, harness.Params())
    assert set(out.final_overall) == {1, 2, 3}
    assert out.final_overall[1] > 1500 > out.final_overall[3]
