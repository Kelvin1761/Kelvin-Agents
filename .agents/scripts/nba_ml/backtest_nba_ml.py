#!/usr/bin/env python3
"""
backtest_nba_ml.py — NBA ML Backtest vs Historical Deterministic Engine

Compare ML model vs the 10-factor engine on historical archive data.
For each archived game, score every prop with both engines and compare:

1. ROC-AUC (ranking props by hit probability)
2. Hit rate at threshold (precision/recall at various cutoffs)
3. Best combo construction (simulated SGM)

Output:
  NBA_ML_Dataset/backtest/
    backtest_results.json      — Per-game + aggregate metrics
    backtest_comparison.csv    — Raw comparison per prop
    combo_simulation.csv       — Simulated combo performance

Usage:
  python .agents/scripts/nba_ml/backtest_nba_ml.py
"""

import os
import sys
import json
import csv
import io
import warnings
warnings.filterwarnings('ignore')

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, brier_score_loss

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from nba_ml_predictor import MLPropPredictor

ARCHIVE_DIR = "Archive_NBA_Analysis"
DATASET_DIR = "NBA_ML_Dataset"
RESULTS_DIR = os.path.join(DATASET_DIR, "results_brief")
OUTPUT_DIR = os.path.join(DATASET_DIR, "backtest")

STAT_KEY_MAP = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "fg3m"}
SPORTSBET_LINES = {
    "PTS": [10, 15, 20, 25, 30, 35, 40],
    "REB": [3, 5, 7, 9, 11, 13, 15],
    "AST": [2, 4, 6, 8, 10, 12],
    "FG3M": [1, 2, 3, 4, 5, 6],
}


