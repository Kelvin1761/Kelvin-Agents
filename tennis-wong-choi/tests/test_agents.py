from __future__ import annotations


def test_agent_runner_returns_final_decision():
    from tennis_wc.agents.runner import run_agents

    snapshot = {
        "match_id": {"value": 1},
        "data_quality": {"score": 90, "is_valid": True, "errors": [], "warnings": []},
        "match_context": {
            "tournament": {"value": "Mock Open"},
            "level": {"value": "ATP_1000"},
            "round": {"value": "R32"},
            "surface": {"value": "Hard"},
            "format": {"value": "BO3"},
        },
        "player_a": {
            "name": "Player A",
            "current_rank": {"value": 18},
            "surface_elo": {"value": 1900},
            "opponent_rank_buckets": {"TOP_50": {"shrinked_win_rate": {"value": 0.55}, "sample_size": {"value": 12}}, "TOP_100": {"shrinked_win_rate": {"value": 0.55}}},
            "tournament_level_stats": {"shrinked_win_rate": {"value": 0.55}, "sample_size": {"value": 12}, "hold_rate": {"value": 0.78}, "break_rate": {"value": 0.25}},
            "round_stats": {"shrinked_win_rate": {"value": 0.52}, "sample_size": {"value": 12}},
            "big_match_stats": {"win_rate": {"value": 0.5}},
            "injury": {"risk": "UNKNOWN"},
        },
        "player_b": {
            "name": "Player B",
            "current_rank": {"value": 42},
            "surface_elo": {"value": 1800},
            "opponent_rank_buckets": {"TOP_25": {"shrinked_win_rate": {"value": 0.45}, "sample_size": {"value": 12}}, "TOP_100": {"shrinked_win_rate": {"value": 0.48}}},
            "tournament_level_stats": {"shrinked_win_rate": {"value": 0.48}, "sample_size": {"value": 12}, "hold_rate": {"value": 0.72}, "break_rate": {"value": 0.20}},
            "round_stats": {"shrinked_win_rate": {"value": 0.48}, "sample_size": {"value": 12}},
            "big_match_stats": {"win_rate": {"value": 0.45}},
            "injury": {"risk": "UNKNOWN"},
        },
        "market": {"player_a_open_odds": {"value": 2.1}, "player_b_open_odds": {"value": 1.8}},
    }
    pricing = {
        "selection_side": "player_a",
        "selection_name": "Player A",
        "current_market_odds": 2.08,
        "minimum_acceptable_odds": 1.95,
        "model_probability": 0.55,
        "fair_odds": 1.82,
        "no_vig_market_probability": 0.49,
        "edge": 0.06,
    }
    filter_result = {"decision": "BET", "confidence": 80, "risk": "Medium", "stake_units": 0.5, "hard_no_bet_reasons": [], "warnings": []}
    output = run_agents(snapshot, pricing, filter_result)
    assert output["final_decision"] == "BET"
    assert len(output["reviews"]) >= 8
