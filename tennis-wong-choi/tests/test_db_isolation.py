from __future__ import annotations

import os
from pathlib import Path


PROJECT_DB = Path(__file__).resolve().parents[1] / "tennis_wc.db"


def test_the_default_database_is_never_the_production_one():
    """The backstop for a whole class of defect, asserted rather than assumed.

    `configure_test_db` is opt-in, so isolation held only for tests that
    remembered to ask. On 2026-08-25 one test in `test_daily_report.py` had not:
    it called `render_daily_report` with no fixture, `DATABASE_URL` stayed at
    its default, and the report wrote into the live betting ledger on every full
    run. It failed nothing and printed nothing -- it was found by watching the
    database file's mtime across a run, which is not a thing anyone does twice.

    `pytest_configure` now points the default at a throwaway file. This test is
    what stops that being quietly undone.
    """
    url = os.environ.get("DATABASE_URL", "")
    assert url, "the suite must pin DATABASE_URL rather than inherit whatever is set"
    assert "tennis-test-db-" in url, f"DATABASE_URL is not a test path: {url}"
    assert str(PROJECT_DB) not in url


def test_the_configured_database_is_writable_and_empty():
    """The guard has to leave a USABLE database behind. Pointing the default at
    an unwritable path would turn one silent-corruption bug into a hundred
    confusing failures."""
    from tennis_wc.database.migrations import init_db
    from tennis_wc.database.db import get_connection

    init_db()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM prop_tracker").fetchone()[0]
    assert count == 0, "a test that forgets to isolate must see an empty ledger"
