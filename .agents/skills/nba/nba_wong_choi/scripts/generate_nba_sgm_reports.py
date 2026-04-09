#!/usr/bin/env python3
"""
generate_nba_sgm_reports.py — NBA Wong Choi 最終報告生成器

從 Game_*_Full_Analysis.md 提取組合分析區塊，自動合併生成兩份最終報告：
  1. NBA_All_SGM_Report.txt — 全日所有場次、所有組合嘅完整 Leg 分析
  2. NBA_Banker_Report.txt  — 每場組合 1 (穩膽) 完整分析 + Top Banker 速覽 + 跨場 Parlay

Usage:
  python3 generate_nba_sgm_reports.py --dir "2026-04-08 NBA Analysis"

Version: 1.0.0
"""

import argparse
import glob
import os
import re
import sys
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def extract_matchup_from_filename(filename):
    """Extract matchup tag (e.g., 'CHA_BOS') from Game_*_Full_Analysis.md filename."""
    base = os.path.basename(filename)
    match = re.search(r'NBA_(.+?)_Analysis\.md', base)
    if match:
        return match.group(1)
    return base


def extract_game_header(content):
    """Extract the game header section (title + 賽事情報)."""
    lines = content.split('\n')
    header_lines = []
    in_header = False
    for line in lines:
        if line.startswith('# 🏀') or line.startswith('# '):
            in_header = True
        if in_header:
            header_lines.append(line)
            if line.strip() == '---' and len(header_lines) > 3:
                break
    return '\n'.join(header_lines) if header_lines else ''


def extract_combos(content):
    """Extract all combo sections (## 🎯 組合 N) with their full leg analysis."""
    combos = {}
    lines = content.split('\n')
    current_combo = None
    current_lines = []
    combo_pattern = re.compile(r'^## 🎯 組合 (\d+)')

    for line in lines:
        m = combo_pattern.match(line)
        if m:
            # Save previous combo
            if current_combo is not None:
                combos[current_combo] = '\n'.join(current_lines).rstrip()
            current_combo = int(m.group(1))
            current_lines = [line]
        elif current_combo is not None:
            # Check for end markers
            if line.startswith('## 💣') or line.startswith('## 📝') or line.startswith('## 💡'):
                combos[current_combo] = '\n'.join(current_lines).rstrip()
                current_combo = None
                current_lines = []
            else:
                current_lines.append(line)

    # Save last combo
    if current_combo is not None:
        combos[current_combo] = '\n'.join(current_lines).rstrip()

    return combos


def extract_value_bomb(content):
    """Extract the Value Bomb section if it exists."""
    lines = content.split('\n')
    bomb_lines = []
    in_bomb = False
    for line in lines:
        if line.startswith('## 💣') or line.startswith('## 💣'):
            in_bomb = True
        elif in_bomb and (line.startswith('## ') or line.startswith('# ')):
            break
        if in_bomb:
            bomb_lines.append(line)
    return '\n'.join(bomb_lines) if bomb_lines else ''


def extract_summary(content):
    """Extract the 總結 section."""
    lines = content.split('\n')
    summary_lines = []
    in_summary = False
    for line in lines:
        if '總結' in line and line.startswith('## '):
            in_summary = True
        elif in_summary and line.startswith('## '):
            break
        if in_summary:
            summary_lines.append(line)
    return '\n'.join(summary_lines) if summary_lines else ''


def extract_banker_leg(content):
    """Extract the strongest single banker leg from the summary section."""
    match = re.search(r'最強一關.*?[：:]\s*(.+?)(?:\n|$)', content)
    if match:
        return match.group(1).strip()
    return None


def generate_all_sgm_report(games_data, analysis_date):
    """Generate the All SGM Report with full leg analysis for every combo."""
    lines = []
    lines.append(f'# 🏀 NBA Wong Choi 全日 SGM 完整分析報告')
    lines.append(f'# 📅 日期: {analysis_date} | 總場次: {len(games_data)}')
    lines.append(f'# 📋 此報告包含每個 Leg 嘅完整數理引擎 + 邏輯引擎分析')
    lines.append('')

    for game in games_data:
        tag = game['tag']
        lines.append('=' * 60)
        lines.append(f'## {tag.replace("_", " @ ")}')
        lines.append('=' * 60)
        lines.append('')

        # Add all combos with full analysis
        for combo_num in sorted(game['combos'].keys()):
            combo_content = game['combos'][combo_num]
            # Remove the leading ## to make it fit under the game section
            lines.append(combo_content)
            lines.append('')

        # Add Value Bomb if exists
        if game.get('value_bomb'):
            lines.append(game['value_bomb'])
            lines.append('')

        # Add summary
        if game.get('summary'):
            lines.append(game['summary'])
            lines.append('')

        lines.append('')

    # Footer stats
    lines.append('=' * 60)
    lines.append('# 📊 全日統計')
    lines.append('=' * 60)
    total_combos = sum(len(g['combos']) for g in games_data)
    total_vb = sum(1 for g in games_data if g.get('value_bomb'))
    lines.append(f'總場次: {len(games_data)}')
    lines.append(f'總組合數: {total_combos}')
    lines.append(f'Value Bomb: {total_vb} 場')
    lines.append('')

    return '\n'.join(lines)


