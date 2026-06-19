from __future__ import annotations

import json


def _row(selection, line, a_games, b_games, retired=False):
    score = {
        "player_a_games": a_games,
        "player_b_games": b_games,
        "player_a_sets": 2,
        "player_b_sets": 0,
        "total_sets": 2,
    }
    if retired:
        score["retired"] = True
        score["total_sets"] = 1
    return {
        "market_key": "total_games",
        "market_name": "Total Games",
        "selection_name": selection,
        "market_line": line,
        "score_json": json.dumps(score),
        "winner_player_id": 1,
        "player_a_id": 1,
        "player_b_id": 2,
    }


def test_total_games_over_under_settles_from_scoreline():
    from tennis_wc.betting.ledger import _settle_market_leg

    # 12 + 7 = 19 total games.
    assert _settle_market_leg(_row("Over 22.5", 22.5, 12, 7)) is False
    assert _settle_market_leg(_row("Under 22.5", 22.5, 12, 7)) is True
    assert _settle_market_leg(_row("Over 18.5", 18.5, 12, 7)) is True


def test_total_games_voids_on_retirement():
    from tennis_wc.betting.ledger import _settle_market_leg

    assert _settle_market_leg(_row("Under 18.5", 18.5, 3, 2, retired=True)) is None


def test_total_games_needs_a_line():
    from tennis_wc.betting.ledger import _settle_market_leg

    assert _settle_market_leg(_row("Over", None, 12, 7)) is None


def test_per_set_total_games_settles_from_that_set_not_match_total():
    from tennis_wc.betting.ledger import _settle_market_leg

    # Match total = 6+4 + 6+3 = 19, but Set 1 total = 6+4 = 10.
    score = json.dumps(
        {
            "player_a_games": 12,
            "player_b_games": 7,
            "player_a_sets": 2,
            "player_b_sets": 0,
            "total_sets": 2,
            "sets": [
                {"player_a_games": 6, "player_b_games": 4},
                {"player_a_games": 6, "player_b_games": 3},
            ],
        }
    )
    base = {
        "market_key": "total_games",
        "market_name": "Set 1 Total Games Over/Under 9.5",
        "market_line": 9.5,
        "score_json": score,
        "winner_player_id": 1,
        "player_a_id": 1,
        "player_b_id": 2,
    }
    # Set 1 = 10 games -> Over 9.5 WINS (must NOT use the match total of 19 only).
    assert _settle_market_leg({**base, "selection_name": "Over 9.5"}) is True
    assert _settle_market_leg({**base, "selection_name": "Under 9.5"}) is False
    # Set 2 = 9 games -> Over 9.5 LOSES.
    s2 = {**base, "market_name": "Set 2 Total Games Over/Under 9.5"}
    assert _settle_market_leg({**s2, "selection_name": "Over 9.5"}) is False
