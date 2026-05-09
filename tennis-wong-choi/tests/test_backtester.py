from __future__ import annotations


def test_backtest_empty_range(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.modelling.backtester import run_backtest

    init_db()
    result = run_backtest("2026-05-08", "2026-05-08")
    assert result["total_predictions"] == 0
