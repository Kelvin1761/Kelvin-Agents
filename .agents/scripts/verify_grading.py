#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys, os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Verification script: test grading engine against real Race 7 & 8 analysis files.
"""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rating_engine_v2 import compute_weighted_score, compute_base_grade, apply_fine_tune, grade_sort_index

# Import the parse_md function from fill_hkjc_verdicts
from fill_hkjc_verdicts import parse_md

RACE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".." , "2026-04-15_HappyValley")

print("=" * 70)
print("VERIFICATION: Real Race Data End-to-End Test")
print("=" * 70)

for race_num in [7, 8]:
    filepath = f"{RACE_DIR}/04-15_HappyValley Race {race_num} Analysis.md"
    if not os.path.exists(filepath):
        print(f"\n⚠️  Race {race_num} file not found, skipping")
        continue
    
    ranked, _ = parse_md(filepath)
    
    print(f"\n{'─' * 60}")
    print(f"📋 Race {race_num} — Top 4 Ranking (by weighted_score)")
    print(f"{'─' * 60}")
    print(f"{'Rank':<5} {'Horse':<20} {'Grade':<8} {'Score':<6} {'✅':<4} {'❌':<4}")
    print(f"{'─' * 60}")
    
    for i, h in enumerate(ranked[:4], 1):
        emoji = ['🥇', '🥈', '🥉', '🏅'][i-1]
        print(f" {emoji}  [{h['num']:>2}] {h['name']:<16} {h['grade']:<8} {h['weighted_score']:>4}   {h['total_strong']:>2}   {h['tot_cross']:>2}")
    
    if len(ranked) > 4:
        print(f"  ... and {len(ranked)-4} more horses")
        for h in ranked[4:]:
            print(f"      [{h['num']:>2}] {h['name']:<16} {h['grade']:<8} {h['weighted_score']:>4}   {h['total_strong']:>2}   {h['tot_cross']:>2}")

# Specific validation: R8 H2 vs R7 H1
print(f"\n{'=' * 60}")
print("🔍 KEY VALIDATION: R8 H2 瑪瑙 vs R7 H1 當家精彩")
print(f"{'=' * 60}")

r8_ranked, _ = parse_md(f"{RACE_DIR}/04-15_HappyValley Race 8 Analysis.md")
r7_ranked, _ = parse_md(f"{RACE_DIR}/04-15_HappyValley Race 7 Analysis.md")

r8_h2 = next((h for h in r8_ranked if h['num'] == 2), None)
r7_h1 = next((h for h in r7_ranked if h['num'] == 1), None)

if r8_h2 and r7_h1:
    print(f"  R8 H2 瑪瑙:     score={r8_h2['weighted_score']}, grade={r8_h2['grade']}, ✅={r8_h2['total_strong']}")
    print(f"  R7 H1 當家精彩:  score={r7_h1['weighted_score']}, grade={r7_h1['grade']}, ✅={r7_h1['total_strong']}")
    
    if r8_h2['weighted_score'] >= r7_h1['weighted_score']:
        print(f"\n  ✅ PASS: 瑪瑙 (score={r8_h2['weighted_score']}) ≥ 當家精彩 (score={r7_h1['weighted_score']})")
        print(f"  → 唔會再出現「高分低評」問題！")
    else:
        print(f"\n  ❌ FAIL: Unexpected score ordering")
else:
    print("  ⚠️  Could not find one or both horses")

print(f"\n{'=' * 60}")
print("Verification complete!")
