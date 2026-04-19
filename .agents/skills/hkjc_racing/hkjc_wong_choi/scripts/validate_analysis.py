import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
validate_analysis.py — Wong Choi Analysis Quality Validator (P0)

Scans a HKJC/AU Analysis.md file and checks every horse for:
1. Structural completeness (7 mandatory section headers)
2. Word count minimum (250 chars hard floor)
3. Rating matrix format (8 dimensions on separate lines)
4. Verdict section (Top 4 with 🥇🥈🥉🏅)
5. CSV block presence

Usage:
  python validate_analysis.py <analysis_file.md>
  python validate_analysis.py <directory_of_analysis_files>

Exit codes:
  0 = All horses PASS
  1 = At least one horse FAIL

Output: JSON report to stdout + human-readable summary
"""
import sys, io, re, json, os, pathlib, argparse

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
MANDATORY_SECTIONS = [
    ("🔬 段速法醫", "🔬"),
    ("⚡ EEM",      "⚡"),
    ("📋 寬恕檔案", "📋"),
    ("🔗 賽績線",   "🔗"),
    ("📊 評級矩陣", "📊"),
    ("💡 結論",     "💡"),
    ("⭐ 最終評級", "⭐"),
]

MATRIX_CATEGORIES = ["核心", "半核心", "輔助"]

VERDICT_PICKS_MIN = 4   # Minimum Top N picks expected
MIN_CHARS_PER_HORSE = 250  # Hard minimum
WORD_COUNT_RATIO_THRESHOLD = 0.35  # Min/Max ratio

# ──────────────────────────────────────────────
# Horse block splitting
# ──────────────────────────────────────────────
HORSE_HEADER_RE = re.compile(
    r'(?:'
    r'^\*\*\[?(\d+)\]?\s+(.+?)\*\*\s*\|'   # Kelvin: **[1] Name** |
    r'|'
    r'^###\s+(\d+)\s+(.+?)\s*\|'            # Heison: ### 1 Name |
    r')',
    re.MULTILINE
)

def split_horses(text):
    """Split analysis text into individual horse blocks."""
    matches = list(HORSE_HEADER_RE.finditer(text))
    horses = []
    for i, m in enumerate(matches):
        num = m.group(1) or m.group(3)
        name = (m.group(2) or m.group(4) or "").strip()
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        block = text[start:end]
        horses.append({
            "number": int(num) if num else 0,
            "name": name,
            "block": block,
        })
    return horses

# ──────────────────────────────────────────────
# Per-horse validation
# ──────────────────────────────────────────────
def validate_horse(horse):
    """Validate a single horse block. Returns (pass, issues)."""
    block = horse["block"]
    issues = []
    
    # 1. Check mandatory section headers
    missing_sections = []
    for section_name, emoji in MANDATORY_SECTIONS:
        if emoji not in block:
            missing_sections.append(section_name)
    
    if missing_sections:
        issues.append(f"MISSING_SECTIONS: {', '.join(missing_sections)}")
    
    # 2. Word count (character count for Chinese)
    # Remove headers, separators, whitespace for counting
    clean = re.sub(r'[\s\-=\*#\|`>]', '', block)
    char_count = len(clean)
    if char_count < MIN_CHARS_PER_HORSE:
        issues.append(f"BELOW_MIN_CHARS: {char_count} < {MIN_CHARS_PER_HORSE}")
    
    # 3. Rating matrix dimensions count
    matrix_dims = len(re.findall(r'-\s*.+?\[(?:核心|半核心|輔助)\]', block))
    if "📊" in block and matrix_dims < 7:
        issues.append(f"MATRIX_INCOMPLETE: {matrix_dims}/8 dimensions")
    
    # 4. Check for core logic / conclusion
    has_core_logic = bool(re.search(r'核心邏輯|結論[：:]', block))
    if "💡" in block and not has_core_logic:
        issues.append("MISSING_CORE_LOGIC: No 核心邏輯 or 結論 found in 💡 section")
    
    # 5. Final grade
    has_grade = bool(re.search(r'⭐.*最終評級.*[SABCD][+\-]?', block))
    if not has_grade:
        issues.append("MISSING_FINAL_GRADE")
    
    passed = len(issues) == 0
    return {
        "number": horse["number"],
        "name": horse["name"],
        "passed": passed,
        "char_count": char_count,
        "sections_found": 7 - len(missing_sections),
        "sections_total": 7,
        "matrix_dims": matrix_dims,
        "issues": issues,
    }

# ──────────────────────────────────────────────
# File-level validation
# ──────────────────────────────────────────────
def validate_file(filepath):
    """Validate an entire analysis file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    horses = split_horses(text)
    if not horses:
        return {
            "file": str(filepath),
            "passed": False, 
            "horses": [],
            "summary": {"total": 0, "passed": 0, "failed": 0},
            "issues": ["NO_HORSES_FOUND"],
        }
    
    results = [validate_horse(h) for h in horses]
    
    # Word count ratio check
    char_counts = [r["char_count"] for r in results]
    min_count = min(char_counts) if char_counts else 0
    max_count = max(char_counts) if char_counts else 1
    ratio = min_count / max_count if max_count > 0 else 0
    
    # Verdict checks
    has_csv = '```csv' in text
    verdict_emojis = len(re.findall(r'🥇|🥈|🥉|🏅', text))
    top_n = 0
    top_match = re.search(r'Top\s*(\d)', text)
    if top_match:
        top_n = int(top_match.group(1))
    
    # Top 4 verdict format consistency checks (P25)
    verdict_section = ""
    verdict_start = re.search(r'(?:第三部分|最終預測|The Verdict|Top.*(?:精選|Verdict|位置))', text)
    if verdict_start:
        verdict_section = text[verdict_start.start():]
    
    file_issues = []
    if not has_csv:
        file_issues.append("MISSING_CSV_BLOCK")
    if verdict_emojis < 4:
        file_issues.append(f"VERDICT_INCOMPLETE: Only {verdict_emojis} pick emojis (need 4: 🥇🥈🥉🏅)")
    if top_n > 0 and top_n < VERDICT_PICKS_MIN:
        file_issues.append(f"TOP_N_TOO_LOW: Top {top_n} (need Top {VERDICT_PICKS_MIN})")
    if ratio < WORD_COUNT_RATIO_THRESHOLD and len(results) > 1:
        file_issues.append(f"WORD_COUNT_IMBALANCE: ratio={ratio:.2f} (min={min_count}, max={max_count})")
    
    # Verdict structure checks
    if verdict_section:
        # Each pick should have: 馬號 + 評級 + 核心理據 + 最大風險 (馬名 auto-populated by compile scripts)
        pick_fields_expected = ["馬號", "評級", "核心理據", "最大風險"]
        for field in pick_fields_expected:
            if field not in verdict_section:
                file_issues.append(f"VERDICT_FORMAT: Missing '{field}' in verdict picks")
        
        # Check for Top 2 confidence
        if "信心度" not in verdict_section and "Confidence" not in verdict_section:
            file_issues.append("VERDICT_FORMAT: Missing Top 2 入三甲信心度")
        
        # Check for pace flip insurance
        if "步速逆轉" not in verdict_section and "Pace Flip" not in verdict_section:
            file_issues.append("VERDICT_FORMAT: Missing 步速逆轉保險")
        
        # Check for emergency brake
        if "緊急煞車" not in verdict_section and "Emergency Brake" not in verdict_section:
            file_issues.append("VERDICT_FORMAT: Missing 緊急煞車檢查")
    elif horses:
        file_issues.append("VERDICT_FORMAT: No verdict section found")
    
    # Check for Part 4 blind spot
    has_blind_spot = bool(re.search(r'第四部分|分析盲區', text))
    if not has_blind_spot and horses:
        file_issues.append("MISSING_BLIND_SPOT: No [第四部分] 分析盲區 section")
    
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    all_passed = failed_count == 0 and len(file_issues) == 0
    
    return {
        "file": str(filepath),
        "passed": all_passed,
        "horses": results,
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "min_chars": min_count,
            "max_chars": max_count,
            "ratio": round(ratio, 2),
            "has_csv": has_csv,
            "verdict_emojis": verdict_emojis,
        },
        "file_issues": file_issues,
    }

