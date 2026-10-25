#!/usr/bin/env python3
"""Chronological NBA ML diagnostic trainer (legacy CLI filename).

Requires a verified v2 priced dataset. Folds and terminal diagnostics use whole
US game dates; each Pipeline persists training-only median imputation. No
terminal early stopping, full-data refit, parameter search or live promotion.

Example: --dataset <verified dataset.csv> --output-dir <new candidate dir> --skip-shap
"""

import os
import sys
import json
import argparse
import io
import warnings
warnings.filterwarnings('ignore')

if __name__ == '__main__' and sys.stdout.encoding != 'utf-8' and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path as _Path
PROJECT_ROOT = _Path(__file__).resolve().parents[3]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import NBA_ML_DATASET

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             roc_auc_score, brier_score_loss, log_loss)
from nba_ml_features import FEATURE_COLS, FEATURE_CONTRACT

# Try XGBoost first (needs libomp on macOS), fallback to RandomForest
USE_XGBOOST = False
try:
    import xgboost as xgb
    # Quick check that it loads
    _ = xgb.XGBClassifier(n_estimators=2)
    USE_XGBOOST = True
except Exception:
    pass

if not USE_XGBOOST:
    from sklearn.ensemble import RandomForestClassifier
    print("⚠️ XGBoost not available (needs libomp), using RandomForest instead")

HAS_SHAP = False
try:
    import shap
    HAS_SHAP = True
except ImportError:
    print("⚠️ SHAP not installed (pip install shap) — skipping SHAP analysis")

DATASET_PATH = str(NBA_ML_DATASET / "dataset.csv")
DEFAULT_OUTPUT = str(NBA_ML_DATASET / "models" / "v1")

def load_and_prepare(path):
    """Validate v2 provenance; never fit an imputer/encoder on the whole pool."""
    from nba_ml_features import FEATURE_CONTRACT, FEATURE_COLS
    from nba_ml_pit import sha, validate_capture
    from build_nba_ml_dataset import extract_game_data
    from pathlib import Path
    df=pd.read_csv(path)
    labeled=df[df['hit'].notna()].copy()
    required=set(FEATURE_COLS)|{'feature_contract','population','game_date','game_group','player_key',
        'stat_category','line_value','actual_value','pit_status','result_status','event_start','captured_at',
        'source_game_path','source_game_sha256','source_odds_path','source_odds_sha256',
        'source_result_path','source_result_sha256','source_provenance','market_price'}
    if required-set(labeled):raise ValueError('unverified legacy dataset: rebuild v2 from pre-tip priced sources')
    if labeled.empty:raise ValueError('no verified labeled rows')
    if not ((labeled['feature_contract']==FEATURE_CONTRACT)&(labeled['population']=='priced_milestone')
            &(labeled['pit_status']=='verified')&(labeled['result_status']=='Final')).all():
        raise ValueError('mixed, unverified, template or non-Final training rows')
    if not labeled['game_date'].astype(str).str.fullmatch(r'\d{4}-\d{2}-\d{2}').all():raise ValueError('invalid US game date')
    pd.to_datetime(labeled['game_date'],format='%Y-%m-%d',errors='raise')
    if (labeled.groupby('game_group')['game_date'].nunique()!=1).any():raise ValueError('event spans multiple game dates')
    key=['game_group','player_key','stat_category','line_value']
    if labeled.duplicated(key).any():raise ValueError('duplicate player/stat/line events; resolve earliest verified capture before training')
    y=pd.to_numeric(labeled['hit'],errors='raise').astype(float)
    actual=pd.to_numeric(labeled['actual_value'],errors='raise')
    threshold=pd.to_numeric(labeled['line_value'],errors='raise')
    if (not y.isin([0,1]).all() or not np.isfinite(actual).all() or (actual<0).any()
            or not (y==(actual>=threshold).astype(int)).all()):raise ValueError('invalid or inconsistent labels')
    # Reconstruct the numeric matrix from the hash-matched pre-tip artifacts.
    # This also prevents a CSV edit from introducing a future/current-game stat.
    for (_,_,provenance_text),group in labeled.groupby(['source_game_path','source_odds_path','source_provenance'],dropna=False):
        first=group.iloc[0]
        game_path,odds_path=Path(first['source_game_path']),Path(first['source_odds_path'])
        if sha(game_path)!=first['source_game_sha256'] or sha(odds_path)!=first['source_odds_sha256']:
            raise ValueError('source input hash mismatch')
        provenance=json.loads(provenance_text)
        evidence=validate_capture(json.loads(game_path.read_text()),game_path,odds_path,provenance)
        if evidence['pit_status']!='verified' or not (group['game_date']==evidence['game_date']).all():
            raise ValueError('source capture is not point-in-time safe')
        rebuilt=extract_game_data(game_path,odds_path=odds_path,provenance=provenance)
        expected={(row['player_key'],row['stat_category'],row['line_value']):row for row in rebuilt}
        for _,row in group.iterrows():
            source=expected.get((row['player_key'],row['stat_category'],row['line_value']))
            if source is None:raise ValueError('priced row not present in source artifacts')
            for feature in [*FEATURE_COLS,"market_price"]:
                left,right=row[feature],source[feature]
                if pd.isna(left) and right is None:continue
                if right is None or pd.isna(left) or not np.isclose(float(left),float(right),rtol=0,atol=1e-9):
                    raise ValueError(f'feature/source mismatch: {feature}')
    for (source,digest),_ in labeled.groupby(['source_result_path','source_result_sha256'],dropna=False):
        if not isinstance(source,str) or sha(source)!=digest:raise ValueError('result source hash mismatch')
    X=labeled[FEATURE_COLS].apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
    context=labeled[['game_date','game_group','stat_category','market_price']].copy()
    context['market_price']=pd.to_numeric(context['market_price'],errors='raise')
    if not np.isfinite(context['market_price']).all() or (context['market_price']<=1).any():raise ValueError('invalid market prices')
    context['dataset_sha256']=sha(path)
    print(f'Verified priced rows: {len(X)}; games: {context.game_group.nunique()}; dates: {context.game_date.nunique()}')
    return X,y.astype(int),list(FEATURE_COLS),context


