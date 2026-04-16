#!/usr/bin/env python3
"""
AU Monte Carlo Injection Script
Reads Race_X_MC_Results.json and injects the MC table into 04-15 Race X Analysis.md
Injection point: before ## [第五部分] 📊 數據庫匯出 (CSV)
Usage: python inject_mc_au.py <meeting_dir> [--races 1 2 3 ...]
"""

import os
import re
import json
import argparse

INJECT_ANCHOR = "## [第五部分] 📊 數據庫匯出 (CSV)"
MC_SECTION_HEADER = "## [第四點五部分] 🎲 Monte Carlo 概率模擬 (10,000 次)"

RANK_ICONS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟",
              "1️⃣1️⃣", "1️⃣2️⃣", "1️⃣3️⃣", "1️⃣4️⃣"]

FORENSIC_RANK_LABELS = {0: "🥇 #1", 1: "🥈 #2", 2: "🥉 #3", 3: "🏅 #4"}


def get_forensic_ranking(logic_json_path: str) -> tuple:
    """Extract forensic ranking + horse numbers from Logic JSON.
    Returns: (ranking_dict {name: rank_idx}, horse_num_dict {name: horse_num})
    """
    if not logic_json_path or not os.path.exists(logic_json_path):
        return {}, {}
    try:
        with open(logic_json_path) as f:
            data = json.load(f)
        horses = data.get("horses", {})
        # Build horse number map: key in JSON is the horse number (stall/barrier)
        horse_nums = {}
        for key, h in horses.items():
            if "horse_name" in h:
                horse_nums[h["horse_name"]] = str(key)
        # Sort by final_rating descending for forensic ranking
        grade_order = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D']
        rated = [(h["horse_name"], h.get("final_rating", 'D'))
                 for h in horses.values() if "horse_name" in h]
        rated.sort(key=lambda x: grade_order.index(x[1]) if x[1] in grade_order else len(grade_order))
        ranking = {name: idx for idx, (name, _) in enumerate(rated)}
        return ranking, horse_nums
    except Exception:
        return {}, {}


