#!/usr/bin/env python3
"""sportsbetform 手機版逐駒 200m 分段：parser + 每日抓取（EXP-20261116-19／-20）。

`/mobile/{eventId}/1/` 嘅 Speed 分頁（`mobile-sectional-times`）係**成場** server-render，每場一版就有全場馬
最近 10 仗：名次／馬數、場地、狀況、日期、路程、本駒完成時間，同 6 格 200m 分段（秒 + km/h）。
格名 = 嗰段起點離終點距離：`Fnsh` = 最後 200m、`200m` = 400→200、`400m` = 600→400、`600m` = 800→600、
`800m` = 1000→800、`1000m` = 1200→1000。起步段從來冇記錄。Sportsbet 自己嘅 EARLY／MID／LATE／AVG 摘要
係「抓取嗰刻」嘅 10 仗平均，point-in-time 唔安全，唔好用。

舊賽事頁固定喺賽事日期（EXP-19：370 版 0 行 ≥ 賽日），所以賽後先抓係安全；讀嘅人仍然要只用日期 < 今仗嘅行。

抓取規矩（Kelvin 定，唔好放寬）：每版隔 ≥25 秒、非 200／逾時／內容唔似 Speed 分頁即停、唔重試、
唔用任何繞過偵測手法；03:00 前或者 09:00 後唔開工（避開 22:00 evening job 同 10:00–16:00 refresh）。

    python3 au_mobile_sectionals.py fetch [--days-back 8] [--max-pages 180] [--status STATUS.json]
    python3 au_mobile_sectionals.py parse PAGE.html
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

COLS = ("1000m", "800m", "600m", "400m", "200m", "Fnsh")
API = "https://www.sportsbet.com.au/apigw/sportsbook-racing/Sportsbook/Racing/AllRacing/{day}"
PAGE = "https://www.sportsbetform.com.au/mobile/{event_id}/1/"
FORWARD_START = "2026-11-17"      # EXP-20261116-20：之前嘅場次用咗嚟定權重，唔入 forward
DELAY_SECONDS = 25.0
MIN_BYTES = 20000
WINDOW = (3, 9)                   # 只喺 [03:00, 09:00) 開工
MARKER = 'data-component="mobile-sectional-times"'


# ---------------------------------------------------------------- parse
def _f(x: str):
    x = (x or "").strip()
    if not x or x == "-":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def parse(page: str) -> list[dict]:
    """→ [{number, name, barrier, runs:[{pos, starters, track, condition, date, distance, time, split{}, kmh{}}]}]。"""
    t = re.sub(r"\s+", " ", page)
    i = t.find(MARKER)
    if i < 0:
        return []
    j = t.find('<script id="template-mobile-sectional-times"', i)
    t = t[i:j if j > 0 else len(t)]
    runners = []
    for block in re.split(r'<a class="sectionals__runner"', t)[1:]:
        num = re.search(r'runner-number">([^<]*)<', block)
        info = re.search(r'runner-info">([^<]*)<', block)
        if not info or "{{" in info.group(1):
            continue
        m = re.match(r"\s*(.*?)\s*\((\d+)\)\s*$", html.unescape(info.group(1)))
        name, barrier = (m.group(1), int(m.group(2))) if m else (html.unescape(info.group(1)).strip(), None)
        runs = []
        for row in re.split(r'class="sectionals__event-row"', block)[1:]:
            fin = re.search(r'finishing-num">([^<]*)<.*?finishing-starters">\s*of\s*([^<]*)<', row)
            hdr = re.search(r'event-name">([^<]*)<.*?track-conditions"[^>]*>([^<]*)<.*?'
                            r'event-info-row">\s*(\d\d)/(\d\d)/(\d{4}),\s*(\d+)m,\s*([\d.]+)s', row)
            if not hdr:
                continue
            cols = re.findall(r'speed-label">([^<]+)</div> <div class="sectionals__speed-data">'
                              r'([^<]*)</div> <div class="sectionals__speed-data">([^<]*)<', row)
            seg = {c: (_f(a), _f(b)) for c, a, b in cols if c in COLS}
            runs.append({
                "pos": fin.group(1).strip() if fin else None,
                "starters": _f(fin.group(2)) if fin else None,
                "track": html.unescape(hdr.group(1)).strip(),
                "condition": hdr.group(2).strip(),
                "date": date(int(hdr.group(5)), int(hdr.group(4)), int(hdr.group(3))).isoformat(),
                "distance": int(hdr.group(6)),
                "time": float(hdr.group(7)),
                "split": {c: seg.get(c, (None, None))[0] for c in COLS},
                "kmh": {c: seg.get(c, (None, None))[1] for c in COLS},
            })
        runners.append({"number": int(num.group(1)) if num and num.group(1).strip().isdigit() else None,
                        "name": name, "barrier": barrier, "runs": runs})
    return runners


def own_l600(run: dict) -> float | None:
    """本駒最後 600m 秒數，由 km/h 反推（避開 0.1 秒捨入）；三格唔齊 = None。"""
    k = run.get("kmh") or {}
    if not all(k.get(c) for c in ("400m", "200m", "Fnsh")):
        return None
    return sum(200 * 3.6 / k[c] for c in ("400m", "200m", "Fnsh"))


# ---------------------------------------------------------------- storage
def data_root() -> Path:
    env = os.environ.get("WONGCHOI_AU_DATA_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        marker = parent / ".wongchoi_au_data_root"
        if marker.exists():
            return Path(marker.read_text(encoding="utf-8").strip())
    raise SystemExit("搵唔到 AU 資料根（WONGCHOI_AU_DATA_ROOT／.wongchoi_au_data_root）")


def store_dir(root: Path | None = None) -> Path:
    return (root or data_root()) / "AU_Mobile_Sectionals"


def load_day(day: str, root: Path | None = None) -> list[dict]:
    """→ 嗰日已抓嘅每場 {event_id, day, venue, race, runners}。"""
    out = []
    folder = store_dir(root) / day
    for path in sorted(folder.glob("*.json.gz")) if folder.exists() else []:
        try:
            out.append(json.loads(gzip.decompress(path.read_bytes()).decode("utf-8")))
        except (OSError, ValueError):
            continue
    return out


# ---------------------------------------------------------------- fetch
def au_events(payload: dict) -> list[dict]:
    """AllRacing → AU 純種馬每場 {event_id, venue, race}。"""
    out = []
    for block in payload.get("dates") or []:
        for section in block.get("sections") or []:
            if section.get("raceType") != "horse":
                continue
            for meeting in section.get("meetings") or []:
                if meeting.get("regionName") != "Australia":
                    continue
                for ev in meeting.get("events") or []:
                    if ev.get("id") and ev.get("raceNumber"):
                        out.append({"event_id": int(ev["id"]), "venue": meeting.get("name") or "",
                                    "race": int(ev["raceNumber"])})
    return out


def in_window(now: datetime) -> bool:
    return WINDOW[0] <= now.hour < WINDOW[1]


def fetch(*, days_back: int, max_pages: int, today: date, session, sleep=time.sleep, now=datetime.now,
          root: Path | None = None, force_window: bool = False, log=print) -> dict:
    """抓前一日至前 days_back 日（≥ FORWARD_START）未有嘅場次。任何非 200／逾時／內容唔啱即停。"""
    status = {"started_at": now().isoformat(timespec="seconds"), "fetched": 0, "skipped_existing": 0,
              "days": {}, "state": "ok", "stop_reason": ""}
    if not force_window and not in_window(now()):
        status.update(state="outside_window", stop_reason=f"只喺 {WINDOW[0]:02d}:00–{WINDOW[1]:02d}:00 開工")
        return status
    base = store_dir(root)
    requests_made = 0

    def polite():
        nonlocal requests_made
        if requests_made:
            sleep(DELAY_SECONDS)
        requests_made += 1

    for back in range(1, days_back + 1):
        day = (today - timedelta(days=back)).isoformat()
        if day < FORWARD_START:
            continue
        polite()
        try:
            resp = session.get(API.format(day=day), timeout=30)
        except Exception as exc:  # noqa: BLE001 — 任何網絡錯誤都即停
            status.update(state="stopped", stop_reason=f"AllRacing {day}: {type(exc).__name__}")
            return status
        if resp.status_code != 200:
            status.update(state="stopped", stop_reason=f"AllRacing {day}: HTTP {resp.status_code}")
            return status
        try:
            events = au_events(resp.json())
        except ValueError:
            status.update(state="stopped", stop_reason=f"AllRacing {day}: 唔係 JSON")
            return status
        folder = base / day
        folder.mkdir(parents=True, exist_ok=True)
        got = 0
        for ev in events:
            target = folder / f"{ev['event_id']}.json.gz"
            if target.exists():
                status["skipped_existing"] += 1
                continue
            if status["fetched"] >= max_pages:
                status.update(state="page_cap", stop_reason=f"每次最多 {max_pages} 版")
                status["days"][day] = got
                return status
            polite()
            try:
                page = session.get(PAGE.format(event_id=ev["event_id"]), timeout=30)
            except Exception as exc:  # noqa: BLE001
                status.update(state="stopped", stop_reason=f"{ev['event_id']}: {type(exc).__name__}")
                status["days"][day] = got
                return status
            body = page.content or b""
            text = body.decode("utf-8", errors="replace")
            if page.status_code != 200 or len(body) < MIN_BYTES or MARKER not in text:
                status.update(state="stopped",
                              stop_reason=f"{ev['event_id']}: HTTP {page.status_code}, {len(body)} bytes")
                status["days"][day] = got
                return status
            record = {**ev, "day": day, "fetched_at": now().isoformat(timespec="seconds"), "runners": parse(text)}
            (folder / f"{ev['event_id']}.html.gz").write_bytes(gzip.compress(body))
            target.write_bytes(gzip.compress(json.dumps(record, ensure_ascii=False).encode("utf-8")))
            status["fetched"] += 1
            got += 1
            log(f"{day} {ev['venue']} R{ev['race']} {len(record['runners'])} runners")
        status["days"][day] = got
    return status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--days-back", type=int, default=8)
    f.add_argument("--max-pages", type=int, default=180)
    f.add_argument("--status", default="")
    f.add_argument("--force-window", action="store_true", help="只供人手測試；排程唔好用")
    p = sub.add_parser("parse")
    p.add_argument("page")
    args = ap.parse_args(argv)
    if args.cmd == "parse":
        print(json.dumps(parse(Path(args.page).read_text(encoding="utf-8", errors="replace")), ensure_ascii=False)[:4000])
        return 0
    from curl_cffi import requests  # 同 claw_sportsbet_form 一樣嘅 client

    status = fetch(days_back=args.days_back, max_pages=args.max_pages, today=date.today(),
                   session=requests.Session(impersonate="chrome120"), force_window=args.force_window)
    status["finished_at"] = datetime.now().isoformat(timespec="seconds")
    if args.status:
        Path(args.status).parent.mkdir(parents=True, exist_ok=True)
        Path(args.status).write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["state"] in ("ok", "page_cap", "outside_window") else 1


if __name__ == "__main__":
    sys.exit(main())
