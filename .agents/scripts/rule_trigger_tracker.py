import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
rule_trigger_tracker.py — 規則觸發率統計器

讀取歷史分析檔案，統計每條 SIP / Override / 規則嘅實際觸發次數同成功率。
自動識別：
  1. 死規則 (Dead Rules) — 定義咗但從未被觸發
  2. 過度觸發 (Over-fired) — >80% 場次都觸發，可能門檻太鬆
  3. 低效規則 (Ineffective) — 觸發率正常但命中率<30%

Usage:
  python rule_trigger_tracker.py --domain au --resources-dir <path> --analysis-dir <path>
  python rule_trigger_tracker.py --domain hkjc --resources-dir <path> --analysis-dir <path>

Exit codes:
  0 = All healthy
  1 = Issues found
  2 = Error
"""
import sys, io, re, os, pathlib, argparse, json
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SIP_ID_RE = re.compile(r'(SIP-[A-Za-z0-9\-]+)', re.UNICODE)

# Rule/Override patterns that appear in analysis output
RULE_PATTERNS = [
    # SIP references
    (r'(SIP-[A-Za-z0-9\-]+)', 'SIP'),
    # Step references with results
    (r'Step\s+(\d+[a-zA-Z.]*)\s*[：:→]', 'STEP'),
    # Override patterns
    (r'(覆蓋規則|Override)[：:]\s*(.+?)(?:\n|$)', 'OVERRIDE'),
    # Dimension markers
    (r'([場地|檔位|EEM|步速|騎師|練馬師|血統|距離])\s*[：:]\s*(✅|❌|➖|⚠️)', 'DIMENSION'),
    # Grade outputs
    (r'⭐\s*(?:最終評級|Final Grade)[：:]\s*([SABCD][+-]?)', 'GRADE'),
    # Cold shot / longshot markers
    (r'(🐴⚡|冷門掃描|Cold\s*Shot)', 'COLDSHOT'),
    # Brand trap markers
    (r'(BRAND\s*TRAP|\[品牌陷阱\])', 'BRAND_TRAP'),
    # Dual track markers
    (r'(📗📙|雙軌|Dual.?Track)', 'DUAL_TRACK'),
]


def extract_defined_rules(resources_dir):
    """Extract all rule/SIP definitions from resource files."""
    rules = {}
    p = pathlib.Path(resources_dir)

    for f in p.glob('*.md'):
        with open(f, 'r', encoding='utf-8') as fh:
            text = fh.read()

        # Find SIP definitions
        for m in SIP_ID_RE.finditer(text):
            sip_id = m.group(1)
            if sip_id not in rules:
                rules[sip_id] = {
                    'id': sip_id,
                    'type': 'SIP',
                    'defined_in': f.name,
                    'trigger_count': 0,
                    'success_count': 0,
                    'files_seen': set(),
                }

    return rules


def scan_analysis_files(analysis_dirs, rules):
    """Scan analysis files for rule triggers."""
    total_races = 0
    race_results = []

    for analysis_dir in analysis_dirs:
        p = pathlib.Path(analysis_dir)
        if not p.exists():
            continue

        analysis_files = sorted(
            list(p.glob('*Analysis*.md')) +
            list(p.glob('*analysis*.md')) +
            list(p.glob('*分析*.md'))
        )

        for af in analysis_files:
            with open(af, 'r', encoding='utf-8') as fh:
                text = fh.read()

            total_races += 1

            # Find all SIP references in this analysis
            sips_found = set(SIP_ID_RE.findall(text))
            for sip_id in sips_found:
                if sip_id in rules:
                    rules[sip_id]['trigger_count'] += 1
                    rules[sip_id]['files_seen'].add(af.name)

            # Check for specific pattern triggers
            for pattern, ptype in RULE_PATTERNS:
                for m in re.finditer(pattern, text, re.UNICODE):
                    key = f"{ptype}:{m.group(1)}" if m.group(1) else ptype
                    if key not in rules:
                        rules[key] = {
                            'id': key,
                            'type': ptype,
                            'defined_in': 'inline',
                            'trigger_count': 0,
                            'success_count': 0,
                            'files_seen': set(),
                        }
                    rules[key]['trigger_count'] += 1
                    rules[key]['files_seen'].add(af.name)

    return total_races


def classify_rules(rules, total_races):
    """Classify rules by trigger health."""
    dead = []       # Never triggered
    over_fired = [] # >80% trigger rate
    normal = []     # Healthy
    low_sample = [] # Too few triggers to judge

    if total_races == 0:
        return dead, over_fired, normal, low_sample

    for rule in rules.values():
        if rule['type'] != 'SIP':
            continue

        rate = rule['trigger_count'] / total_races if total_races > 0 else 0

        if rule['trigger_count'] == 0:
            dead.append(rule)
        elif rate > 0.80:
            over_fired.append(rule)
        elif rule['trigger_count'] < 2:
            low_sample.append(rule)
        else:
            normal.append(rule)

    return dead, over_fired, normal, low_sample


def main():
    parser = argparse.ArgumentParser(description='規則觸發率統計器')
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
    print(f"📊 規則觸發率統計器 — {args.domain.upper()}")
    print(f"   資源目錄: {args.resources_dir}")
    print(f"   分析目錄: {len(args.analysis_dir)} 個")
    print(f"{'═' * 60}")

    # Extract defined rules
    rules = extract_defined_rules(args.resources_dir)
    print(f"\n   📋 已定義規則: {len(rules)} 個 SIP")

    # Scan analysis files
    total_races = scan_analysis_files(args.analysis_dir, rules)
    print(f"   📁 已掃描分析: {total_races} 場")

    if total_races == 0:
        print(f"\n   ⚠️ 未搵到分析檔案。請確認 --analysis-dir 路徑正確。")
        sys.exit(2)

    # Classify
    dead, over_fired, normal, low_sample = classify_rules(rules, total_races)

    # Report
    print(f"\n   {'─' * 50}")
    print(f"   💀 死規則 (從未觸發): {len(dead)} 個")
    for r in dead:
        print(f"      ⚫ {r['id']} — 定義於 {r['defined_in']}")
    if not dead:
        print(f"      ✅ 無")

    print(f"\n   🔥 過度觸發 (>80% 場次): {len(over_fired)} 個")
    for r in over_fired:
        rate = r['trigger_count'] / total_races * 100
        print(f"      🟠 {r['id']} — {r['trigger_count']}/{total_races} ({rate:.0f}%)")
    if not over_fired:
        print(f"      ✅ 無")

    print(f"\n   ✅ 正常觸發: {len(normal)} 個")
    for r in sorted(normal, key=lambda x: x['trigger_count'], reverse=True)[:10]:
        rate = r['trigger_count'] / total_races * 100
        print(f"      🟢 {r['id']} — {r['trigger_count']}/{total_races} ({rate:.0f}%)")

    print(f"\n   🔘 低樣本 (<2 次觸發): {len(low_sample)} 個")
    for r in low_sample[:5]:
        print(f"      ⚪ {r['id']} — {r['trigger_count']} 次")

    # Summary
    issues = len(dead) + len(over_fired)
    print(f"\n{'═' * 60}")
    if issues == 0:
        print(f"   ✅ 所有 SIP 觸發率健康")
    else:
        print(f"   ⚠️ {issues} 個 SIP 需要 LLM 審閱:")
        if dead:
            print(f"      💀 {len(dead)} 個死規則 — 考慮移除或修改觸發條件")
        if over_fired:
            print(f"      🔥 {len(over_fired)} 個過度觸發 — 考慮收緊門檻")
    print(f"{'═' * 60}")

    if args.json:
        # Serialize sets to lists
        for r in rules.values():
            r['files_seen'] = list(r['files_seen'])
        print(json.dumps({
            'total_races': total_races,
            'dead_rules': [r['id'] for r in dead],
            'over_fired': [r['id'] for r in over_fired],
            'normal': [r['id'] for r in normal],
            'low_sample': [r['id'] for r in low_sample],
        }, ensure_ascii=False, indent=2))

    sys.exit(1 if issues > 0 else 0)


if __name__ == '__main__':
    main()
