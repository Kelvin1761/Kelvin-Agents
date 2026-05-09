#!/usr/bin/env python3
from __future__ import annotations

import os
os.environ.setdefault("PYTHONUTF8", "1")
"""
extract_trackwork.py — HKJC trackwork extractor (fail-soft MVP)

Fetches HKJC local trackwork pages and writes per-race JSON/Markdown summaries.
The output is intentionally a Python pre-digest for Logic.json, not a direct
rating score. If HKJC pages are unavailable or the DOM changes, the script exits
non-zero unless --fail-soft is used.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


HKJC_BASE = "https://racing.hkjc.com"
USER_AGENT = "Mozilla/5.0 Antigravity-HKJC-Trackwork/1.0"


class TableParser(HTMLParser):
    """Small table parser that keeps row/cell text plus hrefs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._in_tr = False
        self._in_cell = False
        self._cells: list[str] = []
        self._cell_links: list[list[dict[str, str]]] = []
        self._cell_text: list[str] = []
        self._links: list[dict[str, str]] = []
        self._href: str | None = None
        self._href_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = {k.lower(): v or "" for k, v in attrs}
        if tag.lower() == "tr":
            self._in_tr = True
            self._cells = []
            self._cell_links = []
        elif self._in_tr and tag.lower() in ("td", "th"):
            self._in_cell = True
            self._cell_text = []
            self._links = []
        elif self._in_cell and tag.lower() == "a":
            self._href = attrs_d.get("href", "")
            self._href_text = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_text.append(data)
        if self._href is not None:
            self._href_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._in_cell and tag == "a":
            self._links.append({
                "href": self._href or "",
                "text": clean_text("".join(self._href_text)),
            })
            self._href = None
            self._href_text = []
        elif self._in_tr and self._in_cell and tag in ("td", "th"):
            self._cells.append(clean_text(" ".join(self._cell_text)))
            self._cell_links.append(self._links)
            self._in_cell = False
        elif self._in_tr and tag == "tr":
            if self._cells:
                self.rows.append({"cells": self._cells, "links": self._cell_links})
            self._in_tr = False


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    return value


def fetch_url(url: str, timeout: int = 20, retries: int = 2) -> str:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except Exception as exc:  # noqa: BLE001 - fail-soft CLI reports message
            last_err = exc
            if attempt < retries:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"fetch failed: {url} ({last_err})")


def parse_races(value: str | None) -> list[int]:
    if not value:
        return [1]
    races: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            races.extend(range(int(a), int(b) + 1))
        else:
            races.append(int(part))
    return sorted(set(races))


