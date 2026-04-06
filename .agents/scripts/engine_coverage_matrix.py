"""
engine_coverage_matrix.py — 引擎覆蓋率矩陣

列出所有 resource 檔案中定義嘅規則/Step/覆蓋條件，
對比最近 N 場分析輸出，計算每條規則嘅「覆蓋率」—
即係邊啲被使用過 vs 邊啲係死代碼。

類似 code coverage 但係 for 賽馬引擎規則。

Usage:
  python engine_coverage_matrix.py --domain au --resources-dir <path> --analysis-dir <dir1> [--analysis-dir <dir2>]

Exit codes:
  0 = Coverage ≥70%
  1 = Coverage <70% (uncovered rules found)
  2 = Error
"""
import sys, io, re, os, pathlib, argparse, json
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def extract_engine_rules(resources_dir):
    """Extract all rules/steps/overrides from resource files."""
    rules = {}
    p = pathlib.Path(resources_dir)

    for f in sorted(p.glob('*.md')):
        fname = f.name

        # Skip non-engine files
        if fname.startswith('00_') or fname.startswith('_') or 'DEPRECATED' in fname:
            continue
        if fname in ['sip_changelog.md', 'observation_log.md']:
            continue

        with open(f, 'r', encoding='utf-8') as fh:
            text = fh.read()

        # Extract Step definitions
        for m in re.finditer(r'(?:###?\s*)?Step\s+(\d+[a-zA-Z.\d]*)\s*[：:—\-]?\s*(.*?)(?:\n|$)', text):
            step_id = f"Step {m.group(1)}"
            desc = m.group(2).strip()[:80]
            rule_key = f"{fname}|{step_id}"
            if rule_key not in rules:
                rules[rule_key] = {
                    'file': fname,
                    'rule': step_id,
                    'description': desc,
                    'search_terms': [step_id, m.group(1)],
                    'covered': False,
                    'cover_count': 0,
                }

        # Extract SIP definitions within this file
        for m in re.finditer(r'(SIP-[A-Za-z0-9\-]+)\s*[：:—]?\s*(.*?)(?:\n|$)', text):
            sip_id = m.group(1)
            desc = m.group(2).strip()[:80]
            rule_key = f"{fname}|{sip_id}"
            if rule_key not in rules:
                rules[rule_key] = {
                    'file': fname,
                    'rule': sip_id,
                    'description': desc,
                    'search_terms': [sip_id],
                    'covered': False,
                    'cover_count': 0,
                }

        # Extract override/special rules
        for m in re.finditer(r'(?:####?\s*)?(覆蓋規則|Override|Rule)\s+(\d+[a-zA-Z]*)[：:—]?\s*(.*?)(?:\n|$)', text):
            rule_id = f"{m.group(1)} {m.group(2)}"
            desc = m.group(3).strip()[:80]
            rule_key = f"{fname}|{rule_id}"
            if rule_key not in rules:
                rules[rule_key] = {
                    'file': fname,
                    'rule': rule_id,
                    'description': desc,
                    'search_terms': [rule_id, m.group(2)],
                    'covered': False,
                    'cover_count': 0,
                }

        # Extract dimension-specific rules (e.g., Track modules)
        if 'track_' in fname:
            # Track modules — check if track was analyzed
            track_name = re.search(r'track_(\w+)', fname)
            if track_name:
                rule_key = f"{fname}|Track:{track_name.group(1)}"
                if rule_key not in rules:
                    rules[rule_key] = {
                        'file': fname,
                        'rule': f"Track Module: {track_name.group(1)}",
                        'description': f"賽場模組: {track_name.group(1)}",
                        'search_terms': [track_name.group(1)],
                        'covered': False,
                        'cover_count': 0,
                    }

    return rules


def check_coverage(rules, analysis_dirs):
    """Check which rules are covered by actual analysis output."""
    total_files = 0

    for analysis_dir in analysis_dirs:
        p = pathlib.Path(analysis_dir)
        if not p.exists():
            continue

        analysis_files = sorted(
            list(p.glob('*Analysis*.md')) +
            list(p.glob('*analysis*.md')) +
            list(p.glob('*分析*.md')) +
            list(p.glob('*Skeleton*.md')) +
            list(p.glob('*覆盤*.md'))
        )

        for af in analysis_files:
            total_files += 1
            with open(af, 'r', encoding='utf-8') as fh:
                text = fh.read()

            text_lower = text.lower()

            for rule_key, rule in rules.items():
                for term in rule['search_terms']:
                    if term.lower() in text_lower:
                        rule['covered'] = True
                        rule['cover_count'] += 1
                        break

    return total_files


