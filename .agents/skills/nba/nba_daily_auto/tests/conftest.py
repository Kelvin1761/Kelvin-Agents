"""Keep every test away from the real NBA state on this machine.

The ESPN client keeps its spacing, circuit marker and response cache under
the home directory; a test that exercises those paths must never write (or
read) the production copies.
"""
import sys

import pytest


@pytest.fixture(autouse=True)
def _isolated_nba_state(monkeypatch, tmp_path_factory):
    root = tmp_path_factory.mktemp("nba_state")
    monkeypatch.setenv("WC_NBA_HTTP_CACHE_DIR", str(root / "nba_http"))
