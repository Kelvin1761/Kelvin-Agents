import sys
import argparse
import re
from pathlib import Path

def check_au_hkjc_format(text: str) -> list[str]:
    errors = []
    required_tags = ['⏱️', '🐴', '🔬', '⚡', '📋', '🔗', '🧭', '⚠️', '📊', '💡', '⭐']
    for tag in required_tags:
        if tag not in text:
            errors.append(f"Missing required tag: {tag}")
            
    if '⭐' in text:
        grades = re.findall(r'⭐\s*(?:最終評級[：:])?\s*`?\[?([A-DS][+\-]?)\]?`?', text)
        if not grades:
            grades_fallback = re.findall(r'⭐\s*\*+最終評級[：:]\*+\s*`?\[?([A-DS][+\-]?)\]?`?', text)
            if not grades_fallback:
                errors.append("Missing valid grade format (e.g., ⭐ 最終評級：`[A-]`)")
                
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

def check_au_hkjc_words(text: str) -> list[str]:
    errors = []
    
    # Split by horse analysis block using the standard markers
    blocks = re.split(r'(?=(?:### 【No\.\d+】|\[#\d+\] \w+))', text)
    
    required_tags = ['⏱️', '🐴', '🔬', '⚡', '📋', '🔗', '🧭', '⚠️', '📊', '💡', '⭐']
    
    for block in blocks[1:]: # Skip the first block which is the intro
        # Identify the horse name/number for better error messages
        header_match = re.search(r'(### 【No\.\d+】.*|\[#\d+\] \w+.*)', block)
        horse_id = header_match.group(1).split()[1] if header_match else "Unknown Horse"
        
        grade_match = re.search(r'⭐\s*(?:最終評級[：:])?\s*`?\[?([A-DS][+\-]?)\]?`?', block)
        if not grade_match:
            grade_match = re.search(r'⭐\s*\*+最終評級[：:]\*+\s*`?\[?([A-DS][+\-]?)\]?`?', block)
            
        # If no grade is found, it could be scratched or malformed, but skip if strictly no grade found.
        # Although if it doesn't have a grade, it might be a valid scratched horse block, so we check if it is explicitly skipped.
        if not grade_match:
            continue
            
        # Check required tags PER HORSE directly here
        for tag in required_tags:
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
            
    return errors

def check_nba_format(text: str) -> list[str]:
    errors = []
    if 'Game Header' not in text and '【' not in text:
        errors.append("Missing Game Header")
    if 'Player Stats' not in text and '球員' not in text and '數據' not in text:
        errors.append("Missing Player Stats section")
    if 'Parlay' not in text and '過關' not in text and '組合' not in text:
        errors.append("Missing Parlay/Combination section")
    return errors

def check_nba_words(text: str) -> list[str]:
    # NBA check for entire game analysis
    words = len(re.findall(r'[\w\u4e00-\u9fff]', text))
    if words < 400:
        return [f"NBA Game Analysis has insufficient words ({words} < 400)"]
    return []

def main():
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
        errors.extend(check_au_hkjc_format(text))
        errors.extend(check_au_hkjc_words(text))
        
        # P37: Execute verify_form_accuracy.py if --racecard is provided
        if args.racecard and args.domain == 'au':
            import subprocess
            verify_script = Path(__file__).parent / "verify_form_accuracy.py"
            if verify_script.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, str(verify_script), args.file, args.racecard],
                        capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        # Extract the error lines from the script output (ignoring successful prefix)
                        for line in result.stdout.splitlines():
                            if line.strip().startswith("❌") or line.strip().startswith("⚠️"):
                                errors.append(line.strip())
                except Exception as e:
                    errors.append(f"Failed to run form accuracy verification: {e}")
            else:
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
