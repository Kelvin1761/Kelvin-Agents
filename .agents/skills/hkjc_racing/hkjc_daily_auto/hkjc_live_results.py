#!/usr/bin/env python3
"""即場賽果：開跑後 5 分鐘逐場抓馬會賽果，抓到就更新「即場形勢」並部署 dashboard.

launchd runs this every minute (com.antigravity.hkjc-wong-choi.live). Outside a race
window it exits at once. For each race of tonight's meeting:

* the start time comes from that race's 排位表 (`時間: 18:40`, Hong Kong time);
* from start + 5 minutes it fetches that race's official result page;
* no result yet (late start, inquiry) -> retry every minute for the first ten
  minutes, then every two minutes, and give up at start + 90 minutes (the 08:30
  postrace run still extracts the full day);
* minutes after the race HKJC posts only a provisional top four (名次・馬號・馬名・
  騎師, no trainer, draw or running positions); that is captured at once, trainer and
  draw filled from tonight's card, and replaced when the full table appears (first
  seen 2026-11-04: R1's full table was still missing 14 minutes after the start);
* each captured race is written to
  `HKJC_Race_Results_Database/_live/<date>.json`, the same per-race shape as
  `fast_extract_results.py`, then the dashboard is redeployed once per tick.

Deliberately NOT part of hkjc_daily_schedule.py: that scheduler shares one global
lock across every mode and alerts on Telegram when a mode is starved, so a job
that wakes every minute would crowd out prerace/postrace. This job has its own
lock, only waits on the dashboard publication lock to deploy, and never sends
Telegram (Kelvin 2026-11-04). The canonical `full_day_results.json` is never
touched: the reflector still owns it, and `hkjc_insights` prefers it per race.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[3]
for path in (PROJECT_ROOT, PROJECT_ROOT / ".agents/skills", PROJECT_ROOT / ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from wongchoi_paths import HK_RACING  # noqa: E402

HK = ZoneInfo("Asia/Hong_Kong")
FIRST_TRY = timedelta(minutes=5)
FAST_RETRY_UNTIL = timedelta(minutes=15)
FAST_RETRY, SLOW_RETRY = timedelta(minutes=1), timedelta(minutes=2)
GIVE_UP = timedelta(minutes=90)
VENUE_ZH = {"ShaTin": "沙田", "HappyValley": "跑馬地"}
DEPLOY = PROJECT_ROOT / "deploy.sh"
LOG = HERE / "logs" / "live-results.log"


def live_dir() -> Path:
    return Path(HK_RACING) / "HKJC_Race_Results_Database" / "_live"


def log(message: str) -> None:
    line = f"[{datetime.now(HK):%Y-%m-%d %H:%M:%S} HKT] {message}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def meeting_dirs(now: datetime) -> list[Path]:
    """Tonight's meeting, plus yesterday's until its last race has had time to finish."""
    days = {now.date().isoformat(), (now.date() - timedelta(days=1)).isoformat()}
    root = Path(HK_RACING)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir()
                  if p.is_dir() and p.name[:10] in days and any(v in p.name for v in VENUE_ZH))


def race_starts(meeting_dir: Path) -> dict[int, datetime]:
    """Race number -> start time (HK) from each race's 排位表."""
    day = date.fromisoformat(meeting_dir.name[:10])
    starts = {}
    for card in meeting_dir.glob("* Race * 排位表.md"):
        number = re.search(r"Race (\d+) 排位表", card.name)
        clock = re.search(r"^時間:\s*(\d{1,2}):(\d{2})", card.read_text(encoding="utf-8", errors="ignore"), re.M)
        if number and clock:
            starts[int(number.group(1))] = datetime(day.year, day.month, day.day,
                                                    int(clock.group(1)), int(clock.group(2)), tzinfo=HK)
    return dict(sorted(starts.items()))


def is_official(race: dict | None) -> bool:
    """A real result: at least three placed runners and running positions recorded."""
    rows = (race or {}).get("results") or []
    placed = [r for r in rows if re.match(r"^\d+", str(r.get("pos") or ""))]
    return len(placed) >= 3 and any(str(r.get("running_positions") or "").strip() for r in rows)


def _card(meeting_dir: Path, race: int) -> dict:
    """Horse number -> {horse_name, jockey, trainer, barrier} from that race's Logic.json."""
    horses = _read(meeting_dir / f"Race_{race}_Logic.json").get("horses")
    return horses if isinstance(horses, dict) else {}


