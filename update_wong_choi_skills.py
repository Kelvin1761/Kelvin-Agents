import os
from pathlib import Path

rules = """
# 🛑 Pipeline Testing & Agent Execution Boundaries
**CRITICAL PROTOCOL: How to Avoid Automation Shortcuts in the Future**

1. **停止測試捷徑 (No Automated Shortcuts for LLM Analysis):** 
   身為 LLM 分析引擎，你嘅職責就是根據 `extract_formguide_data.py` (或其他抽取器) 抽出嚟嘅客觀數據，做「深度法醫分析」同判定 Grade。在日後執行任何 Pipeline 測試或端到端執行時，**絕對不能用 Python script 去模擬生成內容或塞字過關**。必須老老實實當自己做緊真飛分析一樣，用 Markdown 直接把高質素、具深度的優質內容完整寫出嚟。
2. **遵守系統角色 (Respect System Roles):** 
   分工極為明確。Python 腳本負責「砌骨架」同做「算術題」（例如抽數、排版、計算 Matrix 分數），而你 (LLM) 負責「入血肉」（撰寫戰術節點、寬恕檔案、段速法醫及風險評估）。**任何企圖繞過血肉生成嘅舉動都係嚴重違反 Protocol 嘅行為。**
"""

paths = [
    ".agents/skills/au_racing/au_wong_choi/SKILL.md",
    ".agents/skills/hkjc_racing/hkjc_wong_choi/SKILL.md",
    ".agents/skills/nba/nba_wong_choi/SKILL.md"
]

base_dir = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"

for p in paths:
    full_path = os.path.join(base_dir, p)
    if os.path.exists(full_path):
        with open(full_path, "a", encoding="utf-8") as f:
            f.write("\n" + rules + "\n")
        print(f"Updated: {p}")
    else:
        print(f"Not found: {p}")

