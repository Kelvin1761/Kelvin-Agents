from __future__ import annotations


def test_pricing_stage_not_implemented():
    from tennis_wc.modelling.probability_model import predict_match_probability

    snapshot = {
        "player_a": {
            "surface_elo": {"value": 1900},
            "overall_elo": {"value": 1880},
            "current_rank": {"value": 20},
            "tournament_level_stats": {"hold_rate": {"value": 0.78}, "break_rate": {"value": 0.24}},
            "opponent_rank_buckets": {"TOP_50": {"shrinked_win_rate": {"value": 0.55}}, "TOP_100": {"shrinked_win_rate": {"value": 0.58}}},
            "round_stats": {"shrinked_win_rate": {"value": 0.52}},
            "big_match_stats": {"win_rate": {"value": 0.5}},
        },
        "player_b": {
            "surface_elo": {"value": 1800},
            "overall_elo": {"value": 1810},
            "current_rank": {"value": 48},
            "tournament_level_stats": {"hold_rate": {"value": 0.72}, "break_rate": {"value": 0.18}},
            "opponent_rank_buckets": {"TOP_25": {"shrinked_win_rate": {"value": 0.44}}, "TOP_100": {"shrinked_win_rate": {"value": 0.5}}},
            "round_stats": {"shrinked_win_rate": {"value": 0.48}},
            "big_match_stats": {"win_rate": {"value": 0.44}},
        },
    }
    result = predict_match_probability(snapshot)
    assert result["player_a_probability"] > 0.5


def test_price_match_snapshot_stops_on_odds_selection_mapping_error():
    from tennis_wc.modelling.pricing import price_match_snapshot

    snapshot = {
        "player_a": {
            "name": "Player A",
            "surface_elo": {"value": 1900},
            "overall_elo": {"value": 1880},
            "current_rank": {"value": 20},
            "tournament_level_stats": {},
            "opponent_rank_buckets": {},
            "round_stats": {},
            "big_match_stats": {},
        },
        "player_b": {
            "name": "Player B",
            "surface_elo": {"value": 1800},
            "overall_elo": {"value": 1810},
            "current_rank": {"value": 48},
            "tournament_level_stats": {},
            "opponent_rank_buckets": {},
            "round_stats": {},
            "big_match_stats": {},
        },
        "market": {"errors": ["odds_selection_mapping_failed"]},
    }

    result = price_match_snapshot(snapshot)

    assert result["selection_name"] is None
    assert result["current_market_odds"] is None
    assert result["errors"] == ["odds_selection_mapping_failed"]
