import re

with open(r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-04-02 Gosford Race 1-7\2026-04-02_Gosford_Race_7_Analysis.md", "r", encoding="utf-8") as f:
    text = f.read()

horses = re.findall(r"### 【No\.(\d+)】(.*?)\（.*?\n.*?- \*\*📙 備選場地：\*\* \`?\[.*?\]\`? → 評級：\`?\[(.*?)\]\`?", text, re.DOTALL)
for num, name, grade in horses:
    print(f"{num} - {name} - {grade}")
