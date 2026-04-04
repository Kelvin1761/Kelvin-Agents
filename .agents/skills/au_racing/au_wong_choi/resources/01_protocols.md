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

# 🚨 CRITICAL: File Writing Protocol — Safe-Writer P19v5 (2026-04-03 更新)

> **所有大型分析內容必須使用 Safe-Writer P19v5 三步管道寫入。**
> `write_to_file` 同 `replace_file_content` 超過 ~100 行會導致 IDE JSON 死機。
> 直接 Python `open()` 寫入 Google Drive 路徑會觸發 FileProvider Lock。

## Mandatory File Writing Rules

| Scenario | Correct Tool | Forbidden |
|---|---|---|
| 寫入分析 Batch (大型內容) | `run_command` heredoc → /tmp → base64 pipe → safe_file_writer.py | `write_to_file`, `replace_file_content`, `python3 -c` |
| 新建分析報告 (第一個 Batch) | safe_file_writer.py `--mode overwrite` | `write_to_file` |
| 追加後續 Batch / Verdict | safe_file_writer.py `--mode append` | `replace_file_content` |
| 微型檔案 (< 20 行: task.md, session_state) | `replace_file_content` ✅ (允許) | N/A |
| 執行 Python 腳本 (generate_reports.py) | `run_command` ✅ (允許) | N/A |

## 執行規則 (P19v5 三步管道)
1. **Step 1:** `cat > /tmp/batch_N.md << 'ENDOFCONTENT'` — heredoc 寫入本地 /tmp（零延遲）
2. **Step 2:** `base64 < /tmp/batch_N.md | python3 .agents/scripts/safe_file_writer.py --target "..." --mode append --stdin`
3. **Step 3 (可選):** `tail -5 "{TARGET_DIR}/{FILE}"` — 驗證寫入成功
4. 每次 heredoc 內容控制在 **50-80 行**，避免 run_command payload 過大
5. safe_file_writer.py 路徑: `.agents/scripts/safe_file_writer.py`

> ✅ 此管道已於 2026-04-03 實戰驗證通過。所有寫入均在 1-2 秒內完成。
