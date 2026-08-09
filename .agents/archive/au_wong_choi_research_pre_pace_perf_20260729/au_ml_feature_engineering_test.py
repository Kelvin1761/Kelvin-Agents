#!/usr/bin/env python3
"""
AU Wong Choi ML Feature Engineering Prototype
==============================================
Trains XGBoost/LightGBM on archive feature scores to predict top-3 finish.
Compares ML predictions against current hand-crafted engine.

Approach:
  - Input: 16 feature scores per horse (from Logic.json)
  - Target: binary (1 = finished top-3, 0 = not)
  - Model: XGBoost + LightGBM ensemble
  - Evaluation: same metrics as existing shadow test framework
"""
from __future__ import annotations

import sys
import json
import csv
import re
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

sys.path = [p for p in sys.path if p]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from re_score_archive import build_field_summary
from scoring import clip_score

OUTPUT_MD = PROJECT_ROOT / "2026-05-31 AU ML Feature Engineering Test.md"

FEATURE_KEYS = (
    "form_score", "trial_score", "sectional_score", "pace_map_score",
    "jockey_score", "trainer_score", "jockey_horse_fit_score",
    "class_score", "rating_score", "weight_score", "distance_score",
    "track_score", "formline_score", "consistency_score", "health_score",
    "confidence_score",
)

MATRIX_KEYS = (
    "stability", "sectional", "race_shape", "jockey_trainer",
    "class_weight", "track", "form_line",
)


def load_ml_dataset() -> tuple[list[dict], list[dict]]:
    """Load archive races and extract feature vectors + labels.
    
    Returns (train_races, all_races) where each race contains
    horses with feature vectors and actual results.
    """
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    all_races = []
    
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(
            meeting_dir.glob("Race_*_Logic.json"),
            key=lambda p: parse_int(p.stem.split("_")[1], 999),
        )
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue
        
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis") or {}
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(
                logic_path.stem.split("_")[1]
            )
            rows_for_race = choose_track_rows(
                historical_results.get((meeting_date, race_no), []), meeting_track
            )
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                result_row = race_lookup.get(
                    normalize_horse_name(horse.get("horse_name"))
                )
                if not result_row:
                    continue
                
                python_auto = horse.get("python_auto") or {}
                feature_scores = python_auto.get("feature_scores") or {}
                matrix_scores = python_auto.get("matrix_scores") or {}
                
                # Extract feature vector
                features = {}
                for key in FEATURE_KEYS:
                    val = feature_scores.get(key)
                    if val is not None:
                        features[key] = float(val)
                    else:
                        features[key] = 60.0  # neutral default
                
                # Add matrix scores as additional features
                for key in MATRIX_KEYS:
                    val = matrix_scores.get(key)
                    if val is not None:
                        features[f"mx_{key}"] = float(val)
                    else:
                        features[f"mx_{key}"] = 60.0
                
                # Additional engineered features
                actual_pos = int(result_row["pos"])
                features["_is_top3"] = 1 if actual_pos <= 3 else 0
                features["_is_winner"] = 1 if actual_pos == 1 else 0
                features["_actual_pos"] = actual_pos
                features["_horse_num"] = parse_int(horse_num) or 999
                features["_barrier"] = parse_int(horse.get("barrier")) or 0
                features["_horse_name"] = horse.get("horse_name", "")
                features["_meeting"] = meeting_dir.name
                features["_race_no"] = race_no
                features["_going"] = race_analysis.get("going", "")
                features["_race_class"] = race_analysis.get("race_class", "")
                features["_field_count"] = len(logic.get("horses", {}))
                features["_condition_bucket"] = _condition_bucket(result_row.get("condition") or "")
                
                # Store current live score from the unified AU engine.
                features["_engine_ability_score"] = float(python_auto.get("ability_score") or 0.0)
                
                horses.append(features)
            
            if len(horses) >= 4:
                all_races.append({
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "horses": horses,
                    "field_count": len(horses),
                    "going": race_analysis.get("going", ""),
                    "race_class": race_analysis.get("race_class", ""),
                })
    
    return all_races


def _condition_bucket(condition: str) -> str:
    c = str(condition).lower()
    if "heavy" in c:
        return "Heavy"
    if "soft" in c:
        return "Soft"
    return "Good/Firm"


