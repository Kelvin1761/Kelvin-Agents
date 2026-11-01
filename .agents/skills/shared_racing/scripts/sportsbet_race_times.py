#!/usr/bin/env python3
"""Sportsbet AllRacing → each race's advertised start, written beside a meeting.

The dashboard shows jump times, countdowns and greys out races that have run
(AU and HKJC race boards, AU 即將開跑 timeline). Both schedulers write the same
`Race_Start_Times.json` into the meeting folder:

    {"source": "sportsbet-allracing", "venue": ..., "fetched_at": ...,
     "races": {"1": <epoch>, ...}, "abandoned": [3, ...]}

AllRacing lists every meeting of a date, Australian and international (Happy
Valley / Sha Tin included), on `www.sportsbet.com.au`, which has never blocked
us (the host that rate-limits is sportsbetform.com.au). Abandoned races
(statusCode B) are listed rather than dropped, so a cancelled race reads 取消
instead of silently vanishing (2026-10-31: Traralgon R4-R6).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

ALL_RACING_URL = ("https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/"
                  "Racing/AllRacing/{day}")
RACE_START_TIMES_FILE = "Race_Start_Times.json"


def venue_key(name: str) -> str:
    """"Happy Valley" == "HappyValley" == "happy-valley"."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def horse_meetings(payload: dict, *, region: str | None = None):
    """Thoroughbred meetings in an AllRacing payload, optionally one region."""
    for day in (payload or {}).get("dates") or []:
        for section in day.get("sections") or []:
            if str(section.get("raceType") or "").lower() != "horse":
                continue
            for meeting in section.get("meetings") or []:
                if not str(meeting.get("name") or "").strip():
                    continue
                if region is None or meeting.get("regionName") == region:
                    yield meeting


def race_times_by_venue(meetings) -> dict[str, dict]:
    """→ {venue: {"races": {"1": epoch}, "abandoned": [3]}}."""
    out: dict[str, dict] = {}
    for meeting in meetings:
        slot = out.setdefault(str(meeting["name"]).strip(), {"races": {}, "abandoned": []})
        for event in meeting.get("events") or []:
            try:
                number = int(event.get("raceNumber"))
            except (TypeError, ValueError):
                continue
            if str(event.get("statusCode") or "") == "B":
                slot["abandoned"].append(number)
                continue
            try:
                slot["races"][str(number)] = int(event.get("startTime"))
            except (TypeError, ValueError):
                continue
    return out


def find_venue(times: dict[str, dict], venue: str, key=venue_key) -> dict | None:
    wanted = key(venue)
    return next((v for k, v in times.items() if key(k) == wanted), None)


def write_race_start_times(folder: Path | None, venue: str, found: dict | None,
                           *, warn=None) -> bool:
    """Write one meeting's timetable. Never raises: a missing timetable only
    means the dashboard shows no times for that meeting."""
    if folder is None or not found or not (found.get("races") or found.get("abandoned")):
        return False
    body = {"source": "sportsbet-allracing", "venue": venue,
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "races": dict(sorted(found["races"].items(), key=lambda kv: int(kv[0]))),
            "abandoned": sorted(found.get("abandoned") or [])}
    path = Path(folder) / RACE_START_TIMES_FILE
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if (old.get("races"), old.get("abandoned")) == (body["races"], body["abandoned"]):
            return True                     # unchanged: keep the folder mtime still
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except (OSError, ValueError) as exc:
        if warn:
            warn(f"{Path(folder).name}: 開跑時間寫唔到（{type(exc).__name__}: {exc}）")
        return False
    return True


def fetch_allracing(day: str, *, timeout: int = 30) -> dict | None:
    """One AllRacing request (curl_cffi, the same chrome120 fingerprint the AU
    extractor uses). None on any failure."""
    try:
        from curl_cffi import requests
        response = requests.Session(impersonate="chrome120").get(
            ALL_RACING_URL.format(day=day), timeout=timeout)
        payload = response.json() if response.status_code == 200 else None
    except Exception:  # noqa: BLE001 - network, TLS, JSON: all mean "no times"
        return None
    return payload if isinstance(payload, dict) else None
