import sys
sys.path.append('backend')
from services.parser_au import _parse_au_verdict_picks, _extract_section
import json

class StructEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        elif hasattr(obj, 'dict'):
            return obj.dict()
        return super().default(obj)

with open("../2026-04-02 Gosford Race 1-7/2026-04-02_Gosford_Race_7_Analysis.md", "r") as f:
    text = f.read()

verdict = _extract_section(text,
    ['🏆 全場最終決策', '🏆 Top 3', '🏆 Top 4', '[第三部分]',
     'Top 4 位置精選', 'Top 3 位置精選', 'Top 4 精選排名', '精選排名'],
    ['[第四部分]', '🔒 COMPLIANCE', '```csv']
)
print("VERDICT:", verdict[:500])

picks = _parse_au_verdict_picks(verdict)
print("PICKS:", json.dumps(picks, cls=StructEncoder, ensure_ascii=False))
