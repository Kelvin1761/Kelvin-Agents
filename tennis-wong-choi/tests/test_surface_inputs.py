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
from tennis_wc.validation.checks import (
    repair_missing_tournament_surface,
    repair_surface_casing,
    tournament_event_key,
)

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


def test_a_fixture_with_no_surface_cannot_become_a_bet():
    from tennis_wc.betting.bet_filter import apply_bet_filter

    snapshot = {
        "data_quality": {"score": 90, "is_valid": True, "errors": [], "warnings": []},
        "match_context": {"tournament": {"value": "National Bank Open"},
                          "level": {"value": "ATP_250"}},
    }
    pricing = {
        "current_market_odds": 2.0, "minimum_acceptable_odds": 1.5, "edge": 0.06,
        "model_probability": 0.56, "errors": [],
        "model": {"components": [{"warnings": ["missing_surface"]}]},
    }
    result = apply_bet_filter(snapshot, pricing)
    assert result["decision"] == "NO_BET"
    assert "missing_surface_input" in result["hard_no_bet_reasons"]


# --------------------------------------------------------------------------- #
# The recovery
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE tournaments (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE tournament_levels (id INTEGER PRIMARY KEY, tournament_id INTEGER,
    level TEXT, surface TEXT);
"""


def _conn(events) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for i, (name, surface) in enumerate(events, start=1):
        conn.execute("INSERT INTO tournaments VALUES (?,?)", (i, name))
        conn.execute(
            "INSERT INTO tournament_levels VALUES (?,?,'CHALLENGER',?)",
            (i, i, surface),
        )
    conn.commit()
    return conn


def _surface(conn, name):
    return conn.execute(
        "SELECT tl.surface FROM tournament_levels tl JOIN tournaments t "
        "ON t.id = tl.tournament_id WHERE t.name = ?", (name,)
    ).fetchone()[0]


def test_a_qualifying_draw_inherits_the_main_draws_court():
    conn = _conn([("ATP Oeiras Challenger", "clay"),
                  ("ATP Oeiras Challenger Qualifiers", None)])
    assert repair_missing_tournament_surface(conn)["filled"] == 1
    assert _surface(conn, "ATP Oeiras Challenger Qualifiers") == "clay"
    conn.close()


def test_a_points_tier_is_not_part_of_the_venue():
    """`Challenger 100 Hagen` and `Challenger 75 Hagen` are the same court."""
    conn = _conn([("ATP Challenger 75 Hagen", "clay"),
                  ("ATP Challenger 100 Hagen Q", None)])
    assert repair_missing_tournament_surface(conn)["filled"] == 1
    assert _surface(conn, "ATP Challenger 100 Hagen Q") == "clay"
    conn.close()


def test_a_generic_name_inherits_nothing():
    """The first attempt matched `ATP Challenger Singles` to a Grass event by
    stripping the suffix. It identifies no venue and must stay unknown."""
    conn = _conn([("ATP Wimbledon Challenger", "grass"),
                  ("ATP Challenger Singles", None),
                  ("ATP Challenger Qualifiers", None)])
    result = repair_missing_tournament_surface(conn)
    assert result["filled"] == 0
    assert result["no_identifying_token"] == 2
    assert _surface(conn, "ATP Challenger Singles") is None
    conn.close()


def test_disagreeing_siblings_inherit_nothing():
    conn = _conn([("ATP Split Challenger", "clay"),
                  ("ATP Split Challenger Doubles", "hard"),
                  ("ATP Split Challenger Qualifiers", None)])
    result = repair_missing_tournament_surface(conn)
    assert result["filled"] == 0 and result["ambiguous_siblings"] == 1
    conn.close()


def test_casing_must_be_folded_before_inheriting():
    """Siblings that differ only in case count as disagreeing. Folding first
    unlocked 44 further recoveries and took the ambiguous count from 82 to 38."""
    conn = _conn([("ATP Oeiras Challenger", "Clay"),
                  ("ATP Oeiras Challenger Doubles", "clay"),
                  ("ATP Oeiras Challenger Qualifiers", None)])
    assert repair_missing_tournament_surface(conn)["ambiguous_siblings"] == 1

    assert repair_surface_casing(conn) == 1
    assert repair_missing_tournament_surface(conn)["filled"] == 1
    assert _surface(conn, "ATP Oeiras Challenger Qualifiers") == "clay"
    conn.close()


def test_the_event_key_keeps_only_what_identifies_the_venue():
    assert tournament_event_key("ATP Challenger 75 Prague Q") == "prague"
    assert tournament_event_key("ATP Tampere Challenger") == "tampere"
    assert tournament_event_key("ATP Challenger Singles") == ""
    assert tournament_event_key("ATP Challenger Qualifiers") == ""
    assert tournament_event_key(None) == ""