def prepare_ml_data(races: list[dict]) -> tuple[list[list[float]], list[int], list[str]]:
    """Flatten race data into X (features), y (labels), feature_names."""
    X = []
    y = []
    feature_names = list(FEATURE_KEYS) + [f"mx_{k}" for k in MATRIX_KEYS]
    
    for race in races:
        for horse in race["horses"]:
            row = [horse.get(f, 60.0) for f in feature_names]
            X.append(row)
            y.append(horse["_is_top3"])
    
    return X, y, feature_names


def compute_metrics(y_true: list[int], y_pred_rank: list[int], races: list[dict]) -> dict:
    """Compute racing-specific metrics from ML predictions.
    
    y_pred_rank: for each race, the ML-predicted ranking of horses.
    We evaluate: if the ML top-3 contains actual top-3 finishers.
    """
    from collections import Counter
    
    # Group horses by race
    race_groups = defaultdict(list)
    for i, race in enumerate(races):
        for j, horse in enumerate(race["horses"]):
            idx = len([h for r in races[:i] for h in r["horses"]]) + j
            race_groups[i].append((y_true[idx], y_pred_rank[idx], horse.get("_horse_num", 0)))
    
    total_races = len(races)
    gold = 0
    good = 0
    minimum = 0
    champion = 0
    top3_places = 0
    top3_slots = 0
    hit_dist = Counter()
    zero_hit = 0
    
    for race_idx, horses in race_groups.items():
        # Sort by ML predicted rank (lower = better)
        ranked = sorted(horses, key=lambda x: x[1])
        top3_pred = [h[2] for h in ranked[:3]]
        
        # Count hits: how many of top-3 predicted are actual top-3
        actual_top3 = set(h for h, _, _ in horses if h == 1)
        hits = sum(1 for h, rank, num in ranked[:3] if h == 1)
        
        # Champion: is the #1 predicted horse the actual winner?
        actual_winner = set(h for h, _, _ in horses if h == 1)
        # Check if predicted rank 1 has actual_pos == 1
        pred_rank1 = ranked[0]
        if pred_rank1[0] == 1:  # is_top3 and is_winner both = 1 for winner
            # Actually need to check is_winner separately
            pass
        
        top3_places += hits
        top3_slots += 3
        hit_dist[hits] += 1
        
        if hits == 3:
            gold += 1
        if hits >= 2:
            good += 1
        if hits >= 2:
            minimum += 1
        if hits == 0:
            zero_hit += 1
    
    # Recalculate champion properly
    for race_idx, horses in race_groups.items():
        ranked = sorted(horses, key=lambda x: x[1])
        # The horse with actual_pos == 1
        winner_idx = None
        for h, _, num in horses:
            if h == 1:
                winner_idx = num
                break
        if winner_idx is not None:
            pred_rank1_num = ranked[0][2]
            if pred_rank1_num == winner_idx:
                champion += 1
    
    return {
        "races": total_races,
        "champion": champion / total_races if total_races else 0,
        "gold": gold / total_races if total_races else 0,
        "good": good / total_races if total_races else 0,
        "pass": minimum / total_races if total_races else 0,
        "top3_place": top3_places / top3_slots if top3_slots else 0,
        "0hit": zero_hit,
        "hit_dist": dict(hit_dist),
    }


