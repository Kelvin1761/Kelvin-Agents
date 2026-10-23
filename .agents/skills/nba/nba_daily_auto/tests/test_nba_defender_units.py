"""The defender sample floor is 20 total attempts; cache migration is explicit."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(NBA))
sys.path.insert(0,str(NBA/'nba_data_extractor/scripts'))
import nba_extractor as e
import nba_orchestrator as o
from nba_data_contract import NBA_STATISTICS_CONTRACT


def test_fetch_requests_total_attempts_and_retains_sample_provenance(monkeypatch):
    calls=[]
    def endpoint(**kwargs):
        calls.append(kwargs)
        frame=pd.DataFrame([{'CLOSE_DEF_PERSON_ID':1,'PLAYER_NAME':'Verified Defender','PLAYER_LAST_TEAM_ABBREVIATION':'GSW',
                             'PLAYER_POSITION':'C','GP':75,'D_FGA':1413,'D_FG_PCT':.45,'NORMAL_FG_PCT':.497,'PCT_PLUSMINUS':-.047}])
        return SimpleNamespace(get_data_frames=lambda:[frame])
    monkeypatch.setattr(e,'NBA_API_AVAILABLE',True)
    monkeypatch.setattr(e.leaguedashptdefend,'LeagueDashPtDefend',endpoint)
    monkeypatch.setattr(e.time,'sleep',lambda _:None)
    data=e.fetch_defender_impact('2025-26',as_of='2026-04-08T23:00Z')
    assert calls[0]['per_mode_simple']=='Totals'
    assert calls[0]['date_to_nullable']=='04/07/2026'
    assert data[1]['D_FGA']==1413 and data[1]['GP']==75 and data[1]['D_FGA_unit']=='total_attempts'
    assert e.key_defenders_for_team(data,'GS')==[data[1]]


def test_twenty_attempt_floor_rejects_per_game_or_unlabelled_values_and_sorts():
    data={i:row for i,row in enumerate([
        {'team':'GSW','D_FGA':19,'D_FGA_unit':'total_attempts','PCT_PLUSMINUS':-.2},
        {'team':'GSW','D_FGA':20,'D_FGA_unit':'total_attempts','PCT_PLUSMINUS':-.1},
        {'team':'GSW','D_FGA':500,'D_FGA_unit':'total_attempts','PCT_PLUSMINUS':-.15},
        {'team':'GSW','D_FGA':30,'D_FGA_unit':'per_game','PCT_PLUSMINUS':-.3},
        {'team':'GSW','D_FGA':500,'PCT_PLUSMINUS':-.3},
        {'team':'BOS','D_FGA':500,'D_FGA_unit':'total_attempts','PCT_PLUSMINUS':-.3},
    ])}
    assert e.key_defenders_for_team(data,'GS')==[data[2],data[1]]


@pytest.mark.parametrize('contract,mode,count,valid',[(None,'Totals',576,False),(1,'Totals',576,False),
    (NBA_STATISTICS_CONTRACT,'PerGame',576,False),(NBA_STATISTICS_CONTRACT,'Totals',0,False),(NBA_STATISTICS_CONTRACT,'Totals','576',False),
    (NBA_STATISTICS_CONTRACT,'Totals',True,False),
    (NBA_STATISTICS_CONTRACT,'Totals',576,True)])
def test_cache_reextracts_old_unit_or_source_failure(tmp_path,contract,mode,count,valid):
    payload={'meta':{'statistics_contract':contract,'defender_source':{'per_mode':mode,'sample_unit':'total_attempts','observed_players':count},
                     'season_phase':'REGULAR_SEASON'},
             'team_stats':{'BOS':{'PACE':99}},'players':{'BOS':[{'position':'C','advanced':{'USG_PCT':20}}]}}
    path=tmp_path/'data.json';path.write_text(json.dumps(payload))
    assert o.extractor_cache_current(str(path)) is valid
