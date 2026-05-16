---
name: HKJC Wong Choi
description: This skill should be used when the user wants to "analyse HKJC races", "run HKJC pipeline", "香港賽馬分析", "HKJC Wong Choi", or needs to orchestrate the full Python Hong Kong horse racing pipeline from data extraction through to final Auto analysis generation.
version: 4.0.0
---

# HKJC Wong Choi — Full Python Architecture

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
- **Python 指令**: macOS/Linux 優先使用 `python3`，若環境沒有 `python3` 則使用 `python`（常見於 Windows）。Orchestrator 內部已有 `shutil.which` 自動偵測後續 `NEXT_CMD`。
- **臨時檔案**: 統一使用 workspace 內嘅 `.scratch/` 目錄或 `tempfile.gettempdir()`。
- **Shell 語法**: 嚴禁使用 shell here-document 寫檔語法。改用既有 Python 腳本或 safe writer。
- **Encoding**: 所有 `open()` 必須指定 `encoding='utf-8'`。

## 唯一動作
收到任何賽事 URL 或指令後，你嘅**絕對第一且唯一動作**：
```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py <URL或資料夾>
```
> 若環境沒有 `python3`，改用 `python` 執行同一指令。
**(重要提示：執行此指令時，必須使用 `run_command` 工具。)**

## 執行循環
1. 若輸入係 HKJC URL，Orchestrator 會先抽取 racecard / formguide / trackwork
2. 然後生成 Facts.md
3. 再生成 Race_X_Logic.json
4. 最後由 `hkjc_wong_choi_auto` 產出 `Race_X_Auto_Analysis.md` / `Race_X_Auto_Scoring.csv`

## 鐵律
- **嚴禁**自行建立任何 `.py` 腳本（包括 auto_fill、auto_expert、auto_analyst 等）
- **嚴禁**跳過 Orchestrator 直接修改 Analysis.md
- **嚴禁**自行計算評級矩陣（由 Python 自動計算）
- **嚴禁**繞過主 orchestrator 直接手動拼接 extraction/facts/logic/output
- 語言：香港繁體中文（廣東話口吻），馬名/騎師/練馬師保留英文
- 分析風格：Opus-Style 極度詳盡，法醫級推理

## LLM 角色定義（鐵律）

> **Python 係主人，LLM 係分析員。Python 話做咩就做咩，LLM 唔可以自作主張。**

### LLM 嘅唯一職責
1. **接收指令**: 執行 Full Python orchestrator
2. **監察結果**: 報告 extraction / facts / logic / auto scoring 成功與否
3. **維護 routing**: 需要時切去 legacy 入口，而唔係手動補寫分析

### LLM 嚴禁行為
- ❌ 跳過 Orchestrator 直接寫 Analysis.md
- ❌ 自行改寫 Python 已產生的 deterministic scoring
- ❌ 自行計算評級


## 分析品質標準（Per-Horse）
每匹馬嘅 `core_logic` 必須：
- **至少 50 個中文字**（約 2-3 句有實質數據支撐嘅分析）
- **引用馬匹專屬事實**（例如具體賽績日期、margin、L400 時間）
- **唔可以用模板句式**（例如「自動匹配系統法則」「具備潛力」「分析中」）
- **每匹馬嘅分析內容必須唯一**（唔可以套用同一個模板再換馬名）

每個 matrix dimension 嘅 `reasoning` 必須：
- **引用該維度嘅具體數據**（例如 stability 引用近績序列、sectional 引用 L400 時間）
- **至少 10 個中文字**

## HKJC Logic JSON Field Responsibilities (V4.2)

HKJC Logic JSON 使用 **canonical English matrix keys only**。
唔准建立 Chinese matrix keys。Compiler 會自動顯示中文 labels。

**Schema Version:** `HKJC_LOGIC_V4_2`
**Matrix Dimensions:** 7D only (`stability`, `sectional`, `race_shape`, `trainer_signal`, `horse_health`, `form_line`, `class_advantage`)

**LLM fills:**
- `core_logic` — 核心分析邏輯
- `advantages` — 最大競爭優勢
- `disadvantages` — 最大失敗風險
- `matrix.*.score` — 5-tier tick (✅✅/✅/➖/❌/❌❌)
- `matrix.*.reasoning` — 基於數據嘅維度分析

**LLM must NOT edit:**
- `locked_data` / `_data` — Python 預填嘅事實數據
- `computed_rating` — Python 計算嘅評級
- `schema_version` — 由 skeleton generator 設定
- `platform` — 由 skeleton generator 設定
- `audit` — 由 pipeline 自動填充

## Failure Protocol
| 情況 | 動作 |
|------|------|
| `orchestrator.py` crash / Python error | 報告完整 error output，嘗試用 Orchestrator stdout 顯示嘅 `NEXT_CMD` 恢復 |
| 網絡中斷 / 數據擷取失敗 | 讀取 `.runtime/` 已存储狀態，通知用戶並嘗試重新執行 |
| `[FILL]` 填寫失敗 3 次 | 停止，報告失敗欄位，詢問用戶介入 |
| `.runtime/` 目錄不存在 | 執行 `mkdir .runtime` 後重試 |
| V4.2 Schema Validation 失敗 | Pipeline 停止，報告具體 SCHEMA-xxx error codes |

## Session Recovery (Pattern 10)
啟動時掃描 `.runtime/` 目錄：
1. 檢查已存在嘅 `*_Analysis.md` 檔案
2. 讀取 orchestrator 狀態檔 → 從上次中斷位置繼續
3. 通知用戶：「偵測到 N/M 場已完成，從 Race X 繼續」
