#!/usr/bin/env python3
"""
monte_carlo_au.py — AU Racing Monte Carlo Simulation Adapter

AU-specific adapter for monte_carlo_core. Handles AU data formats
(kg weights, different column layouts, synthetic/turf track types).

Called automatically by au_orchestrator.py during State 4 (Compile).

Usage:
  python3 monte_carlo_au.py <logic_json> <facts_md> [--output <mc_json>]

Version: 1.0.0
"""
import sys, io, json, os, argparse, re, math

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Import core engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Core engine lives in HKJC scripts dir — add to path
hkjc_scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', '..', '..', 'hkjc_racing', 'hkjc_wong_choi', 'scripts')
sys.path.insert(0, os.path.abspath(hkjc_scripts))

from monte_carlo_core import (
    monte_carlo_race, format_mc_table,
    compute_stability_index, compute_formline_adj,
    weighted_stats
)


def parse_sectional_from_facts(facts_content, horse_num):
    """Extract last 400m/600m sectional times from AU Facts.md."""
    pattern = rf'### 馬號 {horse_num}\b|### No\.{horse_num}\b|### \[#{horse_num}\]'
    match = re.search(pattern, facts_content)
    if not match:
        # Try alternate format: "### No.X — Name"
        pattern2 = rf'### (?:No\.|馬號 ){horse_num} — '
        match = re.search(pattern2, facts_content)
    if not match:
        return []
    
    start = match.start()
    next_match = re.search(r'### (?:No\.|馬號 )\d+', facts_content[match.end():])
    end = match.end() + next_match.start() if next_match else len(facts_content)
    block = facts_content[start:end]
    
    # Extract sectional times (AU format: last 600m or last 400m, range 20-28)
    l400_values = []
    table_rows = re.findall(r'^\|(.+)\|$', block, re.MULTILINE)
    for row in table_rows:
        cols = [c.strip() for c in row.split('|')]
        for col in cols:
            try:
                val = float(col)
                if 19.0 <= val <= 28.0:
                    l400_values.append(val)
                    break
            except (ValueError, TypeError):
                continue
    
    return l400_values[:6]


def parse_energy_from_facts(facts_content, horse_num):
    """Extract energy/efficiency values from AU Facts.md."""
    pattern = rf'### (?:No\.|馬號 ){horse_num} — '
    match = re.search(pattern, facts_content)
    if not match:
        return []
    
    start = match.start()
    next_match = re.search(r'### (?:No\.|馬號 )\d+', facts_content[match.end():])
    end = match.end() + next_match.start() if next_match else len(facts_content)
    block = facts_content[start:end]
    
    energy_values = []
    table_rows = re.findall(r'^\|(.+)\|$', block, re.MULTILINE)
    for row in table_rows:
        cols = [c.strip() for c in row.split('|')]
        for col in cols:
            try:
                val = float(col)
                if 70.0 <= val <= 140.0:
                    energy_values.append(val)
                    break
            except (ValueError, TypeError):
                continue
    
    return energy_values[:6]


def parse_finish_positions_au(facts_content, horse_num):
    """Extract recent finish positions from AU Facts.md."""
    pattern = rf'### (?:No\.|馬號 ){horse_num} — '
    match = re.search(pattern, facts_content)
    if not match:
        return []
    
    start = match.start()
    next_match = re.search(r'### (?:No\.|馬號 )\d+', facts_content[match.end():])
    end = match.end() + next_match.start() if next_match else len(facts_content)
    block = facts_content[start:end]
    
    positions = []
    table_rows = re.findall(r'^\|(.+)\|$', block, re.MULTILINE)
    for row in table_rows:
        cols = [c.strip() for c in row.split('|')]
        if len(cols) >= 10:
            for col_idx in [8, 9]:
                try:
                    val = int(cols[col_idx])
                    if 1 <= val <= 20:
                        positions.append(val)
                        break
                except (ValueError, TypeError, IndexError):
                    continue
    
    return positions[:6]


def extract_horse_mc_data_au(logic_data, facts_content, horse_key):
    """Extract MC data for a single AU horse."""
    horse = logic_data.get('horses', {}).get(horse_key, {})
    horse_num = int(horse_key)
    field_size = len(logic_data.get('horses', {}))
    
    l400_vals = parse_sectional_from_facts(facts_content, horse_num)
    energy_vals = parse_energy_from_facts(facts_content, horse_num)
    finishes = parse_finish_positions_au(facts_content, horse_num)
    
    # Compute statistics (exponential decay weighted)
    if l400_vals:
        days_ago = [i * 21 for i in range(len(l400_vals))]
        mean_speed, sd_speed = weighted_stats(l400_vals, days_ago)
    else:
        mean_speed = 23.5
        sd_speed = 0.8
    
    if energy_vals:
        days_ago = [i * 21 for i in range(len(energy_vals))]
        mean_energy, sd_energy = weighted_stats(energy_vals, days_ago)
    else:
        mean_energy = 100.0
        sd_energy = 5.0
    
    # Matrix risk markers
    matrix = horse.get('matrix', {})
    risk_markers = sum(1 for v in matrix.values() if isinstance(v, dict) and v.get('score') == '❌')
    
    # Forgiveness
    forgiveness = horse.get('forgiveness_archive', {})
    forgiveness_bonus = isinstance(forgiveness, dict) and '寬恕' in str(forgiveness.get('conclusion', ''))
    
    # Determine running style from speed_map
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
    running_style = 'mid_pack'
    for style, key in [('leader', 'leaders'), ('on_pace', 'on_pace'),
                       ('mid_pack', 'mid_pack'), ('closer', 'closers')]:
        if horse_key in [str(m) for m in speed_map.get(key, [])]:
            running_style = style
            break
    
    return {
        'name': horse.get('horse_name', f'No.{horse_key}'),
        'mean_speed': round(mean_speed, 3),
        'sd_speed': round(sd_speed, 3),
        'mean_energy': round(mean_energy, 2),
        'sd_energy': round(sd_energy, 2),
        'stability_idx': compute_stability_index(finishes),
        'trainer_win_rate': horse.get('trainer_win_rate', 0.12),
        'jockey_win_rate': horse.get('jockey_win_rate', 0.08),
        'days_since_last': horse.get('days_since_last', 21),
        'finishes': finishes,
        'class_advantage': horse.get('class_advantage', 0.0),
        'weight': horse.get('weight', 57),
        'barrier': horse.get('barrier', 1),
        'field_size': field_size,
        'risk_markers': risk_markers,
        'running_style': running_style,
        'track_bias_benefit': horse.get('track_bias_benefit', False),
        'forgiveness_bonus': forgiveness_bonus,
        'weight_gain': horse.get('weight_gain', 0),
        'same_venue_dist_wins': horse.get('same_venue_dist_wins', 0),
        'is_hkjc': False,
    }


