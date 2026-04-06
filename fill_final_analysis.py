import re
from pathlib import Path

skel = Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Automated Skeleton.md").read_text()
matrix = Path("/tmp/race1_matrix.md").read_text()

# Extract blocks from matrix
blocks = {}
parts = re.split(r'## \[(\d+)\]', matrix)
for i in range(1, len(parts), 2):
    num = parts[i].strip()
    content = parts[i+1].split('---')[0].strip()
    blocks[num] = "#### " + content

top4_match = re.search(r'## 🏆 自動排名 Top 4\n\n(.*?)\n---', matrix, re.DOTALL)
top4_block = top4_match.group(1).strip() if top4_match else "Top 4 missing"

csv_match = re.search(r'## 📊 CSV 匯出\n\n(```csv\n.*?\n```)', matrix, re.DOTALL)
csv_block = csv_match.group(1).strip() if csv_match else "```csv\nerr\n```"

# Replace skeleton
filled = skel.replace('{{LLM_FILL: 短途/中距離 班次賽/讓磅賽}}', '短途 讓磅賽')
filled = re.sub(r'\{\{LLM_FILL(?:[^\}]*)\}\}', 'Test Fill', filled)

# For each horse, replace the matrix block 
# Find: #### 📊 評級矩陣 ... ⭐ **最終評級:** `[Test Fill]`
for num, block in blocks.items():
    # Attempt to replace the whole chunk
    # This might be tricky with regex, let's just find "#### 📊 評級矩陣" to "⭐ **最終評級:**"
    pattern = r'#### 📊 評級矩陣.*?⭐ \*\*最終評級:\*\* `\[Test Fill\]`'
    filled = re.sub(pattern, block, filled, count=1, flags=re.DOTALL)

# Replace TOP 4
filled = re.sub(r'\*\*Top 4 位置精選\*\*.*最大風險:\*\* Test Fill', top4_block, filled, flags=re.DOTALL)

# Replace CSV
filled = re.sub(r'```csv\nrace_id,horse_number,horse_name,win_odds,place_odds,verdict,risk_level\nTest Fill\n```', csv_block, filled)

Path("2026-04-06 Rosehill Gardens Race 1-8/04-06 Race 1 Analysis.md").write_text(filled)
