"""Synthetic provenance, event grouping and training-only preprocessing tests."""
import copy
import csv
from datetime import datetime,timedelta,timezone
import json
import pickle
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
from sklearn.tree import DecisionTreeClassifier

REPO=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(REPO/'.agents/scripts/nba_ml'))
import build_nba_ml_dataset as builder
import train_nba_xgboost as trainer
from nba_ml_features import FEATURE_COLS,FEATURE_CONTRACT
from nba_ml_pit import sha
from nba_ml_predictor import MLPropPredictor


@pytest.fixture
def dataset(tmp_path):
    rows=[]
    for i in range(12):
        tip=datetime(2026,1,1,20,tzinfo=timezone.utc)+timedelta(days=i)
        capture=tip-timedelta(hours=1);home_ppg=10 if i==0 else (9999 if i>=9 else None)
        players={}
        for team,name,avg in [('BOS','First Star',20),('LAL','Second Star',5)]:
            players[team]=[{'name':name,'position':'G','advanced':{'USG_PCT':25},'splits':{'Home_PPG':home_ppg},
                'gamelog':{'PTS':[avg+v for v in (0,2,0,1,0,2,0,1,0,2)],'MIN':[32]*10,
                           'l10_dates':[(tip-timedelta(days=j)).date().isoformat() for j in range(1,11)]}}]
        payload={'meta':{'date':tip.isoformat(),'extracted_at':capture.isoformat(),
                         'away':{'abbr':'BOS'},'home':{'abbr':'LAL'}},'players':players,'injuries':{'BOS':{},'LAL':{}},
                 'team_stats':{'BOS':{'PACE':96,'DEF_RATING':110,'DEF_RANK':4},'LAL':{'PACE':104,'DEF_RATING':114,'DEF_RANK':20}}}
        folder=tmp_path/str(i);folder.mkdir()
        game=folder/'nba_game_data_BOS_LAL.json';game.write_text(json.dumps(payload))
        odds=folder/'Sportsbet_Odds_BOS_LAL.json';odds.write_text(json.dumps({'player_props':{'points':{
            name:{'lines':{'10':'1.8','20':'2.2','30':'3.4'}} for name in ('First Star','Second Star')}}}))
        source=folder/'synthetic_Final.json';source.write_text(json.dumps({'synthetic_test_only':True,'date':tip.date().isoformat()}))
        provenance={'game_modified_at':capture.isoformat(),'odds_modified_at':capture.isoformat(),'kind':'synthetic test fixture'}
        part=builder.extract_game_data(game,odds_path=odds,provenance=provenance)
        for row in part:
            actual=15 if row['player']=='First Star' else 25
            row.update(actual_value=actual,hit=int(actual>=row['line_value']),result_status='Final',
                       source_result_path=str(source),source_result_sha256=sha(source))
        rows.extend(part)
    path=tmp_path/'dataset.csv'
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return path


def test_temporal_folds_keep_events_together_and_imputer_never_sees_terminal(dataset,monkeypatch):
    X,y,features,context=trainer.load_and_prepare(dataset)
    assert features==FEATURE_COLS and X['home_ppg'].isna().any()
    monkeypatch.setattr(trainer,'_classifier',lambda y:DecisionTreeClassifier(max_depth=2,random_state=42))
    model,metrics,X_test,y_test,pred,prob=trainer.train_model(X,y,context)
    assert len(metrics['folds'])==5 and metrics['test_games']==3
    for fold in metrics['folds']:
        assert max(fold['train_dates'])<min(fold['validation_dates'])
        assert set(fold['train_dates']).isdisjoint(fold['validation_dates'])
        assert set(fold['validation_dates']).isdisjoint(metrics['terminal_diagnostic_dates'])
    assert max(metrics['dev_dates'])<min(metrics['terminal_diagnostic_dates'])
    assert model.named_steps['imputer'].statistics_[FEATURE_COLS.index('home_ppg')]==10
    assert model.named_steps['imputer'].statistics_[FEATURE_COLS.index('defender_pm')]==0
    assert metrics['deployment_eligible'] is False
    assert len(X_test)==18 and len(prob)==18


def test_csv_cannot_override_pre_tip_source_features(dataset):
    frame=pd.read_csv(dataset);frame.loc[0,'l10_avg']=999;frame.to_csv(dataset,index=False)
    with pytest.raises(ValueError,match='feature/source mismatch'):trainer.load_and_prepare(dataset)


