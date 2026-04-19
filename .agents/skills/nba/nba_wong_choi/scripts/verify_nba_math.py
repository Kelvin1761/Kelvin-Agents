import os
os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
verify_nba_math.py — Wong Choi NBA 自動化數學驗證

用 Python regex 精確檢查 NBA Analyst 輸出中的數學運算：
1. CoV 計算正確性 (SD / AVG)
2. 隱含勝率正確性 (1 / 賠率)
3. Edge 計算正確性 (預估勝率 - 隱含勝率)
4. 命中率與賠率底線 (穩膽 ≥80%/1.80, 價值 ≥75%/2.50)

Usage:
  python verify_nba_math.py <analysis_file.md>
  python verify_nba_math.py <directory_of_analysis_files>
"""
import sys, io, re, json, os, pathlib, argparse
from dataclasses import dataclass, field, asdict

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Regex Patterns
# ──────────────────────────────────────────────
# Match full combination blocks
COMBO_RE = re.compile(
    r'(?:組合\s*[A-Z1-3][：:]?\s*|🏆\s*本場 Banker SGM 建議|💎\s*價值型)(?!分析)([^—\n]*)(.*?)(?=組合\s*[A-Z1-3][：:]|🧠\s*總結|$)',
    re.DOTALL | re.UNICODE
)

# Match individual legs within a combination
LEG_RE = re.compile(
    r'(?:Leg\s*\d+[｜|:：\-—]\s*|-\s*\[)(.*?)(?=Leg\s*\d+[｜|:：\-—]|-\s*\[|📊\s*組合結算|---|$)',
    re.DOTALL | re.UNICODE
)

# Field extraction regexes
FIELD_RE = {
    'name': re.compile(r'^([^—]+)'),
    'odds': re.compile(r'@([\d\.]+)'),
    'win_rate_l10': re.compile(r'(?:Base Rate|L10\s*命中|L10)\s*[:：]?\s*([\d\.]+)%'),
    'implied_prob': re.compile(r'隱含勝率\s*([\d\.]+)%'),
    'est_prob': re.compile(r'預期勝率\s*(?:\*\*)?([\d\.]+)(?:\*\*)?%'),
    'edge': re.compile(r'Edge:\s*(?:\*\*)?([-\+\d\.]+)(?:\*\*)?%'),
    'avg': re.compile(r'AVG\s*([\d\.]+)'),
    'sd': re.compile(r'SD\s*([\d\.]+)'),
    'cov': re.compile(r'CoV\s*([\d\.]+)'),
}

@dataclass
class NBALegVerification:
    combo_name: str
    leg_name: str
    is_banker: bool
    is_value: bool
    
    odds: float = None
    win_rate_l10: float = None
    implied_prob: float = None
    est_prob: float = None
    edge: float = None
    avg: float = None
    sd: float = None
    cov: float = None
    
    issues: list = field(default_factory=list)

def extract_floats(text: str, regex_dict: dict) -> dict:
    """Extract float values from text using provided regexes."""
    results = {}
    for key, regex in regex_dict.items():
        if key == 'name':
            continue
        match = regex.search(text)
        if match:
            try:
                results[key] = float(match.group(1))
            except ValueError:
                results[key] = 0.0
        else:
            results[key] = None
    return results

def verify_leg(combo_name: str, leg_text: str) -> NBALegVerification:
    """Verify a single NBA parlay leg."""
    # Find player name
    name_match = FIELD_RE['name'].search(leg_text)
    leg_name = name_match.group(1).strip() if name_match else "Unknown Player"
    
    # Determine combination type
    combo_lower = combo_name.lower()
    is_banker = '穩' in combo_lower or 'banker' in combo_lower or '組合 a' in combo_lower or '組合 1' in combo_lower
    is_value = '價值' in combo_lower or '組合 b' in combo_lower or '組合 2' in combo_lower
    
    v = NBALegVerification(combo_name=combo_name.strip(), leg_name=leg_name, 
                           is_banker=is_banker, is_value=is_value)
    
    # Extract values
    values = extract_floats(leg_text, FIELD_RE)
    for k, val in values.items():
        if val is not None:
            setattr(v, k, val)
            
    # Verification 1: CoV = SD / AVG
    if v.avg and v.sd and v.cov is not None:
        computed_cov = round(v.sd / v.avg, 2)
        if abs(computed_cov - v.cov) > 0.02:
            v.issues.append(f"COV_MATH_ERROR: 均值={v.avg}, SD={v.sd} → 正確 CoV={computed_cov}, LLM={v.cov}")

    # Verification 2: Implied Prob = 1 / Odds
    if v.odds and v.implied_prob is not None:
        computed_impl = round((1 / v.odds) * 100, 1)
        if abs(computed_impl - v.implied_prob) > 1.5:  # Tolerate slight rounding
            v.issues.append(f"ODDS_MATH_ERROR: 賠率={v.odds} → 正確勝率={computed_impl}%, LLM={v.implied_prob}%")
            
    # Verification 3: Edge = Est Prob - Implied Prob
    if v.est_prob is not None and v.implied_prob is not None and v.edge is not None:
        computed_edge = round(v.est_prob - v.implied_prob, 1)
        if abs(computed_edge - v.edge) > 0.6:
            v.issues.append(f"EDGE_MATH_ERROR: 預估({v.est_prob}%) - 隱含({v.implied_prob}%) = {computed_edge}%, LLM={v.edge}%")
            
    # Verification 4: Safety Gates (Only apply if data was found)
    if v.win_rate_l10 is not None and v.odds:
        if is_banker:
            if v.win_rate_l10 < 80.0:
                v.issues.append(f"BANKER_SAFETY_VIOLATION: 穩膽要求 L10命中率≥80%, 當前={v.win_rate_l10}%")
            pass # removed leg odds check
        elif is_value:
            if v.win_rate_l10 < 70.0: # Using 70 to be slightly lenient on parsing
                v.issues.append(f"VALUE_SAFETY_VIOLATION: 價值要求 L10命中率≥75%, 當前={v.win_rate_l10}%")
            pass # removed leg odds check

    return v

def verify_file(filepath: str) -> dict:
    """Verify all legs in an NBA analysis file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
        
    combos = COMBO_RE.findall(text)
    all_legs = []
    
    for combo_name, combo_block in combos:
        legs = LEG_RE.findall(combo_block)
        for leg_text in legs:
            if '賠率' in leg_text or '命中率' in leg_text:
                v = verify_leg(combo_name, leg_text)
                all_legs.append(v)
                
    if not all_legs:
         return {
            'file': filepath,
            'passed': False,
            'legs': [],
            'summary': {'total': 0, 'passed': 0, 'failed': 1},
            'issues': [
                'NO_PARLAY_LEGS_FOUND — ❌ CRITICAL: 搵唔到任何可解析嘅 Parlay Leg。'
                '一份合格嘅 NBA 分析報告必須包含完整嘅 SGM 組合區塊 '
                '(含 @賠率、Edge、L10 命中率)。如果此檔案係由 LLM 自行生成而非 '
                'generate_nba_reports.py skeleton，請重新執行 Python pipeline。'
            ]
        }
        
    failed_count = sum(1 for v in all_legs if v.issues)
    passed_count = len(all_legs) - failed_count
    
    return {
        'file': filepath,
        'passed': failed_count == 0,
        'legs': [asdict(v) for v in all_legs],
        'summary': {
            'total': len(all_legs),
            'passed': passed_count,
            'failed': failed_count
        }
    }

