# NBA Wong Choi — File Writing Protocol (P19V6 強制執行)

> **遵循 GEMINI.md 嘅 Google Drive 寫入防護協議。**

## 寫入規則

| 操作 | 工具 | 規則 |
|------|------|------|
| **創建新檔案 / 覆蓋** | ~~`write_to_file`~~ | ❌ **嚴禁** — 用 `run_command` + `safe_file_writer.py` |
| **小型編輯 (<50 行)** | `replace_file_content` / `multi_replace_file_content` | ✅ 允許 |
| **讀取** | `view_file` / `grep_search` | ✅ 不受影響 |

## Safe Writer 路徑

```
.agents/scripts/safe_file_writer.py  （相對路徑，跨平台適用）
```

## 標準寫入管道（跨平台）

### Windows (PowerShell)
```powershell
$content = @'
[你的分析報告或檔案文字內容]
'@
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("{TARGET_DIR}/{FILE_NAME}", $content, $utf8NoBom)
```

### macOS / Linux (Bash)
```bash
cat > "$TMPDIR/batch_NBA.md" << 'ENDOFCONTENT'
[你的分析報告或檔案文字內容]
ENDOFCONTENT

python .agents/scripts/safe_file_writer.py \
  --target "{TARGET_DIR}/{FILE_NAME}" \
  --mode overwrite \
  --stdin < "$TMPDIR/batch_NBA.md"
```

### 驗證
```bash
# Windows
Get-Content "{TARGET_DIR}/{FILE_NAME}" -Tail 10

# macOS/Linux
tail -n 10 "{TARGET_DIR}/{FILE_NAME}"
```
