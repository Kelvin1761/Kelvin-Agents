"""Keep publication locks out of production while testing."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_dashboard_publication_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_DASHBOARD_PUBLICATION_LOCK_PATH", str(tmp_path / "dashboard.lock"))
    monkeypatch.delenv("_WC_DASHBOARD_PUBLICATION_LOCK_HELD", raising=False)
