# 🔧 ORCHESTRATOR UPGRADE PLAN — V8.1 FULL ANALYST INTEGRATION
# ================================================================
# 
# 📅 Created: 2026-04-11
# 🎯 Goal: Ensure HKJC Analyst and AU Analyst are FULLY utilised by
#          their respective Orchestrators, with 100% of their analytical
#          power reflected in the final Analysis.md output.
#
# ⚠️ CRITICAL: This file is the SINGLE SOURCE OF TRUTH for all upgrades.
#    If you run out of tokens mid-session, the next agent MUST:
#    1. Read this file FIRST
#    2. Check the PROGRESS TRACKER below to see what's done
#    3. Continue from the next uncompleted step
#    4. Mark steps as [DONE] when completed
#
# 🚫 DO NOT simplify, skip steps, or "optimise" this plan.
#    Every line exists because a previous simplification caused bugs.
# ================================================================

## PROGRESS TRACKER
## ================
## Mark [DONE] when completed. Mark [IN PROGRESS] when started.
## 
## Phase A: Compiler Full Upgrade (CRITICAL - DO FIRST)
## - [ ] Step 1: HKJC Compiler full restructure
## - [ ] Step 2: AU Compiler full restructure  
## 
## Phase B: Orchestrator Directive Enhancement
## - [ ] Step 3: HKJC Logic.json schema expansion
## - [ ] Step 4: Batch 0 Speed Map mandatory fields
## - [ ] Step 5: AU Orchestrator 5-step forensic awakening
## - [ ] Step 6: Unify Logic.json format (AU list → dict)
##
## Phase C: Infrastructure Fixes
## - [ ] Step 7: Uncomment HKJC report + add cost tracker
## - [ ] Step 8: AU Orchestrator local folder fallback
## - [ ] Step 9: Unify AU SKILL.md to V8 architecture
## - [ ] Step 10: Speed Map auto-generation script
## - [ ] Step 10.5: compute_rating_matrix.py (AUTO rating/fine-tune/override)
##
## Phase D: QA Enhancement + Cleanup
## - [ ] Step 11: Strengthen completion_gate_v2.py
## - [ ] Step 12: Archive 4 orphaned agents
##
## Phase E: Verification
## - [ ] Step 13: Recompile HKJC with existing JSON
## - [ ] Step 14: Recompile AU with existing JSON
## - [ ] Step 15: Full HKJC orchestrator loop test
## - [ ] Step 16: Full AU orchestrator loop test

---

# ============================================================
# CONTEXT: WHY THIS UPGRADE IS NEEDED
# ============================================================
#
# PROBLEM: The V8 compile_analysis_template scripts (both HKJC and AU)
# only output ~40% of what the Analyst agents are designed to produce.
#
# The Analysts have rich, forensic-level protocols:
# - HKJC: 20 resource files, 370-line rating aggregation (06_rating_aggregation.md)
# - AU: 42 resource files, 165-line synthesis framework (02f_synthesis.md)
#
# But the Compilers discard most of this, producing simplified output
# missing: sectional forensics, EEM energy, forgiveness archives,
# full horse analysis (10 items), 14.2B fine-tune, 14.3 override,
# dual-track grading (AU), and proper CSV data.
#
# ROOT CAUSE: The Compiler defines the final output structure.
# It reads Logic.json but only extracts a few keys.
# The Orchestrator stdout doesn't tell the LLM to fill all keys.
# Result: Analyst capabilities wasted.
#
# ============================================================
# ARCHITECTURAL SOLUTION: LLM = JUDGE, PYTHON = CALCULATOR
# ============================================================
#
# KEY INSIGHT: LLM context pressure is too high because the LLM
# must memorise ~240 lines of deterministic rules (rating table,
# 30 fine-tune rules, 15 override rules, tiebreakers, longshot scans).
# These rules are all numeric/threshold-based — PERFECT for Python.
#
# NEW ARCHITECTURE:
#   1. Python PRE-computes: Facts + Speed Map + forgiveness candidates
#   2. LLM ONLY does: 8-dim scoring (✅/➖/❌ + reasoning) + core logic
#      → Context drops from ~200KB to ~30KB (80% reduction)
#   3. Python POST-processes: auto-lookup rating, auto-apply fine-tune,
#      auto-check overrides, auto-rank, auto-scan longshots
#      → 100% rule coverage guaranteed (deterministic)
#   4. Compiler formats: full 11-section Analysis.md
#
# RESULT: LLM focuses on JUDGMENT, Python handles CALCULATION.
# The 370-line rating table NEVER needs to enter the LLM's context.

---

