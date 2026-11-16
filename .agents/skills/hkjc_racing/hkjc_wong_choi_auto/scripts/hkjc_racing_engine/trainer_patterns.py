"""個別練馬師出擊 pattern（EXP-20261115-20；Kelvin 2026-11-15「加唔到分但幫我搵晒出嚟加 label」）—— 純顯示，唔入分。

表：resources/hkjc_trainer_patterns.json（docs/experiments/patches/hkjc_trainer_patterns/pick_cells.py 生成）。
揀選：2020/21–2025/26 回放殘差（對 live 現行模型），n ≥ 80、|殘差| ≥ 5pp、CI 唔跨零、前後兩段同號各 ≥ 2pp；239 格揀出 19 格
（嚴格條件下估計仍有 ~3 格係撞彩）。live 判斷用 Logic／排位表欄位（配備用排位表 HKJC 代碼：1 = 首次、- = 除去）。
"""
from __future__ import annotations

import json
import re

from . import gear
from datetime import date, datetime
from pathlib import Path

NAMES = {"gear_removed": "除去配備", "gear_first": "首次配備", "last_close_2nd_3rd": "上仗二三名貼近", "quick_backup14": "14 日內再出",
         "layoff90": "休息 ≥90 日", "rest60": "休息 ≥60 日", "dist_up200": "加程 ≥200 米", "dist_down200": "減程 ≥200 米",
         "classdrop_jchange": "降班＋換騎", "third_up": "復出第三仗"}
_TABLE: dict | None = None
_CLOSE = {"鼻": 0.05, "短頭": 0.1, "頭": 0.2, "頸": 0.3}


def table() -> dict:
    global _TABLE
    if _TABLE is None:
        p = Path(__file__).resolve().parents[2] / "resources" / "hkjc_trainer_patterns.json"
        cells = json.loads(p.read_text(encoding="utf-8")).get("cells", []) if p.exists() else []
        _TABLE = {(c["trainer"], c["pattern"]): c for c in cells}
    return _TABLE


def _lengths(text) -> float | None:
    t = str(text or "").strip()
    if t in _CLOSE:
        return _CLOSE[t]
    m = re.fullmatch(r"(?:(\d+)-)?(\d+)/(\d+)|(\d+)", t)
    if not m:
        return None
    if m.group(4):
        return float(m.group(4))
    return float(m.group(1) or 0) + float(m.group(2)) / float(m.group(3))


def patterns(horse: dict, race_class, distance, gear_codes: list[str]) -> set[str]:
    from .form_patterns import class_no
    d = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    out = set()
    if gear.removed(gear_codes):
        out.add("gear_removed")
    if gear.first(gear_codes):
        out.add("gear_first")
    try:
        lf = int(str(d.get("last_finish") or "").strip())
    except ValueError:
        lf = None
    ln = _lengths(d.get("last_margin"))
    if lf in (2, 3) and ln is not None and ln <= 1.25:
        out.add("last_close_2nd_3rd")
    try:
        gap = int(str(d.get("days_since_last") or "").strip())
    except ValueError:
        gap = None
    if gap is not None:
        if gap <= 14:
            out.add("quick_backup14")
        if gap >= 60:
            out.add("rest60")
        if gap >= 90:
            out.add("layoff90")
    last = d.get("l400_last_run") if isinstance(d.get("l400_last_run"), dict) else {}
    if last.get("distance") and distance:
        if distance - int(last["distance"]) >= 200:
            out.add("dist_up200")
        if int(last["distance"]) - distance >= 200:
            out.add("dist_down200")
    m = re.match(r"第1仗\([^)]*?(第[一二三四五]班)", str(d.get("recent_6_detail") or ""))
    tc, lc = class_no(race_class), (class_no(m.group(1)) if m else None)
    if tc and lc and tc > lc and str(d.get("jockey_change_note") or "").strip():
        out.add("classdrop_jchange")
    dates = []
    for s in re.findall(r"第\d仗\((\d{2}/\d{2}/\d{4})", str(d.get("recent_6_detail") or "")):
        try:
            dates.append(datetime.strptime(s, "%d/%m/%Y").date())
        except ValueError:
            pass
    if gap is not None and gap < 90 and len(dates) >= 3 and (dates[0] - dates[1]).days < 90 and (dates[1] - dates[2]).days >= 90:
        out.add("third_up")
    return out


def matches(horse: dict, race_class, distance, gear_codes: list[str]) -> list[dict]:
    trainer = str(horse.get("trainer") or "").strip()
    t = table()
    hits = [p for p in sorted(patterns(horse, race_class, distance, gear_codes)) if (trainer, p) in t]
    if "layoff90" in hits and "rest60" in hits:      # 同一件事（休息），只出較嚴嗰個
        hits.remove("rest60")
    return [t[(trainer, p)] for p in hits]