def build_mc_table(results: dict, forensic_ranking: dict = None, horse_nums: dict = None) -> str:
    """Build enriched MC markdown table with horse number, odds and forensic rank comparison."""
    sorted_horses = sorted(results.items(), key=lambda x: x[1]['win_pct'], reverse=True)

    lines = []
    lines.append(MC_SECTION_HEADER)
    lines.append("")
    lines.append("> 基於 10,000 次模擬，以 Final Rating 作加權概率分佈計算。")
    lines.append("")
    lines.append("| MC排名 | 馬號 | 馬名 | 勝出% | MC獨贏 | 入三甲% | MC位置 | 入四甲% | 法證排名 | 差異 |")
    lines.append("|--------|------|------|-------|--------|---------|--------|---------|---------|------|")

    for i, (name, stats) in enumerate(sorted_horses):
        icon = RANK_ICONS[i] if i < len(RANK_ICONS) else f"{i+1}"
        win_pct = stats['win_pct']
        win   = f"{win_pct:.1f}%"
        odds  = f"${(100/win_pct):.1f}" if win_pct > 0 else "$999+"
        top3_pct = stats['top3_pct']
        top3  = f"{top3_pct:.1f}%"
        place_odds = f"${(100/top3_pct):.1f}" if top3_pct > 0 else "$999+"
        top4  = f"{stats['top4_pct']:.1f}%"
        h_num = horse_nums.get(name, "—") if horse_nums else "—"

        # Forensic rank column
        if forensic_ranking and name in forensic_ranking:
            f_idx = forensic_ranking[name]
            f_label = FORENSIC_RANK_LABELS.get(f_idx, f"#{f_idx+1}")
            diff = i - f_idx
            if diff == 0:
                diff_str = "✅ 一致"
            elif abs(diff) == 1:
                diff_str = "🔄 ±1"
            else:
                arrow = "⬆️" if diff < 0 else "⬇️"
                diff_str = f"❌ {arrow}{abs(diff)}"
        else:
            f_label = "—"
            diff_str = "🆕 MC獨有"

        lines.append(f"| {icon} | {h_num} | {name} | {win} | {odds} | {top3} | {place_odds} | {top4} | {f_label} | {diff_str} |")

    lines.append("")

    # Top 3 verdict
    top3_list = sorted_horses[:3]
    lines.append("**🎯 MC 最佳三選:**")
    for i, (name, stats) in enumerate(top3_list):
        win_pct = stats['win_pct']
        odds_str = f"${(100/win_pct):.1f}" if win_pct > 0 else "$999+"
        lines.append(f"- **#{i+1}** {name} — 勝出 {win_pct:.1f}% (預測賠率 {odds_str})，入三甲 {stats['top3_pct']:.1f}%")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def inject_into_analysis(analysis_path: str, mc_table: str) -> bool:
    """Inject MC table before the CSV export section."""
    with open(analysis_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove existing MC section if already injected (idempotent)
    if MC_SECTION_HEADER in content:
        # Remove old MC block
        mc_start = content.find(MC_SECTION_HEADER)
        mc_end = content.find(INJECT_ANCHOR, mc_start)
        if mc_end != -1:
            content = content[:mc_start] + content[mc_end:]
        else:
            # Remove to end of file (shouldn't happen but safety)
            content = content[:mc_start]

    # Find inject anchor
    if INJECT_ANCHOR in content:
        pos = content.find(INJECT_ANCHOR)
        content = content[:pos] + mc_table + content[pos:]
        with open(analysis_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    else:
        # Append to end as fallback
        content = content.rstrip() + "\n\n" + mc_table
        with open(analysis_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ⚠️  Anchor not found — appended to end of file")
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_dir", help="Path to meeting directory")
    parser.add_argument("--races", nargs="*", type=int, default=list(range(1, 9)),
                        help="Race numbers to process (default: 1-8)")
    args = parser.parse_args()

    meeting_dir = args.meeting_dir
    races = args.races

    # Auto-detect meeting date from folder name (YYYY-MM-DD format)
    folder_name = os.path.basename(meeting_dir)
    # Match YYYY-MM-DD and extract MM-DD
    date_match = re.search(r'\d{4}-(\d{2}-\d{2})', folder_name)
    date_prefix = date_match.group(1) if date_match else "04-15"

    print(f"🎲 AU Monte Carlo Injection")
    print(f"📁 Meeting: {folder_name}")
    print(f"🏇 Races: {races}")
    print()

    for race_num in races:
        mc_path = os.path.join(meeting_dir, f"Race_{race_num}_MC_Results.json")
        analysis_path = os.path.join(meeting_dir, f"{date_prefix} Race {race_num} Analysis.md")
        logic_path = os.path.join(meeting_dir, f"Race_{race_num}_Logic.json")

        if not os.path.exists(mc_path):
            print(f"⚠️  Race {race_num}: MC JSON not found ({mc_path})")
            continue

        if not os.path.exists(analysis_path):
            print(f"⚠️  Race {race_num}: Analysis.md not found ({analysis_path})")
            continue

        with open(mc_path, 'r', encoding='utf-8') as f:
            mc_data = json.load(f)

        results = mc_data.get('results', {})
        if not results:
            print(f"⚠️  Race {race_num}: No results in MC JSON")
            continue

        # Load forensic ranking + horse numbers from Logic JSON
        forensic_ranking, horse_nums = get_forensic_ranking(logic_path)
        if forensic_ranking:
            print(f"  📋 Forensic ranking loaded ({len(forensic_ranking)} horses)")

        mc_table = build_mc_table(results, forensic_ranking, horse_nums)
        success = inject_into_analysis(analysis_path, mc_table)

        if success:
            top1 = max(results.items(), key=lambda x: x[1]['win_pct'])
            win_pct = top1[1]['win_pct']
            odds = f"${(100/win_pct):.1f}" if win_pct > 0 else "$999+"
            print(f"✅ Race {race_num}: Injected → Top pick: {top1[0]} ({win_pct:.1f}% win, {odds})")
        else:
            print(f"❌ Race {race_num}: Injection failed")

    print()
    print("✅ MC Injection complete.")




if __name__ == "__main__":
    main()