def main():
    parser = argparse.ArgumentParser(description='AU Racing Monte Carlo Simulation')
    parser.add_argument('logic_json', help='Path to Race_X_Logic.json')
    parser.add_argument('facts_md', help='Path to Facts.md')
    parser.add_argument('--output', help='Output MC results JSON path')
    parser.add_argument('--n', type=int, default=10000, help='Simulation count')
    parser.add_argument('--analysis', help='Path to Analysis.md for MC injection')
    args = parser.parse_args()
    
    with open(args.logic_json, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    
    with open(args.facts_md, 'r', encoding='utf-8') as f:
        facts_content = f.read()
    
    horses = []
    for horse_key in sorted(logic_data.get('horses', {}).keys(), key=lambda x: int(x)):
        horse_data = logic_data['horses'][horse_key]
        if '[FILL]' in json.dumps(horse_data):
            print(f"⚠️ No.{horse_key} still has [FILL], skipping MC")
            continue
        mc_horse = extract_horse_mc_data_au(logic_data, facts_content, horse_key)
        horses.append(mc_horse)
    
    if len(horses) < 3:
        print(f"❌ Only {len(horses)} horses analyzed, need ≥3 for MC")
        sys.exit(1)
    
    print(f"🎲 Running Monte Carlo for {len(horses)} horses ({args.n:,} iterations)...")
    # Extract pace scenario from speed_map
    pace_scenario = logic_data.get('race_analysis', {}).get('speed_map', {}).get('predicted_pace')
    if not pace_scenario:
        pace_scenario = logic_data.get('race_analysis', {}).get('speed_map', {}).get('expected_pace')
    mc_results = monte_carlo_race(horses, n=args.n, pace_scenario=pace_scenario)
    
    # Get Top 4 from matrix
    top4_picks = []
    grade_order = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D']
    rated = []
    for hk, hd in logic_data.get('horses', {}).items():
        r = hd.get('final_rating', 'D')
        if isinstance(r, str) and r in grade_order:
            rated.append((hd.get('horse_name', '?'), grade_order.index(r)))
    rated.sort(key=lambda x: x[1])
    top4_picks = [h[0] for h in rated[:4]]
    
    print(format_mc_table(mc_results, top4_picks))
    
    output_path = args.output
    if not output_path:
        logic_dir = os.path.dirname(args.logic_json)
        race_match = re.search(r'Race_(\d+)', args.logic_json)
        race_num = race_match.group(1) if race_match else '0'
        output_path = os.path.join(logic_dir, f'Race_{race_num}_MC.json')
    
    mc_output = {
        'simulations': args.n,
        'horses_count': len(horses),
        'results': mc_results,
        'top4_matrix': top4_picks,
        'concordance': len(set(top4_picks) & set(sorted(mc_results, key=lambda n: mc_results[n]['win_pct'], reverse=True)[:4])),
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mc_output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ MC results saved to: {output_path}")
    
    # Inject into Analysis.md if path provided
    if args.analysis and os.path.exists(args.analysis):
        mc_table = format_mc_table(mc_results, top4_picks)
        with open(args.analysis, 'r', encoding='utf-8') as f:
            content = f.read()
        tag1 = "#### 📊 Monte Carlo 概率模擬"
        tag2 = "<!-- MONTE_CARLO_PYTHON_INJECT_HERE -->"
        inject_done = False
        for tag in [tag1, tag2]:
            if tag in content:
                pos = content.find(tag)
                rest = content[pos:]
                end_match = re.search(r'\n(## |---)', rest)
                end_pos = pos + end_match.start() if end_match else len(content)
                content = content[:pos] + mc_table + "\n" + content[end_pos:]
                inject_done = True
                break
        if not inject_done:
            csv_tag = "## [第五部分]"
            if csv_tag in content:
                pos = content.find(csv_tag)
                content = content[:pos] + mc_table + "\n\n" + content[pos:]
            else:
                content = content.rstrip() + "\n\n" + mc_table + "\n"
        with open(args.analysis, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ MC results injected into: {args.analysis}")


if __name__ == '__main__':
    main()