def parse_provisional(html: str, card: dict) -> list[dict] | None:
    """The 名次・馬號・馬名・騎師 table HKJC shows before the full result, or None."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        if not rows or rows[0][:4] != ["名次", "馬號", "馬名", "騎師"]:
            continue
        placed = [r for r in rows[1:] if len(r) >= 4 and re.match(r"^\d+", r[0])]
        if len(placed) < 3:
            return None
        results, seen = [], set()
        for pos, number, name, jockey, *_ in placed:
            horse = card.get(number) or {}
            seen.add(number)
            results.append({"pos": pos, "horse_no": number, "horse_name": name, "jockey": jockey,
                            "trainer": str(horse.get("trainer") or ""), "draw": str(horse.get("barrier") or ""),
                            "running_positions": ""})
        # Everyone else on the card ran unplaced as far as tonight's counts go.
        for number, horse in card.items():
            if number not in seen and isinstance(horse, dict):
                results.append({"pos": "", "horse_no": number, "horse_name": str(horse.get("horse_name") or ""),
                                "jockey": str(horse.get("jockey") or ""), "trainer": str(horse.get("trainer") or ""),
                                "draw": str(horse.get("barrier") or ""), "running_positions": ""})
        return results
    return None


def fetch_provisional(day: str, race: int, venue_zh: str, meeting_dir: Path) -> dict | None:
    """Same per-race shape as fast_extract_results, flagged provisional; race header rows keep the conditions."""
    from bs4 import BeautifulSoup
    from curl_cffi import requests as cffi_requests
    url = ("https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx"
           f"?RaceDate={day.replace('-', '/')}&RaceNo={race}")
    try:
        resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
    except Exception as exc:  # noqa: BLE001 - network faults are a retry, not a crash
        log(f"{day} R{race} 臨時賽果抓唔到：{exc}")
        return None
    if resp.status_code != 200:
        return None
    results = parse_provisional(resp.text, _card(meeting_dir, race))
    if not results:
        return None
    header = next((t for t in BeautifulSoup(resp.text, "html.parser").find_all("table")
                   if f"第 {race} 場" in t.get_text(" ", strip=True)[:20]), None)
    conditions = [[c.get_text(" ", strip=True) for c in tr.find_all("td")] for tr in header.find_all("tr")] if header else []
    return {"racedate": day, "race_no": race, "venue": venue_zh, "results": results,
            "sectional_times": conditions, "provisional": True}


def due(race: int, start: datetime, progress: dict, now: datetime) -> bool:
    record = progress.get(str(race)) or {}
    if record.get("captured_at") or record.get("gave_up") or now < start + FIRST_TRY:
        return False
    if now > start + GIVE_UP:
        return False
    last = record.get("last_attempt")
    if not last:
        return True
    wait = FAST_RETRY if now < start + FAST_RETRY_UNTIL else SLOW_RETRY
    # A minute of launchd jitter must not turn "every minute" into "every two".
    return now - datetime.fromisoformat(last) >= wait - timedelta(seconds=15)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def tick(now: datetime, *, fetch=None, deploy=None, provisional=None) -> dict:
    """One pass over every live meeting; returns what happened (for logs and tests)."""
    if fetch is None:
        from fast_extract_results import extract_race_data as fetch
    provisional = provisional or fetch_provisional
    summary = {"captured": [], "pending": [], "gave_up": [], "deployed": False}
    for meeting_dir in meeting_dirs(now):
        day, venue = meeting_dir.name[:10], next(v for v in VENUE_ZH if v in meeting_dir.name)
        starts = race_starts(meeting_dir)
        if not starts:
            continue
        results_path, state_path = live_dir() / f"{day}.json", live_dir() / f"{day}.state.json"
        results, progress = _read(results_path), _read(state_path)
        changed = False
        for race, start in starts.items():
            record = progress.setdefault(str(race), {})
            if str(race) in results and not results[str(race)].get("provisional") and not record.get("captured_at"):
                record["captured_at"] = now.isoformat()
            if now > start + GIVE_UP and not record.get("captured_at") and not record.get("gave_up"):
                record["gave_up"] = now.isoformat()
                summary["gave_up"].append(f"{day} R{race}")
                log(f"{day} R{race} 開跑後 90 分鐘仍未有賽果，交返 postrace 補抓")
                changed = True
            if not due(race, start, progress, now):
                continue
            record["attempts"] = record.get("attempts", 0) + 1
            record["last_attempt"] = now.isoformat()
            race_data = fetch(day, race, VENUE_ZH[venue])
            changed = True
            if is_official(race_data):
                results[str(race)] = race_data
                record["captured_at"] = now.isoformat()
                summary["captured"].append(f"{day} R{race}")
                log(f"{day} R{race} 賽果已抓（第 {record['attempts']} 次，開跑後 {int((now - start).total_seconds() // 60)} 分鐘）")
            elif str(race) in results:
                summary["pending"].append(f"{day} R{race}")
                log(f"{day} R{race} 已有臨時頭四名，等正式賽果，第 {record['attempts']} 次")
            elif (early := provisional(day, race, VENUE_ZH[venue], meeting_dir)):
                results[str(race)] = early
                record["provisional_at"] = now.isoformat()
                summary["captured"].append(f"{day} R{race}")
                summary["pending"].append(f"{day} R{race}")
                log(f"{day} R{race} 臨時頭四名已抓（第 {record['attempts']} 次），練馬師／檔位由排位表補；繼續等正式賽果")
            else:
                summary["pending"].append(f"{day} R{race}")
                log(f"{day} R{race} 未有賽果，第 {record['attempts']} 次")
        if changed:
            _write(results_path, results)
            _write(state_path, progress)
    if summary["captured"]:
        summary["deployed"] = (deploy or deploy_dashboard)() == 0
    return summary


def deploy_dashboard() -> int:
    """Redeploy so 即場形勢 is rebuilt from the results now on disk; waits on the shared publication lock."""
    from shared_wong_choi.dashboard_publish_lock import publication_lock
    try:
        with publication_lock():
            run = subprocess.run([str(DEPLOY)], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=1800)
    except (TimeoutError, subprocess.TimeoutExpired, OSError) as exc:
        log(f"dashboard deploy 失敗：{exc}")
        return 1
    log(f"dashboard deploy exit={run.returncode}" + ("" if run.returncode == 0 else f"：{(run.stdout + run.stderr)[-600:]}"))
    return run.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--now", help="ISO time to act as (testing), e.g. 2026-11-04T18:46:00+08:00")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now).astimezone(HK) if args.now else datetime.now(HK)
    live_dir().mkdir(parents=True, exist_ok=True)
    with (live_dir() / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # the previous tick is still fetching or deploying
        summary = tick(now)
    if any(summary[k] for k in ("captured", "gave_up")):
        log(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
