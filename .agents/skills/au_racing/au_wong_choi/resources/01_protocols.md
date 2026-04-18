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

# 🚨 CRITICAL: File Writing Protocol — Safe-Writer P33-WLTM (2026-04-05 更新)

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
| 寫入分析 Batch (任何大小) | `run_command` Python heredoc → safe_file_writer.py | `write_to_file`, `replace_file_content` |
| 新建分析報告 (第一個 Batch) | safe_file_writer.py `--mode overwrite` | `write_to_file` |
| 追加後續 Batch / Verdict | safe_file_writer.py `--mode append` | `replace_file_content` |
| 微型檔案 (task.md, session_state) | `run_command` + heredoc 或 safe_file_writer | `write_to_file`, `replace_file_content` |
| 執行 Python 腳本 (generate_reports.py) | `run_command` ✅ (允許) | N/A |

## ✅ 推薦方法: Python Heredoc One-Step Pattern (已驗證 2026-04-05)

> **此方法已於 2026-04-05 實戰驗證,連續 10+ 次成功,零失敗。**
> **所有引擎 (Gemini / Opus / Sonnet) 都應使用此方法。**

```python
# 用 run_command 執行以下 Python 指令（跨平台寫法）:
import subprocess, base64

content = """
[你的分析內容 — 可包含任何 Unicode/特殊字符]
"""

encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
subprocess.run([
    'python',
    '.agents/scripts/safe_file_writer.py',
    '--target', '{TARGET_DIR}/{ANALYSIS_FILE}',
    '--mode', 'append',    # Batch 1 用 'overwrite', Batch 2+ 用 'append'
    '--content', encoded
], check=True)
```

**優點:**
1. 一步完成 — heredoc 寫 Python → 執行 → safe_file_writer 寫入
2. Python triple-quoted string 處理所有特殊字符,無需 shell escaping
3. base64 編碼由 Python 完成,而非 shell,100% 可靠
4. safe_file_writer 使用 WLTM (Write-Local-Then-Move),繞過 Google Drive lock

**模式選擇:**
- **第一個 Batch (B1):** `--mode overwrite`（建立新檔）
- **後續 Batch (B2+):** `--mode append`（追加內容）

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
→ ⛔ STOP → 你已違規 → 改用上方 Python heredoc pattern。

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
