"""Post-training backtest boundary, delivered separately from serving changes."""
import json
import pickle
import pandas as pd
import pytest
from sklearn.tree import DecisionTreeClassifier
from test_nba_ml_temporal_contract import dataset as fixture_dataset, trainer, sha, FEATURE_COLS, FEATURE_CONTRACT, REPO

dataset = fixture_dataset


def test_backtest_excludes_training_dates_and_reproduces_historical_terminal(dataset,tmp_path,monkeypatch):
    from backtest_nba_ml import evaluate_dataset
    X,y,_,context=trainer.load_and_prepare(dataset)
    monkeypatch.setattr(trainer,'_classifier',lambda y:DecisionTreeClassifier(max_depth=2,random_state=42))
    model,metrics,*_=trainer.train_model(X,y,context)
    folder=tmp_path/'model_for_backtest';folder.mkdir();model_path=folder/'model.pkl';model_path.write_bytes(pickle.dumps(model))
    metrics['model_sha256']=sha(model_path)
    (folder/'metrics.json').write_text(json.dumps(metrics))
    metadata={'features':FEATURE_COLS,'feature_contract':FEATURE_CONTRACT,'deployment_eligible':False,
              'model_sha256':sha(model_path),'feature_constructor_sha256':sha(REPO/'.agents/scripts/nba_ml/nba_ml_features.py'),
              'training_protocol':metrics['training_protocol'],'training_end_date':max(metrics['dev_dates'])}
    (folder/'feature_names.json').write_text(json.dumps(metadata))
    report=evaluate_dataset(dataset,folder,tmp_path/'backtest')
    assert report['rows']==18 and report['excluded_in_sample_rows']==54
    assert report['evaluation_status']=='historical_terminal_reproduction' and report['promotion_authorized'] is False
    assert min(report['dates'])>report['training_end_date']
    frame=pd.read_csv(dataset);frame=frame[frame.game_date.isin(metrics['dev_dates'])];frame.to_csv(dataset,index=False)
    with pytest.raises(ValueError,match='no post-training events'):evaluate_dataset(dataset,folder,tmp_path/'invalid_backtest')
