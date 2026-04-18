#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
"""
create_hkjc_logic_skeleton.py — V9 Python-Native Skeleton Generator

Extracts factual data from HKJC Facts.md for a SINGLE horse and
pre-fills Logic.json. LLM only needs to fill [FILL] analysis fields.

Usage:
  python3 create_hkjc_logic_skeleton.py <facts_path> <race_num> <horse_num>
"""
import sys, re, json, os, argparse, io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def extract_race_header(facts_content):
    """Extract race-level info (venue, distance, class) from Facts.md header."""
    result = {}
    m = re.search(r'場地:\s*(.+?)\s*\|', facts_content)
    if m: result['venue'] = m.group(1).strip()
    m = re.search(r'距離:\s*(.+?)\s*\|', facts_content)
    if m: result['distance'] = m.group(1).strip()
    m = re.search(r'班次:\s*(.+?)(?:\n|$)', facts_content)
    if m: result['race_class'] = m.group(1).strip()
    return result


def extract_horse_block(facts_content, horse_num):
    """Extract the text block for a single horse from Facts.md."""
    pattern = rf'### 馬號 {horse_num} — '
    match = re.search(pattern, facts_content)
    if not match:
        return None

    start = match.start()
    # Find next horse header or end of file
    next_match = re.search(r'### 馬號 \d+ — ', facts_content[match.end():])
    if next_match:
        end = match.end() + next_match.start()
    else:
        end = len(facts_content)

    return facts_content[start:end]


def parse_horse_header(block):
    """Extract name, jockey, trainer, weight, barrier from header line."""
    m = re.search(
        r'### 馬號 (\d+) — (.+?) \| 騎師:\s*(.+?) \| 練馬師:\s*(.+?) \| 負磅:\s*(\d+) \| 檔位:\s*(\d+)',
        block
    )
    if not m:
        return {}
    return {
        'num': int(m.group(1)),
        'name': m.group(2).strip(),
        'jockey': m.group(3).strip(),
        'trainer': m.group(4).strip(),
        'weight': int(m.group(5)),
        'barrier': int(m.group(6)),
    }


