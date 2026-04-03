# NBA Wong Choi — File Writing Protocol (強制執行)

> **NEVER use `cat << EOF` or any heredoc syntax via `run_command` to write analysis reports.**
> This causes terminal processes to hang indefinitely (known incident: 9+ hour hang in production session).

## Mandatory File Writing Rules

| Scenario | Correct Tool | Forbidden |
|---|---|---|
| 建立全新分析報告 (.txt) | `write_to_file` (with `Overwrite: false`) | `cat << EOF >` |
| 覆寫完整報告 | `write_to_file` (with `Overwrite: true`) | `cat << EOF >` |
| 追加內容到現有報告 | `replace_file_content` (target the last line) | `cat << EOF >>` |
| 修改報告中多個不連續段落 | `multi_replace_file_content` | `cat << EOF >>` |
| 執行 Python 腳本 | `run_command` ✅ (允許) | N/A |

## 執行規則
1. **每場分析完成後** — 使用 `write_to_file` 建立 `Game_[X]_[Teams]_Full_Analysis.txt`
2. **最終報告** — 使用 `write_to_file` 建立 `NBA_Analysis_Report.txt` + `NBA_Banker_Report.txt`
3. **若需要驗證寫入成功** — 使用 `view_file` 讀取最後 20 行確認
4. **`run_command` 只用於**:執行 Python/shell 腳本、搜尋 grep、讀取檔案清單等輕量指令

> ✅ 遵守此協議可確保所有寫入操作立即完成,不會有任何掛起風險。
