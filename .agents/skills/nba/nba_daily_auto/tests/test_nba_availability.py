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


def test_cached_player_outside_verified_roster_is_excluded_without_injury_donation():
    original=package()
    original['players']['BOS']=[
        {'name':NAMES[0],'advanced':{'USG_PCT':30},'gamelog':{'PTS':[20]}},
        {'name':NAMES[1],'advanced':{'USG_PCT':20},'gamelog':{'PTS':[15]}},
        {'name':'Former Teammate','advanced':{'USG_PCT':50},'gamelog':{'PTS':[30]}},
    ]
    updated=a.apply_availability(original,maps())
    departed=updated['players']['BOS'][2]
    assert departed['roster_verified'] is False
    assert departed['status']=='Not On Verified Roster'
    assert a.classify_injury_status(updated['injuries']['BOS']['Former Teammate'])=='out'
    assert updated['usage_redistribution']['BOS'][NAMES[1]]['bonus_USG']==30  # not 80
    assert departed['gamelog']==original['players']['BOS'][2]['gamelog']
    assert a.availability_current(updated,now=NOW)


def test_refresh_validates_after_request_completion(monkeypatch):
    clock=iter([NOW,NOW+timedelta(seconds=3)])
    monkeypatch.setattr(a,'_utc_now',lambda:next(clock))
    fresh=maps(NOW+timedelta(seconds=1))
    updated=a.refresh_availability(package(NOW-timedelta(hours=1)),fetch=lambda team:fresh[team])
    assert a.availability_current(updated,now=NOW+timedelta(seconds=3))


def test_game_starting_during_refresh_cannot_be_published(monkeypatch):
    old=package();old['meta']['date']=(NOW+timedelta(seconds=2)).isoformat()
    before=copy.deepcopy(old);clock=iter([NOW,NOW+timedelta(seconds=3)])
    monkeypatch.setattr(a,'_utc_now',lambda:next(clock))
    fresh=maps(NOW+timedelta(seconds=1))
    with pytest.raises(a.AvailabilityUnavailable,match='started during'):
        a.refresh_availability(old,fetch=lambda team:fresh[team])
    assert old==before


def test_defender_context_excludes_departed_and_out_but_preserves_reference():
    original=package();original['key_defenders']={'BOS':[{'name':'Former Defender'},{'name':NAMES[0]},{'name':NAMES[1]}],'LAL':[]}
    before=copy.deepcopy(original);fresh=maps();fresh['BOS'][NAMES[1]]='Questionable'
    updated=a.apply_availability(original,fresh)
    assert [d['name'] for d in updated['key_defenders']['BOS']]==[NAMES[1]]
    assert updated['key_defenders_reference']['BOS']==original['key_defenders']['BOS']
    assert not updated['meta']['defender_availability']['actual_matchups_verified']
    assert updated['meta']['defender_availability']['teams']['BOS']['excluded']==[
        {'name':'Former Defender','reason':'not_on_verified_roster'},
        {'name':NAMES[0],'reason':'known_unavailable'}]
    assert original==before
    assert a.apply_availability(updated,fresh)==updated
    recovered=a.apply_availability(updated,maps(status='Active'))
    assert [d['name'] for d in recovered['key_defenders']['BOS']]==[NAMES[0],NAMES[1]]


def test_unverified_defender_roster_is_explicitly_unavailable():
    original=package();original['key_defenders']={'BOS':[{'name':NAMES[1]}]}
    updated=a.apply_availability(original,{'BOS':{},'LAL':{}})
    assert updated['key_defenders']['BOS']==[]
    assert updated['meta']['defender_availability']['teams']['BOS']['status']=='roster_unverified'
    assert not a.availability_current(updated,now=NOW)


def test_full_defender_reference_allows_filter_before_top_eight_limit():
    data={str(i):{'name':f'Former {i}','team':'BOS','D_FGA_unit':'total_attempts','D_FGA':30,'PCT_PLUSMINUS':-.1+i*.001} for i in range(9)}
    data['current']={'name':NAMES[1],'team':'BOS','D_FGA_unit':'total_attempts','D_FGA':30,'PCT_PLUSMINUS':.1}
    assert len(extractor.key_defenders_for_team(data,'BOS'))==8
    original=package();original['key_defenders']={'BOS':extractor.key_defenders_for_team(data,'BOS',limit=None)}
    updated=a.apply_availability(original,maps())
    assert [d['name'] for d in updated['key_defenders']['BOS']]==[NAMES[1]]
    assert len(updated['key_defenders_reference']['BOS'])==10
