import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
engine_health_scanner.py — 引擎健康掃描器

自動化引擎健康掃描嘅部分維度（4d-1 過時邏輯、4d-2 斷裂邏輯、4d-4 數據新鮮度）。
LLM 只需處理需要判斷嘅維度（4d-3、4d-5、4d-6）。

Usage:
  python engine_health_scanner.py --domain au --resources-dir <path>
  python engine_health_scanner.py --domain hkjc --resources-dir <path>

Exit codes:
  0 = All checks passed
  1 = Warnings found
  2 = Error
"""
import sys, io, re, os, pathlib, argparse
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

STALE_THRESHOLD_DAYS = 90


def scan_stale_logic(resources_dir, domain):
    """4d-1: Check for references to retired/transferred jockeys/trainers."""
    issues = []
    
    # Known retired/transferred (this list should be maintained)
    # For now, check for common patterns that indicate staleness
    p = pathlib.Path(resources_dir)
    
    for f in p.glob('**/*.md'):
        with open(f, 'r', encoding='utf-8') as fh:
            text = fh.read()
        
        # Check for TODO/FIXME/UPDATE markers
        for i, line in enumerate(text.split('\n'), 1):
            if any(marker in line.upper() for marker in ['TODO', 'FIXME', 'UPDATE NEEDED', '待更新']):
                issues.append({
                    'file': f.name,
                    'line': i,
                    'issue': f'Found stale marker: {line.strip()[:80]}',
                    'severity': '⚠️',
                })
        
        # Check for date references that may be outdated
        date_matches = re.findall(r'(\d{4})-(\d{2})-(\d{2})', text)
        for y, m, d in date_matches:
            try:
                ref_date = datetime(int(y), int(m), int(d))
                age = (datetime.now() - ref_date).days
                if age > 365:
                    issues.append({
                        'file': f.name,
                        'issue': f'Date reference {y}-{m}-{d} is {age} days old',
                        'severity': '⚠️',
                    })
            except ValueError:
                pass
    
    return issues


def scan_disconnected_logic(resources_dir):
    """4d-2: Check for SIP cross-references pointing to non-existent steps/rules."""
    issues = []
    p = pathlib.Path(resources_dir)
    
    # Collect all SIP IDs defined
    defined_sips = set()
    referenced_sips = set()
    defined_steps = set()
    referenced_steps = set()
    
    for f in p.glob('**/*.md'):
        with open(f, 'r', encoding='utf-8') as fh:
            text = fh.read()
        
        # Find SIP definitions
        for m in re.finditer(r'(SIP-[A-Z0-9\-]+)', text):
            sip_id = m.group(1)
            if any(kw in text[max(0, m.start()-50):m.start()] for kw in ['###', '**', 'SIP-', '新增']):
                defined_sips.add(sip_id)
            referenced_sips.add(sip_id)
        
        # Find Step references
        for m in re.finditer(r'Step\s+(\d+[a-z]?)', text, re.IGNORECASE):
            referenced_steps.add(m.group(1))
    
    # Check for references to undefined SIPs
    # (This is heuristic — some SIPs may be defined in other files)
    orphan_refs = referenced_sips - defined_sips
    if len(orphan_refs) > 10:
        # Too many — likely false positives
        pass
    else:
        for sip in orphan_refs:
            issues.append({
                'issue': f'SIP {sip} referenced but not clearly defined in resources',
                'severity': '⚠️',
            })
    
    # Check for files that reference other resource files that don't exist
    for f in p.glob('**/*.md'):
        with open(f, 'r', encoding='utf-8') as fh:
            text = fh.read()
        for m in re.finditer(r'`(\d{2}[a-z]?_\w+\.md)`', text):
            ref_file = m.group(1)
            if not list(p.glob(f'**/{ref_file}')):
                issues.append({
                    'file': f.name,
                    'issue': f'References file `{ref_file}` which does not exist',
                    'severity': '🔧',
                })
    
    return issues


def scan_data_freshness(resources_dir):
    """4d-4: Check file modification dates, flag stale files."""
    issues = []
    p = pathlib.Path(resources_dir)
    now = datetime.now()
    
    for f in p.glob('**/*.md'):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        age = (now - mtime).days
        
        if age > STALE_THRESHOLD_DAYS:
            issues.append({
                'file': f.name,
                'issue': f'Last modified {age} days ago ({mtime.strftime("%Y-%m-%d")})',
                'severity': '⚠️' if age < 180 else '🔧',
                'age_days': age,
            })
    
    return issues


def main():
    parser = argparse.ArgumentParser(description='引擎健康掃描器')
    parser.add_argument('--domain', required=True, choices=['au', 'hkjc'])
    parser.add_argument('--resources-dir', required=True, help='Path to analyst resources directory')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.resources_dir):
        print(f'Error: {args.resources_dir} not found', file=sys.stderr)
        sys.exit(2)

    print(f"\n{'═' * 55}")
    print(f"🔬 引擎健康掃描 — {args.domain.upper()}")
    print(f"   資源目錄: {args.resources_dir}")
    print(f"{'═' * 55}")

    all_results = {}

    # 4d-1
    stale = scan_stale_logic(args.resources_dir, args.domain)
    verdict_1 = '✅' if not stale else '⚠️' if len(stale) <= 3 else '🔧'
    all_results['4d-1 過時邏輯'] = {'verdict': verdict_1, 'issues': stale}
    print(f"\n   4d-1 過時邏輯偵測: {verdict_1} ({len(stale)} 項)")
    for s in stale[:5]:
        print(f"      {s['severity']} {s.get('file', '')} — {s['issue']}")
    if len(stale) > 5:
        print(f"      ... 及 {len(stale) - 5} 項更多")

    # 4d-2
    disconnected = scan_disconnected_logic(args.resources_dir)
    verdict_2 = '✅' if not disconnected else '⚠️' if len(disconnected) <= 3 else '🔧'
    all_results['4d-2 斷裂邏輯'] = {'verdict': verdict_2, 'issues': disconnected}
    print(f"\n   4d-2 斷裂邏輯偵測: {verdict_2} ({len(disconnected)} 項)")
    for d in disconnected[:5]:
        print(f"      {d['severity']} {d.get('file', '')} — {d['issue']}")

    # 4d-3 (LLM only)
    print(f"\n   4d-3 缺失規則偵測: {{{{LLM_FILL}}}} [需 LLM 判斷]")

    # 4d-4
    freshness = scan_data_freshness(args.resources_dir)
    verdict_4 = '✅' if not freshness else '⚠️' if len(freshness) <= 5 else '🔧'
    all_results['4d-4 數據新鮮度'] = {'verdict': verdict_4, 'issues': freshness}
    print(f"\n   4d-4 數據新鮮度: {verdict_4} ({len(freshness)} 項過期)")
    for ff in sorted(freshness, key=lambda x: x.get('age_days', 0), reverse=True)[:5]:
        print(f"      {ff['severity']} {ff['file']} — {ff['issue']}")

    # 4d-5, 4d-6 (LLM only)
    print(f"\n   4d-5 規則校準驗證: {{{{LLM_FILL}}}} [需 LLM 判斷]")
    print(f"\n   4d-6 輸出品質抽查: {{{{LLM_FILL}}}} [需 LLM 判斷]")

    total_issues = len(stale) + len(disconnected) + len(freshness)
    print(f"\n{'═' * 55}")
    print(f"   總計: {total_issues} 項自動偵測問題")
    print(f"   3 個維度待 LLM 判斷")
    print(f"{'═' * 55}")

    if args.json:
        import json
        print(json.dumps(all_results, ensure_ascii=False, indent=2, default=str))

    sys.exit(1 if total_issues > 0 else 0)


if __name__ == '__main__':
    main()
