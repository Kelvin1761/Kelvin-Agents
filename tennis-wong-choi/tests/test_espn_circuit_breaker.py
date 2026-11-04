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


def test_scoreboard_only_routes_explicit_singles_to_their_own_tour(monkeypatch):
    day = "2026-01-30"

    def competition(match_id, draw):
        return {
            "id": match_id,
            "date": f"{day}T03:00:00Z",
            "type": {"slug": draw},
            "status": {"type": {"completed": True}},
            "competitors": [
                {"id": f"{match_id}-winner", "winner": True},
                {"id": f"{match_id}-loser", "winner": False},
            ],
        }

    competitions = [
        competition("men", "mens-singles"),
        competition("women", "womens-singles"),
        competition("mixed", "mixed-doubles"),
        competition("men-doubles", "mens-doubles"),
        competition("women-doubles", "womens-doubles"),
    ]
    body = {"events": [{"name": "Australian Open", "groupings": [{"competitions": competitions}]}]}
    monkeypatch.setattr(espn_mod, "get_json", lambda *args, **kwargs: body)
    provider = EspnTennisProvider()

    fixtures = provider.fetch_upcoming_matches(day)
    assert [(row["id"], row["tour"]) for row in fixtures] == [("men", "ATP"), ("women", "WTA")]
    history = provider.fetch_historical_matches(day, day)
    assert [(row["id"], row["tour"]) for row in history] == [
        ("men-1", "ATP"), ("men-2", "ATP"), ("women-1", "WTA"), ("women-2", "WTA"),
    ]


def test_espn_history_format_uses_explicit_draw_and_grand_slam_main_round(monkeypatch):
    day = "2026-01-30"

    def match(match_id, draw, stage):
        return {
            "id": match_id,
            "date": f"{day}T03:00:00Z",
            "type": {"slug": draw},
            "round": {"displayName": stage},
            "format": {"regulation": {"periods": 5}},
            "status": {"type": {"completed": True}},
            "competitors": [{"id": "1", "winner": True}, {"id": "2", "winner": False}],
        }

    body = {"events": [
        {"name": "Australian Open", "groupings": [{"competitions": [
            match("main", "mens-singles", "Semifinal"),
            match("qual", "mens-singles", "Qualifying Final"),
            match("women", "womens-singles", "Final"),
        ]}]},
        {"name": "Mutua Madrid Open", "groupings": [{"competitions": [
            match("masters", "mens-singles", "Final"),
        ]}]},
    ]}
    monkeypatch.setattr(espn_mod, "get_json", lambda *args, **kwargs: body)
    rows = EspnTennisProvider().fetch_historical_matches(day, day)

    assert {row["id"]: row["format"] for row in rows} == {
        "main-1": "BO5", "main-2": "BO5",
        "qual-1": "BO3", "qual-2": "BO3",
        "masters-1": "BO3", "masters-2": "BO3",
        "women-1": "BO3", "women-2": "BO3",
    }
