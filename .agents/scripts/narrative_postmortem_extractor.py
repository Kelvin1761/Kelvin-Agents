"""
narrative_postmortem_extractor.py — 法醫數據抽取器

從賽果檔案中抽取每匹失敗精選馬嘅結構化法醫數據：
沿途走位、分段時間、競賽事件報告關鍵字分類。
LLM 只需要做裁定分類 (4e-4)。

Usage:
  python narrative_postmortem_extractor.py <results_file> <analysis_file> --race N
  python narrative_postmortem_extractor.py <results_file> <analysis_dir> --all --domain au|hkjc

Exit codes:
  0 = Success
  2 = Error
"""
import sys, io, re, os, pathlib, argparse, json

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Stewards/Incident keyword classification ──
KEYWORD_CLASSIFICATIONS = {
    '🩸 醫療 (自動 🟢 可寬恕)': [
        '流鼻血', 'bled', '跛行', '不良於行', 'lame', '心律不正', '呼吸異常',
        'respiratory', 'cardiac', 'veterinary',
    ],
    '🏇 干擾': [
        '受碰撞', '被夾擠', '碰撞', 'bumped', 'hampered', 'checked',
        '走勢受阻', '未能走出', 'held up', 'blocked', 'no room',
        'tightened', 'crowded', 'steadied',
    ],
    '⚡ 起步': [
        '出閘緩慢', '起步笨拙', 'slow start', 'slow to begin',
        'began awkwardly', 'dwelt', 'missed the start',
    ],
    '💀 實力 (🔴 邏輯錯誤)': [
        '不願加速', '毫無表現', 'failed to respond', 'never a factor',
        'weakened', 'dropped out', 'tailed off', 'eased',
    ],
    '🐎 行為': [
        '搶口', '不受控', 'pulled hard', 'over-raced', 'hung',
        'shifted', 'laid in', 'laid out', '外閃', 'ducked',
    ],
    '🔧 裝備 (🟢 不可預見)': [
        '蹄鐵鬆脫', '口銜不順', 'lost shoe', 'bit', 'gear',
        'tongue tie', 'blinkers',
    ],
}


def classify_incident_keywords(text):
    """Classify stewards/incident report text into categories."""
    text_lower = text.lower()
    found = {}
    for category, keywords in KEYWORD_CLASSIFICATIONS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                if category not in found:
                    found[category] = []
                found[category].append(kw)
    return found


def parse_running_positions(text):
    """Extract running position data from results text."""
    # HKJC format: (2W3W4W6W) or 2-2-3-1
    pos_matches = re.findall(r'\(([0-9W]+(?:[0-9W]+)*)\)', text)
    if pos_matches:
        return pos_matches

    # Try dash-separated: 2-2-3-1
    dash_matches = re.findall(r'\b(\d+(?:-\d+){2,})\b', text)
    return dash_matches


def parse_sectional_times(text):
    """Extract sectional times from results text."""
    # Common format: 13.2 - 11.5 - 12.0 - 11.8
    time_matches = re.findall(r'\b(\d{1,2}\.\d{1,2})\b', text)
    return time_matches


