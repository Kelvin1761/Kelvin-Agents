from __future__ import annotations


def test_ledger_summary_empty(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import ledger_summary

    init_db()
    assert ledger_summary()["total_bets"] == 0
