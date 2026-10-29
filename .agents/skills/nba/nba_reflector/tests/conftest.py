"""Keep every test away from the real NBA state on this machine.

The extractor now saves league-table / roster snapshots and the nba.com
circuit-breaker marker under the home directory; a test that exercises those
paths must never write (or read) the production copies.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_nba_state(monkeypatch, tmp_path_factory):
    root = tmp_path_factory.mktemp("nba_state")
    monkeypatch.setenv("WC_NBA_LEAGUE_SNAPSHOT_DIR", str(root / "league_snapshots"))
    monkeypatch.setenv("WC_NBA_API_BREAKER_FILE", str(root / "stats_nba_breaker.json"))
