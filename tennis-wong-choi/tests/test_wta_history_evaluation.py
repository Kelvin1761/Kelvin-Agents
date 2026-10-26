"""Count-weighted scores must retain both players in the same match cluster."""
import importlib.util
from pathlib import Path

import pytest
import test_wta_history_overlay as overlay_tests

wta_db = overlay_tests.db


spec = importlib.util.spec_from_file_location(
    "wta_study", Path(__file__).parents[1]/"scripts"/"evaluate_wta_history.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_binomial_score_matches_individual_service_games():
    brier, loss = study.binomial_losses(.8, 8, 10)
    assert brier/10 == pytest.approx(.16)
    import math
    assert loss == pytest.approx(-8*math.log(.8)-2*math.log(.2))


def test_bootstrap_clusters_sides_and_preserves_exposure_weights():
    rows = []
    for cluster, exposure in ((1,10),(1,5),(2,20)):
        rows.append({'cluster':cluster,'exposure':exposure,
                     'losses':{arm:study.binomial_losses(.5,exposure,exposure)
                               for arm in study.ARMS}})
    result=study.paired_summary(rows)
    assert result['observations']==3
    assert result['matches']==2
    assert result['exposure']==35
    assert result['arms']['A0']['brier']==.25
    assert result['arms']['A1']['brier_delta_A0_ci95']==[0,0]
    market=study.paired_summary(rows,reference='A1')
    assert market['arms']['A0']['brier_delta_A1_ci95']==[0,0]


def test_unknown_surface_remains_in_the_reported_cohort():
    row={'cluster':1,'date':'2026-08-01','surface':None,'exposure':1,
         'losses':{arm:(.25,.69) for arm in study.ARMS}}
    assert study.stratified([row])['surface']['unknown']['observations']==1


def test_prop_replay_uses_first_feed_quote_and_actual_recorded_side(wta_db, monkeypatch):
    from tennis_wc.props.settlement import record_prop
    from tennis_wc.research.wta_history import WtaHistoryOverlay

    db=wta_db

    db.execute("INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,"
               "round,source_provider,created_at,updated_at,start_time_utc) VALUES "
               "(1,'M','WTA','2026-06-10',1,1,2,'R1','test','now','now','2026-06-10T12:00:00Z')")
    record_prop(db, match_id=1, match_date='2026-06-10', match_label='Ana vs Bea',
                market_key='player_total_games_1_10.5', line=10.5,selection='Ana Over 10.5',
                side='over',prop_scope='player_games',subject_player_id=1,decimal_odds=4,
                model_prob=.8,model_prob_raw=.8,market_prob_fair=.99,blended_prob=.8,
                edge=.1,ev=.1,predicted_mean=12,stake_units=1,is_value=True,
                feed_market_key='total',feed_market_name='Ana Games',
                feed_selection_name='Over 10.5',feed_line=10.5)
    db.execute("UPDATE prop_tracker SET result_status='WON',is_point_in_time=1")
    for stamp,over,under in [('2026-06-09T09:00:00Z',1.8,2.2),('2026-06-11T09:00:00Z',4,1.2)]:
        for side,odds in [('Over',over),('Under',under)]:
            db.execute("INSERT INTO market_odds_snapshots (event_id,match_id,bookmaker,market_key,"
                       "market_name,selection_name,line,odds,source_provider,raw_response_id,fetched_at,created_at) "
                       "VALUES ('e',1,'test','total','Ana Games',?,10.5,?,'test',0,?,?)",
                       (side+' 10.5',odds,stamp,stamp))

    class FakeDistribution:
        def player_games_over(self,*args):
            return .6

    monkeypatch.setattr(study,'distribution',lambda *args:FakeDistribution())
    original_profiles=study.profiles
    forecast_cutoffs=[]

    def capture_profiles(conn,overlay,a,b,day,surface,start):
        forecast_cutoffs.append((day,start))
        return original_profiles(conn,overlay,a,b,day,surface,start)

    monkeypatch.setattr(study,'profiles',capture_profiles)
    result=study.prop_study(db,WtaHistoryOverlay(db))
    assert forecast_cutoffs==[('2026-06-09','2026-06-09T09:00:00Z')]
    assert result['paired']['all']['observations']==1
    assert result['paired']['all']['arms']['A0']['brier']==pytest.approx(.16)
    assert result['market_and_secondary_roi']['all']['market_brier']==pytest.approx((1-.55)**2)
    records=study.prop_study(db,None,all_tours=True,records_only=True,
                            profile_provider=lambda conn,o,a,b,day,surface,start:{
                                arm:[study.baseline_profile(conn,pid,day,surface,start) for pid in (a,b)]
                                for arm in study.ARMS})
    assert records['records'][0]['contract']==(1,'player_games',1,10.5)
    assert records['records'][0]['quote_id']==1
    db.execute("UPDATE matches SET tour='ATP',tournament_id=7,round='R128'")
    db.execute("INSERT INTO tournament_levels (tournament_id,tour,level,source_provider,raw_response_id,"
               "created_at,updated_at) VALUES (7,'ATP','GRAND_SLAM','test',0,'now','now')")
    guarded=study.prop_study(db,None,all_tours=True,records_only=True,
                             profile_provider=lambda *args:pytest.fail('BO5 profile lookup reached'))
    assert guarded['records']==[]
    assert guarded['coverage']['unsupported_format']==1
