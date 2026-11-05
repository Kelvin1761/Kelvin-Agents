"""Result fetching and the settlement backlog."""
from __future__ import annotations


def test_result_name_matching_requires_confident_pair_match(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.settle.results import _match_by_names

    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
            VALUES
                (1, 'Ben Shelton', 'ATP', 'sportsbet', 'now', 'now'),
                (2, 'Nick Kyrgios', 'ATP', 'sportsbet', 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO tournaments (id, name, tour, external_id, source_provider, created_at, updated_at)
            VALUES (1, 'Halle', 'ATP', 'halle', 'sportsbet', 'now', 'now')
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
        conn.commit()  # _match_by_names opens its own connection; commit so it sees the rows

        assert _match_by_names(conn, "2026-06-16", "Taylor Fritz", "Zizou Bergs") is None
        assert _match_by_names(conn, "2026-06-16", "B. Shelton", "N. Kyrgios")["id"] == 1




def test_local_history_resolver_backfills_pending_match_result(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.settle.results import _resolve_pending_from_player_history

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
            """INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, market_key, line,
                   selection, decimal_odds, stake_units, is_value, result_status, recorded_at, updated_at)
               VALUES ('k', 1, '2026-06-16', 'A vs B', 'player_win_a_set_2', 0.5, 'Yes', 2.1, 1, 1,
                       'PENDING', 'now', 'now')"""
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
        conn.commit()  # resolver opens its own connection; commit so setup is visible

    assert _resolve_pending_from_player_history("2026-06-16") == 1
    with get_connection() as conn:
        result = conn.execute(
            "SELECT winner_player_id, source_provider FROM match_results WHERE match_id = 1"
        ).fetchone()

    assert result["winner_player_id"] == 2
    assert result["source_provider"] == "local_history_resolver"




def test_the_settlement_backlog_sweeps_the_newest_dates_first(tmp_path, monkeypatch):
    """The cap drops the oldest dates, never the freshest (2026-08-10 it did the opposite)."""
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc import run
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.settle import results

    init_db()
    with get_connection() as conn:
        for match_date in ("2026-07-20", "2026-08-07", "2026-08-08", "2026-08-09"):
            conn.execute(
                """INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label, market_key, line,
                       selection, decimal_odds, stake_units, is_value, result_status, recorded_at, updated_at)
                   VALUES (?, 1, ?, 'A vs B', 'player_win_a_set_1', 0.5, 'Yes', 2.0, 1.0, 1, 'PENDING',
                           'now', 'now')""", (f"k-{match_date}", match_date))
    seen = []
    monkeypatch.setattr(results, "fetch_results_for_date", lambda day: seen.append(day) or {})
    summary = run.settle_backlog("2026-08-11", max_dates=3)
    assert seen == ["2026-08-09", "2026-08-08", "2026-08-07"]
    assert summary["skipped_dates"] == ["2026-07-20"]
