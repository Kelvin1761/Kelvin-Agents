"""
reflector_verdict_validator.py — 裁定驗證器

後處理已完成嘅覆盤報告，驗證：
1. 每個裁定 (🟢/🔴/🟡) 有 ≥2 個證據點
2. 每個 SIP 引用指向真實存在嘅 resource 檔案
3. 報告結構完整性（所有必要 section 齊全）

Usage:
  python reflector_verdict_validator.py <report_file> --domain au|hkjc
  python reflector_verdict_validator.py <report_file> --domain au --resources-dir <path>

Exit codes:
  0 = PASS
  1 = FAIL (violations found)
  2 = Error
"""
import sys, io, re, os, pathlib, argparse

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# Required sections for a compliant reflector report
REQUIRED_SECTIONS = {
    'au': [
        '整體命中率',
        '逐場覆盤摘要',
        'False Positives',
        'False Negatives',
        '場地預測覆盤',
        '系統性改善建議',
        '敘事覆盤',
        '單場特殊因素',
        '引擎健康掃描',
    ],
    'hkjc': [
        '整體命中率',
        '逐場覆盤摘要',
        'False Positives',
        'False Negatives',
        '系統性改善建議',
        '敘事覆盤',
        '單場特殊因素',
        '引擎健康掃描',
    ],
}

VERDICT_EMOJIS = ['🟢', '🔴', '🟡']


def check_section_completeness(text, domain):
    """Check if all required sections are present."""
    missing = []
    for section in REQUIRED_SECTIONS[domain]:
        if section not in text:
            missing.append(section)
    return missing


def check_verdict_evidence(text):
    """Check that each verdict has ≥2 evidence points."""
    violations = []
    
    # Find verdict rows in the narrative post-mortem table
    table_rows = re.findall(
        r'\|\s*R?\d+\s*\|.*?\|.*?\|.*?\|.*?\|\s*([🟢🔴🟡][^|]*)\s*\|\s*([^|]*)\s*\|',
        text, re.UNICODE
    )
    
    for i, (verdict, evidence) in enumerate(table_rows, 1):
        verdict = verdict.strip()
        evidence = evidence.strip()
        
        if not verdict or verdict == '{{LLM_FILL}}':
            violations.append(f'Row {i}: 裁定欄位未填寫')
            continue
        
        if not evidence or evidence == '{{LLM_FILL}}':
            violations.append(f'Row {i}: 證據欄位未填寫（裁定: {verdict}）')
            continue
        
        # Count evidence points (separated by ; or + or 、or newline)
        evidence_points = re.split(r'[;+、\n]', evidence)
        evidence_points = [e.strip() for e in evidence_points if e.strip() and e.strip() != '{{LLM_FILL}}']
        
        if len(evidence_points) < 2:
            violations.append(
                f'Row {i}: 裁定 {verdict} 只有 {len(evidence_points)} 個證據點（需要 ≥2）'
            )
    
    return violations


def check_sip_references(text, resources_dir=None):
    """Check that SIP references point to real resource files."""
    violations = []
    
    # Find resource file references in SIP sections
    file_refs = re.findall(r'`(\d{2}[a-z]?_[\w_]+\.md)`', text)
    
    if resources_dir and file_refs:
        p = pathlib.Path(resources_dir)
        for ref in file_refs:
            if not list(p.glob(f'**/{ref}')):
                violations.append(f'SIP 引用檔案 `{ref}` 不存在')
    
    # Check for unfilled SIP placeholders
    sip_headers = re.findall(r'###\s*SIP-\S+[：:]\s*(.+)', text)
    for header in sip_headers:
        if '{{LLM_FILL}}' in header:
            violations.append(f'SIP 標題未填寫: {header}')
    
    return violations


def check_unfilled_placeholders(text):
    """Check remaining {{LLM_FILL}} placeholders with critical vs optional classification."""
    total = text.count('{{LLM_FILL}}')

    # Critical fields — unfilled = FAIL
    CRITICAL_CONTEXTS = [
        '關鍵偏差',      # Per-race deviation
        '偏差類型',      # Per-race deviation type
        '失誤根因',      # False Positive root cause
        '遺漏因素',      # False Negative missed factor
        '裁定',          # Narrative verdict (🟢🔴🟡)
        '證據',          # Narrative evidence
        '問題',          # SIP issue description
    ]

    critical_unfilled = 0
    optional_unfilled = 0
    lines = text.split('\n')
    for line in lines:
        if '{{LLM_FILL}}' not in line:
            continue
        is_critical = any(ctx in line for ctx in CRITICAL_CONTEXTS)
        fill_count = line.count('{{LLM_FILL}}')
        if is_critical:
            critical_unfilled += fill_count
        else:
            optional_unfilled += fill_count

    return {'total': total, 'critical': critical_unfilled, 'optional': optional_unfilled}


