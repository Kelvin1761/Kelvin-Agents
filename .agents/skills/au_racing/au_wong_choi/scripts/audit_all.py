import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
audit_all.py — Wong Choi 全局歷史回測 Grading Drift Report

掃描所有歷史 Analysis.md 檔案，批量行 verify_math 邏輯，
輸出一份統計報告：邊個賽區/賽場/時期最容易出現 Grading Drift。

Usage:
  python audit_all.py <archive_directory>
  python audit_all.py <archive_directory> --json
  python audit_all.py <archive_directory> --csv

Exit codes:
  0 = All clean
  1 = Drift detected
"""
import sys, io, os, re, json, pathlib, argparse, importlib.util
from collections import defaultdict
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Import verify_math core functions
# ──────────────────────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).parent
# Try to find verify_math.py in known locations
VERIFY_PATHS = [
    SCRIPT_DIR.parent.parent / 'au_racing' / 'au_wong_choi' / 'scripts' / 'verify_math.py',
    SCRIPT_DIR.parent.parent / 'hkjc_racing' / 'hkjc_wong_choi' / 'scripts' / 'verify_math.py',
    SCRIPT_DIR / 'verify_math.py',
]

verify_math = None
for vp in VERIFY_PATHS:
    if vp.exists():
        spec = importlib.util.spec_from_file_location("verify_math", str(vp))
        verify_math = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify_math)
        break

if verify_math is None:
    print("ERROR: Cannot find verify_math.py. Place audit_all.py alongside it or in skills root.")
    sys.exit(2)


def find_all_analysis_files(root: str) -> list:
    """Recursively find all Analysis.md files."""
    root_path = pathlib.Path(root)
    files = []
    for pattern in ['*Analysis*.md', '*analysis*.md']:
        files.extend(root_path.rglob(pattern))
    # Deduplicate
    seen = set()
    unique = []
    for f in files:
        if f.resolve() not in seen:
            seen.add(f.resolve())
            unique.append(f)
    return sorted(unique)


def extract_metadata(filepath: pathlib.Path) -> dict:
    """Extract venue, date, race number from file path/name."""
    name = filepath.name
    parent = filepath.parent.name
    
    # Try to extract date (YYYY-MM-DD or YYYY_MM_DD)
    date_match = re.search(r'(\d{4})[_-](\d{2})[_-](\d{2})', str(filepath))
    date_str = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else 'unknown'
    
    # Try to extract venue
    venue = 'unknown'
    for v in ['Warwick Farm', 'Randwick', 'Rosehill', 'Canterbury', 'Newcastle',
              'Flemington', 'Caulfield', 'Moonee Valley', 'Sandown',
              'Eagle Farm', 'Doomben', 'Gosford', 'Kembla Grange',
              'ShaTin', 'Sha Tin', 'HappyValley', 'Happy Valley',
              'Sha_Tin', 'Happy_Valley']:
        if v.lower().replace(' ', '') in str(filepath).lower().replace(' ', '').replace('_', ''):
            venue = v.replace('_', ' ')
            break
    
    # Try to extract race number
    race_match = re.search(r'[Rr]ace[_\s]*(\d+)', name)
    race_num = int(race_match.group(1)) if race_match else 0
    
    # Determine region
    region = 'AU'
    if any(x in str(filepath).lower() for x in ['hkjc', 'shatin', 'sha_tin', 'happyvalley', 'happy_valley']):
        region = 'HKJC'
    
    return {
        'date': date_str,
        'venue': venue,
        'race_num': race_num,
        'region': region,
        'path': str(filepath),
    }


def run_audit(root_dir: str) -> dict:
    """Run full audit across all historical analysis files."""
    files = find_all_analysis_files(root_dir)
    
    if not files:
        return {'error': f'No analysis files found in {root_dir}', 'files_scanned': 0}
    
    results = []
    totals = {
        'files_scanned': len(files),
        'total_horses': 0,
        'horses_with_issues': 0,
        'base_grade_mismatches': 0,
        'final_grade_drifts': 0,
        'core_constraint_violations': 0,
        'count_mismatches': 0,
        'missing_arithmetic': 0,
        'missing_base_grade': 0,
        'missing_final_grade': 0,
    }
    
    by_venue = defaultdict(lambda: {'total': 0, 'drifts': 0})
    by_date = defaultdict(lambda: {'total': 0, 'drifts': 0})
    by_region = defaultdict(lambda: {'total': 0, 'drifts': 0})
    worst_drifts = []  # Top N worst grade drifts
    
    for filepath in files:
        meta = extract_metadata(filepath)
        
        try:
            report = verify_math.verify_file(str(filepath))
        except Exception as e:
            results.append({
                'file': str(filepath),
                'error': str(e),
                'meta': meta,
            })
            continue
        
        for horse in report.get('horses', []):
            totals['total_horses'] += 1
            venue = meta['venue']
            date = meta['date']
            region = meta['region']
            
            by_venue[venue]['total'] += 1
            by_date[date]['total'] += 1
            by_region[region]['total'] += 1
            
            has_issue = False
            issue_types = set()
            
            for issue in horse.get('issues', []):
                if 'BASE_GRADE_MISMATCH' in issue:
                    totals['base_grade_mismatches'] += 1
                    has_issue = True
                    issue_types.add('BASE_MISMATCH')
                elif 'FINAL_GRADE_DRIFT' in issue:
                    totals['final_grade_drifts'] += 1
                    has_issue = True
                    issue_types.add('FINAL_DRIFT')
                elif 'CORE_CONSTRAINT' in issue:
                    totals['core_constraint_violations'] += 1
                    has_issue = True
                    issue_types.add('CORE_VIOLATION')
                elif 'COUNT_MISMATCH' in issue:
                    totals['count_mismatches'] += 1
                    has_issue = True
                    issue_types.add('COUNT_MISMATCH')
                elif 'NO_ARITHMETIC' in issue:
                    totals['missing_arithmetic'] += 1
                elif 'NO_BASE_GRADE' in issue:
                    totals['missing_base_grade'] += 1
                elif 'NO_FINAL_GRADE' in issue:
                    totals['missing_final_grade'] += 1
            
            if has_issue:
                totals['horses_with_issues'] += 1
                by_venue[venue]['drifts'] += 1
                by_date[date]['drifts'] += 1
                by_region[region]['drifts'] += 1
                
                # Track worst drifts
                computed = horse.get('computed_base_grade', '')
                llm_final = horse.get('llm_final_grade', '')
                if computed and llm_final:
                    diff = verify_math.grade_diff(computed, llm_final)
                    if diff >= 2:
                        worst_drifts.append({
                            'file': os.path.basename(str(filepath)),
                            'horse': f"#{horse['number']} {horse['name']}",
                            'computed': computed,
                            'llm_grade': llm_final,
                            'drift': int(diff),
                            'venue': venue,
                            'date': date,
                            'issues': list(issue_types),
                        })
    
    # Sort worst drifts
    worst_drifts.sort(key=lambda x: x['drift'], reverse=True)
    
    # Compute venue drift rates
    venue_rates = []
    for venue, data in sorted(by_venue.items(), key=lambda x: -x[1]['drifts']):
        rate = round(data['drifts'] / data['total'] * 100, 1) if data['total'] > 0 else 0
        venue_rates.append({
            'venue': venue, 'total': data['total'],
            'drifts': data['drifts'], 'rate': rate
        })
    
    # Compute date drift rates
    date_rates = []
    for date, data in sorted(by_date.items()):
        rate = round(data['drifts'] / data['total'] * 100, 1) if data['total'] > 0 else 0
        date_rates.append({
            'date': date, 'total': data['total'],
            'drifts': data['drifts'], 'rate': rate
        })
    
    region_rates = []
    for region, data in sorted(by_region.items()):
        rate = round(data['drifts'] / data['total'] * 100, 1) if data['total'] > 0 else 0
        region_rates.append({
            'region': region, 'total': data['total'],
            'drifts': data['drifts'], 'rate': rate
        })
    
    return {
        'totals': totals,
        'by_venue': venue_rates,
        'by_date': date_rates,
        'by_region': region_rates,
        'worst_drifts': worst_drifts[:20],  # Top 20
    }


def print_report(report: dict):
    """Print formatted audit report."""
    t = report['totals']
    
    drift_rate = round(t['horses_with_issues'] / t['total_horses'] * 100, 1) if t['total_horses'] > 0 else 0
    
    print(f"\n{'=' * 70}")
    print(f"🔬 audit_all.py — Wong Choi 全局歷史 Grading Drift 審計報告")
    print(f"{'=' * 70}")
    print(f"\n📊 全局統計")
    print(f"   檔案掃描: {t['files_scanned']}")
    print(f"   馬匹總數: {t['total_horses']}")
    print(f"   有問題馬匹: {t['horses_with_issues']} ({drift_rate}%)")
    print(f"\n   問題分類:")
    print(f"   ├─ 基礎評級查表不符: {t['base_grade_mismatches']}")
    print(f"   ├─ 最終評級微調過度: {t['final_grade_drifts']}")
    print(f"   ├─ 核心門檻違規 (有核心❌但>B+): {t['core_constraint_violations']}")
    print(f"   ├─ 符號計數不符: {t['count_mismatches']}")
    print(f"   └─ 缺少 🔢 矩陣算術行: {t['missing_arithmetic']}")
    
    if report['by_region']:
        print(f"\n🌏 賽區 Drift 率")
        for r in report['by_region']:
            bar = '█' * int(r['rate'] / 5) + '░' * (20 - int(r['rate'] / 5))
            print(f"   {r['region']:6s} {bar} {r['drifts']}/{r['total']} ({r['rate']}%)")
    
    if report['by_venue']:
        print(f"\n🏟️  馬場 Drift 率 (由高到低)")
        for v in report['by_venue'][:10]:
            bar = '█' * int(v['rate'] / 5) + '░' * (20 - int(v['rate'] / 5))
            print(f"   {v['venue']:20s} {bar} {v['drifts']}/{v['total']} ({v['rate']}%)")
    
    if report['by_date']:
        print(f"\n📅 按日期 Drift 率")
        for d in report['by_date']:
            bar = '█' * int(d['rate'] / 5) + '░' * (20 - int(d['rate'] / 5))
            print(f"   {d['date']} {bar} {d['drifts']}/{d['total']} ({d['rate']}%)")
    
    if report['worst_drifts']:
        print(f"\n🚨 最嚴重 Drift (差距≥2級)")
        for w in report['worst_drifts'][:10]:
            print(f"   {w['horse']:25s} 查表=[{w['computed']}] LLM=[{w['llm_grade']}] "
                  f"差{w['drift']}級 | {w['venue']} {w['date']}")
    
    print(f"\n{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(
        description='Wong Choi 全局歷史 Grading Drift 審計'
    )
    parser.add_argument('path', help='Archive directory to scan recursively')
    parser.add_argument('--json', action='store_true', help='JSON output')
    parser.add_argument('--csv', action='store_true', help='CSV output of worst drifts')
    args = parser.parse_args()
    
    path = pathlib.Path(args.path)
    if not path.is_dir():
        print(f'Error: {path} is not a directory')
        sys.exit(2)
    
    print(f"🔍 掃描 {path} ...")
    report = run_audit(str(path))
    
    if 'error' in report:
        print(f"Error: {report['error']}")
        sys.exit(2)
    
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.csv:
        print("file,horse,computed_grade,llm_grade,drift_levels,venue,date")
        for w in report.get('worst_drifts', []):
            print(f"{w['file']},{w['horse']},{w['computed']},{w['llm_grade']},"
                  f"{w['drift']},{w['venue']},{w['date']}")
    else:
        print_report(report)
    
    has_drift = report['totals']['horses_with_issues'] > 0
    sys.exit(1 if has_drift else 0)


if __name__ == '__main__':
    main()
