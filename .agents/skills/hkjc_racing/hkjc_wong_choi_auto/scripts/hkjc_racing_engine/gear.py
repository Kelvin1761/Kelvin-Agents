"""HKJC 配備：代碼、中文名、首次／除去判斷（全 Wong Choi 只有呢一份；Kelvin 2026-11-16「一樣嘢只准一個標準」）。

排位表代碼：字母 = 配備；尾綴 1 = 首次戴、2 = 再戴、- = 除去。
"""
from __future__ import annotations

import re

GEAR_NAMES = {
    "B": "眼罩", "BO": "單邊眼罩", "CP": "羊毛面箍", "CC": "頸箍",
    "E": "耳塞", "H": "頭罩", "P": "防沙眼罩", "PC": "半掩防沙眼罩",
    "SR": "鼻箍", "SB": "羊毛額箍", "TT": "繫舌帶", "V": "開縫眼罩",
    "VO": "單邊開縫眼罩", "XB": "交叉鼻繃",
}


def base(code: str) -> str:
    return re.sub(r"[\d\-]+$", "", str(code or "").upper().strip())


def name(code: str) -> str:
    b = base(code)
    return GEAR_NAMES.get(b, b or str(code))


def removed(codes) -> list[str]:
    return [c for c in codes or [] if str(c).strip().endswith("-")]


def first(codes) -> list[str]:
    return [c for c in codes or [] if re.fullmatch(r"[A-Z]+1", str(c).strip().upper())]
