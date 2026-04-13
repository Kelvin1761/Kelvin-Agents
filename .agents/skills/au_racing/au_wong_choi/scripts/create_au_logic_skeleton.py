#!/usr/bin/env python3
"""
create_au_logic_skeleton.py — V9 Python-Native Skeleton Generator for AU Racing

Extracts factual data from AU Facts.md for a SINGLE horse and
pre-fills Logic.json. LLM only needs to fill [FILL] analysis fields.

Usage:
  python3 create_au_logic_skeleton.py <facts_path> <race_num> <horse_num>
"""
import sys, re, json, os, argparse, io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def extract_horse_block(facts_content, horse_num):
    """Extract the text block for a single horse from AU Facts.md.
    AU format uses [#X] markers instead of ### 馬號 X."""
    # Try AU format first
    pattern = rf'\[#{horse_num}\]'
    match = re.search(pattern, facts_content)
    if not match:
        # Try HKJC-style format as fallback
        pattern = rf'### 馬號 {horse_num} — '
        match = re.search(pattern, facts_content)
    if not match:
        # Try V2 format
        pattern = rf'### 馬匹 #{horse_num}\b'
        match = re.search(pattern, facts_content, re.IGNORECASE)
    if not match:
        # Try Runner X format
        pattern = rf'(?:Runner|Horse)\s+{horse_num}\b'
        match = re.search(pattern, facts_content, re.IGNORECASE)
    if not match:
        return None

    start = match.start()
    # Find next horse marker
    next_patterns = [
        rf'\[#{horse_num + 1}\]',
        r'\[#\d+\]',
        r'### 馬號 \d+ — ',
        r'### 馬匹 #\d+',
        r'(?:Runner|Horse)\s+\d+\b',
    ]
    for np in next_patterns:
        next_match = re.search(np, facts_content[match.end():])
        if next_match:
            return facts_content[start:match.end() + next_match.start()]
    return facts_content[start:]


def parse_horse_header(block):
    """Extract horse name, jockey, trainer from AU Facts block."""
    result = {}

    # Try [#X] Name format
    m = re.search(r'\[#(\d+)\]\s*(.+?)(?:\n|$)', block)
    if m:
        result['num'] = int(m.group(1))
        result['name'] = m.group(1).strip()
        # The name might be on the same line or the next
        name_line = m.group(2).strip()
        if name_line:
            result['name'] = name_line.split('|')[0].split('—')[0].strip()

    # Try V2 format
    m3 = re.search(r'### 馬匹 #(\d+)\s+(.+?)\s+\(檔位\s*(\d+)\)\s*\|\s*騎師:\s*(.+?)\s*\|\s*練馬師:\s*(.+?)(?:\n|$)', block)
    if m3:
        result['num'] = int(m3.group(1))
        result['name'] = m3.group(2).strip()
        result['barrier'] = int(m3.group(3))
        result['jockey'] = m3.group(4).strip()
        result['trainer'] = m3.group(5).strip()
        return result

    # Try HKJC-compatible format as fallback
    m2 = re.search(r'### 馬號 (\d+) — (.+?) \| 騎師:\s*(.+?) \| 練馬師:\s*(.+?) \| 負磅:\s*(\d+) \| 檔位:\s*(\d+)', block)
    if m2:
        result['num'] = int(m2.group(1))
        result['name'] = m2.group(2).strip()
        result['jockey'] = m2.group(3).strip()
        result['trainer'] = m2.group(4).strip()
        result['weight'] = int(m2.group(5))
        result['barrier'] = int(m2.group(6))
        return result

    # Extract individual fields
    for field, patterns in [
        ('jockey', [r'(?:Jockey|騎師)[：:]\s*(.+?)(?:\n|\||$)']),
        ('trainer', [r'(?:Trainer|練馬師)[：:]\s*(.+?)(?:\n|\||$)']),
        ('weight', [r'(?:Weight|Wt|負磅)[：:]\s*(\d+(?:\.\d+)?)']),
        ('barrier', [r'(?:Barrier|Draw|Gate|檔位)[：:]\s*(\d+)']),
    ]:
        for p in patterns:
            m = re.search(p, block, re.IGNORECASE)
            if m:
                if field in ('weight', 'barrier'):
                    try: result[field] = int(float(m.group(1)))
                    except: result[field] = 0
                else:
                    result[field] = m.group(1).strip()
                break
    return result


def parse_recent_race(block):
    """Extract L400, position from the most recent race for AU."""
    result = {}
    # Look for table rows after any table header
    table_rows = re.findall(r'^\|(.+?)\|$', block, re.MULTILINE)
    data_rows = [r for r in table_rows if not re.match(r'\s*[-]+', r.split('|')[0].strip())]
    # Skip header row
    if len(data_rows) > 1:
        # First data row (most recent race)
        cols = [c.strip() for c in data_rows[1].split('|')]
        # Try to find L400 column (look for decimal number like 22.59)
        for i, c in enumerate(cols):
            if re.match(r'\d{2}\.\d{2}$', c):
                result['raw_L400'] = c
                break
        # Try to find position column (look for patterns like 6-7-5)
        for i, c in enumerate(cols):
            if re.match(r'\d+-\d+-\d+', c):
                result['last_run_position'] = c
                break

    # Fallback: extract from text
    if 'raw_L400' not in result:
        m = re.search(r'L400[：:]\s*([\d.]+)', block)
        if m: result['raw_L400'] = m.group(1)

    if 'last_run_position' not in result:
        m = re.search(r'(?:沿途位|Position|Settling)[：:]\s*([\d-]+)', block, re.IGNORECASE)
        if m: result['last_run_position'] = m.group(1)

    return result


