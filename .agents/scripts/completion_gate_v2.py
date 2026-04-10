import sys
import argparse
import re
from pathlib import Path

def check_au_hkjc_format(text: str, domain: str) -> list[str]:
    errors = []
    if domain == 'au':
        required_tags = ['⏱️', '🐴', '📋', '🧭', '⚠️', '📊', '💡', '⭐']
    else:
        required_tags = ['🔬', '🐴', '⚡', '📋', '🔗', '⚠️', '📊', '💡', '⭐']
    
    for tag in required_tags:

        if tag not in text:
            errors.append(f"Missing required tag: {tag}")
            
    if '⭐' in text:
        grades = re.findall(r'\*?\*?⭐\s*\*?\*?最終評級[：:]\*?\*?\s*`?\[?([A-DS][+\-]?)\]?`?', text)
        if not grades:
            grades_fallback = re.findall(r'⭐\s*(?:最終評級[：:])?\s*`?\[?([A-DS][+\-]?)\]?`?', text)
            if not grades_fallback:
                errors.append("Missing valid grade format (e.g., **⭐ 最終評級:** `[A-]`)")
                
    has_verdict = False
    if '第一選' not in text and 'Top 4' not in text and '🏆' not in text:
        errors.append("Missing Verdict / Top 4 section")
    else:
        has_verdict = True
    
    # P34: Verdict format anti-drift checks
    if has_verdict:
        if '🥇 **第一選**' not in text:
            errors.append("⚠️ P34 DRIFT: Missing exact label '🥇 **第一選**' (do not use 首選)")
        # Must use structured multi-line format, not compressed single-line
        if '- **馬號及馬名:**' not in text:
            errors.append("⚠️ P34 DRIFT: Top 4 missing structured format (need '- **馬號及馬名:**' sub-bullets)")
        if '- **評級與✅數量:**' not in text:
            errors.append("⚠️ P34 DRIFT: Top 4 missing '- **評級與✅數量:**' sub-bullets")
        if '- **核心理據:**' not in text:
            errors.append("⚠️ P34 DRIFT: Top 4 missing '- **核心理據:**' sub-bullets")
        if '- **最大風險:**' not in text:
            errors.append("⚠️ P34 DRIFT: Top 4 missing '- **最大風險:**' sub-bullets")
        # Blacklisted compressed formats
        if re.search(r'🥇\s*首選', text):
            errors.append("⚠️ P34 DRIFT: Blacklisted compressed format containing '首選' detected")
        if '📊 Top 4 排名' in text:
            errors.append("⚠️ P34 DRIFT: Blacklisted custom label '📊 Top 4 排名' detected")
        if '🎯 行動指令' in text:
            errors.append("⚠️ P34 DRIFT: Blacklisted custom label '🎯 行動指令' detected")
        if '💡 投注策略建議' in text:
            errors.append("⚠️ P34 DRIFT: Blacklisted custom label '💡 投注策略建議' detected")
        # Mandatory verdict sections
        if 'Top 2 入三甲信心度' not in text:
            errors.append("⚠️ P34 DRIFT: Missing 'Top 2 入三甲信心度' section")
        if '步速逆轉保險' not in text:
            errors.append("⚠️ P34 DRIFT: Missing '步速逆轉保險' section in Part 4")
        if '```csv' not in text:
            errors.append("⚠️ P34 DRIFT: Missing CSV data block (Part 5)")
    
    # P37: Check Part 1 戰場全景 presence (use Part 1-specific markers, not per-horse markers)
    part1_markers = ['戰場全景', '[第一部分]', '賽事格局', 'Speed Map (速度地圖)', 'Speed Map 回顧']
    has_part1 = any(marker in text for marker in part1_markers)
    if not has_part1:
        errors.append("⚠️ Missing [第一部分] 戰場全景 (Battlefield Panorama) — Batch 1 must include race overview and Speed Map")

    # P37 Check: Verify that 近績序列 is actually populated instead of skipped
    horses_with_form = re.findall(r'近績序列[：:]\s*`?(.+?)`?', text)
    if not horses_with_form and '近績序列' in text:
         errors.append("⚠️ P37: '近績序列' field exists but is empty or malformed.")

    return errors

