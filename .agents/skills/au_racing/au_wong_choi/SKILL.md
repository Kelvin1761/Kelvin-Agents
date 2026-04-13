---
name: AU Wong Choi
description: This skill should be used when the user wants to "analyse AU races", "run AU pipeline", "澳洲賽馬分析", "AU Wong Choi", or needs to orchestrate the full Australian horse racing analysis pipeline from data extraction through to final report generation.
version: 4.0.0
---

# AU Wong Choi — V4 Python-First Architecture

## 唯一動作
收到任何 Racenet URL 或指令後，你嘅**絕對第一且唯一動作**：
```bash
python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py "<URL或資料夾>"
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