# ============================================================
# STEP 1: HKJC COMPILER FULL RESTRUCTURE
# ============================================================
# File: .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py
# Reference: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/08_templates_core.md
#            Archive Race Analysis/2026-04-08_HappyValley/04-08 Race 1_Analysis.md (gold standard)
#
# The generate_hkjc_horse_compiled() function must be rewritten to output
# ALL sections that the HKJC Analyst is designed to produce.
#
# CURRENT OUTPUT (broken):
#   - Horse header + 情境標記
#   - 賽績總結 (basic)
#   - 完整賽績檔案 (table from Facts)
#   - Trends + Engine (from Facts) ← DUPLICATED
#   - 馬匹分析 (5 items only) ← SHOULD BE 10+
#   - 賽績線 ← DUPLICATED
#   - 評級矩陣 (8 dims)
#   - 矩陣算術 + 14.2 基礎評級 ← MISSING 14.2B + 14.3
#   - 核心邏輯 + 優勢 + 風險
#   - 最終評級 + 冷門馬
#
# REQUIRED OUTPUT (per 08_templates_core.md + gold standard):
#   1. Horse header + 📌 情境標記 (A/B/C/D with description)
#   2. ⏱️ 近績解構 (排位表事實錨點 + 統計 + 近六場走勢 + 逆境 + 際遇)
#   3. 📋 完整賽績檔案 (table from Facts, ONE TIME ONLY)
#   4. 🐴 馬匹剖析 (ALL items from skeleton):
#      - 走勢趨勢 (Step 10.3+)
#      - 隱藏賽績 (Step 6+12)
#      - 贏馬回落風險/穩定性 (Step 5)
#      - 級數評估 (Step 8.1)
#      - 路程場地適性 (Step 2)
#      - 引擎距離 (Step 2.6)
#      - 配備變動 (Step 6)
#      - 部署與練馬師訊號 (Step 8.2)
#      - 人馬配搭 (Step 2.5)
#      - 步速段速 (Step 0+10)
#      - 競賽事件/馬匹特性
#   5. 🔬 段速法醫 (Step 10): raw L400, correction, trend
#   6. ⚡ EEM 能量 (Step 11): last position, cumulative, assessment
#   7. 📋 寬恕檔案 (Step 12): factors, conclusion
#   8. 🔗 賽績線 (Step 13): from Facts ONE TIME, + LLM conclusion
#   9. 📊 評級矩陣 (Step 14): 8 dimensions
#  10. 🔢 矩陣算術 + 14.2 基礎評級
#  11. 14.2B 微調: direction + trigger        ← NEW (was missing)
#  12. 14.3 覆蓋: rule name or "無"            ← NEW (was missing)
#  13. 💡 結論與評語: 核心邏輯 + 優勢 + 風險
#  14. <details> 法醫級推演錨點 (Step 0-14)
#  15. ⭐ 最終評級
#  16. 🐴⚡ 冷門馬訊號
#
# EXACT CODE CHANGES:
#
# In generate_hkjc_horse_compiled(), AFTER the 馬匹分析 section (line ~119),
# ADD these new sections:
#
# ```python
#     # --- 5. 段速法醫 ---
#     sf = h_logic.get('sectional_forensic', {})
#     lines.append('**🔬 段速法醫 (Step 10):**')
#     lines.append(f"- **原始 L600/L400:** {sf.get('raw_L400', '[FILL]')} | "
#                  f"**修正因素:** {sf.get('correction_factor', '[FILL]')} | "
#                  f"**修正判斷:** {sf.get('corrected_assessment', '[FILL]')}")
#     lines.append(f"- **所示趨勢(近 3 仗):** `{sf.get('trend', '[FILL]')}`\n")
#
#     # --- 6. EEM 能量 ---
#     eem = h_logic.get('eem_energy', {})
#     lines.append('**⚡ EEM 能量 (Step 11):**')
#     lines.append(f"- **上仗走位:** {eem.get('last_run_position', '[FILL]')}")
#     lines.append(f"- **累積消耗:** `{eem.get('cumulative_drain', '[FILL]')}`")
#     lines.append(f"- **總評:** {eem.get('assessment', '[FILL]')}\n")
#
#     # --- 7. 寬恕檔案 ---
#     forg = h_logic.get('forgiveness_archive', {})
#     lines.append('**📋 寬恕檔案 (Step 12):**')
#     lines.append(f"- **因素:** {forg.get('factors', '[FILL]')}")
#     lines.append(f"- **結論:** `{forg.get('conclusion', '[FILL]')}`\n")
# ```
#
# AFTER 矩陣算術 + 14.2 基礎評級 (line ~170), ADD:
#
# ```python
#     # --- 11-12. 14.2B + 14.3 ---
#     ft = h_logic.get('fine_tune', {})
#     ovr = h_logic.get('override', {})
#     lines.append(f"**14.2B 微調:** `{ft.get('direction', '無')}` | `{ft.get('trigger', '無')}`")
#     lines.append(f"**14.3 覆蓋:** `{ovr.get('rule', '無')}`\n")
# ```
#
# AFTER 核心邏輯 section (line ~178), ADD evidence anchor:
#
# ```python
#     evidence = h_logic.get('evidence_step_0_14', '')
#     if evidence:
#         lines.append(f"\n<details><summary>🔬 法醫級推演錨點 (Step 0-14 Evidence)</summary>\n")
#         lines.append(f"{evidence}\n")
#         lines.append("</details>\n")
# ```
#
# FIX DUPLICATE INJECTION:
# - Remove lines 106-108 (h_fact['trends'], h_fact['engine'], h_fact['new_dims'])
#   These are already injected with the table at line 98-104.
#   The formline at line 121-126 should only inject ONCE.
# - Remove the `綜合結論: [FILL]` line at line 124.
#
# FIX CSV PLACEHOLDER:
# In build_hkjc_verdict_compiled(), replace the PLACEHOLDER with actual data
# from the verdict JSON top4 entries.