def parse_base_url(value: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(value)
    qs = urllib.parse.parse_qs(parsed.query)
    return {
        "racedate": (qs.get("racedate") or qs.get("RaceDate") or [""])[0],
        "racecourse": (qs.get("Racecourse") or qs.get("racecourse") or [""])[0],
        "race_no": (qs.get("RaceNo") or qs.get("raceno") or [""])[0],
    }


def localtrackwork_url(racedate: str, racecourse: str, race_no: int) -> str:
    qs = urllib.parse.urlencode({
        "racedate": racedate,
        "Racecourse": racecourse,
        "RaceNo": str(race_no),
    })
    return f"{HKJC_BASE}/zh-hk/local/information/localtrackwork?{qs}"


def normalize_racecourse(value: str, output_dir: Path | None = None) -> str:
    """Return HKJC racecourse code, inferring from the meeting folder if needed."""
    raw = clean_text(value).upper()
    if raw in {"ST", "HV"}:
        return raw
    if raw in {"SHATIN", "SHA TIN", "SHA_TIN", "沙田"}:
        return "ST"
    if raw in {"HAPPYVALLEY", "HAPPY VALLEY", "HAPPY_VALLEY", "跑馬地"}:
        return "HV"
    folder = str(output_dir or "")
    if re.search(r"shatin|sha[_\s-]?tin|沙田", folder, re.IGNORECASE):
        return "ST"
    if re.search(r"happy[_\s-]?valley|跑馬地", folder, re.IGNORECASE):
        return "HV"
    return raw


def trackworkresult_url(horseid: str) -> str:
    qs = urllib.parse.urlencode({"horseid": horseid})
    return f"{HKJC_BASE}/zh-hk/local/information/trackworkresult?{qs}"


def brand_to_horseid(brand: str) -> str:
    brand = clean_text(brand).upper()
    m = re.match(r"([A-Z])(\d{3})", brand)
    if not m:
        return ""
    letter, num = m.groups()
    year_map = {
        "A": 2016, "B": 2017, "C": 2018, "D": 2019, "E": 2020,
        "G": 2021, "H": 2022, "J": 2023, "K": 2024, "L": 2025,
    }
    year = year_map.get(letter)
    return f"HK_{year}_{letter}{num}" if year else ""


def parse_racecard_horse_list(output_dir: Path, race_no: int) -> list[dict[str, Any]]:
    """Build exact race horse list from local racecard to avoid localtrackwork row drift."""
    candidates = sorted(output_dir.glob(f"* Race {race_no} 排位表.md"))
    if not candidates:
        return []
    text = candidates[0].read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=馬號:\s*\d+)", text)
    horses: list[dict[str, Any]] = []
    for block in blocks:
        no_m = re.search(r"馬號:\s*(\d+)", block)
        name_m = re.search(r"馬名:\s*(.+)", block)
        brand_m = re.search(r"烙號:\s*([A-Z]\d{3})", block)
        trainer_m = re.search(r"練馬師:\s*(.+)", block)
        jockey_m = re.search(r"騎師:\s*(.+)", block)
        if not (no_m and name_m and brand_m):
            continue
        horseid = brand_to_horseid(brand_m.group(1))
        if not horseid:
            continue
        horses.append({
            "horse_no": int(no_m.group(1)),
            "horseid": horseid,
            "horse_name": clean_text(name_m.group(1)),
            "trainer": clean_text(trainer_m.group(1)) if trainer_m else "",
            "jockey": clean_text(jockey_m.group(1)) if jockey_m else "",
            "source": "racecard",
        })
    return sorted(horses, key=lambda h: h["horse_no"])


def parse_date(value: str) -> dt.date | None:
    value = clean_text(value)
    for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_meeting_date(value: str) -> dt.date | None:
    return parse_date(value)


def parse_horse_list(page_html: str) -> list[dict[str, Any]]:
    parser = TableParser()
    parser.feed(page_html)
    horses: list[dict[str, Any]] = []
    seen: set[str] = set()
    fallback_no = 1
    for row in parser.rows:
        cells = row["cells"]
        links_flat = [link for cell_links in row["links"] for link in cell_links]
        horse_links = [l for l in links_flat if "horseid=" in l.get("href", "")]
        if not horse_links:
            continue
        href = horse_links[0]["href"]
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        horseid = (qs.get("horseid") or qs.get("HorseId") or [""])[0]
        if not horseid or horseid in seen:
            continue
        seen.add(horseid)
        horse_no = None
        for cell in cells[:3]:
            m = re.search(r"\b(\d{1,2})\b", cell)
            if m:
                horse_no = int(m.group(1))
                break
        if horse_no is None:
            horse_no = fallback_no
        fallback_no = max(fallback_no, horse_no + 1)
        name = horse_links[0].get("text") or ""
        if not name:
            name = next((c for c in cells if re.search(r"[\u4e00-\u9fffA-Za-z]", c)), "")
        trainer = cells[-1] if len(cells) >= 4 else ""
        horses.append({
            "horse_no": horse_no,
            "horseid": horseid,
            "horse_name": name,
            "trainer": trainer,
            "source_cells": cells,
        })
    return sorted(horses, key=lambda h: h["horse_no"])


def normalize_work_type(value: str, details: str = "") -> str:
    text = f"{value} {details}".lower()
    zh = f"{value} {details}"
    if "試閘" in zh or "trial" in text:
        return "trial"
    if any(k in zh for k in ("快操", "快跳", "拍跳")) or "gallop" in text:
        return "gallop"
    if "踱步" in zh or "trot" in text:
        return "trotting"
    if "游" in zh or "swim" in text:
        return "swimming"
    if "水中" in zh or "aqua" in text:
        return "aqua_walker"
    if "跑步機" in zh or "treadmill" in text:
        return "treadmill"
    return "other"


def extract_times(details: str) -> list[float]:
    values: list[float] = []
    # Avoid obvious distances like 800m/1200m by requiring decimal seconds.
    for m in re.finditer(r"(?<!\d)(\d{2,3}\.\d)(?!\d)", details):
        val = float(m.group(1))
        if 10.0 <= val <= 140.0:
            values.append(val)
    return values


