"""The corpus a judgement is allowed to be measured on.

Guards the 2026-08-26 defect: 9,594 of 13,658 prop rows were written by one
backfill run on 2026-08-10 covering match dates from 2026-05-10, so the
published +2.86% ROI was an average of a real -23.38% loss and an artefact.
Nothing in the suite noticed, because nothing in the suite had an opinion about
WHEN a row was written.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from conftest import configure_test_db

from tennis_wc.evaluation.corpus import (
    POINT_IN_TIME,
    POST_START,
    classify_point_in_time,
    corpus_summary,
    point_in_time_clause,
)


def _seed(conn, mid: int, start_time_utc: str | None) -> None:
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, f"M{mid}", "ATP", "2026-08-20", 1, 1, 2, "R1", "test",
         "now", "now", start_time_utc),
    )


def _record(conn, mid: int, market_key: str, recorded_at: str,
            is_pit, status: str = "WON", pnl: float = 1.0) -> None:
    """Insert a settled row directly -- the classification is the subject here,
    not `record_prop`'s stamping, which has its own test below."""
    conn.execute(
        """INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label,
               market_key, line, selection, side, prop_scope, decimal_odds,
               model_prob, model_prob_raw, market_prob_fair, blended_prob, edge, ev,
               predicted_mean, stake_units, is_value, result_status,
               profit_loss_units, recorded_at, updated_at, is_point_in_time)
           VALUES (?,?,?,?,?,?,?,'over','match',2.0,
                   0.6,0.6,0.5,0.55,0.05,0.1,
                   10.0,1.0,1,?,?,?,?,?)""",
        (f"{mid}|{market_key}|X", mid, "2026-08-20", "A v B", market_key, 5.5, "X",
         status, pnl, recorded_at, recorded_at, is_pit),
    )


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def test_pre_start_write_is_point_in_time():
    assert classify_point_in_time(
        "2026-08-20T01:00:00Z", "2026-08-20T05:00:00Z") == POINT_IN_TIME


def test_write_after_the_first_ball_is_not_point_in_time():
    assert classify_point_in_time(
        "2026-08-20T06:00:00Z", "2026-08-20T05:00:00Z") == POST_START


def test_a_row_written_on_an_earlier_date_can_still_be_post_start():
    """`match_date` is the tournament's local day, `recorded_at` is UTC.

    335 real rows looked pre-match by date and were written after the start,
    which is why the date is not the test.
    """
    assert classify_point_in_time(
        "2026-08-19T23:30:00Z", "2026-08-19T23:00:00Z") == POST_START


def test_no_start_time_is_unverifiable_not_innocent():
    """The 1,392 staked rows with no start time carried ALL the profit
    (+11.74%, CI [+6.24, +17.58]). Admitting them as "probably fine" is the
    mistake this column exists to prevent."""
    assert classify_point_in_time("2026-08-20T01:00:00Z", None) is None
    assert classify_point_in_time("2026-08-20T01:00:00Z", "") is None


def test_clause_demands_one_not_merely_not_zero():
    """`!= 0` would let every unverifiable row back in through NULL."""
    clause = point_in_time_clause("p")
    assert clause == "p.is_point_in_time = 1"


# --------------------------------------------------------------------------- #
# Migration + reporting
# --------------------------------------------------------------------------- #
def test_migration_classifies_existing_rows_from_start_time(tmp_path, monkeypatch):
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    _seed(conn, 2, "2026-08-20T05:00:00Z")
    _seed(conn, 3, None)
    # Written with the column left NULL, exactly as the pre-migration rows were.
    _record(conn, 1, "player_game_handicap_2.5", "2026-08-20T01:00:00Z", None)
    _record(conn, 2, "player_game_handicap_2.5", "2026-08-20T09:00:00Z", None)
    _record(conn, 3, "player_game_handicap_2.5", "2026-08-20T01:00:00Z", None)
    conn.commit()
    conn.execute("ALTER TABLE prop_tracker RENAME COLUMN is_point_in_time TO _drop")
    conn.execute("UPDATE prop_tracker SET _drop = NULL")
    conn.commit()
    conn.close()

    init_db()  # re-run: the column is absent under its own name again

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    got = {
        row["match_id"]: row["is_point_in_time"]
        for row in conn.execute(
            "SELECT match_id, is_point_in_time FROM prop_tracker").fetchall()
    }
    assert got[1] == POINT_IN_TIME
    assert got[2] == POST_START
    assert got[3] is None, "no start time must stay unverifiable"
    conn.close()


