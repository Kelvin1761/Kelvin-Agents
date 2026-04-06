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

# 🚨 CRITICAL: File Writing Protocol — Safe-Writer P19v6 (2026-04-05 更新)

> **⛔ TOTAL BAN — 零例外:**
>
> 以下工具在 Wong Choi pipeline 中 **完全禁止**,無論檔案大小、路徑、或目的:
> 1. ❌ `write_to_file` — 任何大小、任何路徑（包括 /tmp）
> 2. ❌ `replace_file_content` — 任何大小、任何路徑
> 3. ❌ `multi_replace_file_content` — 任何大小、任何路徑
> 4. ❌ `python3 -c '...'` inline script — shell 引號衝突
>
> **歷史教訓:** P19v1-v5 全部失敗。`write_to_file` 即使寫 /tmp 小檔案,
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

```bash
# 用 run_command 執行以下 Python heredoc:
cat << 'PYEOF' > /tmp/batch_N_generate.py
import subprocess, base64

content = """
[你的分析內容 — 可包含任何 Unicode/特殊字符]
"""

encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
subprocess.run([
    'python3',
    '/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/safe_file_writer.py',
    '--target', '{TARGET_DIR}/{ANALYSIS_FILE}',
    '--mode', 'append',    # Batch 1 用 'overwrite', Batch 2+ 用 'append'
    '--content', encoded
], check=True)
PYEOF

python3 /tmp/batch_N_generate.py
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

```bash
# Fallback A — overwrite:
cp /tmp/batch_N.md "{TARGET_DIR}/{ANALYSIS_FILE}"
# Fallback B — append:
cat /tmp/batch_N.md >> "{TARGET_DIR}/{ANALYSIS_FILE}"
# ⛔ 絕對唔可以 fallback 到 write_to_file / replace_file_content！
```

## 自檢觸發器

若你正在準備使用 `write_to_file` / `replace_file_content` / `multi_replace_file_content`:
→ ⛔ STOP → 你已違規 → 改用上方 Python heredoc pattern。
