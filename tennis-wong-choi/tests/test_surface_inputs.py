"""Surface: a silent fallback, a case split, and a free recovery.

The surface component draws its own weight in the Elo backbone, and had two
ways to contribute nothing while looking fully populated:

  * unknown surface -> `get_surface_elo` returns the OVERALL rating
  * known but capitalised surface -> the lookup missed twice and did the same

The case split also mis-sorted 153 of 866 fixtures in the measurement that was
supposed to diagnose this, which is how "the deficit is all on unknown surface"
survived long enough to reach a code comment.
"""
from __future__ import annotations

import json
import sqlite3

from tennis_wc.features.surface_elo import get_surface_elo

RATINGS = json.dumps({"clay": 1710.24, "grass": 1873.09, "hard": 1859.23})


# --------------------------------------------------------------------------- #
# The lookup
# --------------------------------------------------------------------------- #
def test_a_capitalised_surface_finds_its_rating():
    """`"Hard".title()` is `"Hard"`, so the old `data.get(surface) or
    data.get(surface.title())` missed twice and fell through to the overall
    rating. 266 tournament_levels rows carried a capitalised spelling."""
    for spelling in ("hard", "Hard", "HARD", " Hard "):
        assert get_surface_elo(RATINGS, spelling, 9999.0) == 1859.23, spelling


def test_an_unknown_surface_still_falls_back():
    """This fallback is the mechanism the gate exists for -- it must stay, and
    stay visible."""
    assert get_surface_elo(RATINGS, None, 9999.0) == 9999.0
    assert get_surface_elo(RATINGS, "", 9999.0) == 9999.0
    assert get_surface_elo(RATINGS, "carpet", 9999.0) == 9999.0


def test_malformed_ratings_do_not_raise():
    assert get_surface_elo("not json", "hard", 12.0) == 12.0
    assert get_surface_elo("[1,2,3]", "hard", 12.0) == 12.0
    assert get_surface_elo(json.dumps({"hard": None}), "hard", 12.0) == 12.0


# --------------------------------------------------------------------------- #
# The warning and the gate
# --------------------------------------------------------------------------- #
def _snapshot(surface):
    side = {
        "surface_elo": {"value": 1800.0},
        "overall_elo": {"value": 1800.0},
        "current_rank": {"value": 30},
        "opponent_rank_buckets": {
            b: {"shrinked_win_rate": {"value": 0.5}}
            for b in ("UNKNOWN", "TOP_10", "TOP_25", "TOP_50", "TOP_100",
                      "RANK_101_200", "RANK_201_PLUS")
        },
    }
    return {
        "player_a": side, "player_b": side,
        "match_context": {"surface": {"value": surface}},
    }


def test_the_model_says_when_it_was_not_given_a_surface():
    from tennis_wc.modelling.probability_model import _component_probabilities

    named = {w for c in _component_probabilities(_snapshot("hard")) for w in c.warnings}
    assert "missing_surface" not in named

    for blank in (None, "", "   "):
        unnamed = {w for c in _component_probabilities(_snapshot(blank))
                   for w in c.warnings}
        assert "missing_surface" in unnamed, repr(blank)




# --------------------------------------------------------------------------- #
# The recovery
# --------------------------------------------------------------------------- #