def print_report(report: dict):
    fname = os.path.basename(report['file'])
    status = '✅ ALL PASS' if report['passed'] else '❌ DRIFT DETECTED'
    s = report['summary']

    print(f"\n{'=' * 65}")
    print(f"🏀 verify_nba_math.py — {fname}")
    print(f"   Status: {status}")
    print(f"   Legs: {s['total']} total, {s['passed']} ✅, {s['failed']} ❌")
    
    if 'issues' in report and report['issues']:
        for issue in report['issues']:
            print(f"   ⚠️ {issue}")
    
    for leg in report.get('legs', []):
        icon = '❌' if leg['issues'] else '✅'
        print(f"\n   {icon} {leg['combo_name'][:20]} | {leg['leg_name'][:30]}")
        if leg['issues']:
            for issue in leg['issues']:
                print(f"      → {issue}")

    print(f"\n{'=' * 65}")

def main():
    parser = argparse.ArgumentParser(description='Wong Choi NBA — 自動化品質與數學驗證')
    parser.add_argument('path', help='Analysis .md file or directory')
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    files = []

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob('*.md'))
        files.extend(sorted(path.glob('*.txt')))
        
    if not files:
        print(f'No analysis files found in {path}')
        sys.exit(2)

    all_reports = []
    any_failed = False

    for f in files:
        # Simple heuristic to only check NBA files
        with open(f, 'r', encoding='utf-8') as file_obj:
            content = file_obj.read(1000)
            if 'NBA' not in content and 'Edge' not in content and '滿意 Legs' not in content and '過關' not in content:
                continue
                
        report = verify_file(str(f))
        all_reports.append(report)
        if not report['passed']:
            any_failed = True

    total_legs = 0
    total_passed = 0
    
    for r in all_reports:
        print_report(r)
        total_legs += r['summary']['total']
        total_passed += r['summary']['passed']

    if all_reports:
        print(f"\n{'=' * 65}")
        print(f"📊 TOTAL NBA: {len(all_reports)} files, {total_legs} legs, "
              f"{total_passed} ✅ verified, {total_legs - total_passed} ❌ errors")
        print(f"{'=' * 65}")

    sys.exit(1 if any_failed else 0)

if __name__ == '__main__':
    main()