def parse_trends(block):
    """Extract trend summaries."""
    result = {}
    patterns = {
        'l400_trend': r'L400:\s*(.+?)$',
        'energy_trend': r'(?:能量|Energy):\s*(.+?)$',
        'engine': r'(?:引擎|Engine):\s*(.+?)$',
        'formline_strength': r'(?:\*\*綜合評估:\*\*|Formline:)\s*(.+?)$',
        'weight_trend': r'(?:\*\*體重趨勢:\*\*|Weight Trend:)\s*(.+?)$',
    }
    for key, pat in patterns.items():
        m = re.search(pat, block, re.MULTILINE | re.IGNORECASE)
        if m: result[key] = m.group(1).strip()
    return result


def build_skeleton(data):
    """Build JSON skeleton for AU horse analysis."""
    import secrets
    name = data.get('name', '未知')
    raw_l400 = data.get('raw_L400', 'N/A')
    last_pos = data.get('last_run_position', 'N/A')

    return {
        # ===== LOCKED DATA =====
        '_locked': True,
        '_validation_nonce': secrets.token_hex(4),
        'horse_name': name,
        'jockey': data.get('jockey', ''),
        'trainer': data.get('trainer', ''),
        'weight': data.get('weight', 0),
        'barrier': data.get('barrier', 0),

        # ===== ANALYSIS FIELDS =====
        'scenario_tags': '[FILL]',
        'status_cycle': '[FILL]',
        'trend_summary': '[FILL]',

        'analytical_breakdown': {
            'class_weight': '[FILL]',
            'engine_distance': '[FILL]',
            'track_surface_gait': '[FILL]',
            'gear_intent': '[FILL]',
            'jockey_trainer_combination': '[FILL]',
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
            '狀態與穩定性': {'score': '[FILL]', 'reasoning': '[FILL]'},
            '段速與引擎':   {'score': '[FILL]', 'reasoning': '[FILL]'},
            'EEM與形勢':    {'score': '[FILL]', 'reasoning': '[FILL]'},
            '騎練訊號':     {'score': '[FILL]', 'reasoning': '[FILL]'},
            '級數與負重':   {'score': '[FILL]', 'reasoning': '[FILL]'},
            '場地適性':     {'score': '[FILL]', 'reasoning': '[FILL]'},
            '賽績線':       {'score': '[FILL]', 'reasoning': '[FILL]'},
            '裝備與距離':   {'score': '[FILL]', 'reasoning': '[FILL]'},
        },

        'base_rating': '[FILL]',
        'fine_tune': {'direction': '[FILL]', 'trigger': '[FILL]'},
        'override': {'rule': '[FILL]'},
        'final_rating': '[FILL]',
        'core_logic': '[FILL]',
        'advantages': '[FILL]',
        'disadvantages': '[FILL]',
        'stability_index': '[FILL]',
        'tactical_plan': {},
        'dual_track': {'triggered': False},
        'underhorse': {'triggered': False, 'condition': '', 'reason': ''},
    }


def main():
    parser = argparse.ArgumentParser(description='AU V9 Skeleton Generator')
    parser.add_argument('facts_path', help='Path to Facts.md')
    parser.add_argument('race_num', type=int, help='Race number')
    parser.add_argument('horse_num', type=int, help='Horse number to extract')
    parser.add_argument('--output', help='Output Logic.json path')
    args = parser.parse_args()

    with open(args.facts_path, 'r', encoding='utf-8') as f:
        facts_content = f.read()

    block = extract_horse_block(facts_content, args.horse_num)
    if not block:
        print(f'❌ Cannot find horse #{args.horse_num} in Facts')
        sys.exit(1)

    header = parse_horse_header(block)
    recent = parse_recent_race(block)
    trends = parse_trends(block)
    horse_data = {**header, **recent, **trends}

    skeleton = build_skeleton(horse_data)

    json_path = args.output or os.path.join(
        os.path.dirname(args.facts_path),
        f'Race_{args.race_num}_Logic.json'
    )

    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
    else:
        logic_data = {
            'race_analysis': {'race_number': args.race_num, 'speed_map': {}},
            'horses': {},
        }

    if 'horses' not in logic_data:
        logic_data['horses'] = {}

    horse_key = str(args.horse_num)
    existing = logic_data['horses'].get(horse_key, {})
    if existing and '[FILL]' not in json.dumps(existing):
        print(f'✅ Horse #{args.horse_num} ({header.get("name", "")}) already analyzed, skipping.')
        sys.exit(0)

    logic_data['horses'][horse_key] = skeleton

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(logic_data, f, ensure_ascii=False, indent=2)

    name = header.get('name', '?')
    print(f'✅ Created skeleton for Horse #{args.horse_num} ({name})')
    print(f'   → L400: {recent.get("raw_L400", "N/A")}')
    print(f'   → Position: {recent.get("last_run_position", "N/A")}')
    print(f'   → Barrier: {header.get("barrier", "N/A")}')


if __name__ == '__main__':
    main()
