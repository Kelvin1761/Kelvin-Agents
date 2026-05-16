from __future__ import annotations

import json


def test_render_daily_report_includes_match_context_and_explanation():
    from tennis_wc.reports.daily_report import render_daily_report

    rows = [
        {
            "decision": "BET",
            "pricing_json": json.dumps(
                {
                    "pricing": {
                        "model": {
                            "player_a_probability": 0.4,
                            "components": [
                                {"name": "surface_elo_edge", "probability": 0.35, "weight": 0.22, "active": True},
                                {"name": "serve_return_edge", "probability": 0.45, "weight": 0.2, "active": True},
                            ],
                        }
                    },
                    "filter": {"warnings": []},
                }
            ),
            "match_id": 7,
            "tournament_name": "WTA 1000 Rome",
            "level": "WTA_1000",
            "round": "R32",
            "surface": "clay",
            "selection_name": "Karolina Pliskova",
            "player_a_name": "Opponent Player",
            "player_b_name": "Karolina Pliskova",
            "current_market_odds": 1.92,
            "model_probability": 0.6,
            "fair_odds": 1.6667,
            "no_vig_market_probability": 0.49,
            "edge": 0.11,
            "minimum_acceptable_odds": 1.82,
            "confidence": 80,
            "risk": "Medium",
            "stake_units": 1.0,
        }
    ]

    report = render_daily_report("2026-05-10", rows, {}, [])

    assert "- Bankroll：$500 virtual bankroll；1 unit = $1" in report
    assert "## BET 1 Opponent Player vs Karolina Pliskova" in report
    assert "建議注碼：1 unit ($1.00)" in report
    assert "分析：" in report
    assert "支持因素：" in report
    assert "模型勝率係將有效因素按權重合併" in report
    assert "分項拆解：" not in report
    assert "對手：Opponent Player" not in report


def test_sportsbet_round_label_from_event_text():
    from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_round_label

    assert sportsbet_round_label("Round of 32") == "R32"
    assert sportsbet_round_label(None, "Rome Quarter Final") == "QF"
    assert sportsbet_round_label(None, None) == "UNKNOWN"