---

# ============================================================
# STEP 2: AU COMPILER FULL RESTRUCTURE
# ============================================================
# File: .agents/skills/au_racing/au_wong_choi/scripts/compile_analysis_template.py
# Reference: .agents/skills/au_racing/au_horse_analyst/resources/06_templates_core.md
#            .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md
#
# SAME APPROACH as Step 1, but using AU dimension names.
# The generate_horse_section() function must be rewritten.
#
# CURRENT OUTPUT (broken):
#   - Header + 情境標記
#   - ⏱️ 近績解構 (近績序列 + 狀態週期 only)
#   - 📋 完整賽績檔案 (table)
#   - Trends/EEM/Formline/Engine (from Facts, injected raw)
#   - 🐴 馬匹剖析 → ONLY "核心參數: X 級實力" ONE LINE
#   - 🧭 陣型預判 → ONLY "形勢: [視乎起步]"
#   - ⚠️ 風險儀表板 → ONLY risk, no 穩定指數
#   - 📊 評級矩陣 (8 dims, AU naming)
#   - 矩陣算術 ← NO 基礎評級 / 微調 / 覆蓋
#   - 💡 核心邏輯 → NO 最大競爭優勢
#   - ⭐ 最終評級
#   - 冷門馬
#
# REQUIRED OUTPUT (per 06_templates_core.md):
#   1. Header + 📌 情境標記 (A升級/B降級/C正路/D默認)
#   2. ⏱️ 近績解構 (序列 + 狀態週期 + 統計 + 趨勢總評)
#   3. 📋 完整賽績檔案 (table + 寬恕認定 + 段速趨勢 + EEM摘要)
#   4. 🐴 馬匹剖析 (5 items):
#      - 班次負重
#      - 引擎距離 (Type A/B/C + Sire)
#      - 步態場地
#      - 配備意圖
#      - 人馬組合
#   5. 🔗 賽績線 (Python pre-generated table + 綜合結論)
#   6. 🧭 陣型預判 (預計守位 + 形勢判定)
#   7. ⚠️ 風險儀表板 (重大風險 + 穩定指數 X/10)
#   8. 📊 評級矩陣 (8 AU dims):
#      - 狀態與穩定性 [核心]
#      - 段速與引擎 [核心]
#      - EEM與形勢 [半核心]
#      - 騎練訊號 [半核心]
#      - 級數與負重 [輔助]
#      - 場地適性 [輔助]
#      - 賽績線 [輔助]
#      - 裝備與距離 [輔助]
#   9. 🔢 矩陣算術
#  10. 基礎評級: S to D                        ← NEW
#  11. 微調: 升/降/無 + trigger                 ← NEW
#  12. 覆蓋規則: rule or 無                     ← NEW
#  13. 💡 核心邏輯 (≥80-150字 + ≥3 data refs)
#  14. 最大競爭優勢                              ← NEW
#  15. 最大失敗風險
#  16. ⭐ 最終評級
#  17. 📗📙 場地雙軌評級 (UNSTABLE only)         ← NEW
#  18. 🐴⚡ 冷門馬訊號 (B+ or below)
#
# EXACT CODE CHANGES:
# Same pattern as HKJC Step 1. Add the missing sections by reading
# from Logic.json keys: sectional_forensic, eem_energy, forgiveness_archive,
# fine_tune, override, evidence_step_0_14, dual_track_grading.
#
# KEY AU-SPECIFIC DIFFERENCES:
# 1. Matrix keys use Chinese names: "狀態與穩定性" not "stability"
# 2. Add dual_track_grading section (from JSON `dual_track` key)
# 3. Add "最大競爭優勢" line (from JSON `advantages` key)
# 4. Add batch completion self-check line at end

---