def _classifier(y):
    if len(set(y))!=2:raise ValueError('training window needs both outcome classes')
    if USE_XGBOOST:
        return xgb.XGBClassifier(n_estimators=300,max_depth=5,learning_rate=.05,subsample=.8,colsample_bytree=.8,
            scale_pos_weight=float((y==0).sum()/(y==1).sum()),eval_metric='logloss',random_state=42,n_jobs=2,verbosity=0)
    return RandomForestClassifier(n_estimators=300,max_depth=10,min_samples_leaf=5,
        class_weight='balanced_subsample',random_state=42,n_jobs=2,verbose=0)


def _pipeline(y):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    return Pipeline([('imputer',SimpleImputer(strategy='median',keep_empty_features=True)),('classifier',_classifier(y))])


def _metrics(y,prob):
    pred=(np.asarray(prob)>=.5).astype(int)
    return {'accuracy':float(accuracy_score(y,pred)),'precision':float(precision_score(y,pred,zero_division=0)),
        'recall':float(recall_score(y,pred,zero_division=0)),'f1':float(f1_score(y,pred,zero_division=0)),
        'roc_auc':float(roc_auc_score(y,prob)) if len(set(y))==2 else None,
        'brier_score':float(brier_score_loss(y,prob)),
        'log_loss':float(log_loss(y,np.clip(prob,1e-12,1-1e-12),labels=[0,1]))}


def terminal_comparisons(y,prob,X,context):
    """Fixed paired date-cluster diagnostics; historical C is not independent."""
    _sys.path.insert(0,str(PROJECT_ROOT/'.agents/skills/nba/nba_wong_choi/scripts'))
    import nba_prob_layer
    market=1/context['market_price'].to_numpy(dtype=float)
    raw=X['hit_rate_l10'].to_numpy(dtype=float)/100
    calibrated=np.asarray([nba_prob_layer.calibrated_prob(stat,price,hit)/100
        for stat,price,hit in zip(context.stat_category,context.market_price,X.hit_rate_l10)],dtype=float)
    result={}
    target=np.asarray(y);days=np.asarray(context.game_date);unique=sorted(set(days))
    indices=[np.flatnonzero(days==day) for day in unique]
    rng=np.random.default_rng(20261023)
    draws=[np.concatenate([indices[i] for i in rng.integers(0,len(indices),size=len(indices))]) for _ in range(2000)]
    for name,other in {'raw_l10':raw,'market_raw_vig_inclusive':market,'current_C_historical_fit':calibrated}.items():
        if not np.isfinite(other).all():raise ValueError('comparator missing')
        difference=(prob-target)**2-(other-target)**2
        interval=np.percentile([difference[index].mean() for index in draws],[2.5,97.5])
        result[name]={'metrics':_metrics(y,other),'paired_brier_delta_model_minus_comparator':float(difference.mean()),
                      'paired_date_bootstrap_95':interval.tolist(),'date_clusters':len(unique),'replicates':2000,'seed':20261023}
    result['current_C_historical_fit']['probability_model_id']=nba_prob_layer.probability_model_id()
    return result


