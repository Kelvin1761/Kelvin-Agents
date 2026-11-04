"""Season phases come from ESPN's published calendar; the hand config is only a fallback."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import nba_season as s  # noqa: E402

# ESPN core API 2026-27 season types, as published (US-midnight boundaries in UTC).
TYPES = {
    1: ("2026-09-30T07:00Z", "2026-10-20T06:59Z"),
    2: ("2026-10-20T07:00Z", "2027-04-12T06:59Z"),
    3: ("2027-04-17T07:00Z", "2027-06-26T06:59Z"),
    5: ("2027-04-12T07:00Z", "2027-04-17T06:59Z"),
}


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def fake_get(url, timeout=None):
    type_id = int(url.rstrip("/").rsplit("/", 1)[1])
    start, end = TYPES[type_id]
    return Response({"startDate": start, "endDate": end})


def test_espn_windows_become_sydney_game_dates():
    config = s.espn_season_config(datetime(2026, 11, 4), get=fake_get)
    assert config["season"] == "2026-27"
    assert (config["preseason_start"], config["preseason_end"]) == ("2026-10-01", "2026-10-20")
    assert config["regular_season_start"] == "2026-10-21"          # US opening night 10-20
    assert config["regular_season_end"] == "2027-04-12"
    assert (config["play_in_start"], config["play_in_end"]) == ("2027-04-13", "2027-04-17")
    assert (config["playoffs_start"], config["playoffs_end"]) == ("2027-04-18", "2027-06-26")
    assert config["early_regular_end"] == "2026-11-16" and config["late_regular_start"] == "2027-03-25"


@pytest.mark.parametrize("day,phase,mode", [
    ("2026-10-20", "PRESEASON", "shadow"),
    ("2026-10-21", "EARLY_REGULAR", "production"),
    ("2026-12-25", "REGULAR_SEASON", "production"),
    ("2027-04-01", "LATE_REGULAR", "production"),
    ("2027-04-14", "POSTSEASON", "production"),
    ("2027-05-20", "POSTSEASON", "production"),
])
def test_classifier_uses_espn_calendar(monkeypatch, day, phase, mode):
    monkeypatch.setattr(s, "espn_season_config", lambda d: s.__dict__["_real"](d, get=fake_get))
    result = s.classify_nba_season(day)
    assert (result["season_phase"], result["automation_mode"], result["classification_source"]) == (
        phase, mode, "espn_calendar")


s._real = s.espn_season_config


def test_tipoff_timestamps_are_read_as_sydney_dates(monkeypatch):
    monkeypatch.setattr(s, "espn_season_config", lambda d: s._real(d, get=fake_get))
    # US opening night 2026-10-20 19:30 ET = 23:30Z = Sydney 10-21: regular season.
    assert s.classify_nba_season("2026-10-20T23:30Z")["season_phase"] == "EARLY_REGULAR"
    # Last preseason night US 10-19 = Sydney 10-20.
    assert s.classify_nba_season("2026-10-19T23:30Z")["season_phase"] == "PRESEASON"


def test_espn_failure_falls_back_to_hand_config(monkeypatch):
    def broken(url, timeout=None):
        raise ConnectionError("ESPN down")
    assert s.espn_season_config(datetime(2026, 11, 4), get=broken) is None
    monkeypatch.setattr(s, "espn_season_config", lambda d: None)
    assert s.classify_nba_season("2026-11-04")["classification_source"] == "season_config"


def test_tests_never_reach_espn_without_an_injected_get():
    assert s.espn_season_config(datetime(2026, 11, 4)) is None