# ============================================================
# STEP 3: HKJC ORCHESTRATOR — EXPAND LOGIC.JSON SCHEMA
# ============================================================
# File: .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py
# Location: The stdout block for Batch 1~N analysis (around line 309-318)
#
# CURRENT (weak):
#   print("⚠️ 你必須完全依照 hkjc_horse_analyst 設計的流程...")
#   (5 bullet points about the process)
#
# ADD AFTER the 5 bullets (append to the same print block):
#
# ```python
# print("")
# print("📋 Logic.json 必填 Key (每匹馬):")
# print("  analytical_breakdown: {")
# print("    trend_analysis, hidden_form, stability_risk, class_assessment,")
# print("    track_distance_suitability, engine_distance, gear_changes,")
# print("    trainer_signal, jockey_fit, pace_adaptation, race_events")
# print("  }")
# print("  sectional_forensic: {raw_L400, correction_factor, corrected_assessment, trend}")
# print("  eem_energy: {last_run_position, cumulative_drain, assessment}")
# print("  forgiveness_archive: {factors, conclusion}")
# print("  matrix: {stability, speed_mass, eem, trainer_jockey, scenario, freshness, formline, class_advantage}")
# print("    (每個 key 必須有 score 同 reasoning)")
# print("  fine_tune: {direction: '升一級'/'降一級'/'無', trigger: '原因'}")
# print("  override: {rule: '規則名稱或無'}")
# print("  base_rating: 'S' to 'D' (含 +/-)")
# print("  core_logic: ≥120字(C/D) / ≥150字(B) / ≥200字(S/A)")
# print("  advantages: 最大競爭優勢 (具體)")
# print("  disadvantages: 最大失敗風險 (具體)")
# print("  evidence_step_0_14: Step 0-14 證據鏈摘要 (≥50字)")
# print("  scenario_tags: 情境A/B/C/D + 描述")
# print("  underhorse: {triggered: true/false, condition: '...', reason: '...'}")
# ```

---

# ============================================================
# STEP 4: BATCH 0 SPEED MAP MANDATORY FIELDS
# ============================================================
# File: hkjc_orchestrator.py (Batch 0 section ~L288-293)
#       au_orchestrator.py (equivalent Batch 0 section)
#
# ADD to Batch 0 stdout for BOTH orchestrators:
#
# ```python
# print("🚨 Batch 0 戰場全景 JSON 必填欄位 (全部必須有具體內容，禁止留空):")
# print("  speed_map.leaders: ['馬號(檔位)', ...]")
# print("  speed_map.on_pace: ['馬號(檔位)', ...]")
# print("  speed_map.mid_pack: ['馬號(檔位)', ...]")
# print("  speed_map.closers: ['馬號(檔位)', ...]")
# print("  speed_map.predicted_pace: Genuine/Fast/Slow/Moderate/Suicidal")
# print("  speed_map.track_bias: 詳細跑道偏差描述 (≥30字)")
# print("  speed_map.tactical_nodes: 戰術節點分析 (≥50字)")
# print("  speed_map.collapse_point: 步速崩潰點 (如 '400m')")
# print("  speed_map.beneficiaries: 受惠馬匹清單")
# print("  speed_map.victims: 受損馬匹清單")
# ```

---

# ============================================================
# STEP 5: AU ORCHESTRATOR — 5-STEP FORENSIC AWAKENING
# ============================================================
# File: .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py
# Location: ~Line 286-293 (the analysis batch stdout)
#
# REPLACE the current 2-line print with the HKJC-style 5-step directive:
#
# ```python
# print("⚠️ 絕對強制約束：你必須完全依照 `au_horse_analyst` 設計的流程進行以下五步法醫級分析：")
# print("  1. 讀取「完整賽績檔案」(Facts.md)，執行 Steps 0.5/1/2/3:")
# print("     情境標籤判定 + 狀態週期 + 引擎距離分類 + 級數評估")
# print("  2. 嚴格執行 Steps 4-10:")
# print("     段速法醫(L600/修正/趨勢) + EEM 能量模型(消耗/形勢) + 寬恕認定(逐場)")
# print("  3. 執行 Step 14 的 8 維度評級矩陣打分:")
# print("     狀態與穩定性[核心] + 段速與引擎[核心] + EEM與形勢[半核心] + 騎練訊號[半核心]")
# print("     + 級數與負重[輔助] + 場地適性[輔助] + 賽績線[輔助] + 裝備與距離[輔助]")
# print("     每維度必須有 score(✅/➖/❌) 和 reasoning")
# print("  4. 撰寫法醫級「核心邏輯」:")
# print("     S/A級 ≥150字 | B級 ≥100字 | C/D級 ≥80字")
# print("     必須引用 ≥3 個 Facts.md 中的具體數據點 (L600/PI/EEM消耗/跑位)")
# print("     必須包含至少一個「若X則Y」情境分支")
# print("  5. 填寫 fine_tune(14.2B微調) + override(14.3覆蓋) + advantages + disadvantages")
# print("     ⚠️ fine_tune 同 override 唔可以留空！如果無觸發就填 {direction:'無', trigger:'無'}")
# ```
#
# ALSO ADD the same JSON schema block as HKJC Step 3, but with AU key names:
# (matrix keys: 狀態與穩定性, 段速與引擎, EEM與形勢, 騎練訊號, 級數與負重, 場地適性, 賽績線, 裝備與距離)

