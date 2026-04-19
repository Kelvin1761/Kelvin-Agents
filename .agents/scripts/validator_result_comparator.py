import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
validator_result_comparator.py — 驗證官賽果比對器

自動比對盲測輸出同實際賽果，計算三級判定標準（黃金/良好/最低）。
消除 Validator Step 3 嘅所有算術比對工作。

Usage:
  python validator_result_comparator.py <blind_test_file> <results_file> --race N
  python validator_result_comparator.py <blind_test_file> <results_file> --all
  python validator_result_comparator.py <analysis_dir> <results_file> --all --domain au|hkjc

Exit codes:
  0 = PASS (at least minimum threshold met)
  1 = FAIL (below minimum threshold)
  2 = Error
"""
import sys, io, re, json, os, pathlib, argparse
from dataclasses import dataclass, field

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Regex (shared with other scripts) ──

PICK_RE = re.compile(
    r'([🥇🥈🥉🏅])\s*\*?\*?\s*(?:\*\*)?(?:第[一二三四]選\*\*\s*\n-\s*\*\*馬號及馬名[：:]\*\*\s*)?#?(\d+)\s+(.+?)(?:\*\*|\s*[—\-|])',
    re.UNICODE
)
PICK_ALT_RE = re.compile(
    r'(?:Top\s*|Pick\s*)(\d+)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[—\-|（(]|$)',
    re.UNICODE | re.MULTILINE
)
RESULT_RE = re.compile(
    r'(?:(\d+)(?:st|nd|rd|th)[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|'
    r'(?:第(\d+)名[：:.\s]+#?(\d+)\s+(.+?)(?:\s*[\(（]|$))'
    r'|'
    r'(?:\[(\d+)\]\s+(\d+)\.\s+(.+?)(?:\s*[\(（]|$))',
    re.UNICODE | re.MULTILINE
)
RESULT_TABLE_RE = re.compile(
    r'\|\s*(\d+)\s*\|\s*#?(\d+)\s*\|\s*(.+?)\s*\|',
    re.UNICODE
)


def parse_picks(text):
    picks = []
    emoji_map = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    for m in PICK_RE.finditer(text):
        rank = emoji_map.get(m.group(1), len(picks) + 1)
        picks.append((rank, int(m.group(2)), m.group(3).strip().rstrip('*').strip()))
    if not picks:
        for m in PICK_ALT_RE.finditer(text):
            picks.append((int(m.group(1)), int(m.group(2)), m.group(3).strip()))
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


def split_results_by_race(text):
    race_results = {}
    sections = re.split(r'(?:##?\s*(?:Race|第)\s*(\d+)|Race:\s*(\d+))', text)
    if len(sections) <= 1:
        r = parse_results(text)
        if r: race_results[1] = r
    else:
        cur = None
        for s in sections:
            if s and s.strip().isdigit():
                cur = int(s.strip())
            elif cur is not None:
                r = parse_results(s)
                if r: race_results[cur] = r
    return race_results


def compare_race(picks, results):
    """Compare blind test picks vs actual results. Returns structured verdict."""
    if not picks or not results:
        return {'error': 'Missing data', 'verdict': 'ERROR'}

    actual_top3 = {r[1] for r in results[:3]}
    actual_1st = results[0][1]
    pnums = [p[1] for p in picks]

    hits = sum(1 for p in pnums[:3] if p in actual_top3)

    gold = hits == 3
    good = len(pnums) >= 2 and pnums[0] in actual_top3 and pnums[1] in actual_top3
    minimum = hits >= 2
    single = hits >= 1
    champ = pnums[0] == actual_1st if pnums else False
    top3_champ = actual_1st in set(pnums[:3])

    # Exemption checks
    exemptions = []
    # Note: Odds-based exemption (>50x) requires odds data not always available
    # Stewards/medical exemptions require external data
    # These are flagged for LLM to confirm

    if gold:
        verdict = '🏆 PASS (黃金標準)'
        level = 'GOLD'
    elif good:
        verdict = '✅ PASS (良好結果)'
        level = 'GOOD'
    elif minimum:
        verdict = '⚠️ PASS (最低門檻)'
        level = 'MIN'
    elif single:
        verdict = '❌ FAIL (僅單入位)'
        level = 'FAIL'
    else:
        verdict = '❌ FAIL (完全失誤)'
        level = 'FAIL'

    # Detail each pick's outcome
    pick_details = []
    for i, p in enumerate(picks[:4]):
        apos = next((r[0] for r in results if r[1] == p[1]), None)
        in_top3 = p[1] in actual_top3
        pick_details.append({
            'rank': i + 1,
            'horse_num': p[1],
            'name': p[2],
            'actual_pos': apos if apos else '未入位',
            'in_top3': in_top3,
            'is_champion': p[1] == actual_1st,
        })

    return {
        'verdict': verdict,
        'level': level,
        'gold_standard': gold,
        'good_result': good,
        'min_threshold': minimum,
        'single_hit': single,
        'champion_hit': champ,
        'top3_has_champ': top3_champ,
        'hits_in_top3': hits,
        'pick_details': pick_details,
        'actual_top3': [(r[0], r[1], r[2]) for r in results[:3]],
        'exemptions': exemptions,
        'passed': level != 'FAIL',
    }


def print_race_verdict(race_num, result):
    """Print formatted verdict for one race."""
    print(f"\n{'─' * 50}")
    print(f"🔬 Race {race_num} — {result['verdict']}")
    print(f"{'─' * 50}")
    print(f"   🏆 黃金標準: {'✅' if result['gold_standard'] else '❌'}")
    print(f"   ✅ 良好結果: {'✅' if result['good_result'] else '❌'}")
    print(f"   ⚠️ 最低門檻: {'✅' if result['min_threshold'] else '❌'}")
    print(f"   冠軍命中:    {'✅' if result['champion_hit'] else '❌'}")
    print()
    print(f"   預測 vs 實際:")
    for pd in result['pick_details']:
        icon = '✅' if pd['in_top3'] else '❌'
        champ = ' 👑' if pd['is_champion'] else ''
        print(f"      Pick {pd['rank']}: #{pd['horse_num']} {pd['name']} → 實際第{pd['actual_pos']}名 {icon}{champ}")
    print()
    print(f"   實際前三名:")
    for pos, num, name in result['actual_top3']:
        print(f"      {pos}. #{num} {name}")

    if result['exemptions']:
        print(f"\n   豁免條件: {', '.join(result['exemptions'])}")


def main():
    parser = argparse.ArgumentParser(description='驗證官賽果比對器')
    parser.add_argument('input_path', help='Blind test file or analysis directory')
    parser.add_argument('results_file', help='Race results file')
    parser.add_argument('--race', type=int, help='Specific race number to compare')
    parser.add_argument('--all', action='store_true', help='Compare all races')
    parser.add_argument('--domain', choices=['au', 'hkjc'], default='au', help='Domain')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()

    if not os.path.exists(args.input_path):
        print(f'Error: {args.input_path} not found', file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(args.results_file):
        print(f'Error: {args.results_file} not found', file=sys.stderr)
        sys.exit(2)

    # Read results
    with open(args.results_file, 'r', encoding='utf-8') as f:
        results_text = f.read()
    race_results = split_results_by_race(results_text)

    # Determine input mode
    all_verdicts = {}

    if os.path.isdir(args.input_path):
        # Directory mode: scan for analysis files
        p = pathlib.Path(args.input_path)
        files = sorted(p.glob('*Analysis*.md')) or sorted(p.glob('*analysis*.md'))
        for af in files:
            m = re.search(r'[Rr]ace[_\s]*(\d+)', af.name)
            if not m: continue
            rn = int(m.group(1))
            if args.race and rn != args.race: continue
            with open(af, 'r', encoding='utf-8') as f:
                picks = parse_picks(f.read())
            res = race_results.get(rn, [])
            if picks and res:
                all_verdicts[rn] = compare_race(picks, res)
    else:
        # Single file mode
        with open(args.input_path, 'r', encoding='utf-8') as f:
            bt_text = f.read()
        picks = parse_picks(bt_text)
        rn = args.race or 1
        res = race_results.get(rn, [])
        if picks and res:
            all_verdicts[rn] = compare_race(picks, res)

    if not all_verdicts:
        print('Error: No races could be compared. Check input files.', file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(all_verdicts, ensure_ascii=False, indent=2, default=str))
    else:
        for rn in sorted(all_verdicts.keys()):
            print_race_verdict(rn, all_verdicts[rn])

        # Summary
        total = len(all_verdicts)
        passed = sum(1 for v in all_verdicts.values() if v['passed'])
        print(f"\n{'═' * 50}")
        print(f"📊 總結: {passed}/{total} 場通過")
        print(f"{'═' * 50}")

    # Exit code
    all_passed = all(v['passed'] for v in all_verdicts.values())
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