def test_roi_report_excludes_post_start_rows_by_default(tmp_path, monkeypatch):
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props.settlement import prop_roi_report

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    _seed(conn, 2, "2026-08-20T05:00:00Z")
    # One pre-match loser, one post-start winner: the exact shape of the real
    # table, where the backfill read +6.05% and the pre-match rows -15.45%.
    _record(conn, 1, "player_game_handicap_2.5", "2026-08-20T01:00:00Z",
            POINT_IN_TIME, status="LOST", pnl=-1.0)
    _record(conn, 2, "player_game_handicap_3.5", "2026-08-20T09:00:00Z",
            POST_START, status="WON", pnl=1.0)
    conn.commit()

    gated = prop_roi_report(conn)
    assert gated["overall"]["settled"] == 1
    assert gated["overall"]["roi"] < 0, "the post-start winner must not rescue it"

    ungated = prop_roi_report(conn, point_in_time_only=False)
    assert ungated["overall"]["settled"] == 2
    conn.close()


def test_family_reliability_ignores_post_start_rows(tmp_path, monkeypatch):
    """A weight fitted on hindsight prices is not a weight."""
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props.calibration import DEFAULT_MODEL_WEIGHT, family_reliability

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for mid in range(1, 61):
        _seed(conn, mid, "2026-08-20T05:00:00Z")
        # Post-start rows where the model was always right -- a perfect
        # coefficient, available only with hindsight.
        _record(conn, mid, "player_game_handicap_2.5", "2026-08-20T09:00:00Z",
                POST_START, status="WON")
    conn.commit()

    rel = family_reliability(conn, "player_game_handicap")
    assert rel.settled == 0
    assert rel.model_weight == DEFAULT_MODEL_WEIGHT, (
        "with no admissible evidence the weight must fall back to the default, "
        "not be learned from post-start rows"
    )
    conn.close()


def test_corpus_summary_counts_each_class(tmp_path, monkeypatch):
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    _seed(conn, 2, "2026-08-20T05:00:00Z")
    _seed(conn, 3, None)
    _record(conn, 1, "a", "2026-08-20T01:00:00Z", POINT_IN_TIME)
    _record(conn, 2, "b", "2026-08-20T09:00:00Z", POST_START)
    _record(conn, 3, "c", "2026-08-20T01:00:00Z", None)
    conn.commit()

    summary = corpus_summary(conn)
    assert summary["point_in_time_staked"] == 1
    assert summary["post_start_staked"] == 1
    assert summary["unverifiable_staked"] == 1
    conn.close()


def test_record_prop_stamps_the_class_at_write_time(tmp_path, monkeypatch):
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props import settlement

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    _seed(conn, 2, "2026-08-20T05:00:00Z")
    conn.commit()

    _write_prop(settlement, monkeypatch, conn, 1, "2026-08-20T01:00:00Z", odds=2.0)
    _write_prop(settlement, monkeypatch, conn, 2, "2026-08-20T09:00:00Z", odds=2.0)
    got = {
        row["match_id"]: row["is_point_in_time"]
        for row in conn.execute(
            "SELECT match_id, is_point_in_time FROM prop_tracker").fetchall()
    }
    assert got[1] == POINT_IN_TIME
    assert got[2] == POST_START
    conn.close()


