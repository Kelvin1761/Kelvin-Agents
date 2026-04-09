#!/usr/bin/env python3
"""
Monte Carlo Racing Simulation Engine (Shadow Mode)
Usage: python run_monte_carlo.py --target_dir "/path/to/meeting/dir"

This script performs quantitative Monte Carlo simulations (10,000 iterations)
to derive the True Odds of each horse. It then injects a Markdown table
into the existing `*_Analysis.md` files at the designated tag position,
ensuring zero interference with the LLM's qualitative reasoning.
"""

import os
import re
import glob
import argparse
import numpy as np
import pandas as pd

def parse_facts_md(filepath):
    """
    Parses a Facts.md file to extract horse data from the Markdown tables.
    Returns a dict mapping horse_num -> { name, l400_list, margin_list }
    """
    if not os.path.exists(filepath):
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    horses = {}
    current_horse_num = None
    current_horse_name = None

    # Regex to find horse headers like: ### 馬號 1 — 浪漫勇士 | 騎師: 麥道朗 ...
    horse_pattern = re.compile(r'###\s+馬號\s+(\d+)\s+—\s+(.*?)\s*\|')

    lines = content.split('\n')
    for line in lines:
        horse_match = horse_pattern.search(line)
        if horse_match:
            current_horse_num = int(horse_match.group(1).strip())
            current_horse_name = horse_match.group(2).strip()
            horses[current_horse_num] = {
                'name': current_horse_name,
                'l400_list': [],
                'win_margin_list': []
            }
            continue

        # Look for the markdown table rows for the current horse
        if current_horse_num and line.startswith('|') and not line.startswith('| #') and not line.startswith('|-'):
            cols = [c.strip() for c in line.split('|')]
            if len(cols) > 12:
                # Based on Facts.md table:
                # | # | 日期 | 場地 | 距離 | 班次 | 檔位 | 騎師 | 負磅 | 名次 | 頭馬距離 | 能量 | L400 | ...
                margin_str = cols[10]
                l400_str = cols[12]
                
                try:
                    if l400_str != '-':
                        horses[current_horse_num]['l400_list'].append(float(l400_str))
                except ValueError:
                    pass

                # Parse margin (e.g. "1-1/4", "SH", "N", "2")
                if margin_str != '-':
                    val = parse_margin(margin_str)
                    horses[current_horse_num]['win_margin_list'].append(val)

    return horses

def parse_margin(margin_str):
    if margin_str in ['-', '']: return 0.0
    if 'SH' in margin_str: return 0.1
    if 'N' in margin_str: return 0.2
    if 'HD' in margin_str: return 0.25
    if 'SN' in margin_str: return 0.15
    if 'ML' in margin_str: return 0.05
    if 'DH' in margin_str: return 0.0
    
    try:
        if '-' in margin_str:
            parts = margin_str.split('-')
            whole = float(parts[0])
            frac_parts = parts[1].split('/')
            frac = float(frac_parts[0]) / float(frac_parts[1]) if len(frac_parts) == 2 else 0
            return whole + frac
        elif '/' in margin_str:
            frac_parts = margin_str.split('/')
            return float(frac_parts[0]) / float(frac_parts[1])
        else:
            return float(margin_str)
    except:
        return 5.0 # fallback

