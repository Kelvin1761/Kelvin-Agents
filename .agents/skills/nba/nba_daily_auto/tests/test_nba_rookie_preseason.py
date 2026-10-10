from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest import mock
import pandas as pd
import pytest

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / 'nba_data_extractor/scripts'))
sys.path.insert(0, str(NBA / 'nba_wong_choi/scripts'))
import nba_extractor as x
import nba_orchestrator as o
import generate_nba_reports as reports


def row(day, points):
    data = dict.fromkeys(['REB','AST','STL','BLK','TOV','MIN','FGM','FGA','FG_PCT','FG3M','FG3A','FTM','FTA','PLUS_MINUS'],0)
    return dict(data,GAME_DATE=day,MATCHUP='MEM vs. ORL',WL='W',PTS=points)


def test_preseason_history_uses_real_rows_and_excludes_event_day():
    frame=pd.DataFrame([row('2026-10-07',16),row('2026-10-05',11),row('2026-10-09',99)])
    endpoint=mock.Mock(get_data_frames=mock.Mock(return_value=[frame]))
    with mock.patch.object(x.playergamelog,'PlayerGameLog',return_value=endpoint) as api, mock.patch.object(x.time,'sleep'):
        log=x.fetch_player_gamelog(1643409,'Cameron Boozer',season='2026-27',as_of='2026-10-10T00:00Z',season_type='Pre Season')
    assert log['PTS']==[16,11]
    assert log['l10_season_types']==['Pre Season','Pre Season']
    assert log['history_seasons']==['2026-27']
    assert log['history_date_to']=='10/08/2026'
    api.assert_called_once()
    assert api.call_args.kwargs['season_type_all_star']=='Pre Season'


def test_empty_preseason_never_invents_rookie_history():
    endpoint=mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame()]))
    with mock.patch.object(x.playergamelog,'PlayerGameLog',return_value=endpoint),mock.patch.object(x.time,'sleep'):
        assert x.fetch_player_gamelog(1,'Rookie',season='2026-27',as_of='2026-10-10',season_type='Pre Season') is None


def test_preseason_roster_retains_rookie_when_five_veterans_have_usage():
    roster=[{'player_id':i,'name':f'Veteran {i}','experience':'3'} for i in range(5)]
    roster.append({'player_id':9,'name':'Rookie','experience':'R'})
    advanced={i:{'USG_PCT':10} for i in range(5)}
    game={'name':'Memphis Grizzlies at Chicago Bulls','date':'2026-10-10T00:00Z','away':{'name':'Memphis Grizzlies','abbreviation':'MEM'},'home':{'name':'Chicago Bulls','abbreviation':'CHI'}}
    with mock.patch.object(x,'fetch_team_roster',return_value=roster),mock.patch.object(x,'fetch_team_injuries',return_value={}),mock.patch.object(x,'fetch_nba_news',return_value=[]),mock.patch.object(x,'fetch_player_splits',return_value={}),mock.patch.object(x,'compute_prop_analytics',return_value={}),mock.patch.object(x,'compute_fatigue_adjustment',return_value={}),mock.patch.object(x,'fetch_player_gamelog',return_value=None) as history:
        package=x.extract_single_game(game,advanced,{},{},{},{})
    assert package['meta']['preseason_rookie_history_contract']==1
    assert len(package['players']['MEM'])==6
    calls=[c for c in history.call_args_list if c.args[0]==9]
    assert len(calls)==2
    assert all(c.kwargs['season']=='2026-27' and c.kwargs['season_type']=='Pre Season' for c in calls)
    assert all(c.kwargs['season']=='2025-26' and c.kwargs['season_type']=='Regular Season' for c in history.call_args_list if c.args[0]!=9)
    assert all(p['gamelog'] is None for p in package['players']['MEM'])


@pytest.mark.parametrize('meta,valid',[({'season_phase':'PRESEASON'},False),({'season_phase':'PRESEASON','preseason_rookie_history_contract':1},True),({'season_phase':'REGULAR_SEASON'},True)])
def test_stale_preseason_cache_requires_reextraction(tmp_path,meta,valid):
    p=tmp_path/'data.json';p.write_text(json.dumps({'meta':meta}))
    assert o.extractor_cache_current(str(p)) is valid


def test_report_explicitly_discloses_real_small_sample():
    card={'name':'Rookie','team':'MEM','category':'points','jersey':'27','l10':[16,11],'avg':13.5,'med':13.5,'sd':2.5,'cov':0.185,'cov_grade':'低','trend':'樣本不足','history_seasons':['2026-27'],'history_season_types':['Pre Season'],'history_date_to':'10/08/2026'}
    text=reports.gen_player_card(card)
    assert '真實樣本 2 場' in text
    assert '2026-27 / Pre Season' in text
    note=reports.preseason_sample_note([dict(card,category=category) for category in ['points','rebounds','assists','threes_made']] * 2)
    assert '唔代表完整 L10' in note
    assert 'NO BET' in note
    assert note.count('Rookie 2 場')==1
    import validate_nba_output as firewall
    combined=note+'\n'+'\n'.join(reports.gen_player_card(dict(card,category=category)) for category in ['points','rebounds','assists','threes_made'])
    assert firewall.check_fw04_padding(combined)==[]


def test_official_roster_null_position_remains_unknown():
    frame=pd.DataFrame([{'PLAYER_ID':9,'PLAYER':'Rookie','POSITION':None,'EXP':'R'}])
    endpoint=mock.Mock(get_data_frames=mock.Mock(return_value=[frame]))
    with mock.patch.object(x.teams,'get_teams',return_value=[{'id':1,'nickname':'Grizzlies','abbreviation':'MEM','full_name':'Memphis Grizzlies'}]),mock.patch.object(x.commonteamroster,'CommonTeamRoster',return_value=endpoint),mock.patch.object(x.time,'sleep'):
        roster=x.fetch_team_roster('MEM','2026-27')
    assert roster[0]['position']==''
    assert roster[0]['experience']=='R'


def test_null_position_cache_cannot_be_reused(tmp_path):
    p=tmp_path/'data.json';p.write_text(json.dumps({'meta':{'season_phase':'PRESEASON','preseason_rookie_history_contract':1},'players':{'MEM':[{'name':'Rookie','position':None}]}}))
    assert not o.extractor_cache_current(str(p))


def test_existing_report_cannot_bypass_stale_rookie_cache(tmp_path):
    report=tmp_path/'Game_MEM_CHI_Full_Analysis.md';report.write_text('x'*6000)
    (tmp_path/'nba_game_data_MEM_CHI.json').write_text(json.dumps({'meta':{'season_phase':'PRESEASON'},'players':{}}))
    odds={'player_props':{'points':{'Rookie':{'lines':{'15':'1.74'}}}}}
    with mock.patch.object(o,'_load_sportsbet_json',return_value=odds),mock.patch.object(o,'check_skeleton_exists',return_value=str(report)),mock.patch.object(o,'run_script',return_value=False) as run:
        assert not o.process_single_game('MEM_CHI','odds.json',str(tmp_path),'2026-10-10')
    assert run.call_args.args[0]==o.NBA_EXTRACTOR
