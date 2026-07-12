from __future__ import annotations

import json


def _banker_row(
    match_id: int,
    selection_name: str,
    player_a_name: str,
    player_b_name: str,
    odds: float,
    edge: float = 0.08,
    confidence: int = 75,
    mapped_odds: float | None = None,
) -> dict:
    selection_side = "player_a" if selection_name == player_a_name else "player_b"
    return {
        "decision": "BET",
        "pricing_json": json.dumps(
            {
                "pricing": {"selection_side": selection_side, "errors": []},
                "filter": {"warnings": [], "hard_no_bet_reasons": []},
            }
        ),
        "match_id": match_id,
        "tournament_name": "Mens French Open",
        "level": "Grand Slam",
        "round": "R32",
        "surface": "Clay",
        "selection_name": selection_name,
        "player_a_name": player_a_name,
        "player_b_name": player_b_name,
        "current_market_odds": odds,
        "model_probability": 0.6,
        "fair_odds": 1.6667,
        "no_vig_market_probability": 0.52,
        "edge": edge,
        "minimum_acceptable_odds": 1.2,
        "confidence": confidence,
        "risk": "Medium",
        "stake_units": 1.0,
        "mapped_selection_side": selection_side,
        "mapped_selection_odds": odds if mapped_odds is None else mapped_odds,
    }


def _market_banker_row(
    match_id: int,
    selection_name: str,
    odds: float,
    market_name: str = "Match Betting",
    edge: float = 0.08,
    confidence: int = 75,
    eligible: bool = True,
    model_status: str = "MODELLED",
) -> dict:
    return {
        "match_id": match_id,
        "market_key": "match_winner",
        "market_name": market_name,
        "selection_name": selection_name,
        "line": None,
        "odds": odds,
        "model_status": model_status,
        "model_probability": 0.6,
        "no_vig_market_probability": 0.52,
        "edge": edge,
        "minimum_acceptable_odds": 1.2,
        "decision": "BET" if eligible else "UNSUPPORTED_FOR_BANKER",
        "banker_eligible": 1 if eligible else 0,
        "confidence": confidence,
        "risk": "Medium",
        "reason": None if eligible else "unsupported_player_props_model_not_built",
        "tournament_name": "Mens French Open",
        "player_a_name": "Player One",
        "player_b_name": "Opponent One",
    }


def _high_odds_value_row(
    match_id: int,
    selection_name: str,
    player_a_name: str,
    player_b_name: str,
    odds: float,
    edge: float,
    confidence: int,
) -> dict:
    selection_side = "player_a" if selection_name == player_a_name else "player_b"
    return {
        "match_id": match_id,
        "market_key": "match_winner",
        "market_name": "Match Betting",
        "selection_name": selection_name,
        "selection_side": selection_side,
        "line": None,
        "odds": odds,
        "model_status": "MODELLED",
        "model_probability": 0.5,
        "no_vig_market_probability": 0.3,
        "edge": edge,
        "minimum_acceptable_odds": 2.0,
        "decision": "NO_BET",
        "banker_eligible": 0,
        "confidence": confidence,
        "risk": "Medium",
        "reason": "high_odds_value_not_banker",
        "tier": "HIGH_ODDS_VALUE",
        "tournament_name": "WTA 125",
        "player_a_name": player_a_name,
        "player_b_name": player_b_name,
    }


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

    assert "1 unit = $1" in report
    assert "tenth-Kelly" in report
    assert "### BET 1｜Opponent Player vs Karolina Pliskova" in report
    assert "建議注碼：1u ($1.00)" in report
    assert "分析：" in report
    assert "支持因素：" in report
    assert "logit 空間" in report
    assert "分項拆解：" not in report
    assert "對手：Opponent Player" not in report


def test_derived_at_least_one_set_market_uses_yes_no_selection():
    from tennis_wc.reports.daily_report import _derived_market_probability

    prediction = {
        "pricing_json": json.dumps(
            {
                "pricing": {
                    "model": {
                        "player_a_probability": 0.6,
                        "player_b_probability": 0.4,
                    }
                }
            }
        )
    }
    row = {
        "market_key": "player_a_to_win_at_least_one_set",
        "market_name": "Player A to win at least one set",
        "selection_name": "Player A Yes",
        "player_a_name": "Player A",
        "player_b_name": "Player B",
    }

    yes = _derived_market_probability(row, prediction, None)
    no = _derived_market_probability(row | {"selection_name": "Player A No"}, prediction, None)

    assert yes["reason"] == "derived_at_least_one_set_from_match_model"
    assert yes["probability"] > 0.7
    assert round(yes["probability"] + no["probability"], 6) == 1.0