def parse_trackwork_rows(page_html: str, horse: dict[str, Any],
                         meeting_date: dt.date | None,
                         window_days: int) -> list[dict[str, Any]]:
    parser = TableParser()
    parser.feed(page_html)
    entries: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = row["cells"]
        if len(cells) < 3:
            continue
        date = parse_date(cells[0])
        if not date:
            continue
        if meeting_date and (meeting_date - date).days > window_days:
            continue
        if meeting_date and date > meeting_date:
            continue
        work_type_raw = cells[1] if len(cells) > 1 else ""
        location = cells[2] if len(cells) > 2 else ""
        details = cells[3] if len(cells) > 3 else " ".join(cells[1:])
        gear = cells[4] if len(cells) > 4 else ""
        work_type = normalize_work_type(work_type_raw, details)
        entries.append({
            "date": date.isoformat(),
            "type": work_type,
            "type_raw": work_type_raw,
            "location": location,
            "details": details,
            "gear": gear,
            "times": extract_times(details),
            "rider": detect_rider(details),
            "rider_role": classify_rider_role(detect_rider(details), details, horse.get("trainer", "")),
        })
    return sorted(entries, key=lambda e: e["date"])


def detect_rider(details: str) -> str:
    """Extract the named person from details.

    Handles multiple HKJC patterns:
    - 試閘/草地操: '第9組 (潘明輝) 1200M ...' → 潘明輝
    - 距離+騎者:  '1200M (奧爾民) (5/11)' → 奧爾民
    - 策騎語法:   '由班德禮策騎' → 班德禮
    - 末尾括號:   '29.9 27.3 (57.2) (班德禮)' → 班德禮
    - 操練身份:   '內圈 快踱一圈 (助手)' → 助手
    """
    # Pattern 1: trial/gallop group — 第N組 (NAME) DISTANCE
    m_group = re.search(r'第\d+組\s*\(([\u4e00-\u9fffA-Za-z .\'"-]{2,20})\)', details)
    if m_group:
        return clean_text(m_group.group(1))
    # Pattern 2: distance + rider — 1200M (NAME)
    m_dist = re.search(r'\d{3,4}M\s*\(([\u4e00-\u9fffA-Za-z .\'"-]{2,20})\)', details)
    if m_dist:
        return clean_text(m_dist.group(1))
    # Pattern 3: explicit 由/策騎/騎者
    m_verb = re.search(r"(?:由|策騎|騎者[:：]?)\s*([\u4e00-\u9fffA-Za-z .'-]{2,30})", details)
    if m_verb:
        return clean_text(m_verb.group(1))
    # Pattern 4: last parenthesized name (skip times like (57.2) or (1.09.99))
    parens = re.findall(r'\(([\u4e00-\u9fffA-Za-z .\'"-]{2,20})\)', details)
    for p in reversed(parens):
        # Skip if it looks like a time (digits and dots only)
        if re.match(r'^[\d.]+$', p.strip()):
            continue
        # Skip if it looks like a position fraction like 5/11
        if re.match(r'^\d+/\d+$', p.strip()):
            continue
        return clean_text(p)
    return ""


def normalize_person_name(value: str) -> str:
    """Normalize HKJC Chinese/English names for direct rider matching."""
    value = clean_text(value)
    return re.sub(r"[\s·・.\-']", "", value).lower()


def classify_rider_role(rider: str, details: str, trainer: str = "") -> str:
    """Classify rider into: 助手 / 副練馬師 / 練馬師 / 騎師(named) / 未標明."""
    text = clean_text(f"{details} {rider}")
    # Priority 1: explicit 副練馬師
    if "副練馬師" in text or "副練" in text:
        return "副練馬師"
    # Priority 2: explicit 助手
    if any(k in text for k in ("助手", "助理", "策騎員", "騎馬人", "work rider", "assistant")):
        return "助手"
    # Priority 3: 練馬師 himself
    if trainer and rider and (rider == trainer or rider in trainer or trainer in rider):
        return "練馬師"
    if "練馬師" in text or "trainer" in text.lower():
        return "練馬師"
    # Priority 4: named person (likely jockey or other)
    if rider:
        return rider
    return "未標明"


def zh_status(value: str) -> str:
    return {
        "ok": "已提取",
        "partial": "部分提取",
        "missing": "缺資料",
        "failed": "提取失敗",
    }.get(str(value), str(value))