---

# ============================================================
# STEP 6: UNIFY LOGIC.JSON FORMAT (AU list → dict)
# ============================================================
# File: au_orchestrator.py (stdout schema block from Step 5)
#       compile_analysis_template.py (parser)
#
# CHANGE 1 (au_orchestrator.py):
# In the stdout JSON schema, specify dict format:
# ```python
# print("  ⚠️ horses 必須用 dict 格式: {\"1\": {...}, \"2\": {...}}")
# print("     禁止用 list 格式: [{\"id\": 1}, {\"id\": 2}]")
# ```
#
# CHANGE 2 (compile_analysis_template.py):
# The parser at line 336-343 already handles both formats (list→dict conversion).
# Keep this backward compatibility but prioritize dict format.
# No code change needed here, but add a comment noting the dict preference.

---

# ============================================================
# STEP 7: UNCOMMENT HKJC REPORT + ADD COST TRACKER
# ============================================================
# File: .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py
# Location: ~Line 361-365
#
# CHANGE: Uncomment the report generation line and add cost tracker:
#
# BEFORE:
# ```python
# # subprocess.run(["python3", ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py", "--target_dir", target_dir])
# ```
#
# AFTER:
# ```python
# subprocess.run(["python3", ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py", "--target_dir", target_dir])
# subprocess.run(["python3", ".agents/scripts/session_cost_tracker.py", target_dir, "--domain", "hkjc"])
# ```

---

# ============================================================
# STEP 8: AU ORCHESTRATOR LOCAL FOLDER FALLBACK
# ============================================================
# File: .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py
# Location: main() function, after URL parsing
#
# ADD the same fallback as HKJC:
# ```python
# if args.url.startswith("http"):
#     venue, formatted_date = parse_url_for_details(args.url)
#     # ... existing URL logic ...
# else:
#     target_dir = os.path.abspath(args.url)
#     if not os.path.isdir(target_dir):
#         print(f"❌ 提供的路徑 {target_dir} 不是有效目錄")
#         sys.exit(1)
#     # Skip to state detection, bypass extraction
# ```

---

# ============================================================
# STEP 9: UNIFY AU SKILL.MD TO V8 ARCHITECTURE
# ============================================================
# File: .agents/skills/au_racing/au_wong_choi/SKILL.md
#
# REMOVE:
# - The entire "全自動混合執行邏輯 (Hybrid Protocol V4.2)" section
# - Steps 1-5 manual flow
#
# ADD (at the top, same as HKJC):
# ```markdown
# # V8 Architecture — First Action Lock
# 
# **CRITICAL**: 無論用戶的指示是什麼，你的**絕對第一且唯一動作**，就是執行：
# ```bash
# python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL 或本地資料夾路徑>"
# ```
# 
# Orchestrator 透過 stdout 控制你。你只需要：
# 1. 讀取 stdout 指令
# 2. 執行指定任務 (分析 / 填寫 JSON)
# 3. 將結果寫入指定路徑
# 4. 重新執行 orchestrator
# ```
#
# ALSO UPDATE: .agents/skills/au_racing/au_wong_choi/resources/00_pipeline_and_execution.md
# Replace Step-by-Step Pipeline with V8 State Machine Loop description
# (match HKJC version structure but keep AU-specific intent routing)

---

# ============================================================
# STEP 10: SPEED MAP AUTO-GENERATION SCRIPT
# ============================================================
# NEW File: .agents/scripts/predict_speed_map.py
#
# Purpose: Automatically classify horses into Leader/On-Pace/Mid/Closer
# based on their "沿途位" (running position) history from Formguide.
#
# Logic:
# ```python
# def classify_horse(running_positions_last_3):
#     """
#     running_positions_last_3: list of tuples [(pos_800m, pos_400m, pos_finish), ...]
#     """
#     leader_count = sum(1 for r in running_positions_last_3 if r[0] <= 2)
#     front_count = sum(1 for r in running_positions_last_3 if r[0] <= field_size * 0.33)
#     back_count = sum(1 for r in running_positions_last_3 if r[0] >= field_size * 0.67)
#     
#     if leader_count >= 2: return "Leader"
#     if front_count >= 2: return "On-Pace"
#     if back_count >= 2: return "Closer"
#     return "Mid-Pack"
# ```
#
# Input: Facts.md (parse 沿途位 from 完整賽績檔案)
# Output: _Speed_Map_Prediction.json
# {
#   "leaders": ["#7 千杯 (3)", "#10 喆喆友福 (10)"],
#   "on_pace": ["#4 歷險大將 (1)"],
#   "mid_pack": ["#6 神燦金剛 (4)"],
#   "closers": ["#8 焦點 (11)"],
#   "predicted_pace": "Fast",
#   "leader_count": 3,
#   "confidence": "High"
# }
#
# Integration: Orchestrator reads this JSON before Batch 0 and injects
# into the LLM prompt as pre-filled Speed Map suggestion.