def check_hit_rate_tables(text):
    """Verify hit rate tables have actual data, not placeholders."""
    violations = []
    
    # Check for required hit rate metrics
    for metric in ['黃金標準', '良好結果', '最低門檻']:
        if metric not in text:
            violations.append(f'缺少命中率指標: {metric}')
    
    return violations


def check_verdict_statistics(text):
    """Check that verdict statistics section is filled."""
    violations = []
    
    verdict_stats = re.search(r'裁定統計(.*?)(?=##|\Z)', text, re.DOTALL)
    if not verdict_stats:
        violations.append('缺少「裁定統計」section')
    elif '{{LLM_FILL}}' in verdict_stats.group(1):
        violations.append('裁定統計尚有未填寫欄位')
    
    return violations


def main():
    parser = argparse.ArgumentParser(description='裁定驗證器')
    parser.add_argument('report_file', help='Reflector report file to validate')
    parser.add_argument('--domain', required=True, choices=['au', 'hkjc'])
    parser.add_argument('--resources-dir', help='Analyst resources directory for SIP reference checking')
    args = parser.parse_args()

    if not os.path.isfile(args.report_file):
        print(f'Error: {args.report_file} not found', file=sys.stderr)
        sys.exit(2)

    with open(args.report_file, 'r', encoding='utf-8') as f:
        text = f.read()

    print(f"\n{'═' * 55}")
    print(f"🔬 覆盤報告裁定驗證 — {args.domain.upper()}")
    print(f"   檔案: {os.path.basename(args.report_file)}")
    print(f"{'═' * 55}")

    all_violations = []

    # 1. Section completeness
    missing = check_section_completeness(text, args.domain)
    if missing:
        for m in missing:
            all_violations.append(f'❌ 缺少必要 section: {m}')
    print(f"\n   📋 結構完整性: {'✅' if not missing else '❌'} ({len(missing)} 項缺失)")

    # 2. Verdict evidence
    evidence_v = check_verdict_evidence(text)
    if evidence_v:
        all_violations.extend(evidence_v)
    print(f"   📝 裁定證據: {'✅' if not evidence_v else '❌'} ({len(evidence_v)} 項違規)")

    # 3. SIP references
    sip_v = check_sip_references(text, args.resources_dir)
    if sip_v:
        all_violations.extend(sip_v)
    print(f"   🔗 SIP 引用: {'✅' if not sip_v else '❌'} ({len(sip_v)} 項問題)")

    # 4. Hit rate tables
    hit_v = check_hit_rate_tables(text)
    if hit_v:
        all_violations.extend(hit_v)
    print(f"   📊 命中率表: {'✅' if not hit_v else '❌'} ({len(hit_v)} 項缺失)")

    # 5. Verdict statistics
    stats_v = check_verdict_statistics(text)
    if stats_v:
        all_violations.extend(stats_v)
    print(f"   📈 裁定統計: {'✅' if not stats_v else '❌'} ({len(stats_v)} 項問題)")

    # 6. Unfilled placeholders (2-tier: critical vs optional)
    ph = check_unfilled_placeholders(text)
    print(f"   🔲 未填佔位符: {ph['total']} 個 (🔴 critical: {ph['critical']}, 🟡 optional: {ph['optional']})")
    if ph['critical'] > 0:
        all_violations.append(f"🔴 仍有 {ph['critical']} 個 CRITICAL {{{{LLM_FILL}}}} 未填寫（關鍵偏差/裁定/證據等）")
    if ph['optional'] > 0:
        print(f"   ⚠️ WARNING: {ph['optional']} 個 optional 佔位符未填（唔影響 PASS/FAIL）")

    # Final verdict
    print(f"\n{'═' * 55}")
    if not all_violations:
        print(f"   ✅ PASSED — 覆盤報告通過所有驗證")
    else:
        print(f"   ❌ FAILED — {len(all_violations)} 項違規")
        for v in all_violations[:10]:
            print(f"      • {v}")
        if len(all_violations) > 10:
            print(f"      ... 及 {len(all_violations) - 10} 項更多")
    print(f"{'═' * 55}")

    sys.exit(0 if not all_violations else 1)


if __name__ == '__main__':
    main()