def zh_category(value: str) -> str:
    return {
        "status_continuity": "狀態延續",
        "pattern_replay": "翻案復刻",
        "debut_pressure": "初出備戰",
        "insufficient_data": "資料不足",
    }.get(str(value), str(value))


def zh_trend(value: str) -> str:
    return {
        "improving": "操練加壓中",
        "stable": "操練穩定",
        "easing": "操練放緩",
        "interrupted": "操練中斷",
        "unknown": "未明",
    }.get(str(value), str(value))


def zh_confidence(value: str) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
    }.get(str(value).lower(), str(value))


def zh_work_type(value: str) -> str:
    return {
        "gallop": "快操",
        "trial": "試閘",
        "trotting": "踱步",
        "swimming": "游水",
        "aqua_walker": "水中步行機",
        "treadmill": "跑步機",
        "other": "其他",
    }.get(str(value), str(value))


def band_count(n: int) -> str:
    if n <= 0:
        return "0"
    if n == 1:
        return "1"
    if n <= 3:
        return "2-3"
    return "4+"


def classify_trend(gallop_times: list[float], active_days: int, blank_days: int) -> str:
    if blank_days >= 10:
        return "interrupted"
    if len(gallop_times) < 2:
        return "unknown"
    first, last = gallop_times[0], gallop_times[-1]
    if last <= first - 0.5:
        return "improving"
    if last >= first + 0.8:
        return "easing"
    return "stable"


def make_digest(horse: dict[str, Any], entries: list[dict[str, Any]],
                window_days: int, race_jockey: str = "") -> dict[str, Any]:
    counts = {
        "gallops": sum(1 for e in entries if e["type"] == "gallop"),
        "trials": sum(1 for e in entries if e["type"] == "trial"),
        "trotting": sum(1 for e in entries if e["type"] == "trotting"),
        "swimming": sum(1 for e in entries if e["type"] == "swimming"),
        "aqua_walker": sum(1 for e in entries if e["type"] == "aqua_walker"),
        "treadmill": sum(1 for e in entries if e["type"] == "treadmill"),
    }
    active_days = len({e["date"] for e in entries})
    blank_days = max(0, window_days - active_days)
    gallop_times = [t for e in entries if e["type"] == "gallop" for t in e.get("times", [])]
    trial_times = [t for e in entries if e["type"] == "trial" for t in e.get("times", [])]
    trend = classify_trend(gallop_times, active_days, blank_days)
    race_jockey_involved = False
    normalized_race_jockey = normalize_person_name(race_jockey)
    if normalized_race_jockey:
        race_jockey_involved = any(
            normalized_race_jockey in normalize_person_name(e.get("rider", ""))
            or normalized_race_jockey in normalize_person_name(e.get("details", ""))
            for e in entries
        )
    gear_training = sorted({e["gear"] for e in entries if e.get("gear")})
    positive_flags: list[str] = []
    risk_flags: list[str] = []
    if active_days >= 14 and trend in ("stable", "improving", "unknown"):
        positive_flags.append("操練穩定持續")
    if counts["gallops"] <= 1 and (counts["trotting"] + counts["swimming"]) >= 8:
        positive_flags.append("輕量保養操練")
    if counts["gallops"] >= 2 and trend == "improving":
        positive_flags.append("操練加壓超近績")
    if race_jockey_involved:
        positive_flags.append("賽日騎師有參與操練")
    if counts["trials"] >= 2 or (counts["gallops"] >= 2 and trend == "improving"):
        positive_flags.append("初出備戰完備")
    if blank_days >= 10:
        risk_flags.append("操練中斷")
    if trend == "easing":
        risk_flags.append("操練放緩")
    if counts["gallops"] == 0 and (counts["swimming"] + counts["aqua_walker"]) >= 6:
        risk_flags.append("純水療無快操")

    maintenance_score = 50
    if active_days >= 14:
        maintenance_score += 15
    if counts["gallops"] or counts["trials"]:
        maintenance_score += 10
    if "操練穩定持續" in positive_flags:
        maintenance_score += 10
    if "操練中斷" in risk_flags:
        maintenance_score -= 25
    if "操練放緩" in risk_flags:
        maintenance_score -= 15
    if "純水療無快操" in risk_flags:
        maintenance_score -= 10
    maintenance_score = max(0, min(100, maintenance_score))

    readiness_score = 45
    if counts["gallops"] >= 2:
        readiness_score += 15
    if counts["trials"] >= 1:
        readiness_score += 15
    if counts["trials"] >= 2:
        readiness_score += 10
    if trend == "improving":
        readiness_score += 10
    if race_jockey_involved:
        readiness_score += 15
    if trial_times:
        readiness_score += 5
    if blank_days >= 10:
        readiness_score -= 15
    if "操練中斷" in risk_flags:
        readiness_score -= 25
    readiness_score = max(0, min(100, readiness_score))

    signal_score = 40
    signal_score += min(counts["gallops"], 3) * 8
    signal_score += min(counts["trials"], 2) * 10
    if trend == "improving":
        signal_score += 12
    if race_jockey_involved:
        signal_score += 12
    if gear_training:
        signal_score += 8
    if risk_flags:
        signal_score -= 15
    signal_score = max(0, min(100, signal_score))

    return {
        "career_category": "status_continuity",
        "data_status": "ok" if entries else "missing",
        "window_days": window_days,
        "workout_load_21d": {
            "active_days": active_days,
            "blank_days": blank_days,
            **counts,
        },
        "workout_intensity_trend": trend,
        "body_weight_delta_lbs": None,
        "maintenance_score": maintenance_score if entries else None,
        "readiness_score": readiness_score if entries else None,
        "pattern_replay_score": signal_score if entries else None,
        "stability_positive_flags": positive_flags,
        "stability_risk_flags": risk_flags,
        "llm_stability_instruction": build_instruction("status_continuity", maintenance_score, signal_score),
    }


