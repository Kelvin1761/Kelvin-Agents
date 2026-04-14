---
name: HKJC Wong Choi
description: This skill should be used when the user wants to "analyse HKJC races", "run HKJC pipeline", "香港賽馬分析", "HKJC Wong Choi", or needs to orchestrate the full Hong Kong horse racing analysis pipeline from data extraction through to final Excel report generation.
version: 4.0.0
---

# HKJC Wong Choi — V4 Python-First Architecture

## 唯一動作
收到任何賽事 URL 或指令後，你嘅**絕對第一且唯一動作**：
```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```

## 執行循環
1. 執行 Orchestrator → 讀取 stdout 指示
2. 遵從指示完成 JSON 填寫（只填寫 `[FILL]` 欄位）
3. 再次執行 Orchestrator
4. 重複直到 `🎉 [SUCCESS]`

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
| `orchestrator.py` crash / Python error | 報告完整 error output，嘗試 `python3 orchestrator.py --resume` 恢復 |
| 網絡中斷 / 數據擷取失敗 | 讀取 `.runtime/` 已存储狀態，通知用戶並嘗試重新執行 |
| `[FILL]` 填寫失敗 3 次 | 停止，報告失敗欄位，詢問用戶介入 |
| `.runtime/` 目錄不存在 | 執行 `mkdir .runtime` 後重試 |

## Session Recovery (Pattern 10)
啟動時掃描 `.runtime/` 目錄：
1. 檢查已存在嘅 `*_Analysis.md` 檔案
2. 讀取 orchestrator 狀態檔 → 從上次中斷位置繼續
3. 通知用戶：「偵測到 N/M 場已完成，從 Race X 繼續」