def train_model(X,y,context):
    """Fixed chronological terminal diagnostic and expanding date folds.

    No row shuffle, cross-event splitting, whole-pool imputation, hyperparameter
    search, terminal early-stopping or all-data refit is permitted here.
    """
    from sklearn.model_selection import TimeSeriesSplit
    import math
    dates=sorted(context['game_date'].unique())
    if len(dates)<10:raise ValueError('need at least 10 distinct verified dates for the fixed temporal protocol')
    terminal_n=math.ceil(len(dates)*.2)
    dev_dates,terminal_dates=dates[:-terminal_n],dates[-terminal_n:]
    train_index=context.index[context.game_date.isin(dev_dates)]
    test_index=context.index[context.game_date.isin(terminal_dates)]
    X_train,X_test=X.loc[train_index],X.loc[test_index];y_train,y_test=y.loc[train_index],y.loc[test_index]
    folds=[]
    for fold,(date_train,date_valid) in enumerate(TimeSeriesSplit(n_splits=5).split(dev_dates),1):
        train_days=[dev_dates[i] for i in date_train];valid_days=[dev_dates[i] for i in date_valid]
        ti=context.index[context.game_date.isin(train_days)];vi=context.index[context.game_date.isin(valid_days)]
        if set(context.loc[ti,'game_group'])&set(context.loc[vi,'game_group']):raise AssertionError('event leakage')
        model=_pipeline(y.loc[ti]);model.fit(X.loc[ti],y.loc[ti]);prob=model.predict_proba(X.loc[vi])[:,1]
        folds.append({'fold':fold,'train_dates':train_days,'validation_dates':valid_days,
                      'train_size':len(ti),'validation_size':len(vi),**_metrics(y.loc[vi],prob)})
    model=_pipeline(y_train);model.fit(X_train,y_train)
    prob=model.predict_proba(X_test)[:,1];pred=(prob>=.5).astype(int)
    metrics={**_metrics(y_test,prob),'train_size':len(train_index),'test_size':len(test_index),
        'training_protocol':'chronological_whole_date_v2','dev_dates':dev_dates,'terminal_diagnostic_dates':terminal_dates,
        'folds':folds,'dataset_sha256':context['dataset_sha256'].iloc[0],
        'feature_preprocessing':'persisted training-window median imputer; all-empty training features use 0',
        'terminal_status':'historical diagnostic, previously inspected corpus; not a fresh confirmatory holdout',
        'deployment_eligible':False,'deployment_reason':'new forward evidence and controlled promotion required',
        'population':context.groupby('stat_category').size().to_dict(),
        'terminal_population':context.loc[test_index].groupby('stat_category').size().to_dict(),
        'train_games':int(context.loc[train_index,'game_group'].nunique()),'test_games':int(context.loc[test_index,'game_group'].nunique()),
        'terminal_comparisons':terminal_comparisons(y_test,prob,X_test,context.loc[test_index])}
    print(json.dumps(metrics,indent=2,allow_nan=False))
    return model,metrics,X_test,y_test,pred,prob


