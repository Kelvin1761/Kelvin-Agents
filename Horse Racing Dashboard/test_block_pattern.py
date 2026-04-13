import sys
sys.path.append('backend')
from services.parser_au import _extract_section
import re

with open("../2026-04-02 Gosford Race 1-7/2026-04-02_Gosford_Race_7_Analysis.md", "r") as f:
    text = f.read()

verdict = _extract_section(text,
    ['🏆 全場最終決策', '🏆 Top 3', '🏆 Top 4', '[第三部分]',
     'Top 4 位置精選', 'Top 3 位置精選', 'Top 4 精選排名', '精選排名'],
    ['[第四部分]', '🔒 COMPLIANCE', '```csv']
)

block_pattern = re.compile(r'(?:^|\n)(?:\> )?\s*(🥇|🥈|🥉|🏅)\s*(.*?)(?=(?:^|\n)(?:\> )?\s*(?:🥇|🥈|🥉|🏅)\s*|\Z)', re.DOTALL)
block_matches = block_pattern.findall(verdict)
for i, m in enumerate(block_matches):
    print(f"Match {i}: {m[0]} -> {m[1][:50]}...")
