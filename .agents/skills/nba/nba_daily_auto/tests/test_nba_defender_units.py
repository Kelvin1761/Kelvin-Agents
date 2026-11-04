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


# v2 packages (before the ESPN switch) keep their own defender rule.
@pytest.mark.parametrize('contract,mode,count,valid',[(None,'Totals',576,False),(1,'Totals',576,False),
    (2,'PerGame',576,False),(2,'Totals',0,False),(2,'Totals','576',False),
    (2,'Totals',True,False),
    (2,'Totals',576,True)])
def test_cache_reextracts_old_unit_or_source_failure(tmp_path,contract,mode,count,valid):
    payload={'meta':{'statistics_contract':contract,'defender_source':{'per_mode':mode,'sample_unit':'total_attempts','observed_players':count},
                     'season_phase':'REGULAR_SEASON'},
             'team_stats':{'BOS':{'PACE':99}},'players':{'BOS':[{'position':'C','advanced':{'USG_PCT':20}}]}}
    path=tmp_path/'data.json';path.write_text(json.dumps(payload))
    assert o.extractor_cache_current(str(path)) is valid


@pytest.mark.parametrize('count,valid',[(0,False),(None,False),('576',False),(True,False),(576,True)])
def test_new_extraction_checks_statistics_before_report(tmp_path,monkeypatch,count,valid):
    odds=tmp_path/'odds.json';odds.write_text('{}')
    target=tmp_path/'nba_game_data_BOS_LAL.json';calls=[]
    payload={'meta':{'statistics_contract':2,
                     'defender_source':{'per_mode':'Totals','sample_unit':'total_attempts','observed_players':count}}}
    monkeypatch.setattr(o,'player_milestone_markets_available',lambda _:True)
    monkeypatch.setattr(o,'availability_current',lambda _:True)
    def run(script,args,**kwargs):
        calls.append(script)
        if script==o.NBA_EXTRACTOR:
            target.write_text(json.dumps(payload));return True
        return False  # the valid receipt reaches the report generator, which fails here
    monkeypatch.setattr(o,'run_script',run)
    assert not o.process_single_game('BOS_LAL',str(odds),str(tmp_path),'2026-10-24')
    assert calls[0]==o.NBA_EXTRACTOR
    assert (o.GENERATE_REPORTS in calls) is valid
    assert len(calls)==(2 if valid else 1)
    assert target.read_text()==json.dumps(payload)  # diagnostic input is retained


def test_empty_defenders_pass_only_when_marked_unavailable_in_an_outage():
    # EXP-20261031-01: no defender table during an nba.com outage changes no
    # probability, so an explicitly marked empty source may publish.
    from nba_data_contract import TRACKING_UNAVAILABLE, statistics_current
    base = {'statistics_contract': 2,
            'defender_source': {'per_mode': 'Totals', 'sample_unit': 'total_attempts', 'observed_players': 0}}
    assert not statistics_current(base), 'silently empty still blocks'
    marked = {**base, 'defender_source': {**base['defender_source'], 'unavailable': TRACKING_UNAVAILABLE}}
    assert statistics_current(marked)
    wrong = {**base, 'defender_source': {**base['defender_source'], 'unavailable': 'anything'}}
    assert not statistics_current(wrong)


@pytest.mark.parametrize('meta,valid',[
    ({'stat_source':'espn'},True),({'stat_source':'nbacom'},True),({'stat_source':'mixed'},True),
    ({},False),({'stat_source':'nba'},False),
    # v3 needs no defender table at all: tracking data is nba.com-only.
    ({'stat_source':'espn','defender_source':{'observed_players':0}},True)])
def test_v3_contract_names_its_source_and_needs_no_defenders(meta,valid):
    from nba_data_contract import statistics_current
    assert NBA_STATISTICS_CONTRACT == 3
    assert statistics_current({'statistics_contract':NBA_STATISTICS_CONTRACT,**meta}) is valid


def test_stat_source_reads_game_logs_and_league_tables():
    from nba_data_contract import stat_source
    def package(log_sources,table_source):
        return {'players':{'BOS':[{'gamelog':{'source':s}} for s in log_sources]},
                'meta':{'data_sources':{'team_stats':{'rows':30,**({'source':table_source} if table_source else {})},
                                        'key_defenders':{'rows':0}}}}
    assert stat_source(package(['espn','espn'],'espn_box'))=='espn'
    assert stat_source(package(['nba','nba'],None))=='nbacom'
    assert stat_source(package(['espn','nba'],'espn_box'))=='mixed'
    assert stat_source(package(['espn'],None))=='mixed', 'an nba.com table beside ESPN logs is two rulers'
