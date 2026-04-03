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

# 🚨 CRITICAL: File Writing Protocol (強制執行)

> **NEVER use `cat << EOF` or any heredoc syntax via `run_command` to write analysis reports.**
> This causes terminal processes to hang indefinitely (known incident: 9+ hour hang in production session).

## Mandatory File Writing Rules

| Scenario | Correct Tool | Forbidden |
|---|---|---|
| 建立全新分析報告 (.txt) | `write_to_file` (with `Overwrite: false`) | `cat << EOF >` |
| 覆寫完整報告 | `write_to_file` (with `Overwrite: true`) | `cat << EOF >` |
| 追加最終裁決/Verdict到現有報告 | `replace_file_content` (target the last line) | `cat << EOF >>` |
| 修改報告中多個不連續段落 | `multi_replace_file_content` | `cat << EOF >>` |
| 執行 Python 腳本 (generate_reports.py) | `run_command` ✅ (允許) | N/A |

## 執行規則
1. **每個 Batch** — 必須使用 `write_to_file` 建立或用 `replace_file_content` 追加,嚴禁用 `run_command` 寫入大量文字。
2. **Final Verdict** — 使用 `replace_file_content` 定位最後一個 `✅ 批次完成` 行,在其後追加 Part 3 + Part 4。
3. **若需要驗證寫入成功** — 使用 `view_file` 讀取最後 20 行確認。
4. **`run_command` 只用於**:執行 Python/shell 腳本、搜尋 grep、讀取檔案清單等輕量指令。

> ✅ 遵守此協議可確保所有寫入操作立即完成,不會有任何掛起風險。
