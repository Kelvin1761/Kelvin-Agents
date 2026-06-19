#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR))
from au_sip_tester import load_all_races, evaluate_races, report_summary, delta_report, _print_summary, _print_delta

def sip_lower_stability(horses, race):
    for h in horses:
        stability = float(h.get("matrix_scores", {}).get("stability", 60))
        sectional = float(h.get("matrix_scores", {}).get("sectional", 60))
        # Reduce stability by 6%, increase sectional by 6%
        delta = (sectional * 0.06) - (stability * 0.06)
        h["rank_score"] += delta
    return horses

def sip_plodder_penalty(horses, race):
    for h in horses:
        stability = float(h.get("matrix_scores", {}).get("stability", 60))
        class_w = float(h.get("matrix_scores", {}).get("class_weight", 60))
        sectional = float(h.get("matrix_scores", {}).get("sectional", 60))
        
        penalty = 0.0
        # If stability is very high but sectional & class are low -> pure plodder
        if stability >= 72 and sectional < 60 and class_w < 60:
            penalty = -3.0
        elif stability >= 70 and sectional < 60:
            penalty = -1.5
            
        h["rank_score"] += penalty
    return horses

def sip_ml_search_combo(horses, race):
    # What if we apply BOTH? A mild shift and a penalty
    for h in horses:
        stability = float(h.get("matrix_scores", {}).get("stability", 60))
        sectional = float(h.get("matrix_scores", {}).get("sectional", 60))
        class_w = float(h.get("matrix_scores", {}).get("class_weight", 60))
        
        delta = (sectional * 0.03) - (stability * 0.03)
        h["rank_score"] += delta
        
        if stability >= 70 and sectional < 60:
            h["rank_score"] -= 1.5
            
    return horses

def main():
    races = load_all_races()
    print(f"Loaded {len(races)} races from archive")
    
    bl_overall, _, _, _ = evaluate_races(races, "Baseline")
    bl_summary = report_summary(bl_overall, "Baseline")
    print("\n--- BASELINE (Current Engine) ---")
    _print_summary(bl_summary)
    
    print("\n--- TEST 1: Direct Weight Rebalance (-6% Stability, +6% Sectional) ---")
    ov1, _, _, _ = evaluate_races(races, "WeightShift", sip_lower_stability)
    _print_summary(report_summary(ov1, "WeightShift"))
    _print_delta(delta_report(bl_overall, ov1))
    
    print("\n--- TEST 2: Plodder Penalty (-3 if High Stability but Low Sec/Class) ---")
    ov2, _, _, _ = evaluate_races(races, "PlodderCap", sip_plodder_penalty)
    _print_summary(report_summary(ov2, "PlodderCap"))
    _print_delta(delta_report(bl_overall, ov2))
    
    print("\n--- TEST 3: Hybrid (Mild Rebalance + Mild Penalty) ---")
    ov3, _, _, _ = evaluate_races(races, "Hybrid", sip_ml_search_combo)
    _print_summary(report_summary(ov3, "Hybrid"))
    _print_delta(delta_report(bl_overall, ov3))

if __name__ == "__main__":
    main()