def compute_deterioration(times):
    """Compute deterioration rate from sectional times."""
    if len(times) < 2:
        return None
    try:
        floats = [float(t) for t in times]
        first_half = sum(floats[:len(floats)//2]) / (len(floats)//2)
        second_half = sum(floats[len(floats)//2:]) / (len(floats) - len(floats)//2)
        rate = ((second_half - first_half) / first_half) * 100
        return round(rate, 1)
    except (ValueError, ZeroDivisionError):
        return None


# ── Analysis parsing (shared patterns) ──

PICK_RE = re.compile(
    r'([🥇🥈🥉🏅])\s*\*?\*?\s*(?:\*\*)?(?:第[一二三四]選\*\*\s*\n-\s*\*\*馬號及馬名[：:]\*\*\s*)?#?(\d+)\s+(.+?)(?:\*\*|\s*[—\-|])',
    re.UNICODE
)
RESULT_RE = re.compile(
    r'(?:(\d+)(?:st|nd|rd|th)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|(?:第(\d+)名[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|(?:\[(\d+)\]\s+(\d+)\.\s+(.+?)(?:\s*[\(（]|$))',
    re.UNICODE | re.MULTILINE
)
RESULT_TABLE_RE = re.compile(r'\|\s*(\d+)\s*\|\s*#?(\d+)\s*\|\s*(.+?)\s*\|', re.UNICODE)


def parse_picks(text):
    picks = []
    emoji_map = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    for m in PICK_RE.finditer(text):
        rank = emoji_map.get(m.group(1), len(picks) + 1)
        picks.append((rank, int(m.group(2)), m.group(3).strip().rstrip('*').strip()))
    picks.sort(key=lambda x: x[0])
    seen = set()
    return [p for p in picks if p[1] not in seen and not seen.add(p[1])][:4]


def parse_results(text):
    results = []
    for m in RESULT_RE.finditer(text):
        pos = m.group(1) or m.group(4) or m.group(7)
        num = m.group(2) or m.group(5) or m.group(8)
        name = m.group(3) or m.group(6) or m.group(9)
        if pos and num:
            results.append((int(pos), int(num), (name or '').strip()))
    if not results:
        for m in RESULT_TABLE_RE.finditer(text):
            if int(m.group(1)) <= 4:
                results.append((int(m.group(1)), int(m.group(2)), m.group(3).strip()))
    results.sort(key=lambda x: x[0])
    return results[:4]


def extract_postmortem(results_text, analysis_text, race_num, domain='au'):
    """Extract postmortem data for failed picks in a single race."""
    picks = parse_picks(analysis_text)
    results = parse_results(results_text)

    if not picks or not results:
        return {'error': 'Missing picks or results data'}

    actual_top3 = {r[1] for r in results[:3]}
    failed_picks = [p for p in picks[:3] if p[1] not in actual_top3]

    if not failed_picks:
        return {'race': race_num, 'failed_picks': [], 'message': '✅ 所有精選馬入位'}

    postmortems = []
    for p in failed_picks:
        actual_pos = next((r[0] for r in results if r[1] == p[1]), '?')

        # Extract running position & incident data for this horse
        # Search for horse-specific sections in results
        horse_pattern = re.compile(
            rf'#?{p[1]}\b.*?(?=\n#|\Z)',
            re.DOTALL | re.UNICODE
        )
        horse_section = horse_pattern.search(results_text)
        horse_text = horse_section.group(0) if horse_section else ''

        running_pos = parse_running_positions(horse_text)
        sectional_times = parse_sectional_times(horse_text)
        deterioration = compute_deterioration(sectional_times) if sectional_times else None

        # Classify incident keywords
        incidents = classify_incident_keywords(horse_text)

        # Determine auto-verdict suggestion
        auto_verdict = None
        if any('醫療' in k for k in incidents):
            auto_verdict = '🟢 可寬恕 (醫療不可抗力)'
        elif any('裝備' in k for k in incidents):
            auto_verdict = '🟢 可寬恕 (裝備故障)'
        elif any('實力' in k for k in incidents):
            auto_verdict = '🔴 邏輯錯誤候選 (實力不足信號)'

        pm = {
            'pick_rank': p[0],
            'horse_num': p[1],
            'horse_name': p[2],
            'actual_pos': actual_pos,
            'running_positions': running_pos,
            'sectional_times': sectional_times,
            'deterioration_rate': deterioration,
            'incident_keywords': incidents,
            'auto_verdict_suggestion': auto_verdict,
            'llm_verdict_required': True,
        }
        postmortems.append(pm)

    return {'race': race_num, 'failed_picks': postmortems}


def print_postmortem(pm_data):
    """Print formatted postmortem report."""
    rn = pm_data['race']
    print(f"\n{'─' * 55}")
    print(f"🎭 敘事覆盤數據 — Race {rn}")
    print(f"{'─' * 55}")

    if not pm_data.get('failed_picks'):
        print(f"   {pm_data.get('message', '✅ 無失敗精選馬')}")
        return

    for fp in pm_data['failed_picks']:
        print(f"\n   📌 Pick {fp['pick_rank']}: #{fp['horse_num']} {fp['horse_name']} → 實際第{fp['actual_pos']}名")

        if fp['running_positions']:
            print(f"   🏇 沿途走位: {', '.join(fp['running_positions'])}")
        else:
            print(f"   🏇 沿途走位: [未能抽取]")

        if fp['sectional_times']:
            print(f"   ⏱️ 分段時間: {' - '.join(fp['sectional_times'])}")
            if fp['deterioration_rate'] is not None:
                d = fp['deterioration_rate']
                flag = '🔴 崩潰' if d > 15 else '🟡 衰退' if d > 5 else '🟢 穩定'
                print(f"   📉 衰退率: {d}% {flag}")
        else:
            print(f"   ⏱️ 分段時間: [未能抽取]")

        if fp['incident_keywords']:
            print(f"   📋 事件報告關鍵字:")
            for cat, kws in fp['incident_keywords'].items():
                print(f"      {cat}: {', '.join(kws)}")
        else:
            print(f"   📋 事件報告: [無特別記錄]")

        if fp['auto_verdict_suggestion']:
            print(f"   🤖 自動建議: {fp['auto_verdict_suggestion']}")
        print(f"   ❓ LLM 裁定: {{{{LLM_FILL}}}}")


def main():
    parser = argparse.ArgumentParser(description='法醫數據抽取器')
    parser.add_argument('results_path', help='Results file path')
    parser.add_argument('analysis_path', help='Analysis file or directory')
    parser.add_argument('--race', type=int, help='Specific race number')
    parser.add_argument('--all', action='store_true', help='Process all races')
    parser.add_argument('--domain', choices=['au', 'hkjc'], default='au')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()

    if not os.path.exists(args.results_path):
        print(f'Error: {args.results_path} not found', file=sys.stderr)
        sys.exit(2)

    with open(args.results_path, 'r', encoding='utf-8') as f:
        results_text = f.read()

    all_postmortems = []

    if os.path.isdir(args.analysis_path):
        p = pathlib.Path(args.analysis_path)
        files = sorted(p.glob('*Analysis*.md')) or sorted(p.glob('*analysis*.md'))
        for af in files:
            m = re.search(r'[Rr]ace[_\s]*(\d+)', af.name)
            if not m: continue
            rn = int(m.group(1))
            if args.race and rn != args.race: continue
            with open(af, 'r', encoding='utf-8') as f:
                atxt = f.read()
            pm = extract_postmortem(results_text, atxt, rn, args.domain)
            all_postmortems.append(pm)
    else:
        with open(args.analysis_path, 'r', encoding='utf-8') as f:
            atxt = f.read()
        rn = args.race or 1
        pm = extract_postmortem(results_text, atxt, rn, args.domain)
        all_postmortems.append(pm)

    if args.json:
        print(json.dumps(all_postmortems, ensure_ascii=False, indent=2, default=str))
    else:
        for pm in all_postmortems:
            print_postmortem(pm)


if __name__ == '__main__':
    main()
