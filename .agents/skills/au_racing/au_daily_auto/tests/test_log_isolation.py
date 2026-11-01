"""A simulated parser failure must never create the production log."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_daily_schedule as schedule  # noqa: E402


def test_scheduler_log_is_isolated_by_default(monkeypatch, tmp_path):
    production = tmp_path / "production-logs"
    monkeypatch.setattr(schedule, "LOG_DIR", production)

    schedule.log("Randwick: parser exploded")

    assert not production.exists()
    isolated = Path(os.environ["WC_AU_SCHED_LOG_DIR"]) / "au_daily_schedule.log"
    assert "Randwick: parser exploded" in isolated.read_text(encoding="utf-8")
