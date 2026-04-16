---
description: 防串流鎖死寫檔協議 (Anti-Streaming-Lock Safe Write Protocol) — P19v5 簡化版
---
# Safe Write Protocol — P19v5 (Simplified Pipe Writer)

## 為什麼需要這個協議？

本 workspace 位於 **Google Drive 同步目錄**。當 Agent 使用 `write_to_file` 或 `replace_file_content` 寫入大量內容時，會觸發以下死鎖鏈：

```
IDE Tool → open(GDrive path) → macOS FileProvider lock → Google Drive sync
    → write stalls → buffer fills → tool call hangs → +0-0 (零寫入)
```

> [!CAUTION]
> **`write_to_file` 工具完全禁用!** 即使目標為 `/tmp`，`write_to_file` 工具本身也可能卡死（已實測確認 2026-04-03）。所有檔案寫入必須透過 `run_command` 執行。

> [!CAUTION]
> **`shutil.move` 也會死鎖!** Python 的 `shutil.move` 在跨裝置搬移時會觸發 FileProvider 死鎖。必須使用 shell `cp` 命令代替。

## 解決方案：Heredoc → /tmp → cp → Google Drive

```
Agent Content → heredoc → /tmp/safe_file_writer.py → /tmp/_sfw_{name} → cp → Google Drive target
     (瞬間)                    (瞬間)                        (瞬間)          (原子, <100ms)
```

## Step 0：確保 Safe Writer 存在 (每個 session 首次執行)

// turbo
```bash
cat << 'PYEOF' > /tmp/safe_file_writer.py
import sys, os, subprocess

def main():
    if len(sys.argv) != 2:
        print("Usage: cat content | python3 safe_file_writer.py <target_path>")
        sys.exit(1)
    target_path = sys.argv[1]
    tmp_path = f"/tmp/_sfw_{os.path.basename(target_path)}"
    content = sys.stdin.read()
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    # Use cp instead of shutil.move — shutil.move triggers Google Drive FileProvider deadlock
    result = subprocess.run(['cp', tmp_path, target_path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAIL: cp error: {result.stderr}")
        sys.exit(1)
    os.remove(tmp_path)
    print(f"OK: {len(content)} bytes -> {target_path}")

if __name__ == '__main__':
    main()
PYEOF
echo "safe_file_writer.py created OK"
```

## Step 1：寫入檔案 (標準模式)

使用 heredoc 將內容通過管道傳入 safe_file_writer.py：

// turbo
```bash
cat << 'CONTENTEOF' | python3 /tmp/safe_file_writer.py '/path/to/target.md'
# 你的分析內容
## 第一部分
...（任意長度 Markdown）...
CONTENTEOF
```

## Step 2：驗證寫入結果

// turbo
```bash
wc -l '/path/to/target.md' && head -5 '/path/to/target.md'
```

## 何時使用？

| 操作 | 工具 |
|------|------|
| 創建新檔案 | ✅ `heredoc \| python3 /tmp/safe_file_writer.py` (via `run_command`) |
| 覆蓋整個檔案 | ✅ `heredoc \| python3 /tmp/safe_file_writer.py` (via `run_command`) |
| 追加內容到檔案 | ✅ 先 heredoc 到 /tmp 再 `cat >> target` |
| 修改少量行 (<50 行) | ✅ `replace_file_content` / `multi_replace_file_content` |
| 創建新檔案 | ❌ ~~`write_to_file`~~ **完全禁用 — 即使 /tmp 也卡死** |

## 已知死鎖觸發器 (Deadlock Triggers)

| 方法 | 狀態 | 原因 |
|------|------|------|
| `write_to_file` (any path) | ❌ 死鎖 | IDE tool 本身 hang |
| `shutil.move(/tmp → GDrive)` | ❌ 死鎖 | cross-device rename 觸發 FileProvider |
| `cp /tmp/file GDrive/target` | ✅ 正常 | shell cp 不觸發 FileProvider lock |
| heredoc → `/tmp/file` | ✅ 正常 | 本地寫入無鎖 |

> [!CAUTION]
> 違反此協議會導致 IDE 串流鎖死。所有 Wong Choi Engine（HKJC / AU / NBA）的 batch 寫入必須遵守。
> **Gemini 引擎尤其容易觸發此死鎖，請務必嚴格遵守。**