# ──────────────────────────────────────────────
# Pretty print
# ──────────────────────────────────────────────
def print_report(report):
    """Print human-readable report."""
    fname = os.path.basename(report["file"])
    status = "✅ PASSED" if report["passed"] else "❌ FAILED"
    s = report["summary"]
    
    print(f"\n{'='*60}")
    print(f"📄 {fname}")
    print(f"   Status: {status}")
    print(f"   Horses: {s['total']} total, {s['passed']} passed, {s['failed']} failed")
    print(f"   Chars: min={s.get('min_chars',0)} max={s.get('max_chars',0)} ratio={s.get('ratio',0):.0%}")
    print(f"   CSV: {'✅' if s.get('has_csv') else '❌'}  Verdict emojis: {s.get('verdict_emojis',0)}")
    
    if report.get("file_issues"):
        for issue in report["file_issues"]:
            print(f"   ⚠️  {issue}")
    
    # Show failed horses
    for h in report["horses"]:
        if not h["passed"]:
            print(f"   ❌ #{h['number']} {h['name']}: sections={h['sections_found']}/7 chars={h['char_count']} dims={h['matrix_dims']}")
            for issue in h["issues"]:
                print(f"      → {issue}")

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Validate Wong Choi analysis files")
    parser.add_argument("path", help="Analysis .md file or directory")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()
    
    path = pathlib.Path(args.path)
    files = []
    
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("*_Analysis.md"))
    else:
        print(f"Error: {path} not found")
        sys.exit(2)
    
    if not files:
        print(f"No analysis files found in {path}")
        sys.exit(2)
    
    all_reports = []
    any_failed = False
    
    for f in files:
        report = validate_file(f)
        all_reports.append(report)
        if not report["passed"]:
            any_failed = True
    
    if args.json:
        print(json.dumps(all_reports, ensure_ascii=False, indent=2))
    else:
        total_horses = 0
        total_passed = 0
        for r in all_reports:
            print_report(r)
            total_horses += r["summary"]["total"]
            total_passed += r["summary"]["passed"]
        
        print(f"\n{'='*60}")
        print(f"📊 SUMMARY: {len(all_reports)} files, {total_horses} horses, {total_passed} passed, {total_horses-total_passed} failed")
        print(f"{'='*60}")
    
    sys.exit(1 if any_failed else 0)

if __name__ == "__main__":
    main()