def run_simulation(horses_data, iterations=10000):
    """
    Runs Monte Carlo simulations.
    Returns list of dicts: [{'horse_num': 1, 'name': 'A', 'win_prob': 0.25, 'true_odds': 4.0}, ...]
    """
    results = []
    horse_nums = list(horses_data.keys())
    
    if not horse_nums:
        return []

    # Prepare mu and sigma matrices
    mu_list = []
    sigma_list = []
    
    for h_num in horse_nums:
        data = horses_data[h_num]
        l400 = data['l400_list']
        margin = data['win_margin_list']
        
        # Calculate Base Rating (Lower is better, means faster time / smaller margin)
        if l400:
            base_mu = np.mean(l400)
            base_sigma = np.std(l400) if len(l400) > 1 else 0.5
        elif margin:
            base_mu = 23.0 + np.mean(margin) * 0.1 # Fallback approximation
            base_sigma = np.std(margin) * 0.1 if len(margin) > 1 else 0.5
        else:
            base_mu = 24.5 # Slow fallback
            base_sigma = 1.0
            
        # Prevent 0 standard deviation collapses
        if base_sigma < 0.1:
            base_sigma = 0.2
            
        mu_list.append(base_mu)
        sigma_list.append(base_sigma)
        
    mu_array = np.array(mu_list)
    sigma_array = np.array(sigma_list)
    
    # Run Simulation Matrix
    # Shape: (num_horses, iterations)
    sim_matrix = np.random.normal(loc=mu_array[:, None], scale=sigma_array[:, None], size=(len(horse_nums), iterations))
    
    # Find the winner of each iteration (argmin since lower time/score is better)
    winners = np.argmin(sim_matrix, axis=0)
    
    # Calculate Probabilities
    for idx, h_num in enumerate(horse_nums):
        wins = np.sum(winners == idx)
        win_prob = wins / iterations
        true_odds = (1 / win_prob) if win_prob > 0 else 999.0
        
        results.append({
            'horse_num': h_num,
            'name': horses_data[h_num]['name'],
            'win_prob': win_prob,
            'true_odds': true_odds
        })
        
    # Sort by probability descending
    results = sorted(results, key=lambda x: x['win_prob'], reverse=True)
    return results

def inject_markdown_table(analysis_path, simulation_results):
    """
    Finds the <!-- MONTE_CARLO_PYTHON_INJECT_HERE --> tag in the analysis markdown
    and injects the simulation table.
    """
    if not os.path.exists(analysis_path):
        return False
        
    with open(analysis_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    tag = "<!-- MONTE_CARLO_PYTHON_INJECT_HERE -->"
    if tag not in content:
        return False
        
    # Create the markdown table
    md_table = [
        "| 馬號 | 馬名 | MC 模擬勝率 | MC 真實賠率 (True Odds) |",
        "|---|---|---|---|"
    ]
    
    for res in simulation_results:
        prob_str = f"{res['win_prob']*100:.1f}%"
        odds_str = f"{res['true_odds']:.2f}" if res['true_odds'] < 999 else "999+"
        # Highlight strong values
        if res['win_prob'] > 0.30:
            odds_str = f"**{odds_str}** ⭐️"
            
        md_table.append(f"| {res['horse_num']} | {res['name']} | {prob_str} | {odds_str} |")
        
    table_str = "\n".join(md_table)
    new_content = content.replace(tag, table_str)
    
    with open(analysis_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    return True

def export_csv(csv_path, simulation_results):
    df = pd.DataFrame(simulation_results)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')

def process_directory(target_dir):
    print(f"🎲 Monte Carlo Engine starting for {target_dir}")
    
    facts_files = glob.glob(os.path.join(target_dir, "*_Facts.md"))
    for facts_path in facts_files:
        basename = os.path.basename(facts_path)
        # Assuming naming: Race_1_Facts.md
        race_match = re.search(r'(Race_\d+)', basename)
        if not race_match:
            continue
            
        race_prefix = race_match.group(1)
        analysis_path = os.path.join(target_dir, f"{race_prefix}_Analysis.md")
        csv_path = os.path.join(target_dir, f"{race_prefix}_Monte_Carlo.csv")
        
        horses_data = parse_facts_md(facts_path)
        if not horses_data:
            print(f"  [Skipping] No valid horse data found in {basename}")
            continue
            
        results = run_simulation(horses_data)
        
        # Export shadow CSV
        export_csv(csv_path, results)
        
        # Inject to Analysis Markdown
        if inject_markdown_table(analysis_path, results):
            print(f"  ✅ {race_prefix}: Injected Monte Carlo Table")
        else:
            print(f"  ⚠️ {race_prefix}: Tag not found in Analysis.md, saved CSV only")
            
    print("🎲 Monte Carlo Engine processing complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Monte Carlo Dynamic Simulation Engine")
    parser.add_argument('--target_dir', type=str, required=True, help="Path to meeting directory")
    args = parser.parse_args()
    
    process_directory(args.target_dir)
