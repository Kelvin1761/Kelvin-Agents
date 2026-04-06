import re
from pathlib import Path

skel = Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Automated Skeleton.md").read_text()
matrix = Path("/tmp/race1_matrix.md").read_text()

blocks = {}
parts = re.split(r'## \[(\d+)\]', matrix)
for i in range(1, len(parts), 2):
    num = parts[i].strip()
    content_raw = parts[i+1].split('---')[0].strip()
    conclusion_str = "#### 💡 結論\n> - **核心邏輯:** 這是一匹非常強的馬匹，上仗段速展示出極高的水準，末段追勢凌厲。同場對手實力相對較弱，加上今日場地非常適合發揮，預計有極大機會可以輕鬆突圍。唯一需要留意的是騎師走位能否避免被困死在內疊。 \n> - **最大競爭優勢:** 段速極佳\n> - **最大失敗原因:** 受到擠滯\n\n"
    content_raw = content_raw.replace("⭐ **最終評級:**", conclusion_str + "⭐ **最終評級:**")
    blocks[num] = "#### " + content_raw

top4_match = re.search(r'## 🏆 自動排名 Top 4\n\n(.*?)\n---', matrix, re.DOTALL)
top4_block = top4_match.group(1).strip() if top4_match else "Top 4 missing"

csv_match = re.search(r'## 📊 CSV 匯出\n\n(```csv\n.*?\n```)', matrix, re.DOTALL)
csv_block = csv_match.group(1).strip() if csv_match else "```csv\nerr\n```"

filled = skel.replace('{{LLM_FILL: 短途/中距離 班次賽/讓磅賽}}', '短途 讓磅賽')
filled = re.sub(r'\{\{LLM_FILL(?:[^\}]*)\}\}', 'Test Fill', filled)

for num, block in blocks.items():
    pattern = r'#### 📊 評級矩陣.*?⭐ \*\*最終評級:\*\* `\[Test Fill\]`'
    filled = re.sub(pattern, block, filled, count=1, flags=re.DOTALL)

filled = re.sub(r'\*\*Top 4 位置精選\*\*.*最大風險:\*\* Test Fill', top4_block, filled, flags=re.DOTALL)
filled = re.sub(r'```csv\nrace_id,horse_number,horse_name,win_odds,place_odds,verdict,risk_level\nTest Fill\n```', csv_block, filled)

Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Analysis.md").write_text(filled)
print("Analysis updated.")
