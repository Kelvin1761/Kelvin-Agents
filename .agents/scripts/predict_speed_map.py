#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
predict_speed_map.py — Auto Speed Map Generator from Formguide Position Data
=============================================================================

Reads a Facts.md file and auto-classifies each horse as Leader/On-Pace/Mid-Pack/Closer
based on their historical early position data (1200m markers, box positions).

Usage:
  python3 .agents/scripts/predict_speed_map.py <Facts.md> [--output-json <path>]

Output:
  JSON blob injected into race_analysis.speed_map of corresponding Logic.json
  If --output-json not specified, prints to stdout.

INTEGRATION:
  Call BEFORE LLM Batch 0 so LLM gets pre-filled Speed Map suggestion to validate/correct.
"""

import json
import re
import argparse
from pathlib import Path


# ── Classification thresholds ──────────────────────────────────────────────
# Based on average early position across last 5 races
LEADER_THRESHOLD   = 2.5   # avg position ≤ 2.5 in first 400m
ON_PACE_THRESHOLD  = 5.0   # avg position ≤ 5.0
MID_PACK_THRESHOLD = 8.0   # avg position ≤ 8.0
# > 8.0 → Closer

# ── Pace classification heuristics ────────────────────────────────────────
# Number of natural leaders determines overall pace
def classify_pace(leader_count: int, on_pace_count: int, field_size: int) -> str:
    """5-tier pace classification based on leader ratio and front pressure.

    Returns: Very Slow / Slow / Normal / Fast / Very Fast
    """
    if field_size == 0:
        return "Normal"

    front_ratio = (leader_count + on_pace_count) / field_size

    if leader_count == 0 and on_pace_count <= 1:
        return "Very Slow"
    elif leader_count <= 1 and front_ratio < 0.25:
        return "Slow"
    elif leader_count <= 2 and front_ratio < 0.35:
        return "Normal"
    elif leader_count >= 3 or front_ratio >= 0.45:
        return "Very Fast"
    else:
        return "Fast"


def classify_horse(early_positions: list, barrier: int = None) -> str:
    """
    Classify horse as Leader/On-Pace/Mid-Pack/Closer.
    
    early_positions: list of ints (position at first checkpoint, e.g. 400m/600m)
    barrier: draw number (optional, used as tiebreaker for unknown horses)
    """
    if not early_positions:
        # No history — use barrier as proxy
        if barrier is not None:
            if barrier <= 4:
                return "leader_candidate"
            elif barrier <= 8:
                return "on_pace_candidate"
        return "unknown"
    
    avg = sum(early_positions) / len(early_positions)
    
    if avg <= LEADER_THRESHOLD:
        return "leader"
    elif avg <= ON_PACE_THRESHOLD:
        return "on_pace"
    elif avg <= MID_PACK_THRESHOLD:
        return "mid_pack"
    else:
        return "closer"


def extract_early_positions_from_block(horse_block: str) -> list:
    """
    Extract early position data from a horse's race table in Facts.md.
    Looks for columns like '1200m', '800m', 'Pos' after 'Bar'.
    """
    positions = []
    
    # Pattern: table rows with position data
    # Format varies: | Date | Course | Dist | Going | Pos | ... | L400 | L200 |
    # We look for the early position (typically 3rd or 4th numeric column after header)
    
    table_lines = [l for l in horse_block.split('\n') if l.strip().startswith('|') and l.strip().endswith('|')]
    
    if not table_lines:
        return []
    
    # Find header to determine column index
    header = None
    for line in table_lines:
        if any(h in line for h in ['日期', 'Date', '#', 'Pos', '位置', '沿途']):
            header = line
            break
    
    if not header:
        return []
    
    # Try to find early position column index
    cols = [c.strip() for c in header.split('|') if c.strip()]
    early_col_idx = None
    
    for i, col in enumerate(cols):
        if any(marker in col for marker in ['早段', '1200m', '800m', '沿途', 'Early', '走位', 'P1']):
            early_col_idx = i
            break
    
    # Fallback: try column 4-6 range (commonly early position in AU/HKJC tables)
    if early_col_idx is None:
        early_col_idx = 4  # Default guess
    
    for line in table_lines:
        cells = [c.strip() for c in line.split('|') if c.strip()]
        # Skip header/delimiter rows
        if not cells or any(h in cells[0] for h in ['日期', 'Date', '---', ':---']):
            continue
        if early_col_idx < len(cells):
            val = cells[early_col_idx].strip().replace('`', '').replace('[', '').replace(']', '')
            # Parse numeric position
            m = re.match(r'^(\d+)', val)
            if m:
                pos = int(m.group(1))
                if 1 <= pos <= 30:  # sanity check
                    positions.append(pos)
    
    return positions[-5:]  # Last 5 races only


def parse_facts_md_horses(facts_text: str) -> list:
    """Parse horse blocks from Facts.md (works for both HKJC and AU formats)."""
    horses = []
    
    # Try HKJC format: ## 馬匹 #N or ### 馬匹 #N  
    # Try AU format: ### 馬匹 #N Name (檔位 X)
    patterns = [
        re.compile(r'^#{2,3}\s+馬匹\s*#(\d+)\s+(.+?)\s+\(檔位\s*(\d+)\)', re.MULTILINE),
        re.compile(r'^#{2,3}\s+(?:No\.)?(\d+)[\.、]\s*(.+?)\s+\|\s*.*?檔位.*?(\d+)', re.MULTILINE | re.IGNORECASE),
        re.compile(r'\*\*【No\.(\d+)】\s*(.+?)\*\*.*?檔位:(\d+)', re.MULTILINE),
        re.compile(r'^#{2,3}\s+馬號\s*(\d+)\s*—\s*(.+?)\s*\|.*?檔位:\s*(\d+)', re.MULTILINE),
    ]
    
    matches = []
    for pattern in patterns:
        matches = list(pattern.finditer(facts_text))
        if matches:
            break
    
    if not matches:
        # Fallback: try lines starting with horse markers
        for m in re.finditer(r'(?:#{2,3}|##)\s*(?:馬匹)?\s*#?(\d+)[.、\s]+(.+?)\s*[\n(]', facts_text, re.MULTILINE):
            barrier_m = re.search(r'檔位[：:]\s*(\d+)', facts_text[m.start():m.start()+200])
            barrier = int(barrier_m.group(1)) if barrier_m else None
            matches.append(type('Match', (), {
                'group': lambda self, i: [None, m.group(1), m.group(2), str(barrier) if barrier else '1'][i],
                'start': lambda self: m.start(),
                '__class__': type('', (), {'__name__': 'NaiveMatch'})()
            })())
    
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(facts_text)
        block = facts_text[start:end]
        
        try:
            h_num = int(match.group(1))
            h_name = match.group(2).strip() if match.group(2) else f"Horse {h_num}"
            h_barrier = int(match.group(3)) if match.group(3) else h_num
        except (ValueError, TypeError):
            continue
        
        early_positions = extract_early_positions_from_block(block)
        horse_type = classify_horse(early_positions, h_barrier)
        
        horses.append({
            'num': h_num,
            'name': h_name,
            'barrier': h_barrier,
            'early_positions': early_positions,
            'classification': horse_type,
        })
    
    return horses


def build_speed_map(horses: list) -> dict:
    """Build the speed_map dict from classified horses."""
    leaders   = [str(h['num']) for h in horses if 'leader' in h['classification']]
    on_pace   = [str(h['num']) for h in horses if h['classification'] == 'on_pace']
    mid_pack  = [str(h['num']) for h in horses if h['classification'] == 'mid_pack']
    closers   = [str(h['num']) for h in horses if h['classification'] == 'closer']
    unknowns  = [str(h['num']) for h in horses if 'unknown' in h['classification'] or 'candidate' in h['classification']]
    
    # Distribute unknowns into mid_pack by default
    mid_pack.extend(unknowns)
    
    field_size = len(horses)
    pace = classify_pace(len(leaders), len(on_pace), field_size)
    
    return {
        "predicted_pace": pace,
        "leaders": leaders,
        "on_pace": on_pace,
        "mid_pack": mid_pack,
        "closers": closers,
        "track_bias": "[待天氣情報補充 — LLM 必須根據 Intelligence 填寫]",
        "tactical_nodes": "[待 Batch 0 分析 — LLM 必須填寫具體戰術節點]",
        "collapse_point": f"[{'無前領壓力，步速大幅收慢' if pace in ('Very Slow', 'Slow') else '步速拉鋸爭崩' if pace in ('Fast', 'Very Fast') else '中速穩定'}]",
        "_auto_generated": True,
        "_note": "由 predict_speed_map.py 根據往績沿途位數據自動分類。LLM 必須驗證並補充 track_bias、tactical_nodes、collapse_point。"
    }


def main():
    parser = argparse.ArgumentParser(description="Auto Speed Map Generator")
    parser.add_argument("facts", help="Path to Facts.md")
    parser.add_argument("--output-json", help="Output JSON file path (default: stdout)")
    parser.add_argument("--inject-into", help="Existing Logic.json to inject speed_map into")
    args = parser.parse_args()
    
    facts_text = Path(args.facts).read_text(encoding='utf-8')
    horses = parse_facts_md_horses(facts_text)
    
    if not horses:
        print(f"⚠️ No horses parsed from {args.facts}")
        sys.exit(1)
    
    speed_map = build_speed_map(horses)
    
    print(f"\n📍 Speed Map 自動生成結果 ({args.facts}):")
    print(f"   步速預測: {speed_map['predicted_pace']}")
    print(f"   領放群: {', '.join(speed_map['leaders']) or '(無明顯領放)'}")
    print(f"   前中段: {', '.join(speed_map['on_pace']) or '(無)'}")
    print(f"   中後段: {', '.join(speed_map['mid_pack']) or '(無)'}")
    print(f"   後上群: {', '.join(speed_map['closers']) or '(無)'}")
    print(f"\n   分類詳情:")
    for h in horses:
        print(f"   - [{h['num']}] {h['name']} (檔位:{h['barrier']}) → {h['classification']} (近況位置: {h['early_positions'][-3:] if h['early_positions'] else '無數據'})")
    
    if args.inject_into and os.path.exists(args.inject_into):
        with open(args.inject_into, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
        
        if 'race_analysis' not in logic_data:
            logic_data['race_analysis'] = {}
        
        # Only inject if speed_map is missing or auto-generated
        existing_sm = logic_data['race_analysis'].get('speed_map', {})
        if not existing_sm or existing_sm.get('_auto_generated') or existing_sm.get('predicted_pace') == '[FILL]':
            logic_data['race_analysis']['speed_map'] = speed_map
            with open(args.inject_into, 'w', encoding='utf-8') as f:
                json.dump(logic_data, f, ensure_ascii=False, indent=2)
            print(f"\n✅ Speed Map 已注入 → {args.inject_into}")
        else:
            print(f"\n⏭️  Speed Map 已存在且非自動生成，略過注入。")
    else:
        output = json.dumps({"speed_map": speed_map}, ensure_ascii=False, indent=2)
        if args.output_json:
            Path(args.output_json).write_text(output, encoding='utf-8')
            print(f"\n✅ Speed Map JSON → {args.output_json}")
        else:
            print(f"\n{output}")


if __name__ == "__main__":
    main()