def main():
    parser = argparse.ArgumentParser(description='引擎覆蓋率矩陣')
    parser.add_argument('--domain', required=True, choices=['au', 'hkjc'])
    parser.add_argument('--resources-dir', required=True,
                        help='Path to analyst resources directory')
    parser.add_argument('--analysis-dir', action='append', required=True,
                        help='Path(s) to analysis directories (can repeat)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.resources_dir):
        print(f'Error: {args.resources_dir} not found', file=sys.stderr)
        sys.exit(2)

    print(f"\n{'═' * 60}")
    print(f"🗺️ 引擎覆蓋率矩陣 — {args.domain.upper()}")
    print(f"   資源目錄: {args.resources_dir}")
    print(f"{'═' * 60}")

    # Extract rules
    rules = extract_engine_rules(args.resources_dir)
    print(f"\n   📋 已定義規則: {len(rules)} 條")

    # Check coverage
    total_files = check_coverage(rules, args.analysis_dir)
    print(f"   📁 已掃描分析: {total_files} 個檔案")

    if total_files == 0:
        print(f"\n   ⚠️ 未搵到分析檔案")
        sys.exit(2)

    # Calculate coverage
    covered = sum(1 for r in rules.values() if r['covered'])
    uncovered = len(rules) - covered
    coverage_pct = (covered / len(rules) * 100) if rules else 0

    # Group by file
    by_file = defaultdict(lambda: {'covered': 0, 'total': 0, 'uncovered_rules': []})
    for rule in rules.values():
        by_file[rule['file']]['total'] += 1
        if rule['covered']:
            by_file[rule['file']]['covered'] += 1
        else:
            by_file[rule['file']]['uncovered_rules'].append(rule['rule'])

    print(f"\n   📊 整體覆蓋率: {covered}/{len(rules)} ({coverage_pct:.0f}%)")
    bar_len = 30
    filled = int(bar_len * coverage_pct / 100)
    bar = '█' * filled + '░' * (bar_len - filled)
    color = '🟢' if coverage_pct >= 70 else '🟡' if coverage_pct >= 50 else '🔴'
    print(f"   {color} [{bar}] {coverage_pct:.0f}%")

    # Per-file breakdown
    print(f"\n   📁 逐檔案覆蓋率:")
    for fname, data in sorted(by_file.items()):
        pct = data['covered'] / data['total'] * 100 if data['total'] > 0 else 0
        icon = '✅' if pct == 100 else '🟡' if pct >= 50 else '🔴'
        print(f"      {icon} {fname}: {data['covered']}/{data['total']} ({pct:.0f}%)")
        if data['uncovered_rules'] and pct < 100:
            for r in data['uncovered_rules'][:3]:
                print(f"         ❌ {r}")
            if len(data['uncovered_rules']) > 3:
                print(f"         ... 及 {len(data['uncovered_rules']) - 3} 條更多")

    # Top uncovered rules
    uncovered_rules = [r for r in rules.values() if not r['covered']]
    if uncovered_rules:
        print(f"\n   ❌ 未覆蓋規則 Top 10:")
        for r in uncovered_rules[:10]:
            print(f"      🔴 {r['file']} → {r['rule']}")
            if r['description']:
                print(f"         {r['description'][:60]}")

    # Summary
    print(f"\n{'═' * 60}")
    if coverage_pct >= 70:
        print(f"   ✅ 覆蓋率 {coverage_pct:.0f}% — 引擎規則覆蓋充足")
    elif coverage_pct >= 50:
        print(f"   🟡 覆蓋率 {coverage_pct:.0f}% — 部分規則未被測試")
        print(f"   → LLM 需檢查未覆蓋規則是否為死代碼")
    else:
        print(f"   🔴 覆蓋率 {coverage_pct:.0f}% — 大量規則未被使用")
        print(f"   → LLM 需全面審閱，可能有大量死規則待清理")
    print(f"{'═' * 60}")

    if args.json:
        json_rules = []
        for r in rules.values():
            json_rules.append({
                'file': r['file'],
                'rule': r['rule'],
                'description': r['description'],
                'covered': r['covered'],
                'cover_count': r['cover_count'],
            })
        print(json.dumps({
            'coverage_pct': round(coverage_pct, 1),
            'covered': covered,
            'total': len(rules),
            'uncovered': [r['rule'] for r in uncovered_rules],
            'rules': json_rules,
        }, ensure_ascii=False, indent=2))

    sys.exit(0 if coverage_pct >= 70 else 1)


if __name__ == '__main__':
    main()
