"""The ablation harness must reproduce the shipped model before it may judge it.

2026-08-29. Two harnesses disagreed about the same question and the faithful one
won:

  * Reconstructing the Elo backbone from `elo_history.rating_as_of` TODAY and
    treating `logit(stored) - logit(backbone)` as "the nudge" said that turning
    all nine nudges off improved clay by -0.0307, CI [-0.0551, -0.0072],
    monotone in the scale factor.
  * Rebuilding the components from each fixture's STORED feature snapshot said
    that removing any single nudge on clay either does nothing or HURTS
    (head_to_head +0.0051, serve_return +0.0036, opponent_rank_bucket +0.0028,
    tournament_level +0.0018, every CI clear of zero).

The first was wrong. `player_elo_history` is DERIVED from
`player_match_history`, which has grown to 361,200 rows since those predictions
were made, so a rating "as of June" recomputed today is built from matches that
predate June but were ingested afterwards. Every date filter passes and the
information set is still larger than the model had -- so the reconstruction was
a hindsight-complete backbone, and "removing the nudges" was really "replacing
the model's Elo with a better-informed Elo".

Hence this file: a harness that cannot reproduce the shipped number is not
measuring the shipped model.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "ablate_surface_nudges", ROOT / "scripts" / "ablate_surface_nudges.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

from tennis_wc.modelling.probability_model import (  # noqa: E402
    NUDGE_GAINS,
    _component_probabilities,
    predict_match_probability,
)


# A nudge component only contributes when it is ACTIVE and off 0.5. A fixture
# where every bucket rate is 0.5 makes all nine contribute exactly nothing, so
# "dropping a nudge" changes no answer -- which is a property of the fixture,
# not of the harness. The rates here are deliberately asymmetric.
def _side(bucket_rate: float, **over):
    side = {
        "surface_elo": {"value": 1850.0},
        "overall_elo": {"value": 1800.0},
        "current_rank": {"value": 30},
        "opponent_rank_buckets": {
            b: {"shrinked_win_rate": {"value": bucket_rate}}
            for b in ("UNKNOWN", "TOP_10", "TOP_25", "TOP_50", "TOP_100",
                      "RANK_101_200", "RANK_201_PLUS")
        },
        "head_to_head": {"wins": {"value": 4}, "losses": {"value": 1},
                         "matches": {"value": 5}, "sample_size": {"value": 5}},
    }
    side.update(over)
    return side


def _snapshot(a_surface=1850.0, b_surface=1700.0):
    return {
        "player_a": _side(0.72, surface_elo={"value": a_surface}),
        "player_b": _side(0.31, surface_elo={"value": b_surface},
                          overall_elo={"value": 1780.0}),
        "match_context": {"surface": {"value": "clay"}, "tour": {"value": "ATP"},
                          "round": {"value": "R1"}},
    }


def test_the_harness_combiner_matches_the_shipped_one():
    """`combine` is a copy of `_combine_components`, kept separate only so the
    gains can be varied. If the copy drifts, every ablation is measuring a
    different model than the one in production."""
    snapshot = _snapshot()
    components = _component_probabilities(snapshot)
    shipped = predict_match_probability(snapshot)["player_a_probability"]
    assert abs(harness.combine(components, None) - shipped) < 1e-9


def test_dropping_a_nudge_changes_the_answer():
    """A no-op ablation would report every signal as worthless. The gains are
    read from the live NUDGE_GAINS, so this also fails if a nudge is retired
    without the harness noticing."""
    snapshot = _snapshot()
    components = _component_probabilities(snapshot)
    base = harness.combine(components, None)
    moved = [
        name for name in NUDGE_GAINS
        if abs(harness.combine(components, name) - base) > 1e-12
    ]
    assert moved, "no nudge changed the blend -- the harness is not wired"


def test_dropping_every_nudge_actually_moves_the_answer():
    """Guards the previous test from passing on a fixture where nothing was
    active in the first place."""
    snapshot = _snapshot()
    components = _component_probabilities(snapshot)
    assert abs(harness.combine(components, harness.DROP_ALL)
               - harness.combine(components, None)) > 1e-6


def test_dropping_every_nudge_leaves_the_elo_backbone():
    """`__ALL__` is not a nudge name, so it drops nothing by name and everything
    by effect only if the loop is written that way. Verify it really is the
    backbone."""
    snapshot = _snapshot()
    components = _component_probabilities(snapshot)
    stripped = harness.combine(components, harness.DROP_ALL)
    by_name = {c.name: c for c in components}
    backbone = 0.0
    weight = 0.0
    from tennis_wc.modelling.probability_model import ELO_BACKBONE_WEIGHTS
    for name, w in ELO_BACKBONE_WEIGHTS.items():
        component = by_name[name]
        backbone += w * math.log(component.probability / (1 - component.probability))
        weight += w
    expected = 1 / (1 + math.exp(-(backbone / weight)))
    assert abs(stripped - min(max(expected, 0.02), 0.98)) < 1e-9, (
        "__ALL__ must leave exactly the Elo backbone; it currently drops only "
        "nudges whose NAME matches, so a real all-off needs its own branch"
    )


def test_a_blanked_snapshot_body_is_skipped_not_parsed():
    """Retention blanks superseded bodies and keeps the rows."""
    class Conn:
        def execute(self, *_a, **_k):
            class R:
                def fetchone(self_inner):
                    return ("",)
            return R()

    assert harness._latest_snapshot(Conn(), 1, 1) is None


def test_the_bootstrap_refuses_a_small_sample():
    rows = [{"components": _component_probabilities(_snapshot()), "won_a": 1}] * 10
    assert harness.paired(rows, "serve_return_edge") == {"n": 10}
