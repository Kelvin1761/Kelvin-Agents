from __future__ import annotations


def test_history_schema_captures_service_games(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    columns = {
        row["name"]
        for row in get_connection().execute(
            "PRAGMA table_info(player_match_history)"
        ).fetchall()
    }
    assert "service_games_played" in columns


def test_sackmann_metrics_preserve_the_service_games_denominator():
    from tennis_wc.ingestion.ingest_sackmann import _metrics

    row = {
        "w_svpt": "72",
        "w_1stIn": "45",
        "w_1stWon": "34",
        "w_2ndWon": "14",
        "w_SvGms": "12",
        "w_bpSaved": "3",
        "w_bpFaced": "5",
        "w_ace": "8",
        "w_df": "2",
        "l_svpt": "64",
        "l_1stWon": "28",
        "l_2ndWon": "12",
        "l_SvGms": "11",
        "l_bpSaved": "2",
        "l_bpFaced": "4",
    }

    metrics = _metrics(row, "w", "l")

    assert metrics["service_games_played"] == 12.0
