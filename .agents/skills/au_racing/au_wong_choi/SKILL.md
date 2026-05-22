---
name: AU Wong Choi
description: This skill should be used when the user wants to "analyse AU races", "run AU pipeline", "澳洲賽馬分析", "AU Wong Choi", or needs to orchestrate the full Australian horse racing analysis pipeline from data extraction through to final report generation.
version: 5.0.0
---

# AU Wong Choi — Full Python Mainline

## Resource Read-Once Protocol（強制）
在開始任何工作前，你**必須**首先讀取以下資源檔案，並在整個 session 中保留記憶：
- `resources/00_pipeline_and_execution.md` — V8 State Machine 完整流程 [必讀]
- `resources/01_protocols.md` — File Writing Protocol + Template Protocol [必讀]
- `resources/engine_directives.md` — 機讀約束指令 [必讀]
- `resources/01_data_validation.md` — 數據驗證規則 [必讀]
- `resources/session_start_checklist.md` — Pre-flight 檢查 [Orchestrator 引導時讀取]
- `resources/horse_analysis_skeleton.md` — 馬匹分析骨架 [分析時讀取]
- `resources/00_cost_reporting.md` — 成本報告 [Session 結束時讀取]

> 讀取一次後保留在記憶中，嚴禁每場賽事重複讀取。

## 跨平台執行規則
- **Python 指令**: 首次啟動必須使用當前系統可用嘅 Python launcher。macOS/Linux 優先用 `python3`；Windows/已配置環境可用 `python`。Orchestrator 啟動後會用 `shutil.which` 偵測並於 `NEXT_CMD` 印出正確 launcher，之後一律照抄 `NEXT_CMD`。
- **臨時檔案**: 統一使用 workspace 內嘅 `.scratch/` 目錄或 `tempfile.gettempdir()`。
- **Shell 語法**: 嚴禁使用 shell 多行重定向寫檔。改用 Python 腳本配合 `safe_file_writer.py`。
- **Encoding**: 所有 `open()` 必須指定 `encoding='utf-8'`。

## 唯一動作
收到任何 Racenet URL 或指令後，你嘅**絕對第一且唯一動作**：
```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
```
> Windows 或已配置 `python` launcher 嘅環境可將 `python3` 換成 `python`。

## 執行循環
1. 若輸入係 Racenet URL，Python 先抽取 Racecard / Formguide
2. Python 自動生成 `Facts.md`
3. Python 自動生成 canonical `Race_X_Logic.json`
4. `au_wong_choi_auto` 自動計分、排名、render `Race_X_Auto_Analysis.md` / `Race_X_Auto_Scoring.csv`
5. meeting-level summary / reflector 直接讀 deterministic output

## 鐵律
- **嚴禁**自行建立任何 `.py` 腳本
- **嚴禁**跳過 Orchestrator 直接修改 Analysis.md
- **嚴禁**自行計算評級矩陣（由 Python 自動計算）
- **嚴禁**繞過主 orchestrator 手動拼接 extraction / facts / logic / output
- 語言：香港繁體中文（廣東話口吻），馬名/騎師/練馬師保留英文

## LLM 角色定義（鐵律）

> **Python 係主人，LLM 只負責監察與維護流程。**

### LLM 嘅唯一職責
1. **接收指令**: 執行 full Python orchestrator
2. **監察結果**: 報告 extraction / facts / logic / auto scoring 成功與否
3. **維護 routing**: 需要時切去 legacy 入口，而唔係手動補寫分析

### LLM 嚴禁行為
- ❌ 跳過 Orchestrator 直接寫 Analysis.md
- ❌ 自行覆寫 deterministic scoring / ranking
- ❌ 自行補 `[FILL]` 式分析欄位

- 分析風格：Opus-Style 極度詳盡，法醫級推理

## Failure Protocol
| 情況 | 動作 |
|------|------|
| `au_orchestrator.py` crash / Python error | 報告完整 error output，照 stdout 最後一行 `NEXT_CMD` 重跑；若無 `NEXT_CMD`，用可用 launcher 執行 `python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py <目錄> --auto` |
| 網絡中斷 / 數據擷取失敗 | 讀取 `.runtime/` 已存储狀態，通知用戶並嘗試重新執行 |
| `[FILL]` 填寫失敗 3 次 | 停止，報告失敗欄位，詢問用戶介入 |
| `.runtime/` 目錄不存在 | 執行 `mkdir .runtime` 後重試 |

## Session Recovery (Pattern 10)
啟動時掃描 `.runtime/` 目錄：
1. 檢查已存在嘅 `*_Analysis.md` 檔案
2. 讀取 orchestrator 狀態檔 → 從上次中斷位置繼續
3. 通知用戶：「偵測到 N/M 場已完成，從 Race X 繼續」

## Legacy
- 舊版 AU workflow 暫時保留於：
  - `.agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator_legacy.py`
- 用途只限：
  - 過渡期比對
  - 回退
  - 舊 output 對照
