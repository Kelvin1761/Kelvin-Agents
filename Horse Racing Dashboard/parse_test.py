import re

text = "**【No.1】 顏色之皇** | 騎師:潘頓 | 練馬師:游達榮 | 負磅:135 | 檔位:12"

HORSE_HEADER_NEW_RE = re.compile(
    r'^\*{0,2}【No\.(\d+)】\s*(.+?)\*{0,2}\s*\|',
    re.MULTILINE
)

print(HORSE_HEADER_NEW_RE.findall(text))
