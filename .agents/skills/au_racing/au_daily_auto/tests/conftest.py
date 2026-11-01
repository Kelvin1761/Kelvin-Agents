"""Keep test logs and publication locks out of production."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_dashboard_publication_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_DASHBOARD_PUBLICATION_LOCK_PATH", str(tmp_path / "dashboard.lock"))
    monkeypatch.delenv("_WC_DASHBOARD_PUBLICATION_LOCK_HELD", raising=False)


@pytest.fixture(autouse=True)
def isolate_scheduler_log(monkeypatch, tmp_path):
    # log() resolves this at call time; each test gets its own destination even
    # when pytest is run directly from the production checkout.
    monkeypatch.setenv("WC_AU_SCHED_LOG_DIR", str(tmp_path / "scheduler-logs"))
