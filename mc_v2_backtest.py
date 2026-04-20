#!/usr/bin/env python3
"""
MC V2.0 Back-test: Compare V2 predictions against actual ShaTin 2026-04-19 results.
"""
import json
import re
from pathlib import Path

BASE = Path('2026-04-19_ShaTin')

def extract_winners_from_results_md(filepath):
    """Extract top-4 finishers from Reflector Results.md file."""
    text = filepath.read_text(encoding='utf-8')
    
    # Pattern: 第X名 or 🥇🥈🥉🏅 followed by horse name
    winners = []
    
    # Try: | 名次 | 馬號 | 馬名 | pattern (table format)
    # Try: **第一名**: 馬名 pattern
    # Try: 🥇 / 🥈 / 🥉 patterns
    
    # Method 1: Look for "冠軍" / "亞軍" / "季軍" / "殿軍"
    place_patterns = [
        (1, r'(?:冠軍|第一名|🥇)[：:\s]*(?:#?\d+\s+)?(.+?)(?:\s*[\(（]|$|\n)'),
        (2, r'(?:亞軍|第二名|🥈)[：:\s]*(?:#?\d+\s+)?(.+?)(?:\s*[\(（]|$|\n)'),
        (3, r'(?:季軍|第三名|🥉)[：:\s]*(?:#?\d+\s+)?(.+?)(?:\s*[\(（]|$|\n)'),
        (4, r'(?:殿軍|第四名|🏅)[：:\s]*(?:#?\d+\s+)?(.+?)(?:\s*[\(（]|$|\n)'),
    ]
    
    for rank, pattern in place_patterns:
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip().strip('*').strip()
            # Clean up trailing jockey info
            name = re.sub(r'\s*[-–—]\s*.+$', '', name)
            name = re.sub(r'\s*\|.*$', '', name)
            winners.append((rank, name))
    
    if len(winners) >= 2:
        return winners
    
    # Method 2: Look for numbered list 1. horsename 2. horsename
    list_pattern = re.compile(r'^\s*(\d+)[.、)\s]\s*(.+?)(?:\s*[-–—\(（]|\s*$)', re.MULTILINE)
    matches = list(list_pattern.finditer(text))
    if len(matches) >= 3:
        winners = []
        for m in matches[:4]:
            rank = int(m.group(1))
            name = m.group(2).strip().strip('*').strip()
            winners.append((rank, name))
        return winners
    
    # Method 3: Look for table with position markers
    table_rows = re.findall(r'\|\s*(\d+)\s*\|\s*\d+\s*\|\s*(.+?)\s*\|', text)
    if table_rows:
        winners = [(int(r), n.strip()) for r, n in table_rows[:4]]
        return winners
    
    return winners


def load_mc_results(race_num):
    """Load MC V2 results for a race."""
    filepath = BASE / f'Race_{race_num}_MC_Results.json'
    if not filepath.exists():
        return None
    data = json.loads(filepath.read_text(encoding='utf-8'))
    
    # Sort by win_pct
    results = data.get('results', {})
    sorted_r = sorted(results.items(), key=lambda x: x[1]['win_pct'], reverse=True)
    
    return {
        'engine': data.get('engine_version', '?'),
        'rankings': [(i+1, name, stats['win_pct']) for i, (name, stats) in enumerate(sorted_r)],
        'top4': [name for name, _ in sorted_r[:4]],
        'concordance': data.get('concordance', {}),
    }


# ============================================================
# Main analysis
# ============================================================

print("=" * 80)
print("  MC V2.0 Back-test: ShaTin 2026-04-19 — Predicted vs Actual")
print("=" * 80)

total_races = 0
winner_in_top4 = 0
winner_in_top1 = 0
top3_in_top4 = 0
total_actual_top3 = 0

results_summary = []

for race_num in range(1, 12):
    # Find results file
    results_files = list(BASE.glob(f'*Race_{race_num}_Results.md'))
    if not results_files:
        continue
    
    mc = load_mc_results(race_num)
    if not mc:
        continue
    
    actual = extract_winners_from_results_md(results_files[0])
    if not actual:
        # Try manual extraction from filename listing
        print(f"\n--- Race {race_num}: ⚠️ Could not parse results ---")
        continue
    
    total_races += 1
    
    # Get actual winner name
    winner_name = actual[0][1] if actual else '?'
    actual_top3 = [name for _, name in actual[:3]]
    actual_top4 = [name for _, name in actual[:4]]
    
    # Find winner in MC rankings
    winner_mc_rank = '?'
    winner_mc_pct = '?'
    for rank, name, pct in mc['rankings']:
        if name == winner_name:
            winner_mc_rank = rank
            winner_mc_pct = pct
            break
    
    # Stats
    if winner_name in mc['top4']:
        winner_in_top4 += 1
    if mc['top4'] and mc['top4'][0] == winner_name:
        winner_in_top1 += 1
    
    # How many actual top3 were in MC top4?
    overlap = len(set(actual_top3) & set(mc['top4']))
    total_actual_top3 += len(actual_top3)
    top3_in_top4 += overlap
    
    # Display
    print(f"\n--- Race {race_num} ---")
    print(f"  Actual Winner: {winner_name}")
    print(f"  MC Rank: #{winner_mc_rank} ({winner_mc_pct}%)")
    print(f"  MC Top4: {mc['top4']}")
    print(f"  Actual Top3: {actual_top3}")
    
    overlap_names = set(actual_top3) & set(mc['top4'])
    miss_names = set(actual_top3) - set(mc['top4'])
    
    hit = '✅' if winner_name in mc['top4'] else '❌'
    print(f"  Winner in MC Top4: {hit}")
    print(f"  Actual Top3 ∩ MC Top4: {overlap}/3 — {overlap_names if overlap_names else '∅'}")
    if miss_names:
        print(f"  Misses: {miss_names}")
    
    results_summary.append({
        'race': race_num,
        'winner': winner_name,
        'mc_rank': winner_mc_rank,
        'mc_pct': winner_mc_pct,
        'hit': winner_name in mc['top4'],
        'overlap': overlap,
    })

# ============================================================
# Summary
# ============================================================
print(f"\n{'='*80}")
print(f"  AGGREGATE SUMMARY ({total_races} races)")
print(f"{'='*80}")
print(f"  Winner in MC Top4: {winner_in_top4}/{total_races} = {winner_in_top4/max(total_races,1)*100:.0f}%")
print(f"  Winner = MC #1:    {winner_in_top1}/{total_races} = {winner_in_top1/max(total_races,1)*100:.0f}%")
print(f"  Actual Top3 in MC Top4: {top3_in_top4}/{total_actual_top3} = {top3_in_top4/max(total_actual_top3,1)*100:.0f}%")
print()
print("  HKJC Benchmark:")
print("    Favourite win rate: ~30%")
print("    Favourite in top3:  ~65%")
print("    Top4 catch rate:    ~55-65%")
