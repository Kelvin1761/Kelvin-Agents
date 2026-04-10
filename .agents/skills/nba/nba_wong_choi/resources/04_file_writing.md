# NBA Wong Choi — File Writing Protocol (P19V6 強制執行)

> **🚫🚫🚫 TOTAL BAN — `write_to_file` / `replace_file_content` / `multi_replace_file_content` 完全封殺 🚫🚫🚫**
>
> 任何直接修改檔案內容的行為已被禁止，防止 Google Drive 雲端同步死鎖風險。

## Mandatory File Writing Rules (Safe-Writer Protocol)

唯一合法寫檔方式：Heredoc 生成 markdown 暫存檔至 `/tmp`，再透過 base64 傳入 `safe_file_writer.py` 進行操作。

### 標準三步管道：

**Step 1: 用 `run_command` + heredoc 寫入 /tmp 暫存檔**
```bash
cat > /tmp/batch_NBA.md << 'ENDOFCONTENT'
[你的分析報告或檔案文字內容]
ENDOFCONTENT
```

**Step 2: Base64 編碼 + pipe 到 safe_file_writer.py**
```bash
SAFE_WRITER="/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/.agents/scripts/safe_file_writer.py"

base64 < /tmp/batch_NBA.md | python3 "$SAFE_WRITER" \
  --target "{TARGET_DIR}/{FILE_NAME}" \
  --mode overwrite \
  --stdin
```
*註：若要建立新檔請用 `--mode overwrite`，若要追加請用 `--mode append`。*

**Step 3: 驗證**
使用 `run_command` 執行 `tail -n 10 "{TARGET_DIR}/{FILE_NAME}"` 確認已成功寫入。
