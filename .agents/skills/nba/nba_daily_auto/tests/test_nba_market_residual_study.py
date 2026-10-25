"""Research-only dynamic features, train-only transforms and spent-window exclusion."""
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO/'.agents/scripts/nba_ml'))
from nba_market_residual import trend_features, ResidualLogit, game_unit_weights, run_study


def player(cutoff='2026-10-25'):
    day = date.fromisoformat(cutoff)
    return {'gamelog': {'l10_dates': [(day-timedelta(days=i)).isoformat() for i in range(1, 11)],
                        'MIN': [30]*3+[20]*7, 'PTS': [9]*3+[4]*7}}


def test_features_use_aligned_past_minutes_and_production():
    p = player();before = deepcopy(p);f = trend_features(p, 'PTS', '2026-10-25')
    assert f['status'] == 'ok'
    assert f['minutes_trend'] == pytest.approx(30/23-1)
    assert f['rate_trend'] == pytest.approx(.3/(55/230)-1)
    p['actual_value'] = 999;p['projected_today_minutes'] = 48
    assert f == trend_features(p, 'PTS', '2026-10-25')
    assert before['gamelog'] == p['gamelog']


@pytest.mark.parametrize('case,status',[('short','short_history'),('length','unaligned_history'),
    ('future','unsafe_history_dates'),('order','unsafe_history_dates'),('boolean','invalid_history_numbers'),
    ('negative','invalid_history_numbers'),('zero_min','inconsistent_zero_minutes'),('zero_stat','zero_denominator')])
def test_unsafe_or_missing_history_stays_missing(case,status):
    p = player();gl = p['gamelog']
    if case == 'short':
        for name in gl:gl[name] = gl[name][:4]
    elif case == 'length':gl['MIN'].pop()
    elif case == 'future':gl['l10_dates'][0] = '2026-10-25'
    elif case == 'order':gl['l10_dates'][0],gl['l10_dates'][1] = gl['l10_dates'][1],gl['l10_dates'][0]
    elif case == 'boolean':gl['MIN'][0] = True
    elif case == 'negative':gl['PTS'][0] = -1
    elif case == 'zero_min':gl['MIN'][0] = 0
    elif case == 'zero_stat':gl['PTS'] = [0]*10
    result = trend_features(p,'PTS','2026-10-25')
    assert result == {'minutes_trend':None,'rate_trend':None,'status':status}


def test_only_prior_ten_enter_trends():
    p = player();expected = trend_features(p,'PTS','2026-10-25')
    p['gamelog']['MIN'].append(100);p['gamelog']['PTS'].append(100)
    p['gamelog']['l10_dates'].append('2026-10-14')
    assert trend_features(p,'PTS','2026-10-25') == expected


def frame():
    return pd.DataFrame([{'game_group':f'g{i//4}','player_key':f'p{i%2}','stat_category':'PTS',
                          'line_value':4+i%2,'market_price':1.5+i%4*.2,'hit_rate_l10':50+i%4*10,
                          'minutes_trend':i/20,'rate_trend':(i%3)/4,'game_date':f'2026-01-{i//4+1:02d}'}
                         for i in range(24)])


def test_training_weights_give_each_game_and_player_stat_unit_equal_weight():
    f = frame();f = pd.concat([f,f.iloc[[0]]],ignore_index=True)
    w = pd.Series(game_unit_weights(f),index=f.index)
    assert np.allclose(w.groupby(f.game_group).sum(),1)
    for game in f.game_group.unique():
        mask = f.game_group == game
        assert np.allclose(w[mask].groupby(f.loc[mask,'player_key']).sum(),.5)


def test_scaling_fits_train_only_and_predictions_do_not_mutate_it():
    f = frame();y = np.array([0,1,1,0]*6)
    a = ResidualLogit(('minutes_trend','rate_trend')).fit(f,y)
    saved = deepcopy(a.metadata());future = f.iloc[:3].copy();future['minutes_trend'] = 1000
    a.predict(future)
    assert a.metadata() == saved
    b = ResidualLogit(('minutes_trend','rate_trend')).fit(f,y)
    assert np.allclose(a.predict(f),b.predict(f),rtol=0,atol=1e-12)
    assert a.scaler['minutes_trend']['mean'] == pytest.approx(f.minutes_trend.mean())
    assert not a.metadata()['deployment_eligible']


def test_dead_feature_and_nonfinite_input_are_explicit():
    f = frame();f['minutes_trend'] = 0
    a = ResidualLogit(('minutes_trend',)).fit(f,np.array([0,1,1,0]*6))
    assert a.scaler['minutes_trend']['sd'] == 0
    assert np.all(a.design(f)[:,-1] == 0)
    f.loc[0,'minutes_trend'] = np.nan
    with pytest.raises(ValueError,match='nonfinite'):a.predict(f)


def test_cli_research_routes_before_default_model_writes(monkeypatch,tmp_path):
    import train_nba_xgboost as trainer
    import nba_market_residual as residual
    called=[]
    monkeypatch.setattr(residual,'run_study',lambda *args:called.append(args))
    destination=tmp_path/'isolated'
    monkeypatch.setattr(sys,'argv',['trainer','--residual-study','--dataset','input.csv','--output-dir',str(destination)])
    trainer.main()
    assert called == [('input.csv',str(destination))]
    assert not destination.exists()


def test_study_excludes_spent_terminal_and_every_fold_is_prequential(monkeypatch,tmp_path):
    import train_nba_xgboost as trainer
    rows=[]
    for day in range(1,25):
        when=f'2026-01-{day:02d}';p=player(when);p['gamelog']['MIN'][0]+=day
        source=tmp_path/f'{day}.json';source.write_text(json.dumps({'players':{'GS':[dict(p,name='Stephen Curry')]}}))
        for line,hit in [(4,1),(12,0)]:
            rows.append({'game_date':when,'game_group':f'g{day}','player_key':'stephen curry','team':'GSW',
                         'stat_category':'PTS','line_value':line,'market_price':1.5 if hit else 3.0,
                         'hit_rate_l10':90 if hit else 20,'hit':hit,'source_game_path':str(source)})
    f=pd.DataFrame(rows);path=tmp_path/'data.csv';f.to_csv(path,index=False)
    monkeypatch.setattr(trainer,'load_and_prepare',lambda path:(pd.DataFrame(index=f.index),f.hit,[],f))
    result=run_study(path,tmp_path/'output')
    assert result['excluded_spent_terminal_dates']==[f'2026-01-{n:02d}' for n in range(20,25)]
    assert result['oos_dates']==15 and not result['promotion_allowed']
    for fold in result['folds']:assert max(fold['train_dates']) < min(fold['validation_dates'])
    predicted=pd.read_csv(tmp_path/'output/oos_predictions.csv')
    assert not set(predicted.game_date) & set(result['excluded_spent_terminal_dates'])
    assert not (tmp_path/'output/model.pkl').exists()
