import sys
sys.path.append('backend')
from services.parser_au import _parse_au_verdict_picks
import json

class StructEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

block = """
🥇 **第一選**
- **馬號及馬名：** 3 Zing To Me
- **📗 評級：** `[S-]` | ✅ 7
- **核心理據：** 泥地及草地皆交出上佳水準...
- **最大風險：** 直路受困或轉彎大外疊蝕位。

🥈 **第二選**
- **馬號及馬名：** 7 Honey Perfume
- **📗 評級：** `[S-]` | ✅ 6
- **核心理據：** 擁有全場最佳之軟地往績...

🥉 **第三選**
- **馬號及馬名：** 8 Fine Wine
- **📗 評級：** `[A+]` | ✅ 6

🏅 **第四選**
- **馬號及馬名：** 2 Cool Storm
- **📗 評級：** `[A-]` | ✅ 5
"""

picks = _parse_au_verdict_picks(block)
print(json.dumps(picks, cls=StructEncoder, ensure_ascii=False))