def generate_banker_report(games_data, analysis_date):
    """Generate the Banker Report with combo 1 full analysis + top banker table."""
    lines = []
    lines.append(f'# 🛡️ NBA Wong Choi 全日穩膽 Banker 完整分析報告')
    lines.append(f'# 📅 日期: {analysis_date} | 總場次: {len(games_data)}')
    lines.append(f'# 策略: 收錄每場組合 1 (穩膽 SGM) 嘅完整 Leg 分析')
    lines.append('')

    # Section 1: Top Banker Legs quick reference
    lines.append('=' * 60)
    lines.append('## 📋 全日 Top Banker Legs 速覽')
    lines.append('=' * 60)
    lines.append('')
    lines.append('| # | 場次 | Banker Leg | 來源 |')
    lines.append('|---|------|-----------|------|')

    for i, game in enumerate(games_data, 1):
        tag_display = tag_to_display(game['tag'])
        banker = game.get('banker_leg', 'N/A')
        lines.append(f'| {i} | {tag_display} | {banker} | 組合 1 |')

    lines.append('')

    # Section 2: Full combo 1 analysis per game
    lines.append('=' * 60)
    lines.append('## 🏆 逐場穩膽 SGM 完整分析')
    lines.append('=' * 60)
    lines.append('')

    for game in games_data:
        tag = game['tag']
        lines.append('-' * 50)
        lines.append(f'### {tag.replace("_", " @ ")}')
        lines.append('-' * 50)
        lines.append('')

        if 1 in game['combos']:
            lines.append(game['combos'][1])
        else:
            lines.append('⚠️ 本場冇組合 1 (穩膽) 數據')
        lines.append('')

    # Section 3: Risk notes
    lines.append('=' * 60)
    lines.append('## ⚠️ 全日風險提示')
    lines.append('=' * 60)
    lines.append('')
    for game in games_data:
        summary = game.get('summary', '')
        if '風險' in summary or 'Risk' in summary or '⚠️' in summary:
            lines.append(f'- {tag_to_display(game["tag"])}: 見完整分析')

    lines.append('')
    return '\n'.join(lines)


def tag_to_display(tag):
    """Convert CHA_BOS to CHA@BOS."""
    parts = tag.split('_')
    if len(parts) == 2:
        return f'{parts[0]}@{parts[1]}'
    return tag


def main():
    parser = argparse.ArgumentParser(description='NBA Wong Choi SGM Report Generator')
    parser.add_argument('--dir', required=True, help='Path to the NBA Analysis directory')
    parser.add_argument('--date', default=None, help='Analysis date (auto-detected from dir name)')
    args = parser.parse_args()

    target_dir = args.dir
    if not os.path.isdir(target_dir):
        print(f'❌ 目錄不存在: {target_dir}')
        sys.exit(1)

    # Auto-detect date from directory name
    analysis_date = args.date
    if not analysis_date:
        dir_name = os.path.basename(os.path.normpath(target_dir))
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', dir_name)
        if date_match:
            analysis_date = date_match.group(1)
        else:
            analysis_date = 'Unknown'

    # Find all game analysis files
    pattern = os.path.join(target_dir, '*_NBA_*_Analysis.md')
    files = sorted(glob.glob(pattern))

    if not files:
        print(f'⚠️ 搵唔到任何 *_NBA_*_Analysis.md 喺 {target_dir}')
        sys.exit(1)

    print(f'📂 掃描目錄: {target_dir}')
    print(f'📅 分析日期: {analysis_date}')
    print(f'📄 搵到 {len(files)} 場賽事分析')

    # Process each game file
    games_data = []
    for fpath in files:
        tag = extract_matchup_from_filename(fpath)
        print(f'  📖 讀取: {os.path.basename(fpath)}')

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        combos = extract_combos(content)
        value_bomb = extract_value_bomb(content)
        summary = extract_summary(content)
        banker_leg = extract_banker_leg(content)

        print(f'    ✅ 組合: {len(combos)} 個 | Value Bomb: {"有" if value_bomb else "冇"} | Banker: {banker_leg[:40] if banker_leg else "N/A"}')

        games_data.append({
            'tag': tag,
            'combos': combos,
            'value_bomb': value_bomb,
            'summary': summary,
            'banker_leg': banker_leg or 'N/A',
        })

    # Generate reports
    print(f'\n📝 生成報告中...')

    # All SGM Report
    all_sgm = generate_all_sgm_report(games_data, analysis_date)
    all_sgm_path = os.path.join(target_dir, 'NBA_All_SGM_Report.txt')
    with open(all_sgm_path, 'w', encoding='utf-8') as f:
        f.write(all_sgm)
    print(f'  ✅ NBA_All_SGM_Report.txt ({len(all_sgm)} bytes)')

    # Banker Report
    banker = generate_banker_report(games_data, analysis_date)
    banker_path = os.path.join(target_dir, 'NBA_Banker_Report.txt')
    with open(banker_path, 'w', encoding='utf-8') as f:
        f.write(banker)
    print(f'  ✅ NBA_Banker_Report.txt ({len(banker)} bytes)')

    print(f'\n🏆 完成！報告已生成至:')
    print(f'  📄 {all_sgm_path}')
    print(f'  📄 {banker_path}')


if __name__ == '__main__':
    main()