def test_sportsbet_round_label_from_event_text():
    from tennis_wc.ingestion.sportsbet_fixture_mapping import sportsbet_round_label

    assert sportsbet_round_label("Round of 32") == "R32"
    assert sportsbet_round_label(None, "Rome Quarter Final") == "QF"
    assert sportsbet_round_label(None, None) == "UNKNOWN"


def test_render_banker_report_uses_nba_style_four_tiers_and_positive_ev():
    from tennis_wc.reports.daily_report import render_banker_report

    # Two trustworthy match-winner BETs in different matches -> one +EV combo.
    rows = [
        _market_banker_row(1, "Player One", 1.84, edge=0.13, confidence=85),
        _market_banker_row(2, "Player Two", 1.80, edge=0.07, confidence=78),
    ]
    rows[1]["player_a_name"] = "Player Two"
    rows[1]["player_b_name"] = "Opponent Two"

    report = render_banker_report("2026-06-03", rows)

    # 4d7110f demoted the value/high tiers: the headline is now the prop-first
    # strategy banner, but the four tier sections still render (reference-only).
    assert "策略重心：Player Props" in report
    assert "組合1 穩膽" in report
    assert "組合X 火藥庫" in report
    # The combo must be reported with a +EV figure and a half-Kelly stake.
    assert "組合 EV：+" in report
    assert "Player One" in report and "Player Two" in report


def test_chalk_combo_dicts_builds_disjoint_tracked_chains():
    from tennis_wc.reports.daily_report import _chalk_combo_dicts

    def chalk_row(match_id: int, name: str, odds: float, prob: float) -> dict:
        row = _market_banker_row(match_id, name, odds, confidence=80)
        row["model_probability"] = prob
        return row

    rows = [
        chalk_row(1, "Fav One", 1.10, 0.90),
        chalk_row(2, "Fav Two", 1.15, 0.85),
        chalk_row(3, "Fav Three", 1.18, 0.80),
        chalk_row(4, "Fav Four", 1.20, 0.75),
        chalk_row(5, "Fav Five", 1.19, 0.70),
        # Non-qualifiers must be excluded: odds above cap / low model prob.
        chalk_row(6, "Too Long", 1.40, 0.90),
        chalk_row(7, "No Opinion", 1.10, 0.50),
    ]

    combos = _chalk_combo_dicts(rows)

    # 5 qualifying legs -> one 3-leg chain + one 2-leg chain, disjoint.
    assert [len(c["legs"]) for c in combos] == [3, 2]
    assert all(c["tier"] == "穩膽大熱串" for c in combos)
    assert all(c["stake_units"] == 1.0 for c in combos)
    seen: set[str] = set()
    for combo in combos:
        for leg in combo["legs"]:
            assert leg["selection_name"] not in seen
            seen.add(leg["selection_name"])
    assert "Too Long" not in seen and "No Opinion" not in seen
    # Strongest three favourites form the first chain.
    assert {leg["selection_name"] for leg in combos[0]["legs"]} == {"Fav One", "Fav Two", "Fav Three"}


