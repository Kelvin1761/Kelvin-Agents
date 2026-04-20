#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
scratch_handler.py — Late Scratching Handler

Handles late scratchings by removing the scratched horse data from
Logic.json, marking them in Facts.md, and resetting the race for
re-analysis by the orchestrator.

Usage:
  python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/scratch_handler.py <target_dir> <race_num> --scratched <horse_nums>

Example:
  python scratch_handler.py 2026-04-12_ShaTin 2 --scratched 5,8
"""
import json
import re
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Late Scratching Handler')
    parser.add_argument('target_dir', help='Target analysis directory')
    parser.add_argument('race_num', type=int, help='Race number')
    parser.add_argument('--scratched', required=True, help='Comma-separated horse numbers to scratch')
    parser.add_argument('--domain', choices=['hkjc', 'au'], default='hkjc')
    args = parser.parse_args()

    target_dir = os.path.abspath(args.target_dir)
    race_num = args.race_num
    scratched_nums = [int(x.strip()) for x in args.scratched.split(',')]

    print("=" * 60)
    print(f"🔄 Late Scratching Handler — Race {race_num}")
    print(f"   被退賽馬號: {scratched_nums}")
    print("=" * 60)

    # 1. Find relevant files
    date_prefix = ""
    for f in os.listdir(target_dir):
        m = re.match(r'(\d{2}-\d{2})', f)
        if m:
            date_prefix = m.group(1)
            break

    logic_json = os.path.join(target_dir, f"Race_{race_num}_Logic.json")
    analysis_md = None
    facts_md = None

    for f in os.listdir(target_dir):
        if f.endswith(f'Race {race_num} Analysis.md'):
            analysis_md = os.path.join(target_dir, f)
        if f.endswith(f'Race {race_num} Facts.md'):
            facts_md = os.path.join(target_dir, f)

    # 2. Process Logic.json — remove scratched horses
    if os.path.exists(logic_json):
        with open(logic_json, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)

        horses = logic_data.get('horses', {})
        removed = []
        for num in scratched_nums:
            for key in [str(num), num]:
                if str(key) in horses:
                    name = horses[str(key)].get('horse_name', f'Horse #{num}')
                    del horses[str(key)]
                    removed.append(f"#{num} {name}")

        logic_data['horses'] = horses

        # Add scratching metadata
        logic_data.setdefault('_scratching_log', [])
        logic_data['_scratching_log'].append({
            'scratched_horses': scratched_nums,
            'action': 'removed_from_logic'
        })

        # Reset verdict if exists (need recompute with fewer horses)
        if 'race_analysis' in logic_data:
            if 'verdict' in logic_data['race_analysis']:
                # Reset top4 picks that reference scratched horses
                verdict = logic_data['race_analysis']['verdict']
                if 'top4' in verdict:
                    new_top4 = [t for t in verdict['top4']
                               if int(t.get('horse_num', t.get('horse_number', 0))) not in scratched_nums]
                    verdict['top4'] = new_top4
                    if len(new_top4) < 4:
                        print(f"   ⚠️ Top 4 受影響，需要重新生成 Verdict")

        with open(logic_json, 'w', encoding='utf-8') as f:
            json.dump(logic_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Logic.json — 已移除: {', '.join(removed)}")
    else:
        print(f"⚠️ Logic.json 不存在: {logic_json}")

    # 3. Delete Analysis.md (force regeneration)
    if analysis_md and os.path.exists(analysis_md):
        os.remove(analysis_md)
        print(f"✅ Analysis.md — 已刪除 (將自動重新生成)")
    else:
        print(f"ℹ️ Analysis.md 不存在，無需刪除")

    # 4. Mark scratched horses in Facts.md
    if facts_md and os.path.exists(facts_md):
        content = Path(facts_md).read_text(encoding='utf-8')
        for num in scratched_nums:
            # Mark horse header with ⛔
            content = re.sub(
                rf'(### 馬號 {num} — )',
                rf'⛔ [已退出] \1',
                content
            )
            content = re.sub(
                rf'(\[#{num}\])',
                rf'⛔ [已退出] \1',
                content
            )
        Path(facts_md).write_text(content, encoding='utf-8')
        print(f"✅ Facts.md — 已標記退賽馬匹")
    else:
        print(f"⚠️ Facts.md 不存在: {facts_md}")

    # 5. Reset QA strikes for this race
    strikes_path = os.path.join(target_dir, '.qa_strikes.json')
    if os.path.exists(strikes_path):
        with open(strikes_path, 'r', encoding='utf-8') as f:
            strikes = json.load(f)
        if str(race_num) in strikes:
            del strikes[str(race_num)]
            with open(strikes_path, 'w', encoding='utf-8') as f:
                json.dump(strikes, f)
            print(f"✅ QA Strikes — 已重置 Race {race_num}")

    # 6. Summary
    print(f"\n{'='*60}")
    print(f"✅ Race {race_num} 已準備好重新分析！")
    print(f"   下一步：重新執行 Orchestrator")
    if args.domain == 'hkjc':
        print(f"   python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py {os.path.basename(target_dir)}")
    else:
        print(f"   python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py <URL>")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
