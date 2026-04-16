---
name: AU Wong Choi
description: This skill should be used when the user wants to "analyse AU races", "run AU pipeline", "澳洲賽馬分析", "AU Wong Choi", or needs to orchestrate the full Australian horse racing analysis pipeline from data extraction through to final report generation.
version: 4.0.0
---

# AU Wong Choi — V4 Python-First Architecture

## 唯一動作
收到任何 Racenet URL 或指令後，你嘅**絕對第一且唯一動作**：
```bash
python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
```

## 執行循環
1. 第一次執行 Orchestrator（無 `--auto`）→ 印賽日總結 → 等用戶確認
2. 用戶確認後執行 stdout 顯示嘅 `NEXT_CMD`（包含 `--auto`）→ 進入自動模式
3. 遵從指示完成 JSON 填寫（只填寫 `[FILL]` 欄位）
4. 每次 stdout 出現 `NEXT_CMD:` → 完成工作後即刻執行該指令
5. 重複直到 `🎉 [SUCCESS]`

## 鐵律
- **嚴禁**自行建立任何 `.py` 腳本
- **嚴禁**跳過 Orchestrator 直接修改 Analysis.md
- **嚴禁**自行計算評級矩陣（由 Python 自動計算）
- **嚴禁**查閱全局 Facts.md（只讀取 `.runtime/Active_Horse_Context.md`）
- 語言：香港繁體中文（廣東話口吻），馬名/騎師/練馬師保留英文
- 分析風格：Opus-Style 極度詳盡，法醫級推理

## Failure Protocol
| 情況 | 動作 |
|------|------|
| `au_orchestrator.py` crash / Python error | 報告完整 error output，嘗試 `python .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py <目錄> --auto` 恢復 |
| 網絡中斷 / 數據擷取失敗 | 讀取 `.runtime/` 已存储狀態，通知用戶並嘗試重新執行 |
| `[FILL]` 填寫失敗 3 次 | 停止，報告失敗欄位，詢問用戶介入 |
| `.runtime/` 目錄不存在 | 執行 `mkdir .runtime` 後重試 |

## Session Recovery (Pattern 10)
啟動時掃描 `.runtime/` 目錄：
1. 檢查已存在嘅 `*_Analysis.md` 檔案
2. 讀取 orchestrator 狀態檔 → 從上次中斷位置繼續
3. 通知用戶：「偵測到 N/M 場已完成，從 Race X 繼續」