def test_duplicate_event_or_nonfinal_or_unverified_rows_are_rejected(dataset):
    frame=pd.read_csv(dataset)
    for field,value,message in [('pit_status','unverified','unverified'),('result_status','TBD','non-Final')]:
        changed=frame.copy();changed.loc[0,field]=value;changed.to_csv(dataset,index=False)
        with pytest.raises(ValueError,match=message):trainer.load_and_prepare(dataset)
    pd.concat([frame,frame.iloc[[0]]],ignore_index=True).to_csv(dataset,index=False)
    with pytest.raises(ValueError,match='duplicate'):trainer.load_and_prepare(dataset)


def test_source_changes_invalidate_dataset(dataset):
    frame=pd.read_csv(dataset);source=Path(frame.iloc[0]['source_result_path']);source.write_text('changed')
    with pytest.raises(ValueError,match='result source hash'):trainer.load_and_prepare(dataset)


def test_unversioned_old_dataset_never_reproduces_random_row_metrics(tmp_path):
    path=tmp_path/'old.csv';pd.DataFrame({'hit':[1,0],'l10_avg':[20,10]}).to_csv(path,index=False)
    with pytest.raises(ValueError,match='unverified legacy'):trainer.load_and_prepare(path)


def test_v2_serving_uses_same_fitted_imputer_and_numeric_batch_handling(dataset,tmp_path,monkeypatch):
    X,y,_,context=trainer.load_and_prepare(dataset)
    monkeypatch.setattr(trainer,'_classifier',lambda y:DecisionTreeClassifier(max_depth=2,random_state=42))
    model,*_=trainer.train_model(X,y,context)
    folder=tmp_path/'candidate';folder.mkdir()
    (folder/'model.pkl').write_bytes(pickle.dumps(model))
    (folder/'feature_names.json').write_text(json.dumps({'features':FEATURE_COLS,'feature_contract':FEATURE_CONTRACT,'deployment_eligible':False,
        'model_sha256':sha(folder/'model.pkl'),'feature_constructor_sha256':sha(REPO/'.agents/scripts/nba_ml/nba_ml_features.py')}))
    predictor=MLPropPredictor(folder)
    row=X.iloc[1].to_dict();row['home_ppg']=None
    expected=round(float(model.predict_proba(pd.DataFrame([row])[FEATURE_COLS])[0,1]),4)
    assert predictor.predict(row)==expected
    row['home_ppg']='N/A'
    assert predictor.predict_batch([row])==[expected] and predictor.predict_batch([])==[]
    assert predictor.deployment_eligible is False


@pytest.mark.parametrize('minutes,expected',[('0:30',.5),('PT0M30.0S',.5),('12:30',12.5),('DNP',0),('',0),(None,0)])
def test_dnp_is_distinct_from_subminute_play(minutes,expected):
    assert builder.parse_minutes(minutes)==expected


def test_finality_and_exact_us_date_team_identity_control_labels(tmp_path):
    path=tmp_path/'results.json'
    game={'status':'Final','away':{'team':'BOS','score':10},'home':{'team':'LAL','score':15},
          'players':[{'name':'First Star','team':'BOS','minutes':'0:30','pts':10},
                     {'name':'Second Star','team':'LAL','minutes':'32','pts':15}]}
    payload={'date':'2026-01-01','games':[game]};path.write_text(json.dumps(payload))
    lookup=builder.load_results_brief(path)
    row={'game_tag':'BOS_LAL','game_date':'2026-01-01','team':'BOS','player':'First Star','stat_category':'PTS','line_value':5,'hit':None}
    assert builder.match_results([copy.deepcopy(row)],lookup)[0]['hit']==1
    wrong={**row,'game_date':'2026-01-02'}
    assert builder.match_results([wrong],lookup)[0]['hit'] is None
    rebound={**row,'stat_category':'REB'}
    assert builder.match_results([rebound],lookup)[0]['hit'] is None  # absent value is not zero
    game['status']='Not Final';path.write_text(json.dumps(payload))
    assert builder.load_results_brief(path)=={}
    game['status']='Final';game['away']['score']=0;path.write_text(json.dumps(payload))
    assert builder.load_results_brief(path)=={}  # stale scores cannot validate later box scores


