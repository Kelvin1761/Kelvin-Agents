---
name: HKJC Wong Choi
description: This skill should be used when the user wants to "analyse HKJC races", "run HKJC pipeline", "香港賽馬分析", "HKJC Wong Choi", or needs to orchestrate the full Hong Kong horse racing analysis pipeline from data extraction through to final Excel report generation.
version: 4.0.0
---

# HKJC Wong Choi — V4 Python-First Architecture

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
- **Python 指令**: 使用 `python`（macOS 同 Windows 通用）。Orchestrator 內部已有 `shutil.which` 自動偵測。
- **臨時檔案**: macOS 用 `/tmp/`，Windows 用 workspace 內嘅 `.scratch/` 目錄。
- **Shell 語法**: 嚴禁使用 `cat <<EOF` heredoc 語法。改用 Python 腳本寫檔。
- **Encoding**: 所有 `open()` 必須指定 `encoding='utf-8'`。

## 唯一動作
收到任何賽事 URL 或指令後，你嘅**絕對第一且唯一動作**：
```bash
python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```
**(重要提示：執行此指令時，必須使用 `run_command` 工具。)**

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
| `orchestrator.py` crash / Python error | 報告完整 error output，嘗試 `python .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <目錄> --auto` 恢復 |
| 網絡中斷 / 數據擷取失敗 | 讀取 `.runtime/` 已存储狀態，通知用戶並嘗試重新執行 |
| `[FILL]` 填寫失敗 3 次 | 停止，報告失敗欄位，詢問用戶介入 |
| `.runtime/` 目錄不存在 | 執行 `mkdir .runtime` 後重試 |

## Session Recovery (Pattern 10)
啟動時掃描 `.runtime/` 目錄：
1. 檢查已存在嘅 `*_Analysis.md` 檔案
2. 讀取 orchestrator 狀態檔 → 從上次中斷位置繼續
3. 通知用戶：「偵測到 N/M 場已完成，從 Race X 繼續」