def parse_summary(block):
    """Extract last_6, days_since_last, season stats."""
    result = {}
    m = re.search(r'\*\*近六場:\*\*\s*(.+?)\s*\(', block)
    if not m:
        m = re.search(r'\*\*近六場:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m:
        result['last_6'] = m.group(1).strip()

    m = re.search(r'\*\*休後復出:\*\*\s*(\d+)', block)
    if m:
        result['days_since_last'] = int(m.group(1))
    else:
        result['days_since_last'] = 0

    m = re.search(r'\*\*統計:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m:
        result['season_stats'] = m.group(1).strip()

    return result


def parse_recent_race(block):
    """Extract L400, position, consumption etc. from the MOST RECENT race row."""
    # Find the main race table (完整賽績檔案)
    table_start = re.search(r'完整賽績檔案.*?\n(\|[^\n]+\n\|[-\| ]+\n)', block, re.DOTALL)
    if not table_start:
        return {}

    # Get first data row after table header
    remaining = block[table_start.end():]
    first_line = remaining.split('\n')[0]
    if not first_line.startswith('|'):
        return {}

    cols = [c.strip() for c in first_line.split('|')]
    # Table format after split with leading |:
    # cols[0]='', cols[1]='1', cols[2]='22/03/2026', ..., cols[12]='22.59'(L400), cols[15]='6-7-5'(沿途位)

    result = {}
    if len(cols) >= 16:
        result['last_date'] = cols[2] if len(cols) > 2 else ''
        result['last_venue'] = cols[3] if len(cols) > 3 else ''
        result['last_distance'] = cols[4] if len(cols) > 4 else ''
        result['last_finish'] = cols[9] if len(cols) > 9 else ''
        result['last_margin'] = cols[10] if len(cols) > 10 else ''
        result['last_energy'] = cols[11] if len(cols) > 11 else ''
        result['raw_L400'] = cols[12] if len(cols) > 12 else ''
        result['last_xw'] = cols[13] if len(cols) > 13 else ''
        result['last_consumption'] = cols[14] if len(cols) > 14 else ''
        result['last_run_position'] = cols[15] if len(cols) > 15 else ''
    return result


def parse_trends(block):
    """Extract trend summaries from the statistics section."""
    result = {}

    m = re.search(r'L400:\s*(.+?)$', block, re.MULTILINE)
    if m: result['l400_trend'] = m.group(1).strip()

    m = re.search(r'能量:\s*(.+?)$', block, re.MULTILINE)
    if m: result['energy_trend'] = m.group(1).strip()

    m = re.search(r'引擎:\s*(.+?)$', block, re.MULTILINE)
    if m: result['engine'] = m.group(1).strip()

    m = re.search(r'最佳距離:\s*(.+?)$', block, re.MULTILINE)
    if m: result['best_distance'] = m.group(1).strip()

    m = re.search(r'\*\*頭馬距離趨勢:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['margin_trend'] = m.group(1).strip()

    m = re.search(r'\*\*體重趨勢:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['weight_trend'] = m.group(1).strip()

    m = re.search(r'\*\*配備變動:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['gear'] = m.group(1).strip()

    m = re.search(r'\*\*評分變動:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['rating_trend'] = m.group(1).strip()

    m = re.search(r'走位 PI:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['position_pi'] = m.group(1).strip()

    m = re.search(r'\*\*綜合評估:\*\*\s*(.+?)$', block, re.MULTILINE)
    if m: result['formline_strength'] = m.group(1).strip()

    return result


import hashlib
import time

def build_skeleton(data):
    """Build JSON skeleton: real data pre-filled, analysis fields as [FILL]."""
    name = data.get('name', '未知')
    raw_l400 = data.get('raw_L400', 'N/A')
    last_pos = data.get('last_run_position', 'N/A')
    
    # Generate _validation_nonce
    timestamp = str(time.time())
    nonce_input = f"{name}_{timestamp}"
    nonce = hashlib.md5(nonce_input.encode('utf-8')).hexdigest()

    return {
        # ===== LOCKED DATA (Python pre-filled, LLM must NOT modify) =====
        '_locked': True,
        '_validation_nonce': nonce,
        'horse_name': name,
        'jockey': data.get('jockey', ''),
        'trainer': data.get('trainer', ''),
        'weight': data.get('weight', 0),
        'barrier': data.get('barrier', 0),
        'last_6_finishes': data.get('last_6', ''),
        'days_since_last': data.get('days_since_last', 0),
        'season_stats': data.get('season_stats', ''),

        # ===== ANALYSIS FIELDS (LLM must fill all [FILL]) =====
        'scenario_tags': '[FILL]',

        'analytical_breakdown': {
            'trend_analysis': '[FILL]',
            'hidden_form': '[FILL]',
            'stability_risk': '[FILL]',
            'class_assessment': '[FILL]',
            'track_distance_suitability': '[FILL]',
            'engine_distance': '[FILL]',
            'gear_changes': '[FILL]',
            'trainer_signal': '[FILL]',
            'jockey_fit': '[FILL]',
            'pace_adaptation': '[FILL]',
        },

        'sectional_forensic': {
            'raw_L400': raw_l400,  # LOCKED
            'correction_factor': '[FILL]',
            'corrected_assessment': '[FILL]',
            'trend': data.get('l400_trend', ''),  # LOCKED
        },

        'eem_energy': {
            'last_run_position': last_pos,  # LOCKED
            'cumulative_drain': '[FILL]',
            'assessment': '[FILL]',
        },

        'forgiveness_archive': {
            'factors': '[FILL]',
            'conclusion': '[FILL]',
        },

        'matrix': {
            'stability':       {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'speed_mass':      {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'eem':             {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'trainer_jockey':  {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'scenario':        {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'freshness':       {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'formline':        {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'class_advantage': {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
            'forgiveness_bonus': {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[FILL]'},
        },

        'base_rating': '[AUTO]',
        'fine_tune': {'direction': '[FILL: +/-/無]', 'trigger': '[FILL]'},
        'override': {'rule': '[FILL]'},
        'final_rating': '[AUTO]',
        'core_logic': '[FILL]',
        'advantages': '[FILL]',
        'disadvantages': '[FILL]',
        'evidence_step_0_14': '[FILL]',
        'underhorse': {'triggered': False, 'condition': '', 'reason': ''},
    }


def main():
    parser = argparse.ArgumentParser(description='HKJC V9 Skeleton Generator')
    parser.add_argument('facts_path', help='Path to Facts.md')
    parser.add_argument('race_num', type=int, help='Race number')
    parser.add_argument('horse_num', type=int, help='Horse number to extract')
    parser.add_argument('--output', help='Output Logic.json path')
    args = parser.parse_args()

    # Read Facts.md
    with open(args.facts_path, 'r', encoding='utf-8') as f:
        facts_content = f.read()

    # Extract horse block
    block = extract_horse_block(facts_content, args.horse_num)
    if not block:
        print(f'❌ 找不到馬號 {args.horse_num} 的數據')
        sys.exit(1)

    # Parse all data
    header = parse_horse_header(block)
    summary = parse_summary(block)
    recent = parse_recent_race(block)
    trends = parse_trends(block)
    horse_data = {**header, **summary, **recent, **trends}

    # Build skeleton
    skeleton = build_skeleton(horse_data)

    # Determine output path
    json_path = args.output or os.path.join(
        os.path.dirname(args.facts_path),
        f'Race_{args.race_num}_Logic.json'
    )

    # Load existing JSON or create new
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
    else:
        # Extract race header for new JSON
        race_header = extract_race_header(facts_content)
        logic_data = {
            'race_analysis': {
                'race_number': args.race_num,
                'race_class': race_header.get('race_class', ''),
                'distance': race_header.get('distance', ''),
                'venue': race_header.get('venue', ''),
                'speed_map': {},
            },
            'horses': {},
        }

    # Ensure horses dict
    if 'horses' not in logic_data:
        logic_data['horses'] = {}

    horse_key = str(args.horse_num)

    # Skip if horse already fully analyzed (no [FILL] remaining)
    existing = logic_data['horses'].get(horse_key, {})
    if existing and '[FILL]' not in json.dumps(existing):
        print(f'✅ 馬號 {args.horse_num}（{header.get("name", "")}）已完成分析，跳過。')
        sys.exit(0)

    # Write skeleton
    logic_data['horses'][horse_key] = skeleton

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(logic_data, f, ensure_ascii=False, indent=2)

    name = header.get('name', '?')
    print(f'✅ 已為馬號 {args.horse_num}（{name}）建立 JSON 骨架')
    print(f'   → L400: {recent.get("raw_L400", "N/A")}')
    print(f'   → 沿途位: {recent.get("last_run_position", "N/A")}')
    print(f'   → 消耗: {recent.get("last_consumption", "N/A")}')
    print(f'   → 檔位: {header.get("barrier", "N/A")} | 負磅: {header.get("weight", "N/A")}')


if __name__ == '__main__':
    main()
