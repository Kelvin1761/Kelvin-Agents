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

## 執行規則
1. 使用 `scripts/generate_nba_reports.py` 生成報告
2. 使用 `scripts/nba_math_engine.py` 計算數據
3. 使用 `scripts/verify_nba_math.py` 驗證數據
4. 所有 Python 腳本必須被執行，嚴禁自行跳過

## 鐵律
- **嚴禁**自行建立任何 `.py` 腳本
- **嚴禁**跳過 Python 腳本自行計算數據
- **嚴禁**自行修改已有嘅 Python 腳本
- 前置環境檢查：每次啟動前執行 `python3 .agents/scripts/preflight_environment_check.py <分析目錄>`
- 語言：香港繁體中文（廣東話口吻），球員名/球隊名保留英文
- 分析風格：Opus-Style 極度詳盡
