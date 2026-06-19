from __future__ import annotations


def test_ledger_summary_empty(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import ledger_summary

    init_db()
    assert ledger_summary()["total_bets"] == 0
    assert ledger_summary()["clv_tracker"]["total_tracked"] == 0


def test_tier_roi_empty(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import tier_roi_summary

    init_db()
    summary = tier_roi_summary()
    assert summary["ledger_by_tier"] == []
    assert summary["tracker_by_tier"] == []


def test_settle_first_set_winner_market():
    from tennis_wc.betting.ledger import _settle_market_leg

    row = {
        "market_key": "to_win_1st_set",
        "market_name": "To Win 1st Set",
        "selection_name": "Player A",
        "selection_side": "player_a",
        "score_json": '{"sets":[{"player_a_games":6,"player_b_games":4},{"player_a_games":3,"player_b_games":6}]}',
    }

    assert _settle_market_leg(row) is True


def test_settle_set_winner_market_uses_set_number():
    from tennis_wc.betting.ledger import _settle_market_leg

    row = {
        "market_key": "winner_related",
        "market_name": "Set 2 Winner",
        "selection_name": "Player B",
        "selection_side": "player_b",
        "score_json": '{"sets":[{"player_a_games":6,"player_b_games":4},{"player_a_games":3,"player_b_games":6}]}',
    }

    assert _settle_market_leg(row) is True


def test_settle_set_winner_without_set_scores_is_unsupported():
    from tennis_wc.betting.ledger import _settle_market_leg

    row = {
        "market_key": "to_win_1st_set",
        "market_name": "To Win 1st Set",
        "selection_name": "Player A",
        "selection_side": "player_a",
        "score_json": '{"player_a_sets":2,"player_b_sets":1,"sets":[]}',
    }

    assert _settle_market_leg(row) is None


def test_settle_to_win_at_least_one_set_yes_no_market():
    from tennis_wc.betting.ledger import _settle_market_leg

    row = {
        "market_key": "player_a_to_win_at_least_one_set",
        "market_name": "Player A to win at least one set",
        "selection_name": "Player A Yes",
        "selection_side": "player_a",
        "score_json": '{"player_a_sets":1,"player_b_sets":2}',
    }
    assert _settle_market_leg(row) is True

    row["selection_name"] = "Player A No"
    assert _settle_market_leg(row) is False


def test_settlement_block_reason_marks_missing_box_score_for_aces():
    from tennis_wc.betting.ledger import _settlement_block_reason

    row = {
        "winner_player_id": 1,
        "player_a_id": 1,
        "player_b_id": 2,
        "player_a_name": "Player A",
        "player_b_name": "Player B",
        "market_key": "total_aces_20_5",
        "market_name": "Total Aces 20.5",
        "selection_name": "Under 20.5",
        "market_line": 20.5,
        "score_json": '{"sets":[{"player_a_games":6,"player_b_games":4}],"player_a_sets":1,"player_b_sets":0}',
    }

    assert _settlement_block_reason(row) == "missing_box_score"


def test_settlement_block_reason_marks_missing_scoreline():
    from tennis_wc.betting.ledger import _settlement_block_reason

    row = {
        "winner_player_id": 1,
        "market_key": "total_sets",
        "market_name": "Total Sets",
        "selection_name": "Over 2.5",
        "market_line": 2.5,
        "score_json": None,
    }

    assert _settlement_block_reason(row) == "missing_scoreline"


def test_prune_pending_tracker_duplicates_keeps_latest(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import _prune_pending_tracker_duplicates

    init_db()
    with get_connection() as conn:
        base = {
            "recommendation_type": "MARKET_LEG",
            "match_id": 1,
            "match_date": "2026-06-04",
            "selection_name": "Player A",
            "selection_side": "player_a",
            "market_key": "match_winner",
            "market_name": "Match Betting",
            "market_line": None,
            "tier": "VALUE_BANKER",
            "odds_taken": 1.80,
            "result_status": "PENDING",
            "recorded_at": "2026-06-03T00:00:00Z",
            "updated_at": "2026-06-03T00:00:00Z",
        }
        for source_id in (100, 101):
            conn.execute(
                """
                INSERT INTO clv_tracker (
                    recommendation_type, source_id, match_id, match_date, selection_name,
                    selection_side, market_key, market_name, market_line, tier,
                    odds_taken, result_status, recorded_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    base["recommendation_type"],
                    source_id,
                    base["match_id"],
                    base["match_date"],
                    base["selection_name"],
                    base["selection_side"],
                    base["market_key"],
                    base["market_name"],
                    base["market_line"],
                    base["tier"],
                    base["odds_taken"],
                    base["result_status"],
                    base["recorded_at"],
                    base["updated_at"],
                ),
            )
        conn.execute(
            """
            INSERT INTO clv_tracker (
                recommendation_type, source_id, match_id, match_date, selection_name,
                selection_side, market_key, market_name, market_line, tier,
                odds_taken, result_status, recorded_at, updated_at
            )
            VALUES ('MARKET_LEG', 102, 1, '2026-06-04', 'Player B', 'player_b',
                    'match_winner', 'Match Betting', NULL, 'VALUE_BANKER',
                    2.05, 'PENDING', '2026-06-03T00:00:00Z', '2026-06-03T00:00:00Z')
            """
        )

        assert _prune_pending_tracker_duplicates(conn, "2026-06-04") == 1
        rows = conn.execute("SELECT source_id FROM clv_tracker ORDER BY source_id").fetchall()

    assert [row["source_id"] for row in rows] == [101, 102]


def test_write_settlement_qa_report_lists_reasons(tmp_path):
    from tennis_wc.betting.ledger import _write_settlement_qa_report

    path = _write_settlement_qa_report(
        "2026-06-04",
        tmp_path,
        {
            "result_provider_health": {
                "provider": "composite",
                "rows_seen": 0,
                "winners_seen": 0,
                "imported": 0,
                "unmatched": 0,
                "tennismylife": {"files": 3, "rows_seen": 0, "results_imported": 0, "unmatched_rows": 0},
            },
            "reason_counts": {"no_result": 2, "missing_box_score": 1},
            "tracker_items": [],
            "combo_items": [],
        },
    )

    text = path.read_text(encoding="utf-8")
    assert path.name == "06-04 Tennis Settlement QA.txt"
    assert "未搵到賽果：2" in text
    assert "缺少 box score，未能結算 props：1" in text


def test_settlement_block_reason_holds_retired_props_for_policy_review():
    from tennis_wc.betting.ledger import _settle_market_leg, _settlement_block_reason

    row = {
        "winner_player_id": 1,
        "player_a_id": 1,
        "player_b_id": 2,
        "player_a_name": "Player A",
        "player_b_name": "Player B",
        "market_key": "total_aces_20_5",
        "market_name": "Total Aces 20.5",
        "selection_name": "Under 20.5",
        "market_line": 20.5,
        "score_json": '{"retired":true,"player_a_aces":4,"player_b_aces":5,"sets":[{"player_a_games":7,"player_b_games":5}]}',
    }

    assert _settlement_block_reason(row) == "retired_prop_settlement_policy_unknown"
    assert _settle_market_leg(row) is None


def test_result_name_matching_requires_confident_pair_match(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import _match_by_names

    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO players (id, provider_player_id, name, tour, created_at, updated_at)
            VALUES
                (1, 'p1', 'Ben Shelton', 'ATP', 'now', 'now'),
                (2, 'p2', 'Nick Kyrgios', 'ATP', 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO tournaments (id, provider_tournament_id, name, tour, level, start_date, end_date, created_at, updated_at)
            VALUES (1, 't1', 'Halle', 'ATP', 'ATP_500', '2026-06-16', '2026-06-22', 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO matches (
                id, provider_match_id, tour, match_date, tournament_id,
                player_a_id, player_b_id, round, source_provider, created_at, updated_at
            )
            VALUES (1, 'm1', 'ATP', '2026-06-16', 1, 1, 2, 'R32', 'sportsbet', 'now', 'now')
            """
        )

        assert _match_by_names(conn, "2026-06-16", "Taylor Fritz", "Zizou Bergs") is None
        assert _match_by_names(conn, "2026-06-16", "B. Shelton", "N. Kyrgios")["id"] == 1


def test_local_history_resolver_backfills_pending_match_result(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import _resolve_pending_from_player_history

    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO players (
                id, name, tour, source_provider, raw_response_id, created_at, updated_at
            )
            VALUES
                (1, 'Anna Example', 'WTA', 'sportsbet', NULL, 'now', 'now'),
                (2, 'Beth Sample', 'WTA', 'sportsbet', NULL, 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO tournaments (
                id, name, tour, external_id, source_provider, raw_response_id, created_at, updated_at
            )
            VALUES (1, 'Nottingham', 'WTA', 'nottingham', 'sportsbet', NULL, 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO matches (
                id, provider_match_id, market_event_id, tour, match_date, tournament_id,
                player_a_id, player_b_id, round, source_provider, raw_response_id,
                created_at, updated_at
            )
            VALUES (1, 'sportsbet-evt-1', 'evt-1', 'WTA', '2026-06-16', 1,
                    1, 2, 'R32', 'sportsbet', NULL, 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO clv_tracker (
                recommendation_type, source_id, match_id, match_date, selection_name,
                selection_side, market_key, market_name, market_line, tier,
                odds_taken, result_status, recorded_at, updated_at
            )
            VALUES ('MATCH_PREDICTION', 1, 1, '2026-06-16', 'Beth Sample',
                    'player_b', 'match_winner', 'Match Betting', NULL, 'BET',
                    2.10, 'PENDING', 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO player_match_history (
                provider_match_id, player_id, opponent_id, tour, match_date,
                surface, tournament_external_id, tournament_level, round, format,
                won, source_provider, raw_response_id, created_at
            )
            VALUES ('hist-1', 2, 1, 'WTA', '2026-06-16',
                    'Grass', 'nottingham', 'WTA_250', 'R32', 'BO3',
                    1, 'local_fixture', 1, 'now')
            """
        )

        assert _resolve_pending_from_player_history("2026-06-16") == 1
        result = conn.execute(
            "SELECT winner_player_id, source_provider FROM match_results WHERE match_id = 1"
        ).fetchone()

    assert result["winner_player_id"] == 2
    assert result["source_provider"] == "local_history_resolver"


def test_market_validation_blocks_promotion_when_settlement_coverage_is_low(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports.market_validation_report import market_validation_summary

    init_db()
    with get_connection() as conn:
        for idx in range(10):
            status = "WON" if idx < 3 else "PENDING"
            profit = 0.9 if idx < 3 else None
            conn.execute(
                """
                INSERT INTO clv_tracker (
                    recommendation_type, source_id, match_id, match_date, selection_name,
                    selection_side, market_key, market_name, market_line, tier,
                    model_probability, edge, confidence, odds_taken, closing_odds, clv,
                    result_status, profit_loss_units, recorded_at, updated_at
                )
                VALUES (
                    'MARKET_LEG', ?, 1, '2026-06-16', 'Player A',
                    'player_a', 'match_winner', 'Match Betting', NULL, 'VALUE_BANKER',
                    0.7, 0.1, 85, 1.9, 1.8, 0.05,
                    ?, ?, 'now', 'now'
                )
                """,
                (idx + 1, status, profit),
            )

    row = market_validation_summary(min_samples=3)["by_market"][0]
    assert row["settled"] == 3
    assert row["tracked"] == 10
    assert row["coverage_rate"] == 0.3
    assert row["status"] == "LOW_SETTLEMENT_COVERAGE"
    assert row["stable_value_candidate"] is False
