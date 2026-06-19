from __future__ import annotations

import tennis_wc.providers.espn_provider as espn_mod
from tennis_wc.providers.espn_provider import EspnTennisProvider


def test_historical_backfill_aborts_when_espn_is_down(monkeypatch):
    # Simulate a fully-down ESPN: every call raises. Over a wide window
    # (~550 days x 2 tours = ~1100 calls) the circuit breaker must abort after a
    # handful of consecutive failures instead of grinding through everything.
    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("HTTP 502 from ESPN")

    monkeypatch.setattr(espn_mod, "get_json", boom)
    provider = EspnTennisProvider()
    results = provider.fetch_historical_matches("2025-01-01", "2026-06-19")  # ~535 days

    assert results == []
    assert calls["n"] <= EspnTennisProvider._HISTORICAL_MAX_CONSECUTIVE_FAILURES


def test_short_timeout_is_used_for_historical_calls(monkeypatch):
    seen = {}

    def capture(url, params=None, timeout=20):
        seen["timeout"] = timeout
        raise RuntimeError("down")

    monkeypatch.setattr(espn_mod, "get_json", capture)
    EspnTennisProvider().fetch_historical_matches("2026-06-18", "2026-06-18")
    assert seen["timeout"] == EspnTennisProvider._HISTORICAL_TIMEOUT_SECONDS
