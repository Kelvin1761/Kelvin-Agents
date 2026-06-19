#!/usr/bin/env python3
"""
train_nba_xgboost.py — NBA XGBoost Model Trainer V1

Train an XGBoost classifier to predict prop hit probability.
Compare against the current deterministic 10-factor engine.
Output SHAP analysis + model artifact.

Usage:
  python .agents/scripts/nba_ml/train_nba_xgboost.py
  python .agents/scripts/nba_ml/train_nba_xgboost.py --output-dir NBA_ML_Dataset/models/v1
"""

import os
import sys
import json
import argparse
import io
import warnings
warnings.filterwarnings('ignore')

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             roc_auc_score, brier_score_loss, log_loss)
from sklearn.preprocessing import LabelEncoder

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

DATASET_PATH = "NBA_ML_Dataset/dataset.csv"
DEFAULT_OUTPUT = "NBA_ML_Dataset/models/v1"

FEATURE_COLS = [
    # Core L10 stats
    "l10_avg", "l10_sd", "l10_cov", "l10_med", "l5_avg", "l3_avg",
    # Minutes (stat-independent volume signal)
    "min_avg",
    # Pace adjustment
    "pace_projected",
    # Advanced metrics
    "usg_pct", "ts_pct", "def_rtg",
    # Opponent context
    "opp_def_rating", "opp_def_rank", "opp_pace",
    # Defender
    "defender_pm",
    # Usage redistribution
    "usg_bonus_pct",
    # Fatigue
    "b2b_flag", "b2b_ppg_diff_pct", "rest_days",
    # Split stats
    "is_home", "home_ppg", "away_ppg",
    # Current engine baseline (10-factor hit rate + ML recency)
    "hit_rate_l10", "hit_rate_l5", "hit_rate_l3", "amc",
    # Line difficulty
    "line_value",
]

CAT_COLS = ["stat_category", "team", "opponent", "position"]
DROP_COLS_FOR_IMPUTE = [
    "usg_pct", "ts_pct", "def_rtg", "home_ppg", "away_ppg",
    "home_rpg", "away_rpg", "home_apg", "away_apg",
]


def load_and_prepare(path):
    """Load dataset and prepare for training."""
    print("📂 Loading dataset...")
    df = pd.read_csv(path)

    labeled = df[df["hit"].notna()].copy()
    print(f"   Total rows: {len(df):,}")
    print(f"   Labeled rows: {len(labeled):,}")
    print(f"   Hit rate: {labeled['hit'].mean():.1%}")

    # Impute missing numeric values with median
    for col in DROP_COLS_FOR_IMPUTE:
        if col in labeled.columns:
            labeled[col] = labeled[col].fillna(labeled[col].median())

    # Encode categoricals
    encoders = {}
    for col in CAT_COLS:
        if col in labeled.columns:
            le = LabelEncoder()
            labeled[col] = le.fit_transform(labeled[col].astype(str))
            encoders[col] = le

    # Select feature columns that exist
    available_features = [c for c in FEATURE_COLS if c in labeled.columns]
    missing = [c for c in FEATURE_COLS if c not in labeled.columns]
    if missing:
        print(f"   ⚠️ Missing features: {missing}")

    X = labeled[available_features]
    y = labeled["hit"]

    print(f"\n   Features: {len(available_features)}")
    print(f"   Available features: {available_features}")
    print(f"   X shape: {X.shape}")

    return X, y, available_features, encoders


