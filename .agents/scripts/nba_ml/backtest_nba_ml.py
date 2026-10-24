#!/usr/bin/env python3
"""Evaluate a v2 NBA artifact strictly after its last training date.

Uses the same verified priced dataset and persisted preprocessing as training.
Legacy artifacts with unknown training dates cannot claim out-of-sample metrics.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from nba_ml_predictor import MLPropPredictor
from nba_ml_features import FEATURE_CONTRACT
from nba_ml_pit import sha
from train_nba_xgboost import load_and_prepare,_metrics,terminal_comparisons


def evaluate_dataset(dataset,model_dir,output_dir):
    model_dir,output_dir=Path(model_dir),Path(output_dir)
    predictor=MLPropPredictor(model_dir)
    metadata=json.loads((model_dir/'feature_names.json').read_text())
    metrics=json.loads((model_dir/'metrics.json').read_text())
    if (predictor.feature_contract!=FEATURE_CONTRACT or metadata.get('training_protocol')!='chronological_whole_date_v2'
            or metrics.get('model_sha256')!=sha(model_dir/'model.pkl') or not metrics.get('dev_dates')):
        raise ValueError('artifact has no verifiable temporal training boundary')
    cutoff=max(metrics['dev_dates'])
    if metadata.get('training_end_date')!=cutoff:raise ValueError('inconsistent training cutoff')
    X,y,_,context=load_and_prepare(dataset)
    future=context.index[context.game_date>cutoff]
    if future.empty:raise ValueError('no post-training events; refusing in-sample backtest')
    # The saved historical terminal diagnostic has already been inspected. It
    # can be reproduced, but cannot be relabelled a new confirmatory holdout.
    historical=set(metrics.get('terminal_diagnostic_dates') or [])
    inspected=context.loc[future,'game_date'].isin(historical).any()
    probability=predictor.model.predict_proba(X.loc[future])[:,1]
    report={'model_sha256':sha(model_dir/'model.pkl'),'dataset_sha256':sha(dataset),'training_end_date':cutoff,
            'excluded_in_sample_rows':len(context)-len(future),'rows':len(future),
            'dates':sorted(context.loc[future,'game_date'].unique()),
            'evaluation_status':'historical_terminal_reproduction' if inspected else 'post_training_diagnostic',
            'promotion_authorized':False,'metrics':_metrics(y.loc[future],probability),
            'comparisons':terminal_comparisons(y.loc[future],probability,X.loc[future],context.loc[future])}
    output_dir.mkdir(parents=True,exist_ok=False)
    (output_dir/'backtest_results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    comparison=context.loc[future].copy();comparison['hit']=y.loc[future];comparison['p_ml']=probability
    comparison.to_csv(output_dir/'backtest_comparison.csv',index=False)
    print(json.dumps(report,indent=2,allow_nan=False))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',required=True);parser.add_argument('--model-dir',required=True);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();evaluate_dataset(args.dataset,args.model_dir,args.output_dir)


if __name__=='__main__':main()
