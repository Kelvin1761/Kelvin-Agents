#!/usr/bin/env python3
"""Extract Top 4 CSV from all analysis files for both Kelvin and Heison."""
import re, os

BASE = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"

def extract_csv(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = r'```csv\s*\r?\n(.*?)\r?\n```'
    csv_match = re.search(pattern, content, re.DOTALL)
    if csv_match:
        csv_lines = csv_match.group(1).strip().split('\n')
        return [l.strip() for l in csv_lines if l.strip() and not l.strip().startswith('Race,')]
    return []

k_dir = os.path.join(BASE, '2026-04-06_ShaTin (Kelvin)')
h_dir = os.path.join(BASE, '2026-04-04 Sha Tin (Heison)')

print('=== KELVIN TOP 4 ===')
for i in range(1, 12):
    fpath = os.path.join(k_dir, f'04-06_Race_{i}_Analysis.md')
    if os.path.exists(fpath):
        rows = extract_csv(fpath)
        print(f'R{i}: ' + ' | '.join(rows[:4]))

print('\n=== HEISON TOP 4 ===')
for i in range(1, 12):
    fpath = os.path.join(h_dir, f'04-06_Race_{i}_Analysis.md')
    if os.path.exists(fpath):
        rows = extract_csv(fpath)
        print(f'R{i}: ' + ' | '.join(rows[:4]))
