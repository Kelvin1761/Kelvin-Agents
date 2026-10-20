"""HKJC 官方「傷患記錄」頁 → 逐匹馬傷患記錄。

來源：每個賽日資料夾嘅 `MM-DD 全日出賽馬匹資料 (PDF).md`（賽會賽前發佈嘅出賽馬匹資料）。

點解要有呢個（2026-10-20）：`medical_flags` 只係喺近仗**賽事短評**入面搵關鍵字，兩仗之間
喺馬房做嘅手術／受傷永遠唔會出現，搵唔到就當「✅ 無醫療事故記錄」。例：10-21 跑馬地 R5
超強六十 07-16 做咗左前球節關節鏡手術，Logic 照寫無醫療事故。呢頁係賽會自己列嘅官方記錄。

格式（每行一匹，場次只喺該場第一行出現，之後沿用）：
    場次 馬號 馬名 烙印編號 日期 詳情 通過日期
    5 5 豐勝多彩 L324 18/06/2026 試閘時表現欠佳 18/09/2026
    10 超強六十 J071 16/07/2026 左前球節接受關節鏡手術（移除碎骨） 06/10/2026
    2 後備 2 電訊驕陽 J332 23/09/2026 賽後內窺鏡檢查發現氣管內有大量血液 09/10/2026
「其他傷患記錄」節冇通過日期。

Point-in-time：只收事故日期早過賽日、通過日期唔遲過賽日嘅記錄。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

_ROW = re.compile(
    r"^(?:(?P<race>\d{1,2})\s+)?"
    r"(?P<horse>後備\s*\d{1,2}|\d{1,2})\s+"
    r"(?P<name>\S+)\s+(?P<brand>[A-Z]\d{3})\s+"
    r"(?P<inc>\d{2}/\d{2}/\d{4})\s+(?P<detail>.+?)"
    r"(?:\s+(?P<passed>\d{2}/\d{2}/\d{4}))?\s*$"
)
# 呢類係賽後／試閘後嘅表現覆檢，唔係傷患（顯示照列，計分唔當醫療事故）。
PERFORMANCE_ONLY = re.compile(r"表現(?:令人失望|難以接受|欠佳|未如理想)|試閘時表現|並無出賽")
MEDICAL = re.compile(r"血|傷|跛|不良於行|手術|心律|心臟|絞痛|骨|肌腱|蹄|呼吸|喉|發燒|感染|不適|腫|獸醫")
# 同一匹馬第二條記錄（冇馬號／馬名／烙印）：「24/10/2025 未能通過獸醫檢驗：… 12/03/2026」
_EXTRA = re.compile(r"^(?P<inc>\d{2}/\d{2}/\d{4})\s+(?P<detail>.+?)(?:\s+(?P<passed>\d{2}/\d{2}/\d{4}))?\s*$")


def _iso(text):
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def read_text(path: Path) -> str:
    raw = Path(path).read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", "replace")


def parse_injury_page(text: str) -> list[dict]:
    """全份 PDF markdown → 傷患記錄 list（未做 point-in-time 過濾）。"""
    records = []
    section = None
    race = None
    for line in text.splitlines():
        s = line.strip()
        if s == "傷患記錄":
            section, race = "main", None
            continue
        if s.startswith("其他傷患記錄"):
            section, race = "other", None
            continue
        if section and (s.startswith("由香港賽馬會") or s.startswith("## --- PAGE")):
            section = None
            continue
        if not section or not s or s.startswith("場次") or s.startswith("Race"):
            continue
        m = _ROW.match(s)
        if m:
            if m.group("race"):
                race = int(m.group("race"))
            records.append({
                "race": race,
                "horse_no": re.sub(r"\s+", "", m.group("horse")),
                "name": m.group("name"),
                "brand": m.group("brand"),
                "incident_date": _iso(m.group("inc")),
                "detail": m.group("detail").strip(),
                "passed_date": _iso(m.group("passed")) if m.group("passed") else None,
                "section": section,
            })
            continue
        if not records or records[-1]["section"] != section:
            continue
        extra = _EXTRA.match(s)
        if extra:  # same horse, another incident
            prev = records[-1]
            records.append({**{k: prev[k] for k in ("race", "horse_no", "name", "brand", "section")},
                            "incident_date": _iso(extra.group("inc")),
                            "detail": extra.group("detail").strip(),
                            "passed_date": _iso(extra.group("passed")) if extra.group("passed") else None})
            continue
        # wrapped detail: the PDF breaks long 詳情 onto the next line
        tail = re.match(r"^(?P<text>.*?)\s*(?P<passed>\d{2}/\d{2}/\d{4})$", s)
        if tail and records[-1]["passed_date"] is None:
            records[-1]["detail"] += tail.group("text")
            records[-1]["passed_date"] = _iso(tail.group("passed"))
        else:
            records[-1]["detail"] += s
    unique, seen = [], set()
    for rec in records:
        key = (rec["name"], rec["incident_date"], rec["detail"])
        if key in seen:
            continue
        seen.add(key)
        # 「表現令人失望，賽後內窺鏡檢查發現氣管內有大量血液」係流血，唔係淨表現
        rec["performance_only"] = bool(PERFORMANCE_ONLY.search(rec["detail"])) and not MEDICAL.search(rec["detail"])
        unique.append(rec)
    return unique


def records_as_of(records: list[dict], race_day: date) -> list[dict]:
    """Point-in-time：事故早過賽日，通過日期（如有）唔遲過賽日。"""
    out = []
    for rec in records:
        inc = rec.get("incident_date")
        passed = rec.get("passed_date")
        if inc is None or inc >= race_day:
            continue
        if passed is not None and passed > race_day:
            continue
        out.append(rec)
    return out


def pdf_path_for_meeting(meeting_dir: Path) -> Path | None:
    hits = sorted(Path(meeting_dir).glob("*全日出賽馬匹資料*.md"))
    return hits[0] if hits else None


def injury_records_for_meeting(meeting_dir: Path, race_day: date) -> dict[str, list[dict]]:
    """馬名 → JSON-safe 記錄（point-in-time 過濾後）。冇 PDF ＝ {}。"""
    path = pdf_path_for_meeting(meeting_dir)
    if path is None:
        return {}
    out: dict[str, list[dict]] = {}
    for rec in records_as_of(parse_injury_page(read_text(path)), race_day):
        out.setdefault(rec["name"], []).append({
            "race": rec["race"],
            "incident_date": rec["incident_date"].isoformat(),
            "detail": rec["detail"],
            "passed_date": rec["passed_date"].isoformat() if rec["passed_date"] else None,
            "section": rec["section"],
            "performance_only": rec["performance_only"],
        })
    return out
