#!/usr/bin/env python3
"""Quick diagnostic: parse Race 9 and show top_picks + horse grades."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from services.parser_hkjc import parse_hkjc_analysis

target = os.path.join(
    os.path.dirname(__file__), '..', 
    '2026-04-15_HappyValley', '04-15_HappyValley Race 9 Analysis.md'
)

result = parse_hkjc_analysis(target)
if not result:
    print("❌ parse_analysis_file returned None")
    sys.exit(1)

print("=" * 60)
print(f"Race {result.race_number}")
print("=" * 60)
print("\n📊 All Horse Grades (from parser):")
for h in result.horses:
    print(f"  #{h.horse_number:2d}  {h.horse_name:8s}  grade={h.final_grade}")

print("\n🏆 Top Picks (final, after sorting):")
for p in result.top_picks:
    print(f"  Rank {p.rank}: #{p.horse_number} {p.horse_name} [{p.grade}]")
