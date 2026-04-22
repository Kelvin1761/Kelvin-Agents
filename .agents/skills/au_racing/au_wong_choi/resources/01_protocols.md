# AU Wong Choi — 操作協議 (Operational Protocols)

此文件包含 AU Wong Choi 嘅參考協議。SKILL.md 會喺啟動時載入呢個文件。

---

# 統一失敗處理協議 (Unified Failure Protocol)

| 觸發場景 | 處理方式 |
|---|---|
| AU Race Extractor 執行失敗或輸出不完整 | 立即停止並通知用戶,絕不繼續分析不完整的數據 |
| Analyst 連續 3 次無法完成某匹馬的分析 | 標記為 `N/A (分析失敗)`,繼續下一匹 |
| generate_reports.py 腳本執行失敗 | 檢查錯誤訊息。若依賴套件缺失(`pandas`、`openpyxl`),先 `pip install` 安裝後重試 |
| 賽間自檢發現 CRITICAL 問題 | 按 Step 4 賽間自檢報告協議處理(最多重試 1 次,熔斷機制) |
| Context window 接近上限 | 主動建議用戶開啟新 session,Session Recovery 會自動偵測已完成場次 |

---

# 🚨 CRITICAL: File / JSON Writing Protocol — V11 Orchestrator-Owned Output

> **⛔ TOTAL BAN — 零例外:**
>
> 以下工具在 Wong Choi pipeline 中 **完全禁止**,無論檔案大小、路徑、或目的:
> 1. ❌ `write_to_file` — 任何大小、任何路徑（包括 /tmp）
> 2. ❌ `replace_file_content` — 任何大小、任何路徑
> 3. ❌ `multi_replace_file_content` — 任何大小、任何路徑
> 4. ❌ `python -c '...'` inline script — shell 引號衝突
>
> **歷史教訓:** P33-WLTM-v5 全部失敗。`write_to_file` 即使寫 /tmp 小檔案,
> 喺 session context 夠大時一樣卡死在 `+0 -0`。根因係 IDE JSON serialization
> pipeline 嘅系統性 deadlock,與目標路徑無關。

## Mandatory File Writing Rules

| Scenario | Correct Method | Forbidden |
|---|---|---|
| 回填馬匹分析 | Orchestrator 指定 `Race_X_Logic.json` 欄位；完成後重跑 `au_orchestrator.py` | 直接寫 `Analysis.md`, dummy markdown, shell heredoc |
| 新建 / 更新最終報告 | Orchestrator 調用 compile script 生成 `Analysis.md` | Analyst / LLM 手動 overwrite 或 append |
| 微型檔案 (task.md, session_state) | 既有 Python 腳本或 safe_file_writer | `write_to_file`, `replace_file_content`, shell heredoc |
| 執行 Python 腳本 (generate_reports.py) | `run_command` ✅ (允許) | N/A |

## ✅ 推薦方法: Orchestrator JSON-First Pattern

> **所有引擎 (Gemini / Opus / Sonnet) 都應只填 Orchestrator 指定 JSON 欄位。**

```python
# V11 expected shape:
# 1. Read .runtime/Active_Horse_Context.md or Horse_X_WorkCard.md.
# 2. Fill only the requested keys in Race_X_Logic.json.
# 3. Re-run au_orchestrator.py; Python compiles Analysis.md and runs completion_gate_v2.py.
```

**優點:**
1. 每次只讀取當前馬匹 context，降低 Race 1 到尾場嘅 context pressure
2. `Analysis.md` 由 deterministic Python 編譯，避免 LLM 生成 dummy 檔案繞過 firewall
3. Completion gate、batch QA、MC / report generation 全由 Orchestrator 接管

## ⚠️ Fallback (safe_file_writer 不可用時)

```python
# Fallback — 用 Python 直接寫入（跨平台）:
import shutil
shutil.copy('.scratch/batch_N.md', '{TARGET_DIR}/{ANALYSIS_FILE}')  # overwrite
# 或 append:
with open('{TARGET_DIR}/{ANALYSIS_FILE}', 'a', encoding='utf-8') as f:
    f.write(open('.scratch/batch_N.md', encoding='utf-8').read())
# ⛔ 絕對唔可以 fallback 到 write_to_file / replace_file_content！
```

## 自檢觸發器

若你正在準備使用 `write_to_file` / `replace_file_content` / `multi_replace_file_content`:
→ ⛔ STOP → 你已違規 → 改用 Orchestrator JSON 回填；若確實係 standalone 非 V11 任務，改用既有 Python script / safe writer。

# 🛡️ P40: Template Instantiation Protocol (防錯位及漏填機制)

> **⛔ BAN: 盲目順序替換 (Blind Sequential Replacement)**
> 絕對禁止以迴圈 (loop) 配合 `text.replace("[FILL]", val, 1)` 或 `text.replace("{{LLM_FILL}}", val, 1)` 等純文字按順序替換大量變數的方法。Markdown 表格分隔符號 (`----`) 或其他意料外的文本結構極易導致 Regex 擷取中斷，從而造成錯位填充及災難性漏填。

## ✅ 唯一允許寫法: 錨點精準替換 (Anchored Key-Value Replacement)

當透過 Python 腳本更新 Analysis 骨架（例如 `04-08 Race X Analysis.md`）時，每次呼叫 `.replace()` 或 `re.sub()` **必須包含該欄位的標籤 (Label) 或完整上下文作為錨點 (Anchor)**。

**正確示範:**
```python
# 1. 針對單一欄位的替換 (嚴格連同標題配對)
text = text.replace(
    "- **班次負重:** [FILL]", 
    f"- **班次負重:** {weight}"
)

# 2. 針對大區塊的核心邏輯替換 (使用前後文錨點)
text = text.replace(
    "> - **核心邏輯:** [FILL — S/A ≥150字 | B ≥100字 | C/D ≥80字]",
    f"> - **核心邏輯:** {core_logic}"
)
```

**必經安全檢查 (Micro-Batch Validation):**
每次執行腳本替換後，必須主動驗證 `[FILL]` 佔位符的數量是否如預期般減少。若執行後出現異常大量的剩餘 `[FILL]`，或者為 `0` 但內容有誤，必須 **先呼叫 `view_file` 檢查檔案內容**，嚴禁「盲目修補 (Blind Patching)」。