def test_a_post_start_rerecord_cannot_overwrite_a_pre_match_price(tmp_path, monkeypatch):
    """The card and the recovery job both re-record props that are still
    PENDING, and a match that has already started is still PENDING. That was
    replacing real pre-match prices with prices taken 0.3 to 144 hours after
    the first ball, on 1,824 of the last fortnight's 3,991 rows -- destroying
    the only number that made the row a recommendation.
    """
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props import settlement

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    conn.commit()

    _write_prop(settlement, monkeypatch, conn, 1, "2026-08-20T01:00:00Z", odds=2.00)
    _write_prop(settlement, monkeypatch, conn, 1, "2026-08-20T09:00:00Z", odds=7.77)

    row = conn.execute(
        "SELECT decimal_odds, is_point_in_time FROM prop_tracker").fetchone()
    assert row["decimal_odds"] == 2.00, "the pre-match price must survive"
    assert row["is_point_in_time"] == POINT_IN_TIME
    conn.close()


def test_a_pre_match_rerecord_still_updates_the_price(tmp_path, monkeypatch):
    """The guard must not freeze the card: re-pricing before the start is the
    normal case and has to keep working."""
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.props import settlement

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    conn.commit()

    _write_prop(settlement, monkeypatch, conn, 1, "2026-08-20T01:00:00Z", odds=2.00)
    _write_prop(settlement, monkeypatch, conn, 1, "2026-08-20T03:00:00Z", odds=2.50)

    row = conn.execute(
        "SELECT decimal_odds, is_point_in_time FROM prop_tracker").fetchone()
    assert row["decimal_odds"] == 2.50
    assert row["is_point_in_time"] == POINT_IN_TIME
    conn.close()


def _write_prop(settlement, monkeypatch, conn, match_id: int, now: str,
                odds: float) -> None:
    monkeypatch.setattr(settlement, "utc_now", lambda: now)
    settlement.record_prop(
        conn, match_id=match_id, match_date="2026-08-20", match_label="A v B",
        market_key="player_game_handicap_2.5", line=2.5, selection="A",
        side="over", prop_scope="match", subject_player_id=None,
        decimal_odds=odds, model_prob=0.6, market_prob_fair=0.5,
        blended_prob=0.55, edge=0.05, ev=0.1, predicted_mean=10.0,
        stake_units=1.0, is_value=True, model_prob_raw=0.6,
    )


def test_the_guard_check_judges_new_rows_not_history(tmp_path, monkeypatch):
    """The 1,824 already-written offenders cannot be repaired, so judging them
    would block publication for a fortnight over something unfixable. A NEW
    offender means the `record_prop` guard was defeated, which is critical."""
    db_path = configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.validation import checks

    init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed(conn, 1, "2026-08-20T05:00:00Z")
    _seed(conn, 2, "2026-08-20T05:00:00Z")
    monkeypatch.setattr(checks, "POST_START_GUARD_FROM", "2026-08-27")

    # History: written late, before the guard existed.
    _record(conn, 1, "a", "2026-08-20T09:00:00Z", POST_START)
    conn.commit()
    assert checks.check_new_props_are_recorded_before_the_match(conn).passed

    # A late row written after the guard landed is a regression.
    _record(conn, 2, "b", "2026-08-28T09:00:00Z", POST_START)
    conn.commit()
    result = checks.check_new_props_are_recorded_before_the_match(conn)
    assert not result.passed and result.severity == "critical"
    conn.close()


def test_the_replay_refuses_to_delete_a_real_record_without_being_told(tmp_path):
    """`--rebuild-source-tracker` DELETEs the live tracker, and one unguarded
    run of it wrote three months of post-hoc rows over the real record on
    2026-08-10. Provably pre-match rows cannot be regenerated."""
    import subprocess
    import sys

    db = tmp_path / "replay.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE prop_tracker (id INTEGER PRIMARY KEY, is_point_in_time INTEGER);
        INSERT INTO prop_tracker VALUES (1, 1), (2, 0), (3, NULL);
        """
    )
    conn.commit()
    conn.close()

    script = Path(__file__).resolve().parents[1] / "scripts" / "replay_prop_strategy.py"
    result = subprocess.run(
        [sys.executable, str(script), "--source-db", str(db),
         "--rebuild-source-tracker"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "1 provably pre-match rows" in result.stderr
    assert "--discard-point-in-time-record" in result.stderr

    # Still there: the refusal must not have been a partial run.
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM prop_tracker").fetchone()[0] == 3
    conn.close()