def test_render_banker_report_excludes_untrusted_prop_legs(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports.daily_report import render_banker_report

    init_db()  # empty DB -> no authoritative match-winner BET legs
    # A miscalibrated, not-validated prop leg (banker_eligible=0, not match_winner BET)
    # must NOT enter any combo even with a huge fake edge.
    prop = _market_banker_row(1, "Aces Over 2.5", 1.91, eligible=False, model_status="PROP_MODEL")
    prop["market_key"] = "total_aces_in_the_match"
    prop["model_probability"] = 0.93
    prop["edge"] = 0.44
    prop["decision"] = "MODEL_REVIEW"

    report = render_banker_report("2026-06-03", [prop])

    assert "Aces Over 2.5" not in report
    assert "無合格單腳" in report


def test_render_banker_report_empty_when_no_trustworthy_legs(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports.daily_report import render_banker_report

    init_db()  # empty DB -> no authoritative match-winner BET legs
    report = render_banker_report("2026-06-03", [])

    assert "無合格單腳" in report


def test_opened_markets_produce_trial_combos():
    from tennis_wc.reports.daily_report import render_banker_report

    def derived_leg(match_id, selection, odds, edge):
        return {
            "match_id": match_id,
            "market_key": "to_win_1st_set",
            "market_name": "To Win 1st Set",
            "selection_name": selection,
            "selection_side": "player_a",
            "line": None,
            "odds": odds,
            "model_status": "DERIVED_MODEL",
            "model_probability": 0.62,
            "no_vig_market_probability": 0.52,
            "edge": edge,
            "minimum_acceptable_odds": 1.2,
            "decision": "MODEL_REVIEW",
            "banker_eligible": 0,
            "confidence": 70,
            "reason": None,
            "tournament_name": "WTA Test",
            "player_a_name": selection,
            "player_b_name": f"Opp {match_id}",
        }

    rows = [
        derived_leg(101, "Player Set One", 1.95, 0.10),
        derived_leg(102, "Player Set Two", 1.90, 0.09),
    ]
    report = render_banker_report("2026-06-03", rows)

    # The opened (unvalidated) markets must surface as TRIAL combos, clearly flagged.
    assert "試注組合（未驗證市場" in report
    assert "Player Set One" in report


def test_stable_value_history_requires_sample_hit_rate_roi_and_clv(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.reports.daily_report import _stable_value_history_allows

    init_db()
    with get_connection() as conn:
        for idx in range(30):
            status = "WON" if idx < 20 else "LOST"
            profit = 0.8 if status == "WON" else -1.0
            conn.execute(
                """
                INSERT INTO clv_tracker (
                    recommendation_type, source_id, match_id, match_date, selection_name,
                    selection_side, market_key, market_name, market_line, tier,
                    model_probability, edge, confidence, odds_taken, closing_odds, clv,
                    result_status, profit_loss_units, recorded_at, updated_at
                )
                VALUES ('MATCH_PREDICTION', ?, 1, '2026-06-04', 'Player A',
                        'player_a', 'match_winner', 'Match Betting', NULL, 'VALUE_BANKER',
                        0.60, 0.06, 72, 1.8, 1.7, 0.02, ?, ?, 'now', 'now')
                """,
                (idx + 1, status, profit),
            )

    assert _stable_value_history_allows("MODELLED", "match_winner") is True


def test_tier_downgrade_when_value_roi_is_negative(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.reports.daily_report import _tier_downgrade_reason

    init_db()
    with get_connection() as conn:
        for idx in range(30):
            conn.execute(
                """
                INSERT INTO clv_tracker (
                    recommendation_type, source_id, match_id, match_date, selection_name,
                    selection_side, market_key, market_name, market_line, tier,
                    model_probability, edge, confidence, odds_taken, closing_odds, clv,
                    result_status, profit_loss_units, recorded_at, updated_at
                )
                VALUES ('MATCH_PREDICTION', ?, 1, '2026-06-04', 'Player A',
                        'player_a', 'match_winner', 'Match Betting', NULL, 'VALUE_BANKER',
                        0.60, 0.06, 72, 1.8, 1.9, 0.01, 'LOST', -1.0, 'now', 'now')
                """,
                (idx + 1,),
            )

    assert _tier_downgrade_reason("VALUE_BANKER", "MODELLED", "match_winner", 0.60) == "tier_downgraded_negative_roi"


def test_calibration_safety_margin_for_overconfident_bucket(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.reports.calibration_report import banker_probability_safety_margin

    init_db()
    with get_connection() as conn:
        for idx in range(10):
            status = "WON" if idx < 5 else "LOST"
            conn.execute(
                """
                INSERT INTO clv_tracker (
                    recommendation_type, source_id, match_id, match_date, selection_name,
                    selection_side, market_key, market_name, market_line, tier,
                    model_probability, edge, confidence, odds_taken, closing_odds, clv,
                    result_status, profit_loss_units, recorded_at, updated_at
                )
                VALUES ('MATCH_PREDICTION', ?, 1, '2026-06-04', 'Player A',
                        'player_a', 'match_winner', 'Match Betting', NULL, 'CORE_BANKER',
                        0.68, 0.06, 82, 1.8, 1.8, 0.0, ?, 0.0, 'now', 'now')
                """,
                (idx + 1, status),
            )

    assert banker_probability_safety_margin(0.68) > 0