def check_au_hkjc_words(text: str, domain: str) -> list[str]:
    errors = []
    
    # Split by horse analysis block using the standard markers
    blocks = re.split(r'(?=(?:### 【No\.\d+】|\[#\d+\] \w+))', text)
    
    if domain == 'au':
        required_tags = ['⏱️', '🐴', '📋', '🧭', '⚠️', '📊', '💡', '⭐']
    else:
        required_tags = ['🔬', '🐴', '⚡', '📋', '🔗', '📊', '💡', '⭐']

    
    for block in blocks[1:]: # Skip the first block which is the intro
        # Identify the horse name/number for better error messages
        header_match = re.search(r'(### 【No\.\d+】.*|\[#\d+\] \w+.*)', block)
        horse_id = header_match.group(1).split()[1] if header_match else "Unknown Horse"
        
        grade_match = re.search(r'\*?\*?⭐\s*\*?\*?最終評級[：:]\*?\*?\s*`?\[?([A-DS][+\-]?)\]?`?', block)
        if not grade_match:
            grade_match = re.search(r'⭐\s*(?:最終評級[：:])?\s*`?\[?([A-DS][+\-]?)\]?`?', block)
            
        # If no grade is found, it could be scratched or malformed, but skip if strictly no grade found.
        # Although if it doesn't have a grade, it might be a valid scratched horse block, so we check if it is explicitly skipped.
        if not grade_match:
            continue
            
        # Check required tags PER HORSE directly here
        for tag in required_tags:
            if tag in ['🔬', '⚡', '🔗'] and "無往績記錄" in block:
                continue
            if tag not in block:
                errors.append(f"[{horse_id}] Missing required tag/field: {tag}")
            
        grade = grade_match.group(1).replace('+', '').replace('-', '')
        
        # Word counting logic: group English letters into words, count Chinese characters individually
        eng_words = len(re.findall(r'[a-zA-Z0-9_]+', block))
        chi_chars = len(re.findall(r'[\u4e00-\u9fff]', block))
        words = eng_words + chi_chars
        
        if grade in ['S', 'A'] and words < 500:
            errors.append(f"[{horse_id}] Grade {grade} has insufficient words ({words} < 500)")
        elif grade == 'B' and words < 350:
            errors.append(f"[{horse_id}] Grade {grade} has insufficient words ({words} < 350)")
        elif grade in ['C', 'D'] and words < 300:
            errors.append(f"[{horse_id}] Grade {grade} has insufficient words ({words} < 300)")
            
        # Core Logic (核心邏輯) Standard Check
        core_logic_match = re.search(r'核心邏輯[^\*]*\*\*\s*(.*?)(?=\n\s*>?\s*-\s*\*\*|$)', block, re.DOTALL)
        if core_logic_match:
            logic_text = core_logic_match.group(1).strip()
            # Remove framing brackets if they exist
            logic_text = re.sub(r'^\[|\]$', '', logic_text).strip()
            logic_words = len(re.findall(r'[a-zA-Z0-9_]+', logic_text)) + len(re.findall(r'[\u4e00-\u9fff]', logic_text))
            if logic_words < 30:
                errors.append(f"[{horse_id}] '核心邏輯' is too brief or lacks deep forensic detail ({logic_words} chars). Please expand.")
        else:
            errors.append(f"[{horse_id}] Missing properly formatted '- **核心邏輯:**' section.")
            
        # Check Rating Matrix completeness to prevent anti-skipping
        req_matrix_fields = [
            '狀態與穩定性', '段速與引擎', 'EEM與形勢', '騎練訊號'
        ] if domain == 'au' else ['穩定性', '段速質量', 'EEM 潛力', '練馬師訊號']
        
        for field in req_matrix_fields:
            if field not in block:
                errors.append(f"[{horse_id}] 👮‍♂️ ANTI-SKIP: Missing specific matrix field: {field}")
            
    return errors

def check_nba_format(text: str) -> list[str]:
    """Strengthened NBA format check — aligned with HKJC/AU rigor."""
    errors = []

    # 1. Game Header
    has_header = any(marker in text for marker in ['NBA Wong Choi', '🏀', 'Wong Choi —'])
    if not has_header:
        errors.append("Missing Game Header (expected '🏀 NBA Wong Choi — ...')")

    # 2. 3-Combo Structure (🛡️ 1, 🔥 2, 💎 3)
    combo_markers = {
        "🛡️": "組合 1 (穩膽)",
        "🔥": "組合 2 (價值)",
        "💎": "組合 3 (高倍率)",
    }
    found_combos = 0
    for emoji, label in combo_markers.items():
        if emoji in text:
            found_combos += 1
        else:
            errors.append(f"[CRITICAL] STRUCT-COMBO: Missing {label} ({emoji} not found)")
    if found_combos < 3:
        errors.append(f"[CRITICAL] STRUCT-COMBO: Only {found_combos}/3 required combos found")

    # 3. [FILL] Residual Scan
    fill_count = text.count('[FILL]')
    if fill_count > 0:
        errors.append(f"🚨 [CRITICAL] FILL-001: {fill_count} unfilled '[FILL]' placeholders detected")

    # 4. Anti-Laziness Scan
    lazy_patterns = [
        ('[同上]', 'LAZY-001'),
        ('[略]', 'LAZY-001'),
        ('[參見組合', 'LAZY-001'),
        ('[完整數據見組合', 'LAZY-001'),
        ('[見上方]', 'LAZY-001'),
        ('[邏輯同前]', 'LAZY-001'),
        ('[數據略]', 'LAZY-001'),
    ]
    for pattern, code in lazy_patterns:
        if pattern in text:
            errors.append(f"[CRITICAL] {code}: Lazy shortcut detected: '{pattern}'")

    # 5. L10 Array Validation
    l10_arrays = re.findall(r'L10.*?`\[([^\]]+)\]`', text)
    for arr_str in l10_arrays:
        nums = [x.strip() for x in arr_str.split(',') if x.strip()]
        if len(nums) != 10 and len(nums) > 0:
            errors.append(f"[CRITICAL] DATA-003: L10 array has {len(nums)} values (expected 10): [{arr_str[:40]}...]")

    # 6. Template Standard Fields Presence
    required_fields = [
        ('數理引擎', 'STRUCT-TABLE'),
        ('邏輯引擎', 'STRUCT-TABLE'),
        ('盤口對照', 'STRUCT-LINES'),
        ('組合結算', 'STRUCT-SETTLEMENT'),
    ]
    for field, code in required_fields:
        if field not in text:
            errors.append(f"[CRITICAL] {code}: Missing required field/section: '{field}'")

    # 7. Odds Source Verification
    if 'BET365' not in text.upper() and 'bet365' not in text.lower():
        errors.append("[MINOR] ODDS-001: No Bet365 source reference found")

    # 8. Per-Combo Word Count Check
    combo_sections = re.split(r'(?=###\s*[🛡️🔥💎💣])', text)
    for section in combo_sections[1:]:  # Skip header
        header_match = re.search(r'###\s*([🛡️🔥💎💣])\s*(.*?)(?:\n|$)', section)
        if not header_match:
            continue
        combo_label = header_match.group(0).strip()[:30]
        eng_words = len(re.findall(r'[a-zA-Z0-9_]+', section))
        chi_chars = len(re.findall(r'[\u4e00-\u9fff]', section))
        words = eng_words + chi_chars
        if words < 300:
            errors.append(f"[MINOR] MODEL-003: {combo_label} has insufficient depth ({words} < 300 words)")

    return errors