---

# ============================================================
# STEP 10.5: COMPUTE RATING MATRIX (AUTO RATING/FINE-TUNE/OVERRIDE)
# ============================================================
# NEW File: .agents/scripts/compute_rating_matrix.py
#
# ⚠️ THIS IS THE MOST IMPORTANT NEW SCRIPT IN THE ENTIRE PLAN.
# It removes ~240 lines of rules from the LLM's context by automating:
#   - 14.2 Base rating lookup (S to D)
#   - 14.2B Fine-tune rules (30 rules)
#   - 14.2C D-grade longshot scan
#   - 14.2D B- longshot scan
#   - 14.2E B+ upgrade scan
#   - 14.2F Favourite collapse test
#   - 14.3 Override rules (15 rules)
#   - Same-grade tiebreaking (SIP-RR20)
#   - Top 2 robustness test
#
# INPUT: Logic.json (after LLM fills 8 dims + core_logic + advantages/disadvantages)
#        Facts.md (for horse data: weight, barrier, age, recent form, etc.)
#
# OUTPUT: Enriched Logic.json with auto-computed fields:
#   - base_rating (from 14.2 lookup table)
#   - fine_tune.direction + fine_tune.trigger (from 14.2B rules)
#   - override.rule (from 14.3 chain)
#   - final_rating (after fine-tune + override)
#   - matrix_arithmetic (✅/❌ counts)
#   - longshot_scan (D/C/B- scan results)
#   - verdict.top4 (auto-ranked by rating → ✅ count → ❌ count)
#
# ARCHITECTURE:
# The script runs BETWEEN the LLM's JSON output and the Compiler:
#   LLM → Logic.json (raw) → compute_rating_matrix.py → Logic.json (enriched) → Compiler
#
# IMPLEMENTATION OUTLINE:
#
# ```python
# def compute_base_rating(matrix_scores):
#     """Directly translates the rating table from 06_rating_aggregation.md / 02f_synthesis.md"""
#     core = count_type(matrix_scores, "核心", "✅")
#     semi = count_type(matrix_scores, "半核心", "✅")
#     aux = count_type(matrix_scores, "輔助", "✅")
#     total_fail = count_all(matrix_scores, "❌")
#     core_fail = count_type(matrix_scores, "核心", "❌")
#     
#     # Core Engine Protection Wall
#     if core_fail > 0:
#         max_rating = "B+"  # Hard cap
#     
#     # Lookup table (exact copy from Analyst resources)
#     if core == 2 and semi == 2 and aux >= 2 and total_fail == 0:
#         return "S"
#     if core == 2 and semi >= 1 and aux >= 1 and total_fail == 0:
#         return "S-"
#     if core == 2 and total_fail == 0:
#         return "A+"
#     if (core == 1 and semi >= 1 and total_fail == 0) or (core == 2 and total_fail <= 1):
#         return "A"
#     if core >= 1 and total_fail <= 1:
#         return "A-"
#     if (core >= 1 and total_fail == 2) or (semi >= 2 and total_fail <= 1):
#         return "B+"
#     if semi >= 1 and aux >= 2 and total_fail <= 2:
#         return "B"
#     if aux >= 3 and total_fail <= 2:
#         return "B-"
#     if total_fail == 3 and (core >= 1 or semi >= 1):
#         return "C+"
#     if total_fail == 3:
#         return "C"
#     if total_fail == 4:
#         return "C-"
#     return "D"
#
# def apply_fine_tune_rules(base, horse_facts, race_context, is_hkjc=True):
#     """30 if-then rules, all with numeric thresholds"""
#     upgrades = []
#     downgrades = []
#     
#     # --- Upgrade rules ---
#     weight = horse_facts.get('weight', 0)
#     barrier = horse_facts.get('barrier', 99)
#     
#     # 負重/班次協同 (HKJC: 升班輕磅; AU: 見習減磅)
#     if horse_facts.get('weight_diff', 0) <= -10:
#         upgrades.append(("負重協同", 1.0))
#     
#     # 步速形勢配合 (龜速壟斷 / 自殺式後追)
#     pace = race_context.get('predicted_pace', '')
#     if pace in ['Crawl', '龜速'] and horse_facts.get('is_leader'):
#         upgrades.append(("龜速壟斷", 1.0))
#     
#     # ... (all 10 upgrade rules from 06_rating_aggregation.md / 02f_synthesis.md)
#     
#     # --- Downgrade rules ---
#     # 致命死檔
#     if barrier >= 10 and race_context.get('is_tight_track'):
#         downgrades.append(("致命死檔", 1.0))
#     
#     # 頂磅斷尾
#     weight_threshold = 133 if is_hkjc else 60  # lb vs kg
#     if weight >= weight_threshold and not horse_facts.get('heavy_weight_record'):
#         downgrades.append(("頂磅斷尾", 1.0))
#     
#     # ... (all 12 downgrade rules)
#     
#     # Net adjustment (max ±1 grade)
#     max_up = max((u[1] for u in upgrades), default=0)
#     max_down = max((d[1] for d in downgrades), default=0)
#     net = min(max_up - max_down, 1.0)
#     net = max(net, -1.0)
#     
#     return adjust_rating(base, net), upgrades, downgrades
#
# def apply_override_chain(rating, horse_data, risk_count):
#     """15 override rules with clear priority chain"""
#     # Priority 1: Risk cap (highest priority)
#     if risk_count >= 4: return "D", "風險封頂(4+項)"
#     if risk_count >= 3: return min(rating, "C+"), "嚴重風險(3項)"
#     if risk_count >= 2: return min(rating, "B"), "風險封頂(2項)"
#     
#     # Priority 2: Premium cap
#     # ...
#     
#     # Priority 3: Floor rules
#     if stability_index > 0.7: rating = max(rating, "B+")  # 超級鐵腳保底
#     if stability_index > 0.5: rating = max(rating, "B")    # 鐵腳保底
#     # ...
#     
#     return rating, "無"
# ```
#
# INTEGRATION INTO ORCHESTRATOR:
# In both hkjc_orchestrator.py and au_orchestrator.py, AFTER the LLM writes
# Logic.json and BEFORE the Compiler runs, add:
#
# ```python
# # Auto-compute ratings (Python replaces 240 lines of LLM rules)
# subprocess.run(["python3", ".agents/scripts/compute_rating_matrix.py",
#                 logic_json_path, facts_path, "--domain", "hkjc"])
# ```
#
# CRITICAL: The Orchestrator stdout must tell the LLM:
# "你只需要填 8 維度 ✅/➖/❌ + reasoning。
#  base_rating / fine_tune / override 由 Python 自動計算，你唔需要填。
#  但你必須填 core_logic (≥120字) 同 advantages/disadvantages。"
#
# This removes the need for LLM to read/memorise:
#   - 06_rating_aggregation.md lines 85-370 (HKJC)
#   - 02f_synthesis.md lines 54-165 (AU)
#   - 02g_override_chain.md (AU, 13KB)
# Total context savings: ~40KB per session = 80% reduction

