"""Observable context wiring and percentage-point/stat-unit boundaries."""
import copy
import sys
from pathlib import Path

import pytest

NBA=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(NBA));sys.path.insert(0,str(NBA/'nba_wong_choi/scripts'))
import nba_availability as a
import generate_nba_reports as r
import monte_carlo_nba as mc


def player(name,usg,status='Active',games=10):
    return {'name':name,'status':status,'advanced':{'USG_PCT':usg},'gamelog':{'games_played':games,'PTS':[20]*games,'MIN':[32]*games}}


def test_missing_history_is_not_an_injury_and_out_with_history_is_funding():
    missing=player('New Player',10,games=0)
    missing['gamelog']=None
    assert a.compute_usage_redistribution([missing,player('Starter',20)])=={}
    data=[player('Absent Star',30,'Out'),player('Starter',20),player('Other',10),player('Uncertain',25,'Questionable')]
    allocation=a.compute_usage_redistribution(data)
    assert set(allocation)=={'Starter','Other'}
    assert allocation['Starter']['bonus_USG']==20
    assert allocation['Other']['bonus_USG']==10
    assert allocation['Starter']['unit']=='percentage_points'


def test_fresh_injury_map_recomputes_bonus_and_recovery_removes_it():
    players={'BOS':[player('Absent Star',30),player('Starter',20)]}
    assert a.usage_from_injuries(players,{'BOS':{'Absent Star':'Out'}})['BOS']['Starter']['bonus_USG']==30
    assert a.usage_from_injuries(players,{'BOS':{}})=={}
    payload={'meta':{},'players':players,'usage_redistribution':{'BOS':{'Starter':{'bonus_USG':99}}}}
    updated=a.apply_availability(payload,{'BOS':{}})
    assert updated['usage_redistribution']=={} and payload['usage_redistribution']['BOS']['Starter']['bonus_USG']==99


def test_injury_bonus_name_matching_uses_full_normalized_identity():
    data={'DAL':{'Luka Dončić':{'bonus_USG':3}}}
    assert a.usage_bonus_for(data,'DAL','Luka Doncic')==3
    assert a.usage_bonus_for(data,'DAL','Doncic')==0


@pytest.mark.parametrize('category,expected',[('points',4),('threes_made',4),('rebounds',0),('assists',0)])
def test_usg_percentage_points_are_converted_to_relative_scoring_volume(category,expected):
    assert mc.usage_bonus_stat_units(20,category,25,5)==expected
    assert mc.usage_bonus_stat_units(20,category,None,5)==0
    assert mc.usage_bonus_stat_units(20,category,0,5)==0
    assert mc.usage_bonus_stat_units(20,category,90,20)==0
    assert mc.usage_bonus_stat_units(20,category,float('nan'),5)==0


def card(category='points',spread=0,usg=0,team_pace=100):
    ext=player('Starter',25)
    ext['gamelog'].update(PTS=[22,18,24,20,26,18,20,24,22,16],REB=[6,7,5,8,6,7,5,6,8,7],AST=[4,5,3,6,4,5,3,4,6,5],FG3M=[2,3,2,4,2,3,2,3,4,2])
    return r.build_player_card('Starter','BOS',{'lines':{'10':'1.8'}},ext,category,
        opponent_pace=104,spread=spread,usg_bonus=usg,team_stats={'BOS':{'PACE':team_pace}},engine_mode='legacy')


def test_team_pace_reaches_ten_factor_diagnostic_without_changing_c_formula():
    slow=card(team_pace=94);fast=card(team_pace=106)
    assert slow['line_analysis']['10']['adj_breakdown']['matchup_pace']==-1
    assert fast['line_analysis']['10']['adj_breakdown']['matchup_pace']==3
    # Default C reads only price/L10, preserving its approved coefficients.
    assert slow['line_analysis']['10']['estimated_prob']==fast['line_analysis']['10']['estimated_prob']


def test_usage_stat_bonus_reaches_both_marginal_and_joint_mc_context():
    made=card(usg=5)
    assert made['usg_bonus_pct']==5
    assert made['usg_bonus']==pytest.approx(made['avg']*.2)
    result=mc.compute_context_factors(made,usg_bonus=made['usg_bonus'])
    assert result['usg_bonus']==made['usg_bonus']
    for category in ('rebounds','assists'):
        assert card(category=category,usg=5)['usg_bonus']==0


def test_blowout_context_survives_candidate_flattening_and_changes_correlation():
    calm=card(spread=0);risky=card(spread=12)
    lc=r.build_leg_candidates([calm])[0];lr=r.build_leg_candidates([risky])[0]
    assert lr['adj_breakdown']['minutes_floor']==-2
    assert lc['estimated_prob']==lr['estimated_prob']
    other={**copy.deepcopy(lc),'player':'Another Starter','team':'LAL'}
    before=r.compute_combo_ev([lc,other]);after=r.compute_combo_ev([lr,other])
    assert after['correlation_penalty']==before['correlation_penalty']+.05
    assert after['adjusted_joint_prob']==pytest.approx(before['adjusted_joint_prob']*.95)


def test_usage_reaches_actual_marginal_and_joint_simulators(monkeypatch):
    first=card(usg=5);second=copy.deepcopy(first);second.update(name='Other Starter',team='LAL')
    cards=[first,second];legs=r.build_leg_candidates(cards)
    calls=[];real=mc.compute_context_factors
    def observe(card,**kwargs):
        calls.append(kwargs.get('usg_bonus'))
        return real(card,**kwargs)
    monkeypatch.setattr(mc,'compute_context_factors',observe)
    meta={'away':{'abbr':'BOS'},'home':{'abbr':'LAL'}}
    marginal=mc.run_monte_carlo_for_cards(cards,meta=meta,n=100,seed=7)
    joint=mc.simulate_sgm_joint({'1':legs},cards,meta=meta,n=100,seed=7)
    assert len(marginal)==2 and joint['1']['sim_status']=='ok'
    assert len(calls)==4 and all(value==first['usg_bonus'] for value in calls)
