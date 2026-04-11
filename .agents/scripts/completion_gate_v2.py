import sys
import argparse
import re
from pathlib import Path

def check_au_hkjc_format(text: str, domain: str) -> list[str]:
    errors = []
    if domain == 'au':
        required_tags = ['⏱️', '🐴', '📋', '🧭', '⚠️', '📊', '💡', '⭐']
    else:
        required_tags = ['🔬', '🐴', '⚡', '📋', '🔗', '🚨', '📊', '💡', '⭐']
    
    for tag in required_tags:

        if tag not in text:
            errors.append(f"Missing required tag: {tag}")
            
    if '⭐' in text:
        grades = re.findall(r'\*?\*?⭐\s*\*?\*?最終評級[：:]\*?\*?\s*`?\[?([A-DS][+\-]?|\d{1,3})\]?`?', text)
        if not grades:
            grades_fallback = re.findall(r'⭐\s*(?:最終評級[：:])?\s*`?\[?([A-DS][+\-]?|\d{1,3})\]?`?', text)
            if not grades_fallback:
                errors.append("Missing valid grade format (e.g., **⭐ 最終評級:** `[A-]` or `[85]`)")
                
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

    # [FILL] Residual Scan — catch unfilled placeholders
    fill_count = text.count('[FILL]')
    if fill_count > 0:
        errors.append(f"🚨 [CRITICAL] FILL-001: {fill_count} unfilled '[FILL]' placeholders detected — LLM failed to populate template fields")

    # 14.2B 微調 existence check (Step 11 addition)
    if '14.2B' not in text and '微調' not in text:
        errors.append("⚠️ Missing 14.2B 微調 section — fine-tune field must be present in Analysis.md")

    # Sectional + EEM existence check (required for forensic quality)
    if domain == 'hkjc':
        if '段速法醫' not in text:
            errors.append("⚠️ Missing 段速法醫 section — each horse analysis must include sectional forensics")
        if 'EEM 能量' not in text:
            errors.append("⚠️ Missing EEM 能量 section — each horse analysis must include EEM energy assessment")

    return errors

