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
