#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys, re, json, os, argparse, io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
create_hkjc_logic_skeleton.py — V9 Python-Native Skeleton Generator

Extracts factual data from HKJC Facts.md for a SINGLE horse and
pre-fills Logic.json. LLM only needs to fill [FILL] analysis fields.

Usage:
  python3 create_hkjc_logic_skeleton.py <facts_path> <race_num> <horse_num>
"""

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
    """Extract last_6, days_since_last, season stats, wins, starts."""
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
    
    # Extract wins/starts from career line: 生涯：N: W-P-S
    m = re.search(r'生涯：\s*(\d+)\s*[::∶]\s*(\d+)', block)
    if m:
        result['starts'] = int(m.group(1))
        result['wins'] = int(m.group(2))
    else:
        # Fallback: try 總場次 / 總勝
        m = re.search(r'(\d+)\s*戰\s*(\d+)\s*勝', block)
        if m:
            result['starts'] = int(m.group(1))
            result['wins'] = int(m.group(2))
    
    # Extract Last 10 recent form
    m = re.search(r'Last 10.*?[::∶]\s*`?([^`\n]+)`?', block)
    if m:
        result['recent_form'] = m.group(1).strip()
    
    # Extract track/surface records
    m = re.search(r'好地[::∶]\s*([^\|\n]+)', block)
    if m:
        result['good_record'] = m.group(1).strip()
    m = re.search(r'軟地[::∶]\s*([^\|\n]+)', block)
    if m:
        result['soft_record'] = m.group(1).strip()
    m = re.search(r'同場[::∶]\s*([^\|\n]+)', block)
    if m:
        result['course_record'] = m.group(1).strip()

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


def _build_core_logic_scaffold(data):
    """V11: Build data-prompted natural prose scaffold for core_logic.
    Injects actual horse metrics into a guided prompt that produces
    ~100 words of flowing analysis WITHOUT visible tags.
    """
    name = data.get('name', '未知')
    last_6 = data.get('last_6', 'N/A')
    barrier = data.get('barrier', 'N/A')
    weight = data.get('weight', 'N/A')
    raw_l400 = data.get('raw_L400', 'N/A')
    engine = data.get('engine', 'N/A')
    days_since = data.get('days_since_last', 0)
    last_xw = data.get('last_xw', 'N/A')
    last_consumption = data.get('last_consumption', 'N/A')
    jockey = data.get('jockey', 'N/A')
    season_stats = data.get('season_stats', 'N/A')
    margin_trend = data.get('margin_trend', 'N/A')
    l400_trend = data.get('l400_trend', 'N/A')
    rating_trend = data.get('rating_trend', 'N/A')

    scaffold = (
        f"[FILL — 根據以下數據寫約100字流暢廣東話分析，"
        f"必須涵蓋：近態趨勢、檔位形勢、段速能力、整體前景。"
        f"唔好用 tag/標籤，直接寫自然段落。]\n"
        f"數據：{name} "
        f"近6仗={last_6}, "
        f"檔位={barrier}, "
        f"負磅={weight}磅, "
        f"L400={raw_l400}, "
        f"L400趨勢={l400_trend}, "
        f"引擎={engine}, "
        f"休賽={days_since}日, "
        f"走位={last_xw}, "
        f"消耗={last_consumption}, "
        f"騎師={jockey}, "
        f"季績={season_stats}, "
        f"頭馬距離趨勢={margin_trend}, "
        f"評分趨勢={rating_trend}"
    )
    return scaffold


def build_skeleton(data):
    """Build JSON skeleton: real data pre-filled, analysis fields as [FILL].
    V3: Data-anchored reasoning — injects actual horse data into matrix reasoning
    placeholders to structurally prevent LLM laziness.
    """
    name = data.get('name', '未知')
    raw_l400 = data.get('raw_L400', 'N/A')
    last_pos = data.get('last_run_position', 'N/A')
    last_6 = data.get('last_6', 'N/A')
    days_since = data.get('days_since_last', 0)
    season_stats = data.get('season_stats', 'N/A')
    margin_trend = data.get('margin_trend', 'N/A')
    weight_trend = data.get('weight_trend', 'N/A')
    gear = data.get('gear', 'N/A')
    rating_trend = data.get('rating_trend', 'N/A')
    l400_trend = data.get('l400_trend', 'N/A')
    energy_trend = data.get('energy_trend', 'N/A')
    engine = data.get('engine', 'N/A')
    best_dist = data.get('best_distance', 'N/A')
    barrier = data.get('barrier', 'N/A')
    weight = data.get('weight', 'N/A')
    jockey = data.get('jockey', 'N/A')
    trainer = data.get('trainer', 'N/A')
    last_xw = data.get('last_xw', 'N/A')
    last_consumption = data.get('last_consumption', 'N/A')
    last_finish = data.get('last_finish', 'N/A')
    last_margin_val = data.get('last_margin', 'N/A')
    good_rec = data.get('good_record', 'N/A')
    course_rec = data.get('course_record', 'N/A')
    position_pi = data.get('position_pi', 'N/A')
    formline_str = data.get('formline_strength', 'N/A')
    wins = data.get('wins', 0)
    starts = data.get('starts', 0)
    
    # Generate _validation_nonce with SKEL_ prefix (WALL-019 requires this prefix)
    timestamp = str(time.time())
    nonce_input = f"{name}_{timestamp}"
    nonce = 'SKEL_' + hashlib.md5(nonce_input.encode('utf-8')).hexdigest()

    # ── Build data-anchored reasoning for each matrix dimension ──
    # This forces the LLM to engage with real data instead of generating fluff.
    r_stability = (
        f"[數據: 近6仗={last_6}, 季內={season_stats}, "
        f"頭馬距離趨勢={margin_trend}] → [判讀: FILL]"
    )
    r_speed_mass = (
        f"[數據: 上仗L400={raw_l400}, L400趨勢={l400_trend}, "
        f"能量趨勢={energy_trend}] → [判讀: FILL]"
    )
    r_eem = (
        f"[數據: 上仗走位={last_pos}, 上仗XW={last_xw}, "
        f"上仗消耗={last_consumption}] → [判讀: FILL]"
    )
    r_trainer = (
        f"[數據: 騎師={jockey}, 練馬師={trainer}, "
        f"配備={gear}] → [判讀: FILL]"
    )
    r_scenario = (
        f"[數據: 檔位={barrier}, 引擎={engine}, "
        f"走位PI={position_pi}] → [判讀: FILL]"
    )
    r_freshness = (
        f"[數據: 休賽={days_since}日, 最佳距離={best_dist}, "
        f"同場紀錄={course_rec}, 好地={good_rec}] → [判讀: FILL]"
    )
    r_formline = (
        f"[數據: 賽績線強度={formline_str}, "
        f"上仗名次={last_finish}, 上仗距離差={last_margin_val}] → [判讀: FILL]"
    )
    r_class = (
        f"[數據: {starts}戰{wins}勝, 評分趨勢={rating_trend}, "
        f"負磅={weight}] → [判讀: FILL]"
    )

    return {
        # ===== LOCKED DATA (Python pre-filled, LLM must NOT modify) =====
        '_locked': True,
        '_validation_nonce': nonce,
        'horse_name': name,
        'jockey': data.get('jockey', ''),
        'trainer': data.get('trainer', ''),
        'weight': data.get('weight', 0),
        'barrier': data.get('barrier', 0),
        'last_6_finishes': last_6,
        'days_since_last': days_since,
        'season_stats': season_stats,

        # ===== ANALYSIS FIELDS (LLM must fill all [FILL]) =====
        'scenario_tags': '[FILL]',

        'analytical_breakdown': {
            'stability_risk': f'[近6仗={last_6}, 頭馬距離={margin_trend}] → FILL',
            'class_assessment': f'[{starts}戰{wins}勝, 評分={rating_trend}] → FILL',
            'track_distance_suitability': f'[引擎={engine}, 最佳={best_dist}, 同場={course_rec}] → FILL',
            'engine_distance': f'[引擎={engine}, 最佳={best_dist}, 走位PI={position_pi}] → FILL',
            'weight_trend': f'[體重趨勢={weight_trend}, 今仗負磅={weight}] → FILL',
            'gear_changes': f'[配備={gear}] → FILL',
            'draw_verdict': f'[檔位={barrier}] → FILL (必須引用 Facts.md 🎯檔位優劣判讀)',
            'trainer_signal': f'[練馬師={trainer}, 騎師={jockey}] → FILL',
            'jockey_fit': f'[騎師={jockey}] → FILL',
            'pace_adaptation': f'[引擎={engine}, L400={raw_l400}] → FILL',
            'sectional_profile_summary': f'[L400趨勢={l400_trend}, 能量={energy_trend}] → FILL',
            'margin_trend': f'[頭馬距離={margin_trend}] → FILL',
            'position_sectional_composite': f'[走位={last_pos}, XW={last_xw}, 消耗={last_consumption}] → FILL',
            'finish_time_deviation': '[引用 Facts.md 📊完成時間偏差趨勢] → FILL',
            'eem_analysis': f'[走位={last_pos}, XW={last_xw}, 消耗={last_consumption}] → FILL',
            'hidden_form': '[FILL]',
            'competition_events': '[FILL]',
            'trend_analysis': f'[近6仗={last_6}] → FILL',
            'formline_strength': formline_str if formline_str != 'N/A' else '[FILL]',
        },

        'sectional_forensic': {
            'raw_L400': raw_l400,  # LOCKED
            'correction_factor': '[FILL]',
            'corrected_assessment': '[FILL]',
            'trend': l400_trend if l400_trend != 'N/A' else '',  # LOCKED
        },

        'eem_energy': {
            'last_run_position': last_pos,  # LOCKED
            'cumulative_drain': '[FILL]',
            'assessment': '[FILL]',
        },

        'race_forgiveness': '[FILL — JSON Array 格式]',

        'matrix': {
            'stability':       {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_stability},
            'speed_mass':      {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_speed_mass},
            'eem':             {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_eem},
            'trainer_jockey':  {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_trainer},
            'scenario':        {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_scenario},
            'freshness':       {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_freshness},
            'formline':        {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_formline},
            'class_advantage': {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': r_class},
            'forgiveness_bonus': {'score': '[FILL: ✅✅/✅/➖/❌/❌❌]', 'reasoning': '[數據: 見完整賽績檔案寬恕認定] → [判讀: FILL]'},
        },

        'interaction_matrix': {
            'SYN': '[FILL or 無]',
            'CON': '[FILL or 無]',
            'CONTRA': '[FILL or 無]',
        },

        'base_rating': '[AUTO]',
        'fine_tune': {'direction': '[FILL: +/-/無]', 'trigger': '[FILL]', 'channel_a': '[FILL]', 'channel_b': '[FILL]'},
        'override': {'rule': '[FILL]'},
        'final_rating': '[AUTO]',
        'core_logic': _build_core_logic_scaffold(data),
        'advantages': '[FILL]',
        'disadvantages': '[FILL]',
        'evidence_step_0_14': '[FILL]',
        'underhorse': {'triggered': False, 'condition': '', 'reason': ''},
        
        # ===== AUTO-ENRICHMENT (V3: auto-filled from Facts.md) =====
        'wins': wins,
        'starts': starts,
        'recent_form': data.get('recent_form', ''),
        'good_record': good_rec,
        'soft_record': data.get('soft_record', ''),
        'course_record': course_rec,
        'engine_type': engine,
        'best_distance': best_dist,
        'formline_strength': formline_str,
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