def test_archive_builder_labels_each_us_day_and_deduplicates_earliest_capture(tmp_path,monkeypatch):
    folder=tmp_path/'mixed_sydney_folder';folder.mkdir();output=tmp_path/'output'
    files=[]
    for index,(day,hour) in enumerate([(3,18),(3,19),(4,18)]):
        tip=datetime(2026,1,day,20,tzinfo=timezone.utc)
        payload={'meta':{'date':tip.isoformat(),'extracted_at':tip.replace(hour=hour).isoformat(),
                         'away':{'abbr':'BOS'},'home':{'abbr':'LAL'}},
                 'players':{team:[{'name':name,'gamelog':{'PTS':[20]*10,'MIN':[32]*10,
                     'l10_dates':[(tip-timedelta(days=d)).date().isoformat() for d in range(1,11)]}}]
                            for team,name in [('BOS','First Star'),('LAL','Second Star')]},'injuries':{'BOS':{},'LAL':{}}}
        path=folder/f'Game_{index}_data.json';path.write_text(json.dumps(payload));files.append(path.name)
    requested=[]
    def fetch(day):
        requested.append(day);value=10 if day=='2026-01-03' else 30
        path=tmp_path/(day+'.json');path.write_text(json.dumps({'date':day,'games':[{
            'status':'Final','away':{'team':'BOS','score':value},'home':{'team':'LAL','score':value},
            'players':[{'name':name,'team':team,'pts':value,'minutes':'32'} for team,name in [('BOS','First Star'),('LAL','Second Star')]]}]}))
        return str(path)
    monkeypatch.setattr(builder,'DATASET_DIR',str(output));monkeypatch.setattr(builder,'fetch_results_for_date',fetch)
    rows,stats=builder.build_consolidated_dataset([('mixed',str(folder),files)])
    assert requested==['2026-01-03','2026-01-04']
    assert stats['duplicate_rows_resolved_earliest']==14 and len(rows)==28
    assert {row['actual_value'] for row in rows if row['game_date']=='2026-01-03'}=={10}
    assert {row['actual_value'] for row in rows if row['game_date']=='2026-01-04'}=={30}
    assert all('Game_1_data.json' not in row['source_game_path'] for row in rows)


def test_point_in_time_rejects_target_game_future_capture_and_naive_tip(dataset):
    from nba_ml_pit import validate_capture
    first=pd.read_csv(dataset).iloc[0];path=Path(first.source_game_path);odds=Path(first.source_odds_path)
    original=json.loads(path.read_text());provenance=json.loads(first.source_provenance)
    assert validate_capture(original,path,odds,provenance)['pit_status']=='verified'
    changed=copy.deepcopy(original)
    changed['players']['BOS'][0]['gamelog']['l10_dates'][0]=first.game_date
    assert 'target_or_future_game_in_history' in validate_capture(changed,path,odds,provenance)['pit_flags']
    changed=copy.deepcopy(original);changed['meta']['extracted_at']=changed['meta']['date']
    assert validate_capture(changed,path,odds,provenance)['pit_status']=='unverified'
    changed=copy.deepcopy(original);changed['meta']['date']='2026-01-01T20:00:00'
    assert validate_capture(changed,path,odds,provenance)['pit_status']=='unverified'


def test_default_builder_accepts_only_hash_matched_pre_tip_snapshot(dataset):
    from nba_ml_pit import validate_capture
    first=pd.read_csv(dataset).iloc[0];game=Path(first.source_game_path);odds=Path(first.source_odds_path)
    payload=json.loads(game.read_text());folder=game.parent/'_prediction_snapshots'/'test_snapshot';folder.mkdir(parents=True)
    manifest={'sport':'nba','created_at':payload['meta']['extracted_at'],'files':[
        {'name':game.name,'sha256':sha(game)},{'name':odds.name,'sha256':sha(odds)}]}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    assert validate_capture(payload,game,odds)['pit_status']=='verified'
    odds.write_text(odds.read_text()+' ')
    assert validate_capture(payload,game,odds)['pit_status']=='unverified'


def test_capture_order_uses_evidenced_market_time_and_actual_utc_offset():
    from nba_ml_pit import capture_order
    earlier={'pit_status':'verified','captured_at':'2026-05-04T00:00:00+10:00','source_game_path':'a',
             'source_provenance':json.dumps({'odds_modified_at':'2026-05-03T14:00:00Z'})}
    later={'pit_status':'verified','captured_at':'2026-05-03T19:00:00Z','source_game_path':'b',
           'source_provenance':json.dumps({'odds_modified_at':'2026-05-03T19:00:00Z'})}
    assert capture_order(earlier)<capture_order(later)  # lexical ISO order would reverse it
    later['source_provenance']=json.dumps({'odds_modified_at':'2026-05-03T13:00:00Z'})
    assert capture_order(later)<capture_order(earlier)  # earliest market, not freshest features