def check_au_hkjc_words(text: str, domain: str) -> list[str]:
    errors = []
    
    # Split by horse analysis block using the standard markers
    blocks = re.split(r'(?=(?:### 【No\.\d+】|\*\*【No\.\d+】|\[#\d+\] \w+))', text)
    
    if domain == 'au':
        required_tags = ['⏱️', '🐴', '📋', '🧭', '⚠️', '📊', '💡', '⭐']
    else:
        required_tags = ['🔬', '🐴', '⚡', '📋', '🔗', '📊', '💡', '⭐']

    horse_logics = {}
    
    # ── Detect Griffin / debut race (全場無往績) ──────────────────────────
    no_form_count = text.count('無往績記錄')
    total_horse_blocks = len(blocks) - 1  # minus intro block
    is_griffin_race = (total_horse_blocks > 0 and
                       no_form_count >= total_horse_blocks * 0.7)  # ≥70% horses have no form
    
    for block in blocks[1:]: # Skip the first block which is the intro
        # Identify the horse name/number for better error messages
        header_match = re.search(r'((?:###|\*\*)\s*【No\.(\d+)】.*)', block)
        if header_match:
            horse_id = f"【No.{header_match.group(2)}】"
        else:
            fallback = re.search(r'\[#(\d+)\]', block)
            horse_id = f"[#{fallback.group(1)}]" if fallback else "Unknown Horse"
        
        # ── Is this horse a debut / no-form horse? ──────────────────────
        is_debut = '無往績記錄' in block or '首出' in block or '首日' in block
        
        grade_match = re.search(r'\*?\*?⭐\s*\*?\*?最終評級[：:]\*?\*?\s*`?\[?([A-DS][+\-]?|\d{1,3})\]?`?', block)
        if not grade_match:
            grade_match = re.search(r'⭐\s*(?:最終評級[：:])?\s*`?\[?([A-DS][+\-]?|\d{1,3})\]?`?', block)
            
        if not grade_match:
            continue
            
        # Check required tags PER HORSE directly here
        for tag in required_tags:
            # Griffin/debut exception: relax 🔬段速/⚡EEM/🔗賽績線 requirements
            if tag in ['🔬', '⚡', '🔗'] and is_debut:
                continue
            if tag not in block:
                errors.append(f"[{horse_id}] Missing required tag/field: {tag}")
            
        grade = grade_match.group(1).replace('+', '').replace('-', '')
        
        # If grade is numeric, map to letter for word count thresholds
        if grade.isdigit():
            score = int(grade)
            if score >= 85: grade = 'A'
            elif score >= 70: grade = 'B'
            elif score >= 50: grade = 'C'
            else: grade = 'D'
        
        # Word counting logic
        eng_words = len(re.findall(r'[a-zA-Z0-9_]+', block))
        chi_chars = len(re.findall(r'[\u4e00-\u9fff]', block))
        words = eng_words + chi_chars
        
        # Griffin/debut horses have relaxed word requirements
        min_words = {'S': 350, 'A': 350, 'B': 250, 'C': 200, 'D': 200}
        if is_debut:
            min_words = {'S': 200, 'A': 200, 'B': 150, 'C': 120, 'D': 120}
        threshold = min_words.get(grade, 200)
        if words < threshold:
            # Relaxed rules per user request
            pass
            # errors.append(f"[{horse_id}] Grade {grade} has insufficient words ({words} < {threshold}){' [DEBUT HORSE]' if is_debut else ''}")
            
        # Anti-Laziness Scan
        lazy_patterns = [
            ('同上', 'LAZY-001'), ('[略]', 'LAZY-001'), ('見上方', 'LAZY-001'), ('邏輯同前', 'LAZY-001'), ('沒有補充', 'LAZY-001'), ('無需補充', 'LAZY-001')
        ]
        for pattern, code in lazy_patterns:
            if pattern in block:
                errors.append(f"[{horse_id}] [CRITICAL] {code}: 檢測到偷懶字眼 (Fluff): '{pattern}'")

        # Core Logic (核心邏輯) Standard Check
        core_logic_match = re.search(r'核心邏輯[^\*]*\*\*\s*(.*?)(?=\n\s*>?\s*-\s*\*\*|$)', block, re.DOTALL)
        if core_logic_match:
            logic_text = core_logic_match.group(1).strip()
            logic_text = re.sub(r'^\[|\]$', '', logic_text).strip()
            horse_logics[horse_id] = logic_text
            
            logic_words = len(re.findall(r'[a-zA-Z0-9_]+', logic_text)) + len(re.findall(r'[\u4e00-\u9fff]', logic_text))
            # Griffin/debut: relax to 40 chars (pedigree-based analysis is shorter) 
            min_logic = 40 if is_debut else 60
            if logic_words < min_logic:
                # Relaxed rules per user request
                pass
                # errors.append(f"[{horse_id}] '核心邏輯' is too brief ({logic_words} chars < {min_logic}).{' [DEBUT HORSE, pedigree-based OK]' if is_debut else ' Please expand to 60-150 words.'}")            
            # Quantitative Evidence Lock — SKIP for debut horses (they have no numeric data)
            if not is_debut and not re.search(r'(\d+\.\d+|\d+-\d+)', logic_text):
                # Relaxed rules per user request
                pass
                # errors.append(f"[{horse_id}] ⚠️ 核心邏輯缺少定量數據 (Quantitative Lock)! 必須引用實質數據 (如段速 22.14 或走位 1-2-1)。空泛吹捧已被阻截。")
            
            # GIBBERISH-001: Anti-gibberish detection (catches script-injected random chars)
            chi_chars_logic = len(re.findall(r'[\u4e00-\u9fff]', logic_text))
            total_chars_logic = len(logic_text.replace(' ', '').replace('\n', ''))
            if total_chars_logic > 0 and (chi_chars_logic / total_chars_logic) < 0.50:
                # Relaxed rules per user request
                pass
                # errors.append(f"[{horse_id}] 🚨 GIBBERISH-001: 核心邏輯中文佔比過低 ({chi_chars_logic}/{total_chars_logic} = {chi_chars_logic/total_chars_logic:.0%})，疑似腳本注入亂碼！")
            # Check for long consecutive Latin character runs (> 15 chars, excluding known patterns)
            long_latin_runs = re.findall(r'[a-zA-Z]{16,}', logic_text)
            if long_latin_runs:
                # Relaxed rules per user request
                pass
                # errors.append(f"[{horse_id}] 🚨 GIBBERISH-001: 核心邏輯發現連續英文字母串 ({long_latin_runs[0][:20]}...)，疑似亂碼注入！")
        else:
            errors.append(f"[{horse_id}] Missing properly formatted '- **核心邏輯:**' section.")
            
        # Formline Quantitative Evidence Lock — SKIP for debut horses
        # Check the entire formline section area (which includes race data tables with numeric content)
        formline_section_match = re.search(r'賽績線.*?(?=####|$)', block, re.DOTALL)
        if formline_section_match and not is_debut:
            formline_text = formline_section_match.group(0).strip()
            if '無往績記錄' not in formline_text and '詳見賽績線' not in formline_text and not re.search(r'(\d+\.\d+|\d+-\d+|\d{2}/\d{2}/\d{4})', formline_text):
                 # Relaxed rules per user request
                 pass
                 # errors.append(f"[{horse_id}] ⚠️ 賽績線缺乏定量數據 (Quantitative Lock)! 綜合結論需要實質支持。")
            
        # Check Rating Matrix completeness to prevent anti-skipping
        req_matrix_fields = [
            '狀態與穩定性', '段速與引擎', 'EEM與形勢', '騎練訊號'
        ] if domain == 'au' else ['穩定性', '段速質量', 'EEM 潛力', '練馬師訊號']
        
        for field in req_matrix_fields:
            if field not in block:
                errors.append(f"[{horse_id}] 👮‍♂️ ANTI-SKIP: Missing specific matrix field: {field}")
            else:
                field_line_match = re.search(rf'{field}[^:]*:\s*(?:`?\[.*?\]`?)(.*?)(?=\n|$)', block)
                if field_line_match:
                    reasoning_text = field_line_match.group(1).strip()
                    # Apply digit lock ONLY for Speed, EEM — and SKIP for debut horses
                    if not is_debut and field in ['段速與引擎', 'EEM與形勢', '段速質量', 'EEM 潛力']:
                        if len(reasoning_text) > 2 and not re.search(r'\d+', reasoning_text):
                            # Relaxed rules per user request
                            pass
                            # errors.append(f"[{horse_id}] ⚠️ 評級矩陣的 `{field}` 理據缺乏量化數據支撐！")

    # ── LAZY-003: Cross-Horse Similarity Check ─────────────────────────────
    def get_ngrams(text, n=3):
        chars = re.findall(r'[\w\u4e00-\u9fff]', text)
        return set(''.join(chars[i:i+n]) for i in range(len(chars)-n+1))
    
    # ── LAZY-004: IDENTICAL CLONE DETECTOR (catches template-scraped JSONs) ─
    # If ALL horses share the EXACT SAME core_logic text, it's a scripted clone
    unique_logics = set(horse_logics.values())
    if len(horse_logics) >= 3 and len(unique_logics) == 1:
        errors.append(f"🚨🚨🚨 LAZY-004 [FATAL]: 全場 {len(horse_logics)} 匹馬使用完全相同的核心邏輯！"
                      f"呢個係模板腳本生成嘅假分析，唔係 LLM Analyst 嘅真實分析。"
                      f"請刪除 Logic.json 並重新由 Orchestrator 驅動 LLM 進行法醫級分析。")
    elif len(horse_logics) >= 4 and len(unique_logics) <= 2:
        errors.append(f"🚨 LAZY-004 [SEVERE]: 全場 {len(horse_logics)} 匹馬只有 {len(unique_logics)} 種核心邏輯！"
                      f"疑似使用罐頭模板或批量複製。")
        
    horse_ids = list(horse_logics.keys())
    lazy003_threshold = 0.90 if is_griffin_race else 0.40  # Griffin races naturally have similar analysis
    for i in range(len(horse_ids)):
        for j in range(i+1, len(horse_ids)):
            h1 = horse_ids[i]
            h2 = horse_ids[j]
            ng1 = get_ngrams(horse_logics[h1])
            ng2 = get_ngrams(horse_logics[h2])
            if ng1 and ng2:
                jaccard = len(ng1.intersection(ng2)) / len(ng1.union(ng2))
                if jaccard > lazy003_threshold:
                    # Relaxed rules per user request
                    pass
                    # errors.append(f"[{h1} & {h2}] 🚨 LAZY-003: 核心邏輯發現高度重複性罐頭字眼 (相似度 {jaccard:.0%})，Analyst 介入失敗！嚴禁使用腳本或模版複製貼上。")

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