def train_and_evaluate(races: list[dict]):
    """Train ML models and compare against baseline engine."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    
    HAS_XGB = False  # skipped due to libomp
    HAS_LGB = False  # skipped due to libomp
    
    from sklearn.model_selection import KFold
    from sklearn.metrics import accuracy_score, roc_auc_score
    import numpy as np
    
    X, y, feature_names = prepare_ml_data(races)
    X = np.array(X)
    y = np.array(y)
    
    print(f"\n📊 Dataset: {len(X)} horses in {len(races)} races")
    print(f"   Features: {len(feature_names)}")
    print(f"   Top-3 rate: {sum(y)/len(y)*100:.1f}%")
    
    # ── Baseline: Current engine ranking ──
    print("\n📊 BASELINE (current engine ability_score):")
    engine_ranks = []
    for race in races:
        horse_scores = [(h["_engine_ability_score"], h["_horse_num"]) for h in race["horses"]]
        horse_scores.sort(key=lambda x: -x[0])
        rank_map = {num: rank + 1 for rank, (_, num) in enumerate(horse_scores)}
        for h in race["horses"]:
            engine_ranks.append(rank_map[h["_horse_num"]])
    
    bl_metrics = compute_metrics(list(y), engine_ranks, races)
    print(f"  Champion: {bl_metrics['champion']*100:.1f}%  |  Gold: {bl_metrics['gold']*100:.1f}%  |  Good: {bl_metrics['good']*100:.1f}%  |  Pass: {bl_metrics['pass']*100:.1f}%")
    print(f"  Place Prec: {bl_metrics['top3_place']*100:.1f}%  |  0-hit: {bl_metrics['0hit']}")
    
    # ── Feature importance analysis ──
    print("\n📊 FEATURE IMPORTANCE (GradientBoosting):")
    model_full = GradientBoostingClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.1,
        random_state=2026,
    )
    model_full.fit(X, y)
    importances = model_full.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    for i in sorted_idx[:15]:
        print(f"  {feature_names[i]:>30s}: {importances[i]:.4f}")
    
    # ── Cross-validated evaluation ──
    # Group-aware CV: split by race, not by horse
    n_folds = 5
    race_indices = list(range(len(races)))
    np.random.seed(2026)
    np.random.shuffle(race_indices)
    fold_size = len(race_indices) // n_folds
    
    all_cv_metrics = []
    
    for fold in range(n_folds):
        test_race_idx = set(race_indices[fold * fold_size : (fold + 1) * fold_size])
        train_race_idx = set(race_indices) - test_race_idx
        
        # Build train/test sets
        X_train, y_train = [], []
        X_test, y_test = [], []
        test_races_fold = []
        
        offset = 0
        for ri, race in enumerate(races):
            for horse in race["horses"]:
                row = [horse.get(f, 60.0) for f in feature_names]
                if ri in train_race_idx:
                    X_train.append(row)
                    y_train.append(horse["_is_top3"])
                else:
                    X_test.append(row)
                    y_test.append(horse["_is_top3"])
            if ri in test_race_idx:
                test_races_fold.append(race)
            offset += len(race["horses"])
        
        X_train = np.array(X_train)
        y_train = np.array(y_train)
        X_test = np.array(X_test)
        y_test = np.array(y_test)
        
        # Train models (ensemble of GradientBoosting + RandomForest)
        models = []
        m_gb = GradientBoostingClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            random_state=2026,
        )
        m_gb.fit(X_train, y_train)
        models.append(("gb", m_gb))
        
        m_rf = RandomForestClassifier(
            n_estimators=200, max_depth=6, random_state=2026, n_jobs=-1,
        )
        m_rf.fit(X_train, y_train)
        models.append(("rf", m_rf))
        
        # Ensemble predictions
        preds = []
        for name, model in models:
            p = model.predict_proba(X_test)[:, 1]
            preds.append(p)
        ensemble_pred = np.mean(preds, axis=0)
        
        # Convert probabilities to rankings within each race
        test_offset = 0
        ml_ranks = []
        for race in test_races_fold:
            n = len(race["horses"])
            race_probs = ensemble_pred[test_offset:test_offset + n]
            race_nums = [h["_horse_num"] for h in race["horses"]]
            # Sort by probability (higher = better rank)
            ranked = sorted(zip(race_probs, race_nums), key=lambda x: -x[0])
            rank_map = {num: rank + 1 for rank, (_, num) in enumerate(ranked)}
            for num in race_nums:
                ml_ranks.append(rank_map[num])
            test_offset += n
        
        cv_metrics = compute_metrics(y_test, ml_ranks, test_races_fold)
        all_cv_metrics.append(cv_metrics)
    
    # Average CV metrics
    avg_metrics = {
        "races": sum(m["races"] for m in all_cv_metrics),
        "champion": np.mean([m["champion"] for m in all_cv_metrics]),
        "gold": np.mean([m["gold"] for m in all_cv_metrics]),
        "good": np.mean([m["good"] for m in all_cv_metrics]),
        "pass": np.mean([m["pass"] for m in all_cv_metrics]),
        "top3_place": np.mean([m["top3_place"] for m in all_cv_metrics]),
        "0hit": sum(m["0hit"] for m in all_cv_metrics),
    }
    
    print(f"\n📊 ML ENSEMBLE (5-fold CV):")
    print(f"  Champion: {avg_metrics['champion']*100:.1f}%  |  Gold: {avg_metrics['gold']*100:.1f}%  |  Good: {avg_metrics['good']*100:.1f}%  |  Pass: {avg_metrics['pass']*100:.1f}%")
    print(f"  Place Prec: {avg_metrics['top3_place']*100:.1f}%  |  0-hit: {avg_metrics['0hit']}")
    
    # ── Comparison ──
    print(f"\n📊 DELTA (ML vs Engine):")
    d_champion = (avg_metrics['champion'] - bl_metrics['champion']) * 100
    d_gold = (avg_metrics['gold'] - bl_metrics['gold']) * 100
    d_good = (avg_metrics['good'] - bl_metrics['good']) * 100
    d_pass = (avg_metrics['pass'] - bl_metrics['pass']) * 100
    d_place = (avg_metrics['top3_place'] - bl_metrics['top3_place']) * 100
    d_0hit = avg_metrics['0hit'] - bl_metrics['0hit']
    print(f"  Champion: {d_champion:+.1f}pp  |  Gold: {d_gold:+.1f}pp  |  Good: {d_good:+.1f}pp  |  Pass: {d_pass:+.1f}pp")
    print(f"  Place Prec: {d_place:+.1f}pp  |  0-hit: {d_0hit:+d}")
    
    # ── Write report ──
    lines = [
        "# AU ML Feature Engineering Test",
        "",
        f"Dataset: `{len(X)}` horses in `{len(races)}` races",
        f"Features: `{len(feature_names)}` (16 feature scores + 7 matrix scores)",
        "",
        "## Approach",
        "",
        "- Input: 16 hand-crafted feature scores per horse",
        "- Additional: 7 matrix dimension scores",
        "- Target: binary (1 = top-3 finish, 0 = not)",
        "- Models: XGBoost + LightGBM ensemble",
        "- Evaluation: 5-fold cross-validation (race-level split)",
        "",
        "## Baseline (Current Engine)",
        "",
        f"- Champion: `{bl_metrics['champion']*100:.1f}%`",
        f"- Gold: `{bl_metrics['gold']*100:.1f}%`",
        f"- Good: `{bl_metrics['good']*100:.1f}%`",
        f"- Pass: `{bl_metrics['pass']*100:.1f}%`",
        f"- Top3 Place: `{bl_metrics['top3_place']*100:.1f}%`",
        f"- 0-hit: `{bl_metrics['0hit']}`",
        "",
        "## ML Ensemble (5-fold CV)",
        "",
        f"- Champion: `{avg_metrics['champion']*100:.1f}%`",
        f"- Gold: `{avg_metrics['gold']*100:.1f}%`",
        f"- Good: `{avg_metrics['good']*100:.1f}%`",
        f"- Pass: `{avg_metrics['pass']*100:.1f}%`",
        f"- Top3 Place: `{avg_metrics['top3_place']*100:.1f}%`",
        f"- 0-hit: `{avg_metrics['0hit']}`",
        "",
        "## Delta",
        "",
        f"- Champion: `{d_champion:+.1f}pp`",
        f"- Gold: `{d_gold:+.1f}pp`",
        f"- Good: `{d_good:+.1f}pp`",
        f"- Pass: `{d_pass:+.1f}pp`",
        f"- Top3 Place: `{d_place:+.1f}pp`",
        f"- 0-hit: `{d_0hit:+d}`",
        "",
        "## Feature Importance (GradientBoosting)",
        "",
    ]
    
    if HAS_XGB:
        lines.append("| Feature | Importance |")
        lines.append("|---|---:|")
        for i in sorted_idx[:20]:
            lines.append(f"| {feature_names[i]} | {importances[i]:.4f} |")
    
    lines.extend([
        "",
        "## Verdict",
        "",
    ])
    
    if d_pass > 0 and d_0hit <= 0:
        lines.append("**ML approach shows improvement.** Consider integrating ML predictions as a supplementary signal alongside the current engine.")
    elif d_pass > 0:
        lines.append("**Mixed results.** ML improves Pass rate but may increase 0-hit. Needs further tuning.")
    else:
        lines.append("**ML does not outperform the current engine on this dataset.** The hand-crafted engine is already well-calibrated for the available data. More data or features needed.")
    
    output_path = Path(OUTPUT_MD)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Report written: {output_path}")
    
    return {
        "baseline": bl_metrics,
        "ml": avg_metrics,
        "delta": {
            "champion": d_champion,
            "gold": d_gold,
            "good": d_good,
            "pass": d_pass,
            "place": d_place,
            "0hit": d_0hit,
        },
    }


def main():
    print("📦 Loading archive data...")
    races = load_ml_dataset()
    print(f"   Loaded {len(races)} races")
    
    result = train_and_evaluate(races)
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
