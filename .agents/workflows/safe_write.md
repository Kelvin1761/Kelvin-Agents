---
description: 防串流鎖死寫檔協議 (Anti-Streaming-Lock Safe Write Protocol) — V2 跨平台版
---
# Safe Write Protocol — V2 (Cross-Platform)

## 為什麼需要這個協議？

本 workspace 位於 **Google Drive 同步目錄**。當 Agent 使用 `write_to_file` 或 `replace_file_content` 寫入大量內容時，會觸發以下死鎖鏈：

```
IDE Tool → open(GDrive path) → macOS FileProvider lock → Google Drive sync
    → write stalls → buffer fills → tool call hangs → +0-0 (零寫入)
```

> [!CAUTION]
> **`write_to_file` 工具完全禁用!** 即使目標為臨時目錄，`write_to_file` 工具本身也可能卡死（已實測確認 2026-04-03）。所有檔案寫入必須透過 `run_command` 執行。

> [!CAUTION]
> **`shutil.move` 也會死鎖!** Python 的 `shutil.move` 在跨裝置搬移時會觸發 FileProvider 死鎖。`safe_file_writer.py` 已內建 timeout 保護。

## 解決方案：使用 safe_file_writer.py（跨平台）

`safe_file_writer.py` 位於 `.agents/scripts/safe_file_writer.py`，**無需 Step 0 建立**——已永久存在於 repo 中。

```
Agent Content → base64 encode → python safe_file_writer.py → staging dir → atomic move → target
     (瞬間)                          (瞬間)                    (timeout 保護)
```

## 寫入方法

### 方法 A：Base64 模式（推薦 — 最穩定）

```bash
# 先將內容 base64 encode，然後傳入
CONTENT=$(echo '你的分析內容...' | base64)
python .agents/scripts/safe_file_writer.py --target '/path/to/target.md' --mode overwrite --content "$CONTENT"
```

### 方法 B：stdin 模式

```bash
echo '你的分析內容...' | python .agents/scripts/safe_file_writer.py --target '/path/to/target.md' --mode overwrite --stdin
```

### 方法 C：Python 腳本內使用

```python
import subprocess, base64, sys, shutil

_py = "python3" if shutil.which("python3") else "python"
content = "你的分析內容..."
b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
subprocess.run([_py, ".agents/scripts/safe_file_writer.py",
                "--target", target_path, "--mode", "overwrite", "--content", b64], check=True)
```

## 驗證寫入結果

```bash
wc -l '/path/to/target.md' && head -5 '/path/to/target.md'
```

## 何時使用？

| 操作 | 工具 |
|------|------|
| 創建新檔案 | ✅ `python .agents/scripts/safe_file_writer.py` (via `run_command`) |
| 覆蓋整個檔案 | ✅ `python .agents/scripts/safe_file_writer.py --mode overwrite` |
| 追加內容到檔案 | ✅ `python .agents/scripts/safe_file_writer.py --mode append` |
| 修改少量行 (<50 行) | ✅ `replace_file_content` / `multi_replace_file_content` |
| 創建新檔案 | ❌ ~~`write_to_file`~~ **完全禁用** |

## 已知死鎖觸發器 (Deadlock Triggers)

| 方法 | 狀態 | 原因 |
|------|------|------|
| `write_to_file` (any path) | ❌ 死鎖 | IDE tool 本身 hang |
| `shutil.move(tmp → GDrive)` | ⚠️ 有 timeout | safe_file_writer.py 已內建 SIGALRM/threading.Timer 保護 |
| `python .agents/scripts/safe_file_writer.py` | ✅ 安全 | staging → atomic move with timeout |

> [!CAUTION]
> 違反此協議會導致 IDE 串流鎖死。所有 Wong Choi Engine（HKJC / AU / NBA）的 batch 寫入必須遵守。
> **Gemini 引擎尤其容易觸發此死鎖，請務必嚴格遵守。**