def load_results_for_date(game_date):
    """Load Results_Brief for a given date."""
    path = os.path.join(RESULTS_DIR, f"Results_Brief_{game_date}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    games = data.get("games", [])
    lookup = {}
    for g in games:
        home = g.get("home", {}).get("team", "")
        away = g.get("away", {}).get("team", "")
        tag = f"{away}_{home}"
        players = {}
        for p in g.get("players", []):
            name = p.get("name", "")
            if name and name != "?":
                players[name] = p
        lookup[tag] = {"players": players, "final_score": g.get("final_score", "")}
        lookup[f"{home}_{away}"] = lookup[tag]
    return lookup


def find_archive_dates():
    """Find archive dates that have both nba_game_data and Results_Brief."""
    dates = set()
    for entry in sorted(os.listdir(ARCHIVE_DIR)):
        path = os.path.join(ARCHIVE_DIR, entry)
        if not os.path.isdir(path):
            continue
        has_data = any(f.startswith("nba_game_data_") or ("_data.json" in f and f.startswith("Game_"))
                       for f in os.listdir(path))
        if not has_data:
            continue
        # Try to extract date from first JSON
        ff = [f for f in os.listdir(path) if f.startswith("nba_game_data_") or ("_data.json" in f and f.startswith("Game_"))]
        if ff:
            fp = os.path.join(path, ff[0])
            try:
                with open(fp) as f:
                    d = json.load(f)
                game_date = (d.get("meta", {}).get("date") or "")[:10]
                if game_date:
                    dates.add(game_date)
            except Exception:
                pass
    return sorted(dates)


def evaluate_game(game_date, predictor):
    """Evaluate ML model vs 10-factor engine on all props for a given date."""
    results_lookup = load_results_for_date(game_date)
    if not results_lookup:
        return None

    # Find archive folder for this date
    folder_path = None
    for entry in sorted(os.listdir(ARCHIVE_DIR)):
        path = os.path.join(ARCHIVE_DIR, entry)
        if not os.path.isdir(path):
            continue
        ff = [f for f in os.listdir(path) if f.startswith("nba_game_data_") or ("_data.json" in f and f.startswith("Game_"))]
        for fname in ff:
            fp = os.path.join(path, fname)
            try:
                with open(fp) as f:
                    d = json.load(f)
                dt = (d.get("meta", {}).get("date") or "")[:10]
                if dt == game_date:
                    folder_path = path
                    break
            except Exception:
                pass
        if folder_path:
            break

    if not folder_path:
        return None

    records = []
    for fname in os.listdir(folder_path):
        if not (fname.startswith("nba_game_data_") or ("_data.json" in fname and fname.startswith("Game_"))):
            continue

        fp = os.path.join(folder_path, fname)
        try:
            with open(fp) as f:
                data = json.load(f)
        except Exception:
            continue

        meta = data.get("meta", {})
        away_abbr = (meta.get("away") or {}).get("abbr", "")
        home_abbr = (meta.get("home") or {}).get("abbr", "")
        tag_std = f"{away_abbr}_{home_abbr}"

        game_results = results_lookup.get(tag_std)
        if not game_results:
            rev = f"{home_abbr}_{away_abbr}"
            game_results = results_lookup.get(rev)
        if not game_results:
            continue

        players_lookup = game_results.get("players", {})
        team_stats = data.get("team_stats", {})

        for abbr in [away_abbr, home_abbr]:
            is_home = abbr == home_abbr
            opp_abbr = home_abbr if is_home else away_abbr
            opp_stats = team_stats.get(opp_abbr, {})

            for player in data.get("players", {}).get(abbr, []):
                pname = player.get("name", "")
                actual_stats = players_lookup.get(pname)
                if not actual_stats:
                    continue

                adv = player.get("advanced") or {}
                splits = player.get("splits") or {}
                gl = player.get("gamelog") or {}
                fatigue = player.get("fatigue") or {}
                pa = player.get("prop_analytics") or {}

                for stat in ["PTS", "REB", "AST", "FG3M"]:
                    arr = gl.get(stat) or []
                    stat_key = STAT_KEY_MAP[stat]
                    actual_val = int(actual_stats.get(stat_key, 0))

                    for line in SPORTSBET_LINES.get(stat, []):
                        # Deterministic: hit_rate_l10 / 100
                        pa_stat = pa.get(stat) or {}
                        det_prob = 0
                        if pa_stat and "sportsbet_lines" in pa_stat:
                            for li in pa_stat["sportsbet_lines"]:
                                if li.get("line") == line:
                                    det_prob = li.get("hit_rate_L10", 0) / 100.0
                                    break
                        if det_prob == 0 and arr:
                            hits = sum(1 for x in arr if x > line)
                            det_prob = hits / len(arr)

                        # ML probability
                        features = predictor.build_features(player, stat, line, 1 if is_home else 0, opp_abbr)
                        features["opp_def_rating"] = opp_stats.get("DEF_RATING", 0) or 0
                        features["opp_def_rank"] = opp_stats.get("DEF_RANK", 0) or 0
                        features["opp_pace"] = opp_stats.get("PACE", 98.0) or 98.0
                        ml_prob = predictor.predict(features)

                        label = 1 if actual_val >= line else 0

                        records.append({
                            "game_date": game_date,
                            "game_tag": tag_std,
                            "player": pname,
                            "team": abbr,
                            "stat": stat,
                            "line": line,
                            "actual": actual_val,
                            "label": label,
                            "det_prob": round(det_prob, 4),
                            "ml_prob": ml_prob,
                        })

    return records


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    predictor = MLPropPredictor()

    dates = find_archive_dates()
    print(f"📂 Found {len(dates)} archive dates with Results_Brief")

    all_records = []
    for date in dates:
        records = evaluate_game(date, predictor)
        if records:
            all_records.extend(records)
            labeled = sum(1 for r in records)
            hits = sum(1 for r in records if r["label"] == 1)
            print(f"   {date}: {labeled} props ({hits} hits)")
        else:
            print(f"   {date}: skipped (no matching Results_Brief)")

    if not all_records:
        print("❌ No records found")
        return

    df = pd.DataFrame(all_records)

    # Aggregate metrics
    det_auc = roc_auc_score(df["label"], df["det_prob"])
    ml_auc = roc_auc_score(df["label"], df["ml_prob"])
    det_brier = brier_score_loss(df["label"], df["det_prob"])
    ml_brier = brier_score_loss(df["label"], df["ml_prob"])

    print(f"\n{'='*55}")
    print(f"📊 BACKTEST RESULTS — {len(df)} props across {df['game_date'].nunique()} dates")
    print(f"{'='*55}")
    print(f"{'Metric':<25} {'10-Factor':>10} {'ML Model':>10} {'Δ':>10}")
    print(f"{'-'*55}")
    print(f"{'ROC-AUC':<25} {det_auc:>10.4f} {ml_auc:>10.4f} {ml_auc - det_auc:>+10.4f}")
    print(f"{'Brier Score':<25} {det_brier:>10.4f} {ml_brier:>10.4f} {ml_brier - det_brier:>+10.4f}")

    # Precision@K (top 10% by probability)
    top_k = int(len(df) * 0.1)
    df_sorted_det = df.sort_values("det_prob", ascending=False)
    df_sorted_ml = df.sort_values("ml_prob", ascending=False)
    det_top = df_sorted_det.head(top_k)
    ml_top = df_sorted_ml.head(top_k)
    det_top_hit_rate = det_top["label"].mean()
    ml_top_hit_rate = ml_top["label"].mean()
    print(f"\n📊 Precision@10% (top {top_k} props):")
    print(f"{'10-Factor':<25} {det_top_hit_rate:>10.1%}")
    print(f"{'ML Model':<25} {ml_top_hit_rate:>10.1%}")
    print(f"{'Improvement':<25} {ml_top_hit_rate - det_top_hit_rate:>+10.1%}")

    # Per-stat breakdown
    print(f"\n📊 Per-Stat ROC-AUC:")
    for stat in ["PTS", "REB", "AST", "FG3M"]:
        sub = df[df["stat"] == stat]
        if len(sub) < 10:
            continue
        sd = roc_auc_score(sub["label"], sub["det_prob"])
        sm = roc_auc_score(sub["label"], sub["ml_prob"])
        print(f"   {stat:<6}  10-Factor: {sd:.4f}  ML: {sm:.4f}  Δ: {sm - sd:+.4f}")

    # Save
    csv_path = os.path.join(OUTPUT_DIR, "backtest_comparison.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n✅ Raw comparison: {csv_path}")

    results = {
        "total_props": len(df),
        "total_dates": df["game_date"].nunique(),
        "det_roc_auc": round(det_auc, 4),
        "ml_roc_auc": round(ml_auc, 4),
        "det_brier": round(det_brier, 4),
        "ml_brier": round(ml_brier, 4),
        "det_top10_hit_rate": round(float(det_top_hit_rate), 4),
        "ml_top10_hit_rate": round(float(ml_top_hit_rate), 4),
    }

    res_path = os.path.join(OUTPUT_DIR, "backtest_results.json")
    with open(res_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"✅ Results: {res_path}")
    print(f"\n📁 All outputs → {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
