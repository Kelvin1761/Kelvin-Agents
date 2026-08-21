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