def shap_analysis(model, X, feature_names, output_dir):
    """Run SHAP analysis on the trained model."""
    if not HAS_SHAP:
        print("\n⏭️  Skipping SHAP (shap not installed)")
        return None

    print("\n🔍 Running SHAP analysis...")

    # Use a sample for speed
    X_sample = X.sample(min(1000, len(X)), random_state=42)

    if hasattr(model, "named_steps"):
        X_sample = pd.DataFrame(model.named_steps["imputer"].transform(X_sample), columns=feature_names)
        model = model.named_steps["classifier"]
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    # Summary plot (save to file)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Use SHAP values for class 1 for binary classification
    plot_sv = shap_values[1] if isinstance(shap_values, list) else shap_values

    plt.figure(figsize=(12, 8))
    shap.summary_plot(plot_sv, X_sample, feature_names=feature_names, show=False)
    plt.tight_layout()
    summary_path = os.path.join(output_dir, "shap_summary.png")
    plt.savefig(summary_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ SHAP summary: {summary_path}")

    # Bar plot (top 15)
    plt.figure(figsize=(10, 8))
    shap.summary_plot(plot_sv, X_sample, feature_names=feature_names,
                      plot_type="bar", show=False)
    plt.tight_layout()
    bar_path = os.path.join(output_dir, "shap_importance_bar.png")
    plt.savefig(bar_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"   ✅ SHAP bar: {bar_path}")

    # Handle SHAP values (binary: list of 2 arrays, use class 1)
    if isinstance(shap_values, list):
        sv = shap_values[1]
    else:
        sv = shap_values
    if sv.ndim == 3:
        sv = sv[:, :, 1]

    importances = pd.DataFrame({
        "feature": feature_names,
        "importance_mean_abs": np.abs(sv).mean(axis=0),
    }).sort_values("importance_mean_abs", ascending=False)

    imp_path = os.path.join(output_dir, "shap_importance.csv")
    importances.to_csv(imp_path, index=False)
    print(f"   ✅ SHAP importance: {imp_path}")

    print("\n📊 Top 10 Feature Importance (SHAP):")
    for i, row in importances.head(10).iterrows():
        print(f"   {i+1}. {row['feature']}: {row['importance_mean_abs']:.4f}")

    return importances


def compare_to_baseline(X_test,y_test,y_proba_ml):
    """The same metrics/clipping as the terminal comparison table."""
    baseline=X_test['hit_rate_l10'].to_numpy(dtype=float)/100
    comparison={'raw_l10':_metrics(y_test,baseline),'model':_metrics(y_test,y_proba_ml),
                'classifier':'XGBoost' if USE_XGBOOST else 'RandomForest'}
    print(json.dumps(comparison,indent=2,allow_nan=False))
    return comparison


def main():
    parser = argparse.ArgumentParser(description="NBA XGBoost Model Trainer")
    parser.add_argument("--dataset", default=DATASET_PATH, help="Path to dataset CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--skip-shap", action="store_true", help="Skip SHAP analysis")
    parser.add_argument("--residual-study", action="store_true", help="Research-only market residual trends; no live artifact")
    args = parser.parse_args()
    if args.residual_study:
        from nba_market_residual import run_study
        run_study(args.dataset, args.output_dir)
        return

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=False)

    print("🏀 NBA Chronological ML Trainer V2")
    print("=" * 55)

    # Load data
    X, y, feature_names, context = load_and_prepare(args.dataset)

    # Train
    model, metrics, X_test, y_test, y_pred, y_proba = train_model(X, y, context)

    # SHAP
    if not args.skip_shap:
        shap_analysis(model, X.loc[context.game_date.isin(metrics["dev_dates"])], feature_names, output_dir)

    # Compare vs baseline
    comparison = compare_to_baseline(X_test, y_test, y_proba)

    # Save model (pickle for sklearn, JSON for xgboost)
    import pickle
    model_path = os.path.join(output_dir, "model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    print(f"\n✅ Model saved: {model_path}")

    from nba_ml_pit import sha
    metrics["model_sha256"] = sha(model_path)
    metrics["training_end_date"] = max(metrics["dev_dates"])
    metrics["feature_constructor_sha256"] = sha(_Path(__file__).with_name("nba_ml_features.py"))
    # Save feature names
    feat_path = os.path.join(output_dir, "feature_names.json")
    with open(feat_path, "w") as f:
        json.dump({
            "features": feature_names,
            "categorical_cols": [],
            "feature_contract": FEATURE_CONTRACT,
            "training_protocol": metrics["training_protocol"],
            "deployment_eligible": False,
            "feature_cols": FEATURE_COLS,
            "classifier": "XGBoost" if USE_XGBOOST else "RandomForest",
            "model_sha256": metrics["model_sha256"],
            "training_end_date": metrics["training_end_date"],
            "feature_constructor_sha256": metrics["feature_constructor_sha256"],
        }, f, indent=2)
    print(f"✅ Features saved: {feat_path}")

    # Save metrics
    all_metrics = {**metrics}
    if comparison:
        all_metrics["baseline_comparison"] = comparison

    metrics_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2, allow_nan=False)
    print(f"✅ Metrics saved: {metrics_path}")

    print(f"\n📁 All outputs → {output_dir}/")
    print("   model.pkl (persisted imputer + classifier Pipeline; diagnostic only)")
    print("   metrics.json (performance)")
    print("   feature_names.json (features)")
    print("   shap_*.png (SHAP plots)")
    print("   shap_importance.csv (feature importance table)")


if __name__ == "__main__":
    main()
