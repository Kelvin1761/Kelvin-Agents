#!/usr/bin/env python3
"""
nba_ml_predictor.py — NBA ML Inference Engine

Load trained model, predict prop hit probabilities.
Drops in to replace/augment the 10-factor rules engine.

Usage:
  from nba_ml_predictor import MLPropPredictor

  predictor = MLPropPredictor("NBA_ML_Dataset/models/v2")
  prob = predictor.predict(player_features, stat="PTS", line=25.5)
"""

import os
import json
import pickle
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path as _Path
PROJECT_ROOT = _Path(__file__).resolve().parents[3]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import NBA_ML_DATASET

MODEL_DIR = os.environ.get("NBA_WC_MODEL_DIR") or str(NBA_ML_DATASET / "models" / "v3")


# Training-parity constants (build_nba_ml_dataset.py). The model was trained
# with these conventions; live inputs must be built the same way.
TRAIN_PACE_BASELINE = 98.0   # build_nba_ml_dataset.py: pace_adj uses (opp_pace-98)/98
TRAIN_USG_BONUS_PCT = 0      # training never populated usg_bonus_pct (always 0)


def training_hit_features(arr, line_value):
    """Hit-rate / AMC features exactly as the training builder computes them.

    ``arr`` is the newest-first game log for the stat; threshold is ``>=``
    (a milestone "N+"), percentages rounded to 0 dp, AMC to 1 dp.
    """
    arr = arr or []
    l5, l3 = arr[:5], arr[:3]

    def rate(xs):
        return round(sum(1 for x in xs if x >= line_value) / len(xs) * 100, 0) if xs else 0

    clr = [x - line_value for x in arr if x >= line_value]
    return {
        "hit_rate_l10": rate(arr),
        "hit_rate_l5": rate(l5),
        "hit_rate_l3": rate(l3),
        "amc": round(sum(clr) / len(clr), 1) if clr else 0,
    }


def training_pace_projected(l10_avg, opp_pace):
    pace_adj = round((opp_pace - TRAIN_PACE_BASELINE) / TRAIN_PACE_BASELINE * l10_avg, 1) if l10_avg > 0 else 0
    return round(l10_avg + pace_adj, 1)