---

# ============================================================
# STEP 11: STRENGTHEN COMPLETION_GATE_V2.PY
# ============================================================
# File: .agents/scripts/completion_gate_v2.py
# (or wherever completion_gate is located - search for it)
#
# ADD these checks:
#
# 1. Per-horse core_logic word count:
#    - Extract each 核心邏輯 section via regex
#    - Count Chinese characters
#    - FAIL if any horse below minimum (80 for C/D, 100 for B, 150 for S/A)
#
# 2. [FILL] residual scan:
#    - Count remaining [FILL] or [需判定] in Analysis.md
#    - FAIL if > 0 (means compiler or LLM left blanks)
#
# 3. 14.2B + 14.3 existence check:
#    - Regex for "14.2B 微調" and "14.3 覆蓋"
#    - FAIL if either is missing
#
# 4. Matrix completeness:
#    - Count 📊 sections = number of horses
#    - Each must have 8 dimension lines
#
# 5. Sectional/EEM/Forgiveness existence:
#    - Check for 🔬 段速法醫 / ⚡ EEM / 📋 寬恕 headers
#    - FAIL if any is missing (except 首出馬 which can have N/A)

---

# ============================================================
# STEP 12: ARCHIVE ORPHANED AGENTS
# ============================================================
# Files to modify (add [DEPRECATED] header):
# - .agents/skills/hkjc_racing/hkjc_batch_qa/SKILL.md
# - .agents/skills/au_racing/au_batch_qa/SKILL.md
# - .agents/skills/hkjc_racing/hkjc_compliance/SKILL.md
# - .agents/skills/au_racing/au_compliance/SKILL.md
#
# Add to line 1 of each:
# ```markdown
# # [DEPRECATED] — 此 Agent 已被 completion_gate_v2.py 取代
# # 保留此檔案僅供歷史參考。請勿調用。
# ```

---

# ============================================================
# STEPS 13-16: VERIFICATION
# ============================================================
#
# Step 13: Recompile HKJC
# ```bash
# cd "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"
# python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py \
#   "2026-04-12_ShaTin/04-12_ShaTin Race 1 Facts.md" \
#   "2026-04-12_ShaTin/Race_1_Logic.json" \
#   --output "2026-04-12_ShaTin/04-12_ShaTin Race 1 Analysis_v2.md"
# ```
# Then: view the output, compare with Archive/.../04-08 Race 1_Analysis.md
# Check: 14.2B/14.3 present? 段速法醫 present? EEM present?
#
# Step 14: Recompile AU (same pattern with AU paths)
#
# Step 15: Full HKJC loop
# ```bash
# python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py "2026-04-12_ShaTin"
# ```
# Check: State 4 calls report + cost tracker
#
# Step 16: Full AU loop
# ```bash
# python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<existing AU folder>"
# ```
# Check: No crash with local path, analyst awakening is complete

