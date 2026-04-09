#!/usr/bin/env python3
"""
fetch_nba_h2h.py
(Phase 2.5: H2H Historic Data Integration)

This script searches a mock API (or balldontlie/odds api) for historical matchups
between two teams. It extracts the mean (average performance / margins) and computes
a direct comparison against the current Bookmaker Line to flag significant deviations
that can be injected into the Expected Win Rate Model.
"""

import argparse
import random

def fetch_h2h_historic_data(team_a, team_b, stat_type="points_margin"):
    print(f"🔄 Fetching H2H Historic Data for {team_a} vs {team_b}...")
    
    # Mocking fetching from an API (e.g., past 5 games)
    # E.g., Team A's points minus Team B's points
    past_margins = [random.randint(-15, 15) for _ in range(5)]
    
    mean_margin = sum(past_margins) / len(past_margins)
    margin_range = (min(past_margins), max(past_margins))
    
    print(f"📊 Past 5 Matchups Margins ({team_a} advantage): {past_margins}")
    print(f"📈 History Mean: {mean_margin:+.1f} | Range: {margin_range[0]} to {margin_range[1]}")
    
    return {
        "mean_margin": mean_margin,
        "past_margins": past_margins
    }

def calculate_h2h_probability_injection(team_a, team_b, current_line):
    """
    Compares the historical average to the current bookmaker line.
    Returns a probability adjustment weight.
    """
    h2h_data = fetch_h2h_historic_data(team_a, team_b)
    mean_margin = h2h_data["mean_margin"]
    
    # Line is usually relative to Team A (e.g., -5.5 means Team A favored by 5.5)
    # Let's say Team A is favored by 5.5 -> current_line = 5.5
    # If mean_margin is +10, then Team A historically outperforms the current 5.5 line
    
    discrepancy = mean_margin - current_line
    
    # Simple probability injection calculation
    # For every 1 pt of positive discrepancy, add 1.5% probability to the Expected Win Rate
    prob_bump = discrepancy * 1.5
    
    injection_text = (
        f"⚔️ **H2H 歷史交手權重 (H2H Injection)**:\n"
        f" {team_a} 對 {team_b} 近 5 場場均淨勝: {mean_margin:+.1f} 分\n"
        f" 莊家開盤 (Line): {team_a} {current_line:+.1f}\n"
        f" 現價偏差 (Discrepancy): {discrepancy:+.1f} 分\n"
    )
    
    if discrepancy > 3.0:
        injection_text += f" 📈 結論: {team_a} 歷史明顯剋制對手，建議勝率模型注入 +{abs(prob_bump):.1f}%。\n"
    elif discrepancy < -3.0:
        injection_text += f" 📉 結論: {team_a} 歷史明顯被對手剋制，建議勝率模型扣減 -{abs(prob_bump):.1f}%。\n"
    else:
        injection_text += f" ⚖️ 結論: 歷史交手與現盤相符，無須大幅微調勝率權重。\n"
        
    print("\n--- LLM Context Injection String ---")
    print(injection_text)
    return injection_text

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--team_a', type=str, required=True, help="Home Team (e.g. BOS)")
    parser.add_argument('--team_b', type=str, required=True, help="Away Team (e.g. MIA)")
    parser.add_argument('--line', type=float, required=True, help="Current Bookmaker Line for Team A (e.g. 5.5)")
    args = parser.parse_args()
    
    calculate_h2h_probability_injection(args.team_a, args.team_b, args.line)
