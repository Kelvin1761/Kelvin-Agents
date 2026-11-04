"""HKJC ROI 分項用嘅賽事資料（Kelvin 2026-11-05）。

App 記錄嘅注單（D1 ledger）只有日期、馬場、場次、馬號、賠率、結果，冇路程、班次、賽道、
騎師、練馬師，所以 ROI 頁嘅分項表一直只計舊 snapshot（2026-07 之前）。呢度由每個 HKJC
場次嘅 `Race_N_Logic.json` 抽返嗰五樣嘢，放入 snapshot，等頁面可以喺瀏覽器配對任何注單。

格式（壓縮，因為成個 snapshot 會俾手機下載）：
    {"2026-11-04|happyvalley|1": {"d": "1000", "c": "第五班", "v": "跑馬地", "t": "草地 A",
                                  "h": {"7": ["周俊樂", "沈集成"], ...}}}
馬場 key = 英文場名去空格細階（ledger 用 HappyValley，舊 snapshot 用 Happy Valley）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_MEETING = re.compile(r"^(\d{4}-\d{2}-\d{2})_(ShaTin|HappyValley|Sha_Tin|Happy_Valley)", re.I)
_RACE = re.compile(r"Race_(\d+)_Logic\.json$")
_VENUE_ZH = {"shatin": "沙田", "happyvalley": "跑馬地"}


def venue_key(name: str) -> str:
    text = re.sub(r"[\s_]+", "", str(name or "")).lower()
    if text in ("沙田", "st"):
        return "shatin"
    if text in ("跑馬地", "hv"):
        return "happyvalley"
    return text


def _track(analysis: dict) -> str:
    surface = " ".join(str(analysis.get(k) or "") for k in ("track", "surface", "course_type"))
    if re.search(r"AWT|全天候|泥地", surface, re.I):
        return "全天候"
    rail = str(analysis.get("rail") or analysis.get("course") or "").strip().strip('"')
    if re.fullmatch(r"[ABC](\+\d)?", rail):
        return f"草地 {rail}"
    return "草地" if re.search(r"turf|草地", surface, re.I) else ""


_CLASS_NUM = {"1": "第一班", "2": "第二班", "3": "第三班", "4": "第四班", "5": "第五班"}
_GROUP = {"1": "一級賽", "2": "二級賽", "3": "三級賽"}


def race_class(text: str) -> str:
    """C4／Class 4／第四班（條件限制）→ 第四班；G1／Group 1／一級賽 → 一級賽；GR／Griffin → 新馬賽。"""
    t = str(text or "").strip()
    if not t:
        return ""
    m = re.match(r"^(?:C|Class\s*)([1-5])$", t, re.I)
    if m:
        return _CLASS_NUM[m.group(1)]
    m = re.match(r"^(?:G|Group\s*)([1-3])$", t, re.I) or re.match(r"^([一二三])級賽", t)
    if m:
        g = m.group(1)
        return _GROUP.get(g) or {"一": "一級賽", "二": "二級賽", "三": "三級賽"}[g]
    if re.match(r"^(GR|Griffin|新馬)", t, re.I):
        return "新馬賽"
    m = re.match(r"^第([一二三四五])班", t)
    if m:
        return f"第{m.group(1)}班"
    if t in _CLASS_NUM:
        return _CLASS_NUM[t]
    return ""          # 「[FILL]」、標題殘留之類嘅壞值當未知，唔好變成一行分項


def _card_track(meeting: Path, race_number: int) -> str:
    """舊 Logic 冇 track／rail：由排位表「場地: 草地」「賽道: C 賽道」補。"""
    for card in meeting.glob(f"* Race {race_number} 排位表.md"):
        try:
            head = card.read_text(encoding="utf-8")[:1500]
        except OSError:
            return ""
        surface = re.search(r"^場地[:：]\s*(\S+)", head, re.M)
        rail = re.search(r"^賽道[:：]\s*\"?([ABC](?:\+\d)?)", head, re.M)
        return _track({"track": surface.group(1) if surface else "",
                       "rail": rail.group(1) if rail else ""})
    return ""


def build_race_meta(hk_root: Path) -> dict:
    meta = {}
    for meeting in sorted(Path(hk_root).iterdir()) if Path(hk_root).is_dir() else []:
        m = _MEETING.match(meeting.name)
        if not m or not meeting.is_dir():
            continue
        date, vkey = m.group(1), venue_key(m.group(2))
        for logic in meeting.glob("Race_*_Logic.json"):
            rn = _RACE.search(logic.name)
            if not rn:
                continue
            try:
                payload = json.loads(logic.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            analysis = payload.get("race_analysis") or {}
            distance = re.search(r"\d{3,4}", str(analysis.get("distance") or ""))
            horses = {}
            for number, horse in (payload.get("horses") or {}).items():
                if isinstance(horse, dict):
                    horses[str(number)] = [str(horse.get("jockey") or "").strip(),
                                           str(horse.get("trainer") or "").strip()]
            race_number = int(rn.group(1))
            meta[f"{date}|{vkey}|{race_number}"] = {
                "d": distance.group() if distance else "",
                "c": race_class(analysis.get("race_class")),
                "v": _VENUE_ZH.get(vkey, ""),
                "t": _track(analysis) or _card_track(meeting, race_number),
                "h": horses,
            }
    return meta


def export_race_meta(repo_root: Path) -> dict:
    import sys
    sys.path.insert(0, str(Path(repo_root)))
    try:
        from wongchoi_paths import HK_RACING
    finally:
        sys.path.remove(str(Path(repo_root)))
    return build_race_meta(Path(HK_RACING))
