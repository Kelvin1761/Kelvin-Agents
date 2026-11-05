"""Pricing produces ledger rows directly; value is judged on the raw model.

The numeric equivalence with the pre-rebuild engine is proven by the replay
harness (docs/experiments/patches/tennis_rebuild/replay.py); these tests pin
the rules a reader of pricing/props.py should be able to rely on.
"""
from __future__ import annotations

import pytest

from tennis_wc.model import market
from tennis_wc.pricing.families import ValueProfile, family_for_market, is_value_selection
from tennis_wc.pricing.props import _Side, _first_set_match_rows, _spread_rows

PROFILE = ValueProfile()  # min_edge 0.06, odds 1.30-2.25


def test_value_is_raw_minus_fair_not_the_blend():
    # raw 0.62 vs fair 0.5 at 1.95: value even though the 10% blend barely moves.
    side = _Side(0.62, 1.95, 1.95, 0.10, PROFILE)
    assert side.value == "a"
    rows = side.rows({}, {"x": "a"}, {"x": "b"})
    assert len(rows) == 1
    row = rows[0]
    assert row["edge"] == pytest.approx(0.12) and row["ev"] == pytest.approx(round(0.62 * 1.95 - 1, 4))
    assert row["blended_prob"] == pytest.approx(round(market.blend(0.62, 0.5, 0.10), 4))
    assert row["temper_strength"] == pytest.approx(0.9)
    assert row["stake_units"] == 1.0 and row["is_value"] is True


def test_b_side_value_writes_a_second_row_with_complements():
    side = _Side(0.38, 1.95, 1.95, 0.10, PROFILE)
    assert side.value == "b"
    a, b = side.rows({}, {"selection": "A"}, {"selection": "B"})
    assert a["is_value"] is False and a["edge"] == 0.0 and a["stake_units"] == 0.0
    assert b["is_value"] is True and b["selection"] == "B"
    assert b["model_prob_raw"] == pytest.approx(round(1 - round(0.38, 4), 4))
    assert b["market_prob_fair"] == pytest.approx(0.5)


def test_strip_keeps_the_scorecard_row_but_removes_value():
    side = _Side(0.38, 1.95, 1.95, 0.10, PROFILE)
    side.strip()
    rows = side.rows({}, {}, {})
    assert len(rows) == 1 and rows[0]["is_value"] is False and rows[0]["ev"] == 0.0


def test_odds_outside_the_family_band_are_never_value():
    assert not is_value_selection(0.9, 0.5, 2.5, PROFILE)
    assert not is_value_selection(0.9, 0.5, 1.2, PROFILE)
    assert is_value_selection(0.9, 0.5, 2.25, PROFILE)


def _meta():
    return {"id": 9, "player_a_id": 1, "player_b_id": 2, "a_name": "Ann", "b_name": "Bea"}


def _quote(a_h=-2.5, a=1.9, b=1.9, key="game_handicap"):
    return {"a": {"odds": a, "handicap": a_h}, "b": {"odds": b, "handicap": -a_h},
            "a_name": f"Ann {a_h:+g}", "b_name": f"Bea {-a_h:+g}", "market_key": key, "market_name": "Game Handicap"}


def test_spread_rows_settle_on_player_a_margin():
    rows = _spread_rows(_meta(), "Ann vs Bea", "2026-11-07", "player_game_handicap_2.5",
                        "player_game_margin", _quote(), 0.30, -1.2, 0.1, strip=False)
    a, b = rows
    assert a["line"] == 2.5 and a["side"] == "over" and a["selection"] == "Ann (-2.5)"
    assert b["side"] == "under" and b["subject_player_id"] == 1, "both rows grade A's margin"
    assert b["feed_selection_name"] == "Bea +2.5" and b["feed_line"] == 2.5


@pytest.mark.parametrize("quote", [_quote(a_h=-2.0), _quote(a=1.0), {**_quote(), "b": {"odds": 1.9, "handicap": 3.5}}])
def test_spread_rows_refuse_pushes_bad_odds_and_unpaired_lines(quote):
    assert _spread_rows(_meta(), "x", "d", "k", "s", quote, 0.5, 0.0, 0.1, strip=False) == []


def test_first_set_and_match_only_stakes_a_won_first_set():
    quotes = {k: {"odds": 4.0, "selection_name": k, "market_key": "m", "market_name": "n"}
              for k in ("a_win", "a_lose", "b_win", "b_lose")}
    probs = {"a_win": 0.10, "a_lose": 0.40, "b_win": 0.10, "b_lose": 0.40}
    rows = {r["market_key"]: r for r in _first_set_match_rows(_meta(), "x", "d", quotes, probs, 0.1, True)}
    assert rows["player_first_set_match_1_lose_first"]["is_value"] is False, "lose-first is never staked"
    assert len(rows) == 4
    assert not any(r["is_value"] for r in _first_set_match_rows(_meta(), "x", "d", quotes, probs, 0.1, False))


@pytest.mark.parametrize("key,name,family", [
    ("player_total_games_5_12.5", "", "player_total_games"),
    ("total_games", "Ben Shelton Total Games", "player_total_games"),
    ("total_games", "Match Total Games", "match_total_games"),
    ("winner_related", "Set 1 Winner", "first_set_winner"),
    ("game_handicap", "Set 1 Game Handicap", "player_first_set_game_handicap"),
    ("set_handicap", "Set Handicap", "player_set_handicap"),
])
def test_family_classification(key, name, family):
    assert family_for_market(key, name) == family