---

# ============================================================
# HKJC ANALYST ↔ COMPILER KEY MAPPING REFERENCE
# ============================================================
# Use this table when modifying the HKJC compiler to ensure
# it reads the correct JSON keys that the Analyst will write.
#
# | Analyst Resource File | JSON Key (Logic.json) | Compiler Output Section |
# |---|---|---|
# | 06_rating_aggregation.md Step 14.1 | matrix.stability | 位置穩定性 [核心] |
# | 06_rating_aggregation.md Step 14.1 | matrix.speed_mass | 段速質量 [核心] |
# | 05_forensic_eem.md | matrix.eem | EEM 潛力 [半核心] |
# | 07b_trainer_signals.md | matrix.trainer_jockey | 練馬師訊號 [半核心] |
# | 03_engine_pace_context.md | matrix.scenario | 情境適配 [輔助] |
# | 04_engine_corrections.md | matrix.freshness | 路程/新鮮度 [輔助] |
# | 06_rating_aggregation.md Step 13 | matrix.formline | 賽績線 [輔助] |
# | 06_rating_aggregation.md Step 8.1 | matrix.class_advantage | 級數優勢 [輔助] |
# | 06_rating_aggregation.md Step 14.2B | fine_tune | 14.2B 微調 |
# | 06_rating_aggregation.md Step 14.3 | override | 14.3 覆蓋 |
# | 08_templates_core.md 核心邏輯 | core_logic | 💡 核心邏輯 |
# | 05_forensic_eem.md | sectional_forensic | 🔬 段速法醫 |
# | 05_forensic_eem.md | eem_energy | ⚡ EEM 能量 |
# | 06_rating_aggregation.md Step 12 | forgiveness_archive | 📋 寬恕檔案 |

---

# ============================================================
# AU ANALYST ↔ COMPILER KEY MAPPING REFERENCE
# ============================================================
# | Analyst Resource File | JSON Key (Logic.json) | Compiler Output Section |
# |---|---|---|
# | 02f_synthesis.md Step 14.E | matrix.狀態與穩定性 | 狀態與穩定性 [核心] |
# | 02f_synthesis.md Step 14.E | matrix.段速與引擎 | 段速與引擎 [核心] |
# | 02d_eem_pace.md | matrix.EEM與形勢 | EEM與形勢 [半核心] |
# | 02e_jockey_trainer.md | matrix.騎練訊號 | 騎練訊號 [半核心] |
# | 02f_synthesis.md Step 14.E | matrix.級數與負重 | 級數與負重 [輔助] |
# | 02c_track_and_gear.md | matrix.場地適性 | 場地適性 [輔助] |
# | 02f_synthesis.md Step 14.E | matrix.賽績線 | 賽績線 [輔助] |
# | 02c_track_and_gear.md | matrix.裝備與距離 | 裝備與距離 [輔助] |
# | 02f_synthesis.md 微調因素 | fine_tune | 微調 |
# | 02g_override_chain.md | override | 覆蓋規則 |
# | 06_templates_core.md 核心邏輯 | core_logic | 💡 核心邏輯 |
# | 02b_form_analysis.md | sectional_forensic | 段速法醫 (融入核心邏輯) |
# | 02d_eem_pace.md | eem_energy | EEM 能量 (融入核心邏輯) |
# | 02b_form_analysis.md Step 6 | forgiveness_archive | 寬恕認定 |
# | 06_templates_core.md Dual-Track | dual_track | 📗📙 場地雙軌評級 |

---

# ============================================================
# EMERGENCY REFERENCE: GOLD STANDARD EXAMPLES
# ============================================================
# If you need to see what the CORRECT output looks like:
#
# HKJC Gold Standard:
#   Archive Race Analysis/2026-04-08_HappyValley (Kelvin)/04-08 Race 1_Analysis.md
#   - Lines 28-92: Horse #1 有情有義 (complete 11-section format)
#   - Lines 234-298: Horse #4 歷險大將 (A+ rated, excellent core_logic quality)
#
# AU Gold Standard:
#   .agents/skills/au_racing/au_horse_analyst/resources/06_templates_core.md
#   - Lines 56-150: Complete per-horse template
#   .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md
#   - Lines 54-165: Complete rating matrix with all override rules

---

# END OF PLAN
# ============================================================
# When all 16 steps are marked [DONE], delete this file
# or move it to Archive/ for reference.
# ============================================================
