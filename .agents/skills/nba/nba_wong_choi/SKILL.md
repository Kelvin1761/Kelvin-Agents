---
name: NBA Wong Choi
description: This skill should be used when the user wants to "analyse NBA", "NBA 過關分析", "NBA Wong Choi", "分析今晚 NBA", "幫我睇 NBA", or needs to orchestrate the full NBA player props parlay analysis pipeline from data extraction through to final parlay report generation.
version: 3.0.0
---

# NBA Wong Choi — V3 Python-First Architecture

## 唯一動作
收到任何 NBA 分析指令後，你嘅**第一動作**：
1. 讀取 `resources/00_pipeline_and_execution.md` — 了解完整管線流程
2. 讀取 `resources/engine_directives.md` — 了解硬性約束
3. 嚴格按照 pipeline 步驟執行

## 執行規則（嚴格順序）
1. **Step 0 (強制 — Python Skeleton 生成)**:
   執行 `python3 scripts/generate_nba_reports.py` 生成 pre-filled skeleton report。
   呢個 skeleton 已包含所有數學數據（賠率/Edge/Kelly/組合選擇/Monte Carlo）。
   **Skeleton 係唯一合法嘅報告起點。嚴禁跳過此步驟自行從零撰寫任何分析。**
2. 使用 `scripts/nba_math_engine.py` 計算數據
3. 使用 `scripts/verify_nba_math.py` 驗證數據
4. **Step Final (強制 — 防火牆驗證)**:
   每份 `Game_*_Full_Analysis.md` 寫入後，必須執行
   `python3 scripts/validate_nba_output.py <分析檔案路徑>`
   任何 `❌ BLOCKED` 結果必須立即重寫，嚴禁提交不合格報告。
5. 所有 Python 腳本必須被執行，嚴禁自行跳過

## Anti-Bypass Guard（反繞過檢測）
以下特徵係 Python skeleton 嘅合法簽名。如果 LLM 輸出缺少以下任何標記，
即表明 LLM 跳過咗 Python pipeline，報告無效：
- `Python Auto-Selection` 或 `Python 自動`
- `8-Factor` 或 `10-Factor`
- `@X.XX` 格式嘅真實賠率（唔係 "X.5" 格式）
- 真實球員名（唔係 "Player A/B/C"）
- 真實 L10 數組（唔係 `[1,2,3,4,5,6,7,8,9,10]`）

## 鐵律
- **嚴禁**自行建立任何 `.py` 腳本
- **嚴禁**跳過 Python 腳本自行計算數據
- **嚴禁**自行修改已有嘅 Python 腳本
- **嚴禁**使用 "Player A/B/C" 等 placeholder 名稱
- **嚴禁**自創假 L10 數據（如連續整數序列）
- **嚴禁**重複句子灌水 — 每個句子只可出現一次
- 前置環境檢查：每次啟動前執行 `python3 .agents/scripts/preflight_environment_check.py <分析目錄>`
- 語言：香港繁體中文（廣東話口吻），球員名/球隊名保留英文
- 分析風格：Opus-Style 極度詳盡
