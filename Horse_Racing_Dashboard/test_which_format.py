import sys
sys.path.append('backend')
from services.parser_au import _extract_section
import re

with open("../2026-04-02 Gosford Race 1-7/2026-04-02_Gosford_Race_7_Analysis.md", "r") as f:
    text = f.read()

verdict = _extract_section(text,
    ['🏆 全場最終決策', '�� Top 3', '🏆 Top 4', '[第三部分]',
     'Top 4 位置精選', 'Top 3 位置精選', 'Top 4 精選排名', '精選排名'],
    ['[第四部分]', '🔒 COMPLIANCE', '```csv']
)

# test format 1
medals = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
for medal, rank in medals.items():
    idx = verdict.find(medal)
    if idx < 0: continue
    
    end_idx = len(verdict)
    for other_medal in medals:
        if other_medal == medal: continue
        other_idx = verdict.find(other_medal, idx + 1)
        if 0 < other_idx < end_idx: end_idx = other_idx
        
    block = verdict[idx:end_idx]
    hn_m = re.search(r'馬號[及與]?馬名[：:]\s*\*{0,2}\s*\[?(\d+)\]?\s+(.+?)(?:\n|$)', block)
    print(medal, "match:", hn_m.groups() if hn_m else "None")