def check_nba_words(text: str) -> list[str]:
    """NBA overall word count check — minimum 1500 for a complete game analysis."""
    errors = []
    eng_words = len(re.findall(r'[a-zA-Z0-9_]+', text))
    chi_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    words = eng_words + chi_chars
    if words < 1500:
        errors.append(f"NBA Game Analysis has insufficient words ({words} < 1500)")
    return errors

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Antigravity Completion Gate V2")
    parser.add_argument("file", type=str, help="Path to Analysis.md")
    parser.add_argument("--domain", type=str, choices=['au', 'hkjc', 'nba'], required=True, help="Domain of the analysis")
    parser.add_argument("--racecard", type=str, help="Path to Racecard.md for P37 Form Accuracy Verification")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[FAILED] File {args.file} not found.")
        sys.exit(1)

    try:
        text = path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"[FAILED] Could not read file: {e}")
        sys.exit(1)

    errors = []
    if args.domain in ['au', 'hkjc']:
        errors.extend(check_au_hkjc_format(text, args.domain))
        errors.extend(check_au_hkjc_words(text, args.domain))

        
        # P39: Execute verify_form_accuracy.py — AUTO-DETECT Racecard + Formguide
        if args.domain == 'au':
            import subprocess
            verify_script = Path(__file__).parent / "verify_form_accuracy.py"
            
            # Auto-detect Racecard if not explicitly provided
            racecard_path = args.racecard
            formguide_path = None
            if not racecard_path:
                analysis_dir = Path(args.file).parent
                race_num_match = re.search(r'Race (\d+)', args.file)
                if race_num_match:
                    race_num = race_num_match.group(1)
                    # Find Racecard
                    rc_candidates = list(analysis_dir.glob(f"*Race {race_num} Racecard*"))
                    if rc_candidates:
                        racecard_path = str(rc_candidates[0])
                    # Find Formguide
                    fg_candidates = list(analysis_dir.glob(f"*Race {race_num} Formguide*"))
                    if fg_candidates:
                        formguide_path = str(fg_candidates[0])
            
            if racecard_path and verify_script.exists():
                try:
                    cmd = [sys.executable, str(verify_script), args.file, racecard_path]
                    if formguide_path:
                        cmd.append(formguide_path)
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        for line in result.stdout.splitlines():
                            if line.strip().startswith(("❌", "🔄", "⚠️")):
                                errors.append(line.strip())
                except Exception as e:
                    errors.append(f"Failed to run form accuracy verification: {e}")
            elif not racecard_path:
                errors.append("⚠️ P39: Could not auto-detect Racecard.md — supply --racecard manually")
            elif not verify_script.exists():
                errors.append("⚠️ verify_form_accuracy.py script not found.")
                
    elif args.domain == 'nba':
        errors.extend(check_nba_format(text))
        errors.extend(check_nba_words(text))

    if errors:
        print(f"\n❌ [FAILED] Completion Gate V2 ({args.domain.upper()})")
        for err in set(errors):
            print(f"  - {err}")
        print("\nACTION REQUIRED: Please fix the errors above before submitting.")
        sys.exit(1)
    else:
        print(f"✅ [PASSED] Completion Gate V2 ({args.domain.upper()})")
        sys.exit(0)

if __name__ == "__main__":
    main()
