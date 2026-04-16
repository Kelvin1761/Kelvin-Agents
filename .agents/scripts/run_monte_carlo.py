#!/usr/bin/env python3
"""
Monte Carlo Racing Simulation Engine (Shadow Mode) V2
Usage: python run_monte_carlo.py --target_dir "/path/to/meeting/dir"

This script performs quantitative Monte Carlo simulations (10,000 iterations)
to derive the True Odds of each horse. It then injects an enhanced Markdown table
into the existing `*_Analysis.md` files at the designated tag position,
ensuring zero interference with the LLM's qualitative reasoning.

V2 Enhancements:
- MC排名 (MC Ranking by probability)
- 馬號 (Horse Number) column
- 預測賠率 (Predicted Odds from MC simulation)
- 法證排名 (Original Forensic Analysis Ranking)
- 差異 (Agreement/Divergence indicator)
"""

import os
import re
import glob
import csv
import io
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

def parse_original_ranking(analysis_path):
    """
    Parses the Analysis.md to extract Top 4 forensic analysis ranking.
    Looks for the CSV block and Top 4 verdict section.
    Returns dict: {horse_num: rank_position} e.g. {2: 1, 4: 2, 10: 3, 1: 4}
    """
    if not os.path.exists(analysis_path):
        return {}

    with open(analysis_path, 'r', encoding='utf-8') as f:
        content = f.read()

    rankings = {}

    # Method 1: Parse ```csv block — skip if contains PLACEHOLDER
    csv_match = re.search(r'```csv\s*\n(.*?)```', content, re.DOTALL)
    if csv_match:
        csv_text = csv_match.group(1).strip()
        if 'PLACEHOLDER' not in csv_text and csv_text:
            try:
                reader = csv.DictReader(io.StringIO(csv_text))
                for rank_idx, row in enumerate(reader, 1):
                    h_num_raw = row.get('horse_num', row.get('horse_number', '0'))
                    h_num = int(str(h_num_raw).strip())
                    if h_num > 0:
                        rankings[h_num] = rank_idx
            except Exception:
                pass

    # Method 2: Parse Top 4 verdict markers from compiled format
    # Supports: "- **馬號及馬名:** [1] 馬達"  AND  "- **馬號及馬名:** 1 馬達"
    if not rankings:
        rank_patterns = [
            (r'\U0001f947 \*\*第一選\*\*.*?馬號及馬名:\*\*\s*\[?(\d+)\]?', 1),
            (r'\U0001f948 \*\*第二選\*\*.*?馬號及馬名:\*\*\s*\[?(\d+)\]?', 2),
            (r'\U0001f949 \*\*第三選\*\*.*?馬號及馬名:\*\*\s*\[?(\d+)\]?', 3),
            (r'\U0001f3c5 \*\*第四選\*\*.*?馬號及馬名:\*\*\s*\[?(\d+)\]?', 4),
        ]
        for pattern, rank in rank_patterns:
            m = re.search(pattern, content, re.DOTALL)
            if m:
                rankings[int(m.group(1))] = rank

    # Method 3: Fallback — derive full ranking from ⭐ 最終評級 grades in analysis
    if not rankings:
        grade_order = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'E', 'E-']
        horse_grades = []
        for m in re.finditer(r'\*\*【No\.(\d+)】.*?⭐ 最終評級:\s*`([^`]+)`', content, re.DOTALL):
            h_num = int(m.group(1))
            grade = m.group(2).strip()
            grade_idx = grade_order.index(grade) if grade in grade_order else 99
            horse_grades.append((h_num, grade_idx))
        horse_grades.sort(key=lambda x: (x[1], x[0]))
        for rank_idx, (h_num, _) in enumerate(horse_grades, 1):
            rankings[h_num] = rank_idx

    return rankings


