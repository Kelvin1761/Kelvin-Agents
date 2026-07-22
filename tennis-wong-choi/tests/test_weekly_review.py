"""Weekly validation review — structure + read-only guarantees."""


def test_weekly_review_renders_on_empty_db(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports.weekly_review import render_weekly_review, weekly_review_data

    init_db()
    report = render_weekly_review("2026-07-15")
    # Section headers always present, even with nothing settled.
    assert "每週檢討" in report
    assert "一眼睇晒" in report
    assert "衍生市場畢業進度" in report
    assert "決策提示" in report
    # Empty DB -> nothing graduated, nothing to raise stakes on.
    assert "未有衍生市場畢業" in report

    data = weekly_review_data("2026-07-15")
    # Every settlement-supported derived market is listed with a graduation gap.
    markets = {r["market"] for r in data["derived_markets"]}
    assert {"total_sets", "to_win_1st_set", "set_betting"} <= markets
    for row in data["derived_markets"]:
        assert row["settled"] == 0
        assert row["to_graduate"] == 20


def test_weekly_review_does_not_mutate_trackers(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.reports.weekly_review import render_weekly_review

    init_db()
    with get_connection() as conn:
        before = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("clv_tracker", "combo_tracker", "prop_tracker")
        }
    render_weekly_review("2026-07-15")
    with get_connection() as conn:
        after = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("clv_tracker", "combo_tracker", "prop_tracker")
        }
    assert before == after
