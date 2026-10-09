from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def configure_test_db(tmp_path, monkeypatch) -> Path:
    db_path = tmp_path / "tennis_wc_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("TENNIS_PROVIDER", "mock")
    monkeypatch.setenv("ODDS_PROVIDER", "mock")
    monkeypatch.setenv("NEWS_PROVIDER", "mock")
    # Tests exercise a fresh bootstrap, not the production incremental refresh
    # window loaded from the developer's local .env.
    monkeypatch.setenv("HISTORY_BACKFILL_DAYS", "550")
    return db_path


def mark_tracker_pre_match(conn, recorded_at: str = "2026-01-01T00:00:00Z",
                           start_time_utc: str = "2099-01-01T00:00:00Z") -> None:
    """Make every `clv_tracker` row provably pre-match.

    Gates read only legs written before their match started
    (`evaluation.corpus.tracker_point_in_time_clause`), so a fixture that wants
    its rows counted must give them a match with a later start time.
    """
    for row in conn.execute("SELECT DISTINCT match_id FROM clv_tracker").fetchall():
        match_id = row[0]
        conn.execute(
            """INSERT OR IGNORE INTO matches (id, provider_match_id, tour, match_date, tournament_id,
                   player_a_id, player_b_id, round, source_provider, created_at, updated_at,
                   start_time_utc)
               VALUES (?, ?, 'ATP', '2026-06-01', 1, 1, 2, 'R1', 'pit-fixture', ?, ?, ?)""",
            (match_id, f"pit-{match_id}", recorded_at, recorded_at, start_time_utc),
        )
        conn.execute(
            "UPDATE matches SET start_time_utc = ? WHERE id = ? "
            "AND (start_time_utc IS NULL OR start_time_utc = '')",
            (start_time_utc, match_id),
        )
    conn.execute("UPDATE clv_tracker SET recorded_at = ?", (recorded_at,))


def _isolate_scheduler_log() -> None:
    """Keep the test suite out of the log the live scheduler reads.

    `scripts/tennis_daily_schedule.log` had grown to 866,594 lines and 28MB
    with pytest's own "Live network preflight passed" and "Notify skipped"
    entries interleaved through the real run history. Setting this before any
    test imports the scheduler puts every test line in a temp directory
    instead, in one place rather than per test.
    """
    import tempfile

    os.environ.setdefault(
        "TENNIS_LOG_DIR", tempfile.mkdtemp(prefix="tennis-test-logs-")
    )


_isolate_scheduler_log()


def pytest_configure(config) -> None:
    """Make the production database read-only for the whole test session.

    `configure_test_db` is opt-in, and on 2026-08-25 exactly one test in
    `test_daily_report.py` had been written without it. It called
    `render_daily_report` with no fixture, so `DATABASE_URL` stayed at its
    default and the report wrote straight into the live `tennis_wc.db` -- four
    prop_tracker rows on 2026-05-10 took an `updated_at` bump on every full
    run. Nothing failed and nothing printed; it was found only by watching the
    file's mtime across a run.

    The next such test will not be found that way. Pointing the default at a
    throwaway file means a test that forgets to isolate itself gets an empty
    database -- which is a loud, ordinary test failure -- instead of quietly
    editing a real betting ledger. Tests that WANT the default still get their
    own path per test via `configure_test_db`'s monkeypatch, which takes
    precedence over this.
    """
    import tempfile

    os.environ["DATABASE_URL"] = (
        f"sqlite:///{tempfile.mkdtemp(prefix='tennis-test-db-')}/tennis_wc_test.db"
    )