def run_simulation(horses_data, iterations=10000):
    """
    Runs Monte Carlo simulations.
    Returns list of dicts with mc_rank, horse_num, name, win_prob, true_odds.
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
    
    # Find rankings for each iteration (argsort since lower time/score is better)
    ranks = np.argsort(sim_matrix, axis=0)
    winners = ranks[0, :]
    
    # Calculate Probabilities
    for idx, h_num in enumerate(horse_nums):
        wins = np.sum(winners == idx)
        top3_count = np.sum(np.any(ranks[:3, :] == idx, axis=0))
        top4_count = np.sum(np.any(ranks[:4, :] == idx, axis=0))
        
        win_prob = wins / iterations
        top3_prob = top3_count / iterations
        top4_prob = top4_count / iterations
        true_odds = (1 / win_prob) if win_prob > 0 else 999.0
        
        results.append({
            'horse_num': h_num,
            'name': horses_data[h_num]['name'],
            'win_prob': win_prob,
            'top3_prob': top3_prob,
            'top4_prob': top4_prob,
            'true_odds': true_odds
        })
        
    # Sort by probability descending and assign MC rank
    results = sorted(results, key=lambda x: x['win_prob'], reverse=True)
    for mc_rank, res in enumerate(results, 1):
        res['mc_rank'] = mc_rank
    return results

def inject_markdown_table(analysis_path, simulation_results, original_rankings=None):
    """
    Finds the existing Monte Carlo section or <!-- MONTE_CARLO_PYTHON_INJECT_HERE --> tag 
    in the analysis markdown and injects the enhanced simulation table with ranking comparison.
    
    V2 columns: MC排名 | 馬號 | 馬名 | MC 勝率 | 預測賠率 | 法證排名 | 差異
    """
    if not os.path.exists(analysis_path):
        return False
        
    with open(analysis_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    tag1 = "#### 📊 Monte Carlo 概率模擬 (10,000 次)"
    tag2 = "<!-- MONTE_CARLO_PYTHON_INJECT_HERE -->"
    
    insert_pos = -1
    if tag1 in content:
        insert_pos = content.find(tag1)
    elif tag2 in content:
        insert_pos = content.find(tag2)
        
    if insert_pos == -1:
        # If neither tag is found, we will just append to the end
        pass
    else:
        # Strip everything from the insertion point downwards to cleanly replace
        content = content[:insert_pos].strip() + "\n\n"

    original_rankings = original_rankings or {}
    rank_icons = {1: '🥇', 2: '🥈', 3: '🥉', 4: '🏅'}
        
    # Create the enhanced markdown table
    md_table = [
        "#### 📊 Monte Carlo 概率模擬 (10,000 次)",
        "",
        "> 🐍 由 Python `run_monte_carlo.py` 自動計算 | V2 9-Column Enhanced Distribution",
        "",
        "| MC排名 | 馬號 | 馬名 | MC 勝率 | 預測賠率 | Top 3% | Top 4% | 法證排名 | 差異 |",
        "|--------|------|------|---------|---------|--------|--------|---------|------|"
    ]
    
    for res in simulation_results:
        mc_rank = res.get('mc_rank', '?')
        mc_rank_icon = rank_icons.get(mc_rank, str(mc_rank))
        prob_str = f"{res['win_prob']*100:.1f}%"
        odds_val = res['true_odds']
        odds_str = f"${odds_val:.2f}" if odds_val < 999 else "$999+"
        top3_str = f"{res['top3_prob']*100:.1f}%"
        top4_str = f"{res['top4_prob']*100:.1f}%"
        
        # Highlight top probability
        if res['win_prob'] > 0.25:
            prob_str = f"**{prob_str}** ⭐️"
            odds_str = f"**{odds_str}** ⭐️"

        # Original forensic ranking
        h_num = res['horse_num']
        orig_rank = original_rankings.get(h_num)
        if orig_rank:
            orig_icon = rank_icons.get(orig_rank, f'#{orig_rank}')
            orig_str = f"{orig_icon} #{orig_rank}"
        else:
            orig_str = "—"
        
        # Agreement/divergence indicator
        if orig_rank and mc_rank:
            diff = abs(mc_rank - orig_rank)
            if diff == 0:
                diff_str = "✅ 一致"
            elif diff == 1:
                diff_str = "🔄 ±1"
            elif diff <= 2:
                diff_str = "⚠️ ±" + str(diff)
            else:
                diff_str = "❌ ±" + str(diff)
        elif orig_rank is None and mc_rank <= 4:
            diff_str = "🆕 MC獨有"
        else:
            diff_str = "—"
            
        md_table.append(f"| {mc_rank_icon} | {h_num} | {res['name']} | {prob_str} | {odds_str} | {top3_str} | {top4_str} | {orig_str} | {diff_str} |")
        
    table_str = "\n".join(md_table)
    
    # Check if there is an existing target path and save it
    new_content = content + "\n\n" + table_str + "\n"
    
    with open(analysis_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    return True

def export_csv(csv_path, simulation_results):
    df = pd.DataFrame(simulation_results)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')

def process_directory(target_dir):
    print(f"🎲 Monte Carlo Engine V2 starting for {target_dir}")
    
    facts_files = glob.glob(os.path.join(target_dir, "*Facts.md"))
    for facts_path in facts_files:
        basename = os.path.basename(facts_path)
        # Assuming naming: Race 1 Facts.md or Race_1_Facts.md
        race_match = re.search(r'(Race[ _]\d+)', basename)
        if not race_match:
            continue
            
        race_prefix = race_match.group(1).replace(" ", "_")
        # Find the actual date prefix for the Analysis file
        analysis_prefix = basename.replace(" Facts.md", "").replace("_Facts.md", "")
        analysis_path = os.path.join(target_dir, f"{analysis_prefix} Analysis.md")
        if not os.path.exists(analysis_path):
            analysis_path = os.path.join(target_dir, f"{analysis_prefix}_Analysis.md")
        csv_path = os.path.join(target_dir, f"{race_prefix}_Monte_Carlo.csv")
        
        horses_data = parse_facts_md(facts_path)
        if not horses_data:
            print(f"  [Skipping] No valid horse data found in {basename}")
            continue
        
        # Parse original forensic rankings from Analysis.md
        original_rankings = parse_original_ranking(analysis_path)
        if original_rankings:
            print(f"  📋 {race_prefix}: Found forensic rankings: {original_rankings}")
        else:
            print(f"  ⚠️ {race_prefix}: No forensic rankings found in Analysis.md")
            
        results = run_simulation(horses_data)
        
        # Attach original rankings to results for CSV export
        for res in results:
            res['original_rank'] = original_rankings.get(res['horse_num'], None)
        
        # Export shadow CSV
        export_csv(csv_path, results)
        
        # Inject to Analysis Markdown with ranking comparison
        if inject_markdown_table(analysis_path, results, original_rankings):
            print(f"  ✅ {race_prefix}: Injected Enhanced Monte Carlo Table")
        else:
            print(f"  ⚠️ {race_prefix}: Tag not found in Analysis.md, saved CSV only")
            
    print("🎲 Monte Carlo Engine V2 processing complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Monte Carlo Dynamic Simulation Engine")
    parser.add_argument('--target_dir', type=str, required=True, help="Path to meeting directory")
    args = parser.parse_args()
    
    process_directory(args.target_dir)