def build_instruction(category: str, maintenance_score: int | None,
                      pattern_score: int | None) -> str:
    if category == "pattern_replay":
        return "近績差馬要將晨操視為翻案入口；若 pattern_replay_score 高，stability 不可單憑近績死扣。"
    if category == "debut_pressure":
        return "初出馬 stability 維持 Neutral；晨操強訊號優先 route 去 trainer_signal，試閘分段輔助 sectional。"
    return "正式賽績與晨操 digest 50/50 判讀；晨操反映今次賽前狀態與部署意圖。"


def summarize_trackwork(horse: dict[str, Any], entries: list[dict[str, Any]],
                        digest: dict[str, Any]) -> dict[str, Any]:
    gallop_times = [t for e in entries if e["type"] == "gallop" for t in e.get("times", [])]
    trial_times = [t for e in entries if e["type"] == "trial" for t in e.get("times", [])]
    return {
        "window_days": digest.get("window_days"),
        "gallops_21d": digest["workout_load_21d"]["gallops"],
        "trials_21d": digest["workout_load_21d"]["trials"],
        "trotting_21d": digest["workout_load_21d"]["trotting"],
        "swimming_21d": digest["workout_load_21d"]["swimming"],
        "aqua_walker_21d": digest["workout_load_21d"]["aqua_walker"],
        "treadmill_21d": digest["workout_load_21d"]["treadmill"],
        "gallop_times": gallop_times,
        "trial_times": trial_times,
        "gallop_time_trend": digest.get("workout_intensity_trend"),
        "race_jockey_involved": "賽日騎師有參與操練" in digest.get("stability_positive_flags", []),
        "named_rider_count": len({e.get("rider") for e in entries if e.get("rider")}),
        "rider_role_counts": {
            role: sum(1 for e in entries if e.get("rider_role") == role)
            for role in sorted({e.get("rider_role", "未標明") for e in entries})
        },
        "trainer_self_count": sum(1 for e in entries if e.get("rider_role") == "練馬師"),
        "assistant_count": sum(1 for e in entries if e.get("rider_role") == "助手"),
        "rider_samples": [
            {
                "date": e.get("date"),
                "rider": e.get("rider") or "未標明",
                "role": e.get("rider_role", "未標明"),
                "type": zh_work_type(e.get("type", "other")),
            }
            for e in entries[:5]
        ],
        "gear_training": sorted({e["gear"] for e in entries if e.get("gear")}),
        "trial_sectional_signal": "strong" if trial_times else "unknown",
    }


