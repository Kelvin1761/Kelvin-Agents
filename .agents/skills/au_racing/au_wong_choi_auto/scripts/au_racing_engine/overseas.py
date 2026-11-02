"""海外往績嘅班次標籤（EXP-20261102-11，§7 正確性修正）。

Sportsbet 將英國、愛爾蘭、香港、法國嘅班次照當地寫法印 `CL1`…`CL6`。喺嗰啲地方 **Class 1 係最高**
（英愛 Class 1 = Group／Listed；香港 Class 1 = 最高評分組），但澳洲 Class 1 係最低。引擎一直當澳洲標籤讀：
`exact_race_class_level("CL1")` = 62、`race_class_tier` = 7（最低），即係 Royal Ascot、Curragh 嘅 Group 馬
被當成鄉鎮 Class 1。2026-10-17 Caulfield Cup：Enfjaar（6 場英國）模型排 12，跑第 3。

修法：海外往績嘅 `CLn` 先換成澳洲對等標籤，再交返原本兩個函數（數值階梯唔郁）：

    CL1 → LR（82）  CL2 → BM88  CL3 → BM80  CL4 → BM72  CL5 → BM64  CL6 → BM56

對應係固定判斷（冇用賽果擬合）：Class 1 混合 Group／Listed，保守當 Listed；其餘按每級約 8 分落。
邊條係海外往績：場地喺下面清單；同名澳洲場地（Ascot、Sandown、Newcastle、Hamilton…）只喺匹馬另有
明確海外往績先當海外。紐西蘭用澳洲式標籤，唔使轉。
"""
from __future__ import annotations

import re

OVERSEAS_VENUES = frozenset(v.lower() for v in (
    # 英國
    "Royal Ascot", "Newmarket", "Goodwood", "Epsom", "Newbury", "Kempton", "Haydock", "Chester", "Lingfield",
    "Windsor", "Leicester", "Nottingham", "Salisbury", "Ripon", "Thirsk", "Beverley", "Pontefract", "Carlisle",
    "Musselburgh", "Redcar", "Catterick", "Wolverhampton", "Southwell", "Chelmsford", "Chelmsford City",
    "Brighton", "Yarmouth", "Great Yarmouth", "Ffos Las", "Chepstow", "Doncaster", "Bath", "Leopardstown",
    # 愛爾蘭
    "Curragh", "The Curragh", "Galway", "Listowel", "Roscommon", "Gowran Park", "Navan", "Naas", "Dundalk",
    "Fairyhouse", "Punchestown", "Cork", "Limerick", "Killarney", "Tipperary", "Tramore", "Bellewstown",
    "Down Royal", "Sligo", "Ballinrobe", "Kilbeggan", "Laytown", "Wexford", "Thurles", "Clonmel",
    # 香港
    "Sha Tin", "Happy Valley",
    # 法國
    "Longchamp", "ParisLongchamp", "Chantilly", "Deauville", "Saint-Cloud", "Saint Cloud",
))
# 澳洲都有同名場地：要匹馬另有明確海外往績先當海外。
AMBIGUOUS_VENUES = frozenset(v.lower() for v in ("Ascot", "Sandown", "Newcastle", "Hamilton", "York", "Ayr", "Warwick"))

CLASS_EQUIVALENT = {1: "LR", 2: "BM88", 3: "BM80", 4: "BM72", 5: "BM64", 6: "BM56"}
_CLASS_RE = re.compile(r"\b(?:CLASS|CL|C)\s*([1-6])\b", re.I)


def venue_name(cell):
    """Facts 場地格（`Royal Ascot R6`、`Pakenham Synthetic **(TRIAL)** R1`）→ 場地名（細楷）。"""
    text = re.sub(r"\*\*.*?\*\*", "", str(cell or ""))
    return re.sub(r"\s+R\d+\s*$", "", text).strip().lower()


def horse_has_overseas(venues):
    return any(v in OVERSEAS_VENUES for v in venues)


def is_overseas(venue, horse_overseas):
    return venue in OVERSEAS_VENUES or (horse_overseas and venue in AMBIGUOUS_VENUES)


def normalise_class(label, venue, horse_overseas):
    """海外往績嘅 `CLn` → 澳洲對等標籤；其他原封不動。"""
    if not label or not is_overseas(venue, horse_overseas):
        return label
    m = _CLASS_RE.search(str(label))
    return CLASS_EQUIVALENT[int(m.group(1))] if m else label
