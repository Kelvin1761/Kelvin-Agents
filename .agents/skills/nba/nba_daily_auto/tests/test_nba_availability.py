"""Availability refresh is verified and atomic; no live network or data writes."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / "nba_data_extractor" / "scripts"))
import nba_availability as a
import nba_extractor as extractor

NOW = datetime(2026, 10, 23, 0, tzinfo=timezone.utc)
NAMES = [f"Fixture Player{i}" for i in range(5)]


def maps(captured=NOW, status="Out"):
    return {team: a.InjuryMap({NAMES[0]: status}, [a.player_name_key(n) for n in NAMES], captured.isoformat())
            for team in ("BOS", "LAL")}


def package(captured=NOW):
    base = {"meta": {"date": (NOW + timedelta(hours=2)).isoformat(),
                     "away": {"abbr": "BOS"}, "home": {"abbr": "LAL"}},
            "players": {t: [{"name": NAMES[0], "gamelog": {"PTS": [10]}}] for t in ("BOS", "LAL")},
            "team_stats": {"BOS": {"PACE": 99}}}
    return a.apply_availability(base, maps(captured))


class Response:
    status_code = 200

    def __init__(self, athletes):
        self.athletes = athletes

    def json(self):
        return {"athletes": self.athletes}


def test_verified_empty_injury_list_is_healthy_and_aliases_are_supported():
    get = mock.Mock(return_value=Response([{"fullName": n, "injuries": []} for n in NAMES]))
    result = a.fetch_team_availability("GSW", get=get, now=NOW)
    assert isinstance(result, a.InjuryMap) and result == {}
    assert len(result.roster_names) == 5
    assert "/GS/roster" in get.call_args.args[0]


@pytest.mark.parametrize("athletes", [None, [], [{"fullName": n} for n in NAMES[:4]],
                                        [{"fullName": "Same Name"}] * 5,
                                        [{"fullName": n, "injuries": [{}]} for n in NAMES]])
def test_incomplete_roster_is_not_a_healthy_response(athletes):
    with pytest.raises(a.AvailabilityUnavailable):
        a.fetch_team_availability("BOS", get=lambda *args, **kwargs: Response(athletes), now=NOW)


def test_network_or_http_failure_is_not_healthy():
    with pytest.raises(a.AvailabilityUnavailable):
        a.fetch_team_availability("BOS", get=mock.Mock(side_effect=TimeoutError))
    response = Response([])
    response.status_code = 503
    with pytest.raises(a.AvailabilityUnavailable, match="HTTP 503"):
        a.fetch_team_availability("BOS", get=lambda *args, **kwargs: response)


@pytest.mark.parametrize("age,current", [(0, True), (1800, True), (1801, False), (-1, False)])
def test_fixed_operational_freshness_window(age, current):
    assert a.availability_current(package(NOW - timedelta(seconds=age)), now=NOW) is current


def test_refresh_updates_status_but_preserves_historical_stats_and_input():
    old = package(NOW - timedelta(hours=2))
    original = copy.deepcopy(old)
    changed = maps(status="Questionable")
    new = a.refresh_availability(old, fetch=lambda team: changed[team], now=NOW)
    assert old == original
    assert new["players"]["BOS"][0]["status"] == "Questionable"
    assert new["players"]["BOS"][0]["gamelog"] == old["players"]["BOS"][0]["gamelog"]
    assert new["team_stats"] == old["team_stats"]
    assert a.availability_current(new, now=NOW)


def test_roster_change_requires_full_extraction_without_mutating_old_package():
    old = package()
    before = copy.deepcopy(old)
    changed = maps()
    changed["BOS"].roster_names = ["new signing", *changed["BOS"].roster_names]
    with pytest.raises(a.RosterChanged):
        a.refresh_availability(old, fetch=lambda team: changed[team], now=NOW)
    assert old == before


def test_started_game_never_queries_source_or_changes_cache():
    old = package()
    old["meta"]["date"] = NOW.isoformat()
    fetch = mock.Mock()
    with pytest.raises(a.AvailabilityUnavailable, match="already started"):
        a.refresh_availability(old, fetch=fetch, now=NOW)
    fetch.assert_not_called()


def test_failed_availability_refresh_leaves_original_file_exactly_unchanged(tmp_path):
    old = package(NOW - timedelta(hours=2))
    path = tmp_path / "game.json"
    path.write_text(json.dumps(old))
    original = path.read_bytes()
    with mock.patch.object(extractor, "fetch_team_injuries", side_effect=a.AvailabilityUnavailable("offline")), \
         mock.patch.object(sys, "argv", ["extractor", "--refresh-availability", str(path)]), \
         pytest.raises(SystemExit) as error:
        extractor.main()
    assert error.value.code == 75
    assert path.read_bytes() == original


def test_legacy_cache_without_provenance_is_stale():
    old = package()
    del old["meta"]["availability"]
    assert not a.availability_current(old, now=NOW)