def extract_one_horse(horse: dict[str, Any], meeting_date: dt.date | None,
                      window_days: int) -> dict[str, Any]:
    detail_html = fetch_url(trackworkresult_url(horse["horseid"]))
    entries = parse_trackwork_rows(detail_html, horse, meeting_date, window_days)
    digest = make_digest(horse, entries, window_days, horse.get("jockey", ""))
    return {
        "horse_no": horse["horse_no"],
        "horseid": horse["horseid"],
        "horse_name": horse.get("horse_name", ""),
        "trainer": horse.get("trainer", ""),
        "jockey": horse.get("jockey", ""),
        "status": "ok" if entries else "missing",
        "mode": digest.get("career_category", "status_continuity"),
        "confidence": "中" if entries else "低",
        "entries": entries,
        "summary": summarize_trackwork(horse, entries, digest),
        "stability_digest": digest,
        "flags": [
            {"code": code, "level": "positive", "reason": code}
            for code in digest.get("stability_positive_flags", [])
        ] + [
            {"code": code, "level": "caution", "reason": code}
            for code in digest.get("stability_risk_flags", [])
        ],
    }


def write_outputs(output_dir: Path, date_prefix: str, race_no: int,
                  payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{date_prefix} Race {race_no} 晨操.json"
    md_path = output_dir / f"{date_prefix} Race {race_no} 晨操.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# 晨操資料 — Race {payload['race_no']}",
        f"提取時間: {payload['extracted_at']}",
        f"數據範圍: 近 {payload['window_days']} 日",
        "",
    ]
    for h in payload.get("horses", {}).values():
        d = h.get("stability_digest", {})
        load = d.get("workout_load_21d", {})
        summary = h.get("summary", {}) if isinstance(h.get("summary"), dict) else {}
        roles = summary.get("rider_role_counts", {})
        named_roles = {k: v for k, v in roles.items() if k != "未標明"}
        role_text = "、".join(f"{k} {v}次" for k, v in named_roles.items()) if named_roles else "未標明"
        lines.extend([
            f"### 馬號 {h.get('horse_no')} — {h.get('horse_name', '')} | 騎師: {h.get('jockey', '') or 'N/A'} | 練馬師: {h.get('trainer', '')}",
            f"- 狀態: {zh_status(h.get('status'))} | 分類: {zh_category(d.get('career_category'))} | 信心: {zh_confidence(h.get('confidence', 'low'))}",
            f"- 近{d.get('window_days', payload['window_days'])}日: 快操 {load.get('gallops', 0)}、試閘 {load.get('trials', 0)}、踱步 {load.get('trotting', 0)}、游水 {load.get('swimming', 0)}、水中步行機 {load.get('aqua_walker', 0)}、空白日 {load.get('blank_days', 0)}",
            f"- 趨勢: {zh_trend(d.get('workout_intensity_trend'))} | 體能維持={d.get('maintenance_score')} | 備戰程度={d.get('readiness_score')} | 復刻信號={d.get('pattern_replay_score')}",
            f"- 操練者身份: {role_text}",
            f"- 正面訊號: {', '.join(d.get('stability_positive_flags', [])) or '無'}",
            f"- 風險訊號: {', '.join(d.get('stability_risk_flags', [])) or '無'}",
            f"- LLM 指令: {d.get('llm_stability_instruction', '')}",
            "",
        ])
        if h.get("entries"):
            lines.append("| 日期 | 類型 | 地點 | 操練者 | 配備 | 摘要 |")
            lines.append("|---|---|---|---|---|---|")
            for e in h.get("entries", []):
                detail = clean_text(e.get("details", ""))[:80]
                lines.append(
                    f"| {e.get('date', '')} | {zh_work_type(e.get('type', 'other'))} | "
                    f"{e.get('location', '')} | {e.get('rider_role', '未標明')} | "
                    f"{e.get('gear') or '無'} | {detail} |"
                )
            lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    info = parse_base_url(args.base_url) if args.base_url else {}
    racedate = args.racedate or info.get("racedate")
    output_dir = Path(args.output_dir).resolve()
    racecourse = normalize_racecourse(args.racecourse or info.get("racecourse"), output_dir)
    races = parse_races(args.races or info.get("race_no"))
    if not racedate or not racecourse:
        raise ValueError("racedate and racecourse are required unless --base_url provides them")
    # Sanitize racedate: strip venue suffixes like _ShaTin, _HappyValley
    racedate_clean = re.sub(r'[_\s]+(ShaTin|HappyValley|ST|HV)$', '', racedate, flags=re.IGNORECASE)
    if racedate_clean != racedate:
        print(f"⚠️ Sanitized racedate: '{racedate}' → '{racedate_clean}'", file=sys.stderr)
        racedate = racedate_clean
    meeting_date = parse_meeting_date(racedate)
    # date_prefix: only keep YYYY-MM-DD portion for consistent file naming
    date_prefix = re.sub(r'[_\s]+.*$', '', racedate.replace("/", "-"))

    for race_no in races:
        url = localtrackwork_url(racedate, racecourse, race_no)
        page_html = fetch_url(url)
        web_horses = parse_horse_list(page_html)
        racecard_horses = parse_racecard_horse_list(output_dir, race_no)
        if racecard_horses and web_horses:
            # Cross-reference: override racecard horseid with authoritative
            # HKJC horseid from localtrackwork page (brand_to_horseid is
            # ambiguous for some letter prefixes like H → 2021 vs 2022)
            web_id_by_no = {h["horse_no"]: h["horseid"] for h in web_horses}
            web_id_by_name = {h.get("horse_name", ""): h["horseid"] for h in web_horses if h.get("horse_name")}
            for h in racecard_horses:
                real_id = web_id_by_no.get(h["horse_no"]) or web_id_by_name.get(h["horse_name"])
                if real_id and real_id != h["horseid"]:
                    print(f"   🔄 Horse #{h['horse_no']} {h['horse_name']}: "
                          f"corrected horseid {h['horseid']} → {real_id}",
                          file=sys.stderr)
                    h["horseid"] = real_id
        horse_list = racecard_horses or web_horses
        horses_payload: dict[str, Any] = {}
        errors: list[str] = []
        for horse in horse_list:
            try:
                h_payload = extract_one_horse(horse, meeting_date, args.window_days)
            except Exception as exc:  # noqa: BLE001 - per-horse fail-soft
                h_payload = {
                    "horse_no": horse["horse_no"],
                    "horseid": horse["horseid"],
                    "horse_name": horse.get("horse_name", ""),
                    "trainer": horse.get("trainer", ""),
                    "jockey": horse.get("jockey", ""),
                    "status": "failed",
                    "mode": "insufficient_data",
                    "confidence": "low",
                    "entries": [],
                    "summary": {},
                    "stability_digest": {
                        "career_category": "insufficient_data",
                        "data_status": "failed",
                        "window_days": args.window_days,
                        "workout_load_21d": {"active_days": 0, "blank_days": args.window_days, "gallops": 0, "trials": 0, "trotting": 0, "swimming": 0, "aqua_walker": 0, "treadmill": 0},
                        "workout_intensity_trend": "unknown",
                        "body_weight_delta_lbs": None,
                        "maintenance_score": None,
                        "readiness_score": None,
                        "pattern_replay_score": None,
                        "stability_positive_flags": [],
                        "stability_risk_flags": [],
                        "llm_stability_instruction": "晨操資料提取失敗，不可憑空推斷。",
                    },
                    "flags": [],
                    "error": str(exc),
                }
                errors.append(f"horse {horse['horse_no']}: {exc}")
            horses_payload[str(h_payload["horse_no"])] = h_payload

        payload = {
            "source": url,
            "race_no": race_no,
            "racedate": racedate,
            "racecourse": racecourse,
            "window_days": args.window_days,
            "extracted_at": dt.datetime.now().isoformat(timespec="seconds"),
            "status": "ok" if horse_list and not errors else ("partial" if horse_list else "missing"),
            "errors": errors,
            "horses": horses_payload,
        }
        write_outputs(output_dir, date_prefix, race_no, payload)
        print(f"✅ Race {race_no} 晨操: {payload['status']} ({len(horses_payload)} horses)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract HKJC trackwork data")
    parser.add_argument("--base_url", help="HKJC racecard/localtrackwork URL")
    parser.add_argument("--racedate", help="YYYY/MM/DD")
    parser.add_argument("--racecourse", help="ST or HV")
    parser.add_argument("--races", help="Race range, e.g. 1-9 or 1,3,5")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--window-days", type=int, default=21)
    parser.add_argument("--fail-soft", action="store_true")
    args = parser.parse_args()
    try:
        raise SystemExit(run(args))
    except Exception as exc:  # noqa: BLE001 - CLI fail-soft
        print(f"⚠️ Trackwork extraction failed: {exc}", file=sys.stderr)
        if args.fail_soft:
            raise SystemExit(0)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
