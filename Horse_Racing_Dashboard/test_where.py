import sys
sys.path.append('backend')
from services.parser_au import _extract_section
with open("../2026-04-02 Gosford Race 1-7/2026-04-02_Gosford_Race_7_Analysis.md", "r") as f:
    verdict = _extract_section(f.read(), ['🏆 全場最終決策'], ['[第四部分]'])
print("🥇 1:", verdict.find('🥇'))
print("🥇 2:", verdict.find('🥇', verdict.find('🥇')+1))
print("🥇 3:", verdict.find('🥇', verdict.find('🥇', verdict.find('🥇')+1)+1))
print("🥈 1:", verdict.find('🥈'))
print("🥉 1:", verdict.find('🥉'))
print("🏅 1:", verdict.find('🏅'))