def train_model(X, y):
    """Train XGBoost with cross-validation."""
    print("\n🏋️ Training XGBoost...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pos_weight = (y_train == 0).sum() / (y_train == 1).sum()

    if USE_XGBOOST:
        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=pos_weight,
            eval_metric="logloss", random_state=42,
            use_label_encoder=False, verbosity=0,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    else:
        model = RandomForestClassifier(
            n_estimators=300, max_depth=10, min_samples_leaf=5,
            class_weight="balanced_subsample",
            random_state=42, n_jobs=-1, verbose=0,
        )
        model.fit(X_train, y_train)

    # Predictions
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    # Metrics
    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred), 4),
        "recall": round(recall_score(y_test, y_pred), 4),
        "f1": round(f1_score(y_test, y_pred), 4),
        "roc_auc": round(roc_auc_score(y_test, y_proba), 4),
        "brier_score": round(brier_score_loss(y_test, y_proba), 4),
        "log_loss": round(log_loss(y_test, y_proba), 4),
        "test_size": len(y_test),
        "train_size": len(y_train),
        "baseline_hit_rate": round(y_train.mean(), 4),
    }

    print(f"\n📊 Test Set Metrics:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"   {k}: {v:.4f}")
        else:
            print(f"   {k}: {v}")

    # CV score
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
    metrics["cv_roc_auc_mean"] = round(cv_scores.mean(), 4)
    metrics["cv_roc_auc_std"] = round(cv_scores.std(), 4)
    print(f"\n📊 5-Fold CV ROC-AUC: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    return model, metrics, X_test, y_test, y_pred, y_proba


def shap_analysis(model, X, feature_names, output_dir):
    """Run SHAP analysis on the trained model."""
    if not HAS_SHAP:
        print("\n⏭️  Skipping SHAP (shap not installed)")
        return None

    print("\n🔍 Running SHAP analysis...")

    # Use a sample for speed
    X_sample = X.sample(min(1000, len(X)), random_state=42)

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


def compare_to_baseline(X_test, y_test, y_proba_ml):
    """Compare ML model vs the current 10-factor engine's hit_rate_l10 baseline."""
    baseline_proba = X_test["hit_rate_l10"].values / 100.0  # hit_rate_l10 is 0-100

    valid = ~np.isnan(baseline_proba)
    if valid.sum() < 10:
        print("\n⏭️  Skipping baseline comparison (too few valid rows)")
        return

    baseline_proba = baseline_proba[valid]
    y_test_v = y_test.values[valid]
    ml_proba = y_proba_ml[valid]

    baseline_auc = roc_auc_score(y_test_v, baseline_proba)
    ml_auc = roc_auc_score(y_test_v, ml_proba)

    baseline_brier = brier_score_loss(y_test_v, baseline_proba)
    ml_brier = brier_score_loss(y_test_v, ml_proba)

    baseline_log = log_loss(y_test_v, baseline_proba)
    ml_log = log_loss(y_test_v, ml_proba)

    print(f"\n{'='*55}")
    print(f"📊 ML Model vs Current 10-Factor Engine")
    print(f"{'='*55}")
    print(f"{'Metric':<20} {'10-Factor':>10} {'XGBoost':>10} {'Δ':>10}")
    print(f"{'-'*50}")
    print(f"{'ROC-AUC':<20} {baseline_auc:>10.4f} {ml_auc:>10.4f} {ml_auc - baseline_auc:>+10.4f}")
    print(f"{'Brier Score':<20} {baseline_brier:>10.4f} {ml_brier:>10.4f} {ml_brier - baseline_brier:>+10.4f}")
    print(f"{'Log Loss':<20} {baseline_log:>10.4f} {ml_log:>10.4f} {ml_log - baseline_log:>+10.4f}")

    # Edge accuracy comparison
    baseline_pred = (baseline_proba >= 0.5).astype(int)
    ml_pred = (ml_proba >= 0.5).astype(int)
    baseline_acc = accuracy_score(y_test_v, baseline_pred)
    ml_acc = accuracy_score(y_test_v, ml_pred)
    print(f"{'Accuracy':<20} {baseline_acc:>10.4f} {ml_acc:>10.4f} {ml_acc - baseline_acc:>+10.4f}")

    return {
        "baseline_roc_auc": round(baseline_auc, 4),
        "ml_roc_auc": round(ml_auc, 4),
        "baseline_brier": round(baseline_brier, 4),
        "ml_brier": round(ml_brier, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="NBA XGBoost Model Trainer")
    parser.add_argument("--dataset", default=DATASET_PATH, help="Path to dataset CSV")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--skip-shap", action="store_true", help="Skip SHAP analysis")
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    print("🏀 NBA XGBoost Model Trainer V1")
    print("=" * 55)

    # Load data
    X, y, feature_names, encoders = load_and_prepare(args.dataset)

    # Train
    model, metrics, X_test, y_test, y_pred, y_proba = train_model(X, y)

    # SHAP
    if not args.skip_shap:
        shap_analysis(model, X, feature_names, output_dir)

    # Compare vs baseline
    comparison = compare_to_baseline(X_test, y_test, y_proba)

    # Save model (pickle for sklearn, JSON for xgboost)
    import pickle
    model_path = os.path.join(output_dir, "model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    print(f"\n✅ Model saved: {model_path}")

    # Save feature names
    feat_path = os.path.join(output_dir, "feature_names.json")
    with open(feat_path, "w") as f:
        json.dump({
            "features": feature_names,
            "categorical_cols": CAT_COLS,
            "feature_cols": FEATURE_COLS,
        }, f, indent=2)
    print(f"✅ Features saved: {feat_path}")

    # Save metrics
    all_metrics = {**metrics}
    if comparison:
        all_metrics["baseline_comparison"] = comparison

    metrics_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"✅ Metrics saved: {metrics_path}")

    print(f"\n📁 All outputs → {output_dir}/")
    print("   xgboost_model.json (model artifact)")
    print("   metrics.json (performance)")
    print("   feature_names.json (features)")
    print("   shap_*.png (SHAP plots)")
    print("   shap_importance.csv (feature importance table)")


if __name__ == "__main__":
    main()