class MLPropPredictor:
    """Loads trained model and predicts prop hit probability."""

    def __init__(self, model_dir=MODEL_DIR):
        model_path = os.path.join(model_dir, "model.pkl")
        feat_path = os.path.join(model_dir, "feature_names.json")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")

        with open(model_path, "rb") as f:
            self.model = pickle.load(f)

        with open(feat_path) as f:
            meta = json.load(f)
        self.feature_names = meta.get("features", [])

        self.stat_map = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "fg3m"}
        print(f"🏀 MLPropPredictor loaded: {os.path.basename(model_dir)}")
        print(f"   Features: {len(self.feature_names)}")

    def predict(self, row_dict):
        """Predict hit probability for a single prop.

        row_dict: dict with keys matching feature_names.
        Returns probability (0-1) that prop hits.
        """
        df = pd.DataFrame([row_dict])
        for col in self.feature_names:
            if col not in df.columns:
                df[col] = 0
        X = df[self.feature_names].fillna(0)
        # Convert any string "N/A" or similar to 0
        for col in X.columns:
            if X[col].dtype == object:
                X[col] = pd.to_numeric(X[col], errors='coerce').fillna(0)
        prob = self.model.predict_proba(X)[0, 1]
        return round(float(prob), 4)

    def predict_batch(self, rows):
        """Predict hit probabilities for multiple props.

        rows: list of dicts.
        Returns list of probabilities.
        """
        df = pd.DataFrame(rows)
        for col in self.feature_names:
            if col not in df.columns:
                df[col] = 0
        X = df[self.feature_names].fillna(0)
        probs = self.model.predict_proba(X)[:, 1]
        return [round(float(p), 4) for p in probs]

    def build_features(self, player_data, stat, line_value, is_home, opp_abbr,
                       opp_def_rating=0, opp_def_rank=0, opp_pace=98.0,
                       defender_pm=0, usg_bonus_pct=0):
        """Build feature dict from player_data JSON + context.

        player_data: dict from nba_game_data.json's player entry.
        stat: "PTS" | "REB" | "AST" | "FG3M"
        line_value: the milestone line (e.g. 25.5)
        is_home: 0 or 1
        opp_abbr: opponent team abbreviation
        opp_def_rating: opponent defensive rating (from team_stats)
        opp_def_rank: opponent defensive rank (from team_stats)
        opp_pace: opponent pace (from team_stats)
        defender_pm: defender plus-minus (from key_defenders)
        usg_bonus_pct: usage bonus from injuries (from usage_redistribution)
        """
        gl = player_data.get("gamelog") or {}
        gl_stats = gl.get(f"{stat}_stats") or {}
        arr = gl.get(stat) or []
        l5_arr = arr[:5]
        l3_arr = arr[:3]

        # MIN gamelog (stat-independent feature)
        min_arr = gl.get("MIN") or []
        min_stats = gl.get("MIN_stats") or {}

        pa = (player_data.get("prop_analytics") or {}).get(stat) or {}
        adv = player_data.get("advanced") or {}
        splits = player_data.get("splits") or {}
        fatigue = player_data.get("fatigue") or {}

        def safe_float(v, default=0.0):
            if v is None:
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        features = {
            "l10_avg": safe_float(gl_stats.get("avg"), 0),
            "l10_sd": safe_float(gl_stats.get("sd"), 0),
            "l10_cov": safe_float(gl_stats.get("cov"), 0),
            "l10_med": safe_float(gl_stats.get("med"), 0),
            "l5_avg": round(sum(l5_arr) / len(l5_arr), 1) if l5_arr else 0,
            "l3_avg": round(sum(l3_arr) / len(l3_arr), 1) if l3_arr else 0,
            "min_avg": safe_float(min_stats.get("avg"), round(sum(min_arr) / len(min_arr), 1) if min_arr else 0),
            # Same baseline as training (98), NOT the extractor's 100-based value.
            "pace_projected": training_pace_projected(safe_float(gl_stats.get("avg"), 0), opp_pace),
            "usg_pct": safe_float(adv.get("USG_PCT")),
            "ts_pct": safe_float(adv.get("TS_PCT")),
            "def_rtg": safe_float(adv.get("DEF_RATING")),
            "opp_def_rating": opp_def_rating,
            "opp_def_rank": opp_def_rank,
            "opp_pace": opp_pace,
            "defender_pm": defender_pm,
            "usg_bonus_pct": TRAIN_USG_BONUS_PCT,  # arg ignored: never non-zero in training
            "b2b_flag": 1 if fatigue and fatigue.get("is_b2b", False) else 0,
            "b2b_ppg_diff_pct": self._b2b_diff(fatigue),
            "rest_days": safe_float((fatigue or {}).get("rest_days", 1) if fatigue else 1, 1),
            "is_home": is_home,
            "home_ppg": safe_float(splits.get("Home_PPG")),
            "away_ppg": safe_float(splits.get("Road_PPG")),
            "line_value": line_value,
        }
        # Always computed from the game log for the requested line (integer
        # milestone), as in training. The extractor's sportsbet_lines are x.5
        # lines with a different `>` convention and never match a milestone.
        features.update(training_hit_features(arr, line_value))

        return features

    def _b2b_diff(self, fatigue):
        if not fatigue:
            return 0
        normal = fatigue.get("normal_ppg", 0) or 0
        b2b = fatigue.get("b2b_ppg", 0) or 0
        return round((b2b - normal) / normal, 4) if normal > 0 else 0


if __name__ == "__main__":
    # Smoke test
    predictor = MLPropPredictor()
    test_features = {
        "l10_avg": 25.0, "l10_sd": 5.0, "l10_cov": 20.0, "l10_med": 24.0,
        "l5_avg": 26.0, "l3_avg": 28.0, "pace_projected": 25.5,
        "usg_pct": 28.0, "ts_pct": 58.0, "def_rtg": 110.0,
        "opp_def_rating": 108.0, "opp_def_rank": 8, "opp_pace": 100.0,
        "defender_pm": -3.0, "usg_bonus_pct": 0,
        "b2b_flag": 0, "b2b_ppg_diff_pct": 0, "rest_days": 1,
        "is_home": 1, "home_ppg": 26.0, "away_ppg": 24.0,
        "hit_rate_l10": 60.0, "hit_rate_l5": 80.0, "amc": 4.5,
        "line_value": 25,
    }
    prob = predictor.predict(test_features)
    print(f"\n🧪 Smoke test: PTS 25+ probability = {prob:.1%}")
    print("✅ ML Predictor ready")
