#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
fetch_injury_domino.py
(Phase 2.2: Injury Domino Effect Engine)

This script calculates how the 'Usage Rate' is redistributed when a core player 
is marked as OUT. It identifies the direct beneficiaries and adjust the expectations
and points projections for the remaining players.
"""

import json
import argparse

# Mocked Usage Rate Matrix
USAGE_MATRIX = {
    "DEN": {
        "Nikola Jokic": 32.5,
        "Jamal Murray": 27.0,
        "Michael Porter Jr.": 20.1,
        "Aaron Gordon": 15.5
    },
    "BOS": {
        "Jayson Tatum": 30.0,
        "Jaylen Brown": 28.5,
        "Kristaps Porzingis": 22.0,
        "Derrick White": 18.0
    }
}

# Pre-defined beneficiaries logic
BENEFICIARIES = {
    "Nikola Jokic": ["Jamal Murray", "Michael Porter Jr."],
    "Jamal Murray": ["Nikola Jokic", "Reggie Jackson"],
    "Jayson Tatum": ["Jaylen Brown", "Derrick White"],
    "Kristaps Porzingis": ["Al Horford", "Jayson Tatum"]
}

def analyze_domino_effect(team, players_out):
    print(f"🚑 Analyzing Injury Domino Effect for {team}...")
    
    impact_report = []
    total_usage_vacated = 0.0
    
    team_usage = USAGE_MATRIX.get(team, {})
    
    for player in players_out:
        usage = team_usage.get(player, 15.0) # Fallback 15%
        total_usage_vacated += usage
        
        bens = BENEFICIARIES.get(player, ["Bench Unit"])
        impact_report.append({
            "player_out": player,
            "usage_vacated": usage,
            "primary_beneficiaries": bens
        })
        
    # Redistribute Usage (Mock Algorithm)
    redistribution = {}
    for ir in impact_report:
        share = ir["usage_vacated"] / len(ir["primary_beneficiaries"])
        for b in ir["primary_beneficiaries"]:
            redistribution[b] = redistribution.get(b, 0.0) + share
            
    # Print logic
    print(f"📊 Total Usage Vacated: {total_usage_vacated}%")
    print(f"💰 Usage Redistribution Map:")
    for b, amount in redistribution.items():
        print(f"   -> {b}: +{amount:.1f}% Expected Usage")
        
    # Compile text for LLM injection
    injection_text = f"🚨 **傷患骨牌效應 (Injury Domino)**:\n"
    injection_text += f"缺陣: {', '.join(players_out)} (釋放 {total_usage_vacated}% Usage Rate)\n"
    injection_text += f"最大得益者 (Usage 上升預測): "
    b_strings = [f"{b} (+{amt:.1f}%)" for b, amt in redistribution.items()]
    injection_text += ", ".join(b_strings) + "\n"
    
    print("\n--- LLM Context Injection String ---")
    print(injection_text)
    
    return injection_text

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--team', type=str, required=True, help="Team Abbreviation (e.g., DEN)")
    parser.add_argument('--out', type=str, nargs='+', required=True, help="List of players out")
    args = parser.parse_args()
    
    analyze_domino_effect(args.team, args.out)
